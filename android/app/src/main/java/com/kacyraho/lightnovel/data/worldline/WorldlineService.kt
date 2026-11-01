package com.kacyraho.lightnovel.data.worldline

import com.kacyraho.lightnovel.core.settings.ApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.knowledge.Fact
import com.kacyraho.lightnovel.data.knowledge.KnowledgeStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.story.StoryMemoryStore
import com.kacyraho.lightnovel.data.translation.ChatMessage
import com.kacyraho.lightnovel.data.translation.DeepSeekClient
import com.kacyraho.lightnovel.data.translation.TranslationClient
import com.kacyraho.lightnovel.data.translation.TranslationException
import com.kacyraho.lightnovel.data.translation.TranslationValidators
import com.kacyraho.lightnovel.data.translation.translationKeyScope
import com.kacyraho.lightnovel.data.translation.translationRequiresKey
import java.time.Instant
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

class WorldlineService(
    private val contentStore: ContentStore,
    private val knowledgeStore: KnowledgeStore,
    private val storyMemoryStore: StoryMemoryStore?,
    private val worldlineStore: WorldlineStore,
    private val branchKnowledgeExtractor: BranchKnowledgeExtractor? = null,
    private val settingsStore: SettingsStore,
    private val apiKeyStore: ApiKeyStore,
    private val clientFactory: (String, String) -> TranslationClient = { base, key ->
        DeepSeekClient(base, key)
    },
) {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        explicitNulls = false
    }
    private val contexts = WorldlineContextBuilder(knowledgeStore, storyMemoryStore)

    suspend fun createBranch(
        book: BookEntity,
        title: String,
        forkChapter: Int,
        forkParagraph: Int,
        intervention: Intervention,
        mode: String = "exploration",
    ): Result<WorldlineFile> {
        if (intervention.character.isBlank() || intervention.action.isBlank()) {
            return Result.failure(IllegalArgumentException("角色和行动不能为空"))
        }
        val now = Instant.now().toString()
        val worldline = WorldlineFile(
            id = worldlineStore.newId(book.id, forkChapter, forkParagraph),
            bookId = book.id,
            title = title.ifBlank { "从第 $forkChapter 章开始的分支" },
            forkChapter = forkChapter,
            forkParagraph = forkParagraph,
            intervention = intervention,
            mode = if (mode == "comparison") "comparison" else "exploration",
            createdAt = now,
            updatedAt = now,
        )
        val generated = generateChapter(book, worldline, 1, "", "")
            .getOrElse { return Result.failure(it) }
        val updated = worldline.copy(
            chapters = listOf(generated.chapter),
            state = generated.state,
            divergences = listOf(generated.divergence),
            diffReports = listOfNotNull(generated.diffReport),
            branchExtractedThrough = generated.knowledge?.branchExtractedThrough ?: 0,
            knowledgeStatus = generated.knowledgeStatus,
            updatedAt = now,
        )
        return Result.success(worldlineStore.save(book.storageDir, updated))
    }

    suspend fun continueBranch(book: BookEntity, id: String): Result<WorldlineFile> {
        val current = worldlineStore.load(book.storageDir, id)
            ?: return Result.failure(IllegalStateException("分支不存在"))
        val previous = current.chapters.lastOrNull()
        val generated = generateChapter(
            book = book,
            worldline = current,
            chapterIndex = current.chapters.size + 1,
            previousSummary = previous?.summary.orEmpty(),
            previousTail = previous?.text?.takeLast(600).orEmpty(),
        ).getOrElse { return Result.failure(it) }
        val now = Instant.now().toString()
        val updated = current.copy(
            chapters = current.chapters + generated.chapter,
            state = generated.state,
            divergences = current.divergences + generated.divergence,
            diffReports = current.diffReports + listOfNotNull(generated.diffReport),
            branchExtractedThrough = generated.knowledge?.branchExtractedThrough
                ?: current.branchExtractedThrough,
            knowledgeStatus = generated.knowledgeStatus,
            updatedAt = now,
        )
        return Result.success(worldlineStore.save(book.storageDir, updated))
    }

    private suspend fun generateChapter(
        book: BookEntity,
        worldline: WorldlineFile,
        chapterIndex: Int,
        previousSummary: String,
        previousTail: String,
    ): Result<GeneratedChapter> {
        val model = client() ?: return Result.failure(IllegalStateException("未配置翻译 API Key"))
        val branchKnowledge = worldlineStore.loadKnowledge(book.storageDir, worldline.id)
        val comparison = worldline.mode == "comparison"
        val forbidden = contexts.forbiddenTerms(book, worldline.forkChapter)
        val futureTerms = contexts.futureOnlyTerms(book, worldline.forkChapter)

        val plan = planner(
            model = model,
            context = contexts.plannerContext(
                book = book,
                forkChapter = worldline.forkChapter,
                comparison = comparison,
                branch = worldline,
                branchKnowledge = branchKnowledge,
            ),
            chapterIndex = chapterIndex,
        ).getOrElse { return Result.failure(it) }
        validatePlan(plan, futureTerms, forbidden)?.let {
            return Result.failure(IllegalStateException("plan 校验失败：$it"))
        }
        val planText = buildString {
            appendLine(plan.intendedDivergence)
            plan.beats.forEachIndexed { index, beat -> appendLine("${index + 1}. $beat") }
            if (plan.stateChanges.isNotEmpty()) {
                appendLine("状态变化：${plan.stateChanges.joinToString("；")}")
            }
        }

        var draft = writer(
            model = model,
            context = contexts.writerContext(
                book = book,
                forkChapter = worldline.forkChapter,
                forkParagraph = worldline.forkParagraph,
                branch = worldline,
                branchKnowledge = branchKnowledge,
                plan = planText,
                previousSummary = previousSummary,
                previousTail = previousTail,
            ),
            chapterIndex = chapterIndex,
            repairNotes = emptyList(),
        ).getOrElse { return Result.failure(it) }

        var violations = validateProse(
            model = model,
            book = book,
            worldline = worldline,
            branchKnowledge = branchKnowledge,
            draft = draft,
            comparison = comparison,
            forbidden = forbidden,
        )
        if (violations.isNotEmpty()) {
            draft = writer(
                model = model,
                context = contexts.writerContext(
                    book = book,
                    forkChapter = worldline.forkChapter,
                    forkParagraph = worldline.forkParagraph,
                    branch = worldline,
                    branchKnowledge = branchKnowledge,
                    plan = planText,
                    previousSummary = previousSummary,
                    previousTail = previousTail,
                ),
                chapterIndex = chapterIndex,
                repairNotes = violations.map { it.reason },
            ).getOrElse { return Result.failure(it) }
            violations = validateProse(
                model = model,
                book = book,
                worldline = worldline,
                branchKnowledge = branchKnowledge,
                draft = draft,
                comparison = comparison,
                forbidden = forbidden,
            )
            if (violations.isNotEmpty()) {
                return Result.failure(
                    IllegalStateException(
                        "正文校验失败：" + violations.joinToString("；") { it.reason },
                    ),
                )
            }
        }

        val chapter = BranchChapter(
            index = chapterIndex,
            title = draft.title,
            text = draft.text,
            summary = draft.summary,
            createdAt = Instant.now().toString(),
        )
        val temp = worldline.copy(chapters = worldline.chapters + chapter)
        val knowledgeResult = branchKnowledgeExtractor?.extract(book, temp, chapterIndex)
        val knowledge = knowledgeResult?.getOrNull()
        val knowledgeStatus = when {
            knowledgeResult == null -> "pending"
            knowledgeResult.isSuccess -> "ready"
            else -> "pending"
        }
        val diff = if (comparison) {
            diffReport(
                model = model,
                book = book,
                worldline = worldline,
                chapter = chapter,
                canonReference = contexts.canonReference(book, worldline.forkChapter, true),
            )
        } else {
            null
        }
        return Result.success(
            GeneratedChapter(
                chapter = chapter,
                state = draft.state,
                divergence = draft.divergence,
                knowledge = knowledge,
                knowledgeStatus = knowledgeStatus,
                diffReport = diff,
            ),
        )
    }

    private suspend fun planner(
        model: ModelClient,
        context: String,
        chapterIndex: Int,
    ): Result<PlanOutput> {
        val reply = try {
            model.client.complete(
                messages = listOf(
                    ChatMessage("system", PLANNER_PROMPT),
                    ChatMessage(
                        "user",
                        "$context\n【任务】写第 $chapterIndex 章的分支 plan，只输出 JSON。",
                    ),
                ),
                model = model.model,
                maxTokens = 2_048,
                temperature = 0.7,
            )
        } catch (error: TranslationException) {
            return Result.failure(error)
        }
        return runCatching {
            json.decodeFromString(PlanOutput.serializer(), cleanJson(reply.content))
        }.fold(
            onSuccess = { Result.success(it) },
            onFailure = { Result.failure(IllegalStateException("plan 解析失败：${it.message}")) },
        )
    }

    private suspend fun writer(
        model: ModelClient,
        context: String,
        chapterIndex: Int,
        repairNotes: List<String>,
    ): Result<ChapterOutput> {
        val repair = if (repairNotes.isEmpty()) "" else
            "\n【上一次校验问题，必须修复】\n" + repairNotes.joinToString("\n")
        val reply = try {
            model.client.complete(
                messages = listOf(
                    ChatMessage("system", WRITER_PROMPT),
                    ChatMessage(
                        "user",
                        "$context$repair\n【任务】写分支第 $chapterIndex 章，只输出 JSON。",
                    ),
                ),
                model = model.model,
                maxTokens = 8_192,
                temperature = 0.8,
            )
        } catch (error: TranslationException) {
            return Result.failure(error)
        }
        return runCatching {
            json.decodeFromString(ChapterOutput.serializer(), cleanJson(reply.content))
        }.fold(
            onSuccess = { Result.success(it) },
            onFailure = { Result.failure(IllegalStateException("正文解析失败：${it.message}")) },
        )
    }

    private suspend fun validateProse(
        model: ModelClient,
        book: BookEntity,
        worldline: WorldlineFile,
        branchKnowledge: BranchKnowledgeFile?,
        draft: ChapterOutput,
        comparison: Boolean,
        forbidden: List<String>,
    ): List<Violation> {
        val deterministic = mutableListOf<Violation>()
        if (draft.title.isBlank()) deterministic += Violation("length", "", "标题为空")
        if (draft.summary.isBlank()) deterministic += Violation("length", "", "梗概为空")
        if (draft.text.length < 500 || draft.text.length > 12_000) {
            deterministic += Violation("length", "", "正文长度异常")
        }
        if (!TranslationValidators.detectChinese(draft.text)) {
            deterministic += Violation("length", "", "正文不是中文")
        }
        forbidden.firstOrNull { it.isNotBlank() && it in draft.text }?.let {
            deterministic += Violation("term", it, "正文提前出现禁用词：$it")
        }
        if (deterministic.isNotEmpty()) return deterministic

        val characterView = contexts.characterView(
            book = book,
            forkChapter = worldline.forkChapter,
            forkParagraph = worldline.forkParagraph,
            branchKnowledge = branchKnowledge,
        )
        val canonReference = contexts.canonReference(book, worldline.forkChapter, comparison)
        val prompt = buildString {
            appendLine("【角色已知信息（只能使用这些）】")
            appendLine(characterView)
            appendLine("【canon 参照（仅用于判断矛盾，不得当作角色已知）】")
            appendLine(canonReference.take(4_000))
            appendLine("【禁止提前出现】${forbidden.joinToString("、")}")
            appendLine("【待校验正文】")
            appendLine(draft.text)
            appendLine("只输出 JSON：{\"violations\":[{\"type\":\"knowledge|canon|voice|term|length\",\"quote\":\"\",\"reason\":\"\"}],\"canProceed\":true}")
        }
        val reply = try {
            model.client.complete(
                messages = listOf(
                    ChatMessage("system", VALIDATOR_PROMPT),
                    ChatMessage("user", prompt),
                ),
                model = model.model,
                maxTokens = 2_048,
                temperature = 0.1,
            )
        } catch (error: TranslationException) {
            return listOf(Violation("canon", "", "校验器调用失败：${error.message}"))
        }
        val output = runCatching {
            json.decodeFromString(ValidationOutput.serializer(), cleanJson(reply.content))
        }.getOrElse {
            return listOf(Violation("canon", "", "校验器返回无法解析"))
        }
        return output.violations
    }

    private suspend fun diffReport(
        model: ModelClient,
        book: BookEntity,
        worldline: WorldlineFile,
        chapter: BranchChapter,
        canonReference: String,
    ): DiffReport? {
        val prompt = buildString {
            appendLine("【canon 参照】")
            appendLine(canonReference.take(5_000))
            appendLine("【分支介入】${worldline.intervention.character}：${worldline.intervention.action}")
            appendLine("【分支章节】")
            appendLine(chapter.text.take(8_000))
            appendLine("只输出 JSON：{\"items\":[{\"type\":\"event|relationship|secret|timeline\",\"branchEvent\":\"\",\"canonReference\":\"\",\"impact\":\"\",\"causedByIntervention\":true}]}")
        }
        val reply = runCatching {
            model.client.complete(
                messages = listOf(
                    ChatMessage("system", DIFF_PROMPT),
                    ChatMessage("user", prompt),
                ),
                model = model.model,
                maxTokens = 2_048,
                temperature = 0.2,
            )
        }.getOrNull() ?: return null
        val output = runCatching {
            json.decodeFromString(DiffOutput.serializer(), cleanJson(reply.content))
        }.getOrNull() ?: return null
        return DiffReport(
            id = "diff-" + Integer.toHexString(
                (worldline.id + chapter.index).hashCode(),
            ),
            chapter = chapter.index,
            items = output.items,
            createdAt = Instant.now().toString(),
        )
    }

    private suspend fun client(): ModelClient? {
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) return null
        return ModelClient(
            client = clientFactory(settings.deepSeekBaseUrl, key),
            model = settings.deepSeekModel,
        )
    }

    private fun validatePlan(
        plan: PlanOutput,
        futureTerms: List<String>,
        forbidden: List<String>,
    ): String? {
        if (plan.beats.isEmpty()) return "beats 为空"
        val text = (plan.beats + plan.intendedDivergence + plan.stateChanges)
            .joinToString("\n")
        futureTerms.firstOrNull { it.isNotBlank() && it in text }?.let {
            return "提前使用未来实体：$it"
        }
        forbidden.firstOrNull { it.isNotBlank() && it in text }?.let {
            return "提前出现禁用词：$it"
        }
        return null
    }

    private fun cleanJson(raw: String): String {
        var text = raw.replace("\r\n", "\n").trim()
        if (text.startsWith("```")) {
            text = text.removePrefix("```json").removePrefix("```")
                .removeSuffix("```").trim()
        }
        val start = text.indexOf('{')
        val end = text.lastIndexOf('}')
        if (start >= 0 && end > start) text = text.substring(start, end + 1)
        return text
    }

    private data class ModelClient(
        val client: TranslationClient,
        val model: String,
    )

    private data class GeneratedChapter(
        val chapter: BranchChapter,
        val state: BranchState,
        val divergence: Divergence,
        val knowledge: BranchKnowledgeFile?,
        val knowledgeStatus: String,
        val diffReport: DiffReport?,
    )

    @Serializable
    private data class PlanOutput(
        val beats: List<String> = emptyList(),
        val characters: List<String> = emptyList(),
        val intendedDivergence: String = "",
        val futureRisks: List<String> = emptyList(),
        val stateChanges: List<String> = emptyList(),
    )

    @Serializable
    private data class ChapterOutput(
        val title: String = "",
        val text: String = "",
        val summary: String = "",
        val state: BranchState = BranchState(),
        val divergence: Divergence = Divergence(),
    )

    @Serializable
    private data class ValidationOutput(
        val violations: List<Violation> = emptyList(),
        val canProceed: Boolean = true,
    )

    @Serializable
    private data class Violation(
        val type: String = "canon",
        val quote: String = "",
        val reason: String = "",
    )

    @Serializable
    private data class DiffOutput(
        val items: List<DiffItem> = emptyList(),
    )

    private companion object {
        const val PLANNER_PROMPT =
            "你是轻小说分支剧情规划师。只使用给定的分叉前知识、分支状态和用户介入。" +
                "不得使用分叉点之后的 canon 事件，不得提前揭示秘密。" +
                "输出 3-5 个 beats、涉及角色、预期偏离、状态变化。只输出 JSON。"

        const val WRITER_PROMPT =
            "你是轻小说分支续写作者。只写用户介入后的分支下一章，不写元叙述。" +
                "必须遵守 plan、用户介入和约束，保持角色声音、称呼、锁定译名和已有设定。" +
                "不得引用分叉点之后的 canon 事件，不得提前揭示秘密，不得新增原文没有的世界规则。" +
                "正文用简体中文，500-12000 字，保留段落空行；只输出 JSON。"

        const val VALIDATOR_PROMPT =
            "你是分支一致性校对员。检查正文是否让角色知道了角色未知的信息、" +
                "是否与 canon 参照矛盾、是否 OOC、是否用错锁定译名、是否出现禁止词。" +
                "canon 参照只能用于判断矛盾，不能当作角色已知。只输出 JSON。"

        const val DIFF_PROMPT =
            "你是世界线差异分析员。对照 canon 参照和分支章节，列出本分支改变了什么、" +
                "哪些 canon 事件不会发生、影响是什么。不要重写正文。只输出 JSON。"
    }
}
