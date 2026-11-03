package com.kacyraho.lightnovel.data.worldline

import com.kacyraho.lightnovel.core.settings.ApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.knowledge.Fact
import com.kacyraho.lightnovel.data.knowledge.KnowledgeStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.story.StoryMemoryStore
import com.kacyraho.lightnovel.data.translation.ChatMessage
import com.kacyraho.lightnovel.data.translation.ChatResult
import com.kacyraho.lightnovel.data.translation.DeepSeekClient
import com.kacyraho.lightnovel.data.translation.TranslationClient
import com.kacyraho.lightnovel.data.translation.TranslationException
import com.kacyraho.lightnovel.data.translation.TranslationValidators
import com.kacyraho.lightnovel.data.translation.translationKeyScope
import com.kacyraho.lightnovel.data.translation.translationRequiresKey
import java.io.IOException
import java.time.Instant
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

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
    private val contexts = WorldlineContextBuilder(knowledgeStore, storyMemoryStore, contentStore)

    suspend fun createBranch(
        book: BookEntity,
        title: String,
        forkChapter: Int,
        forkParagraph: Int,
        intervention: Intervention,
        mode: String = "exploration",
        forkText: String = "",
        lengthMode: String = "standard",
        creativity: String = "balanced",
        directive: String = "",
    ): Result<WorldlineFile> {
        if (forkChapter < 1 || (book.episodes > 0 && forkChapter > book.episodes)) {
            return Result.failure(
                IllegalArgumentException("分叉章超出范围：本书共 ${book.episodes} 章"),
            )
        }
        val edited = forkText.trim().take(12_000)
        if ((intervention.character.isBlank() || intervention.action.isBlank()) &&
            edited.isBlank()
        ) {
            return Result.failure(IllegalArgumentException("请先修改正文或填写角色行动"))
        }
        val now = Instant.now().toString()
        val worldline = WorldlineFile(
            id = worldlineStore.newId(book.id, forkChapter, forkParagraph),
            bookId = book.id,
            title = title.ifBlank {
                if (edited.isNotBlank()) "从第 $forkChapter 章修改开始的分支"
                else "从第 $forkChapter 章开始的分支"
            },
            forkChapter = forkChapter,
            forkParagraph = forkParagraph,
            forkText = edited,
            intervention = intervention,
            mode = if (mode == "comparison") "comparison" else "exploration",
            lengthMode = WorldlineGeneration.normalizeLength(lengthMode),
            creativity = WorldlineGeneration.normalizeCreativity(creativity),
            directive = WorldlineGeneration.normalizeDirective(directive),
            createdAt = now,
            updatedAt = now,
        )
        val generated = generateChapter(book, worldline, 1, "", "")
            .getOrElse { return Result.failure(it) }
        val updated = worldline.copy(
            chapters = listOf(generated.chapter),
            chapterStates = listOf(generated.state),
            state = generated.state,
            divergences = listOf(generated.divergence),
            diffReports = listOfNotNull(generated.diffReport),
            branchExtractedThrough = generated.knowledge?.branchExtractedThrough ?: 0,
            knowledgeStatus = generated.knowledgeStatus,
            updatedAt = now,
        )
        return Result.success(worldlineStore.save(book.storageDir, updated))
    }

    suspend fun continueBranch(
        book: BookEntity,
        id: String,
        count: Int = 1,
        lengthMode: String? = null,
        creativity: String? = null,
        directive: String? = null,
        onProgress: (done: Int, total: Int) -> Unit = { _, _ -> },
    ): Result<WorldlineFile> {
        val loaded = worldlineStore.load(book.storageDir, id)
            ?: return Result.failure(IllegalStateException("分支不存在"))
        var current = applyOptions(loaded, lengthMode, creativity, directive)
        if (current != loaded) {
            current = worldlineStore.save(book.storageDir, current)
        }
        val total = count.coerceIn(1, 5)
        repeat(total) { index ->
            onProgress(index, total)
            val previous = current.chapters.lastOrNull()
            val generated = generateChapter(
                book = book,
                worldline = current,
                chapterIndex = current.chapters.size + 1,
                previousSummary = previous?.summary.orEmpty(),
                previousTail = previous?.text?.takeLast(600).orEmpty(),
            ).getOrElse { return Result.failure(it) }
            val updated = current.copy(
                chapters = current.chapters + generated.chapter,
                chapterStates = current.chapterStates + generated.state,
                state = generated.state,
                divergences = current.divergences + generated.divergence,
                diffReports = current.diffReports + listOfNotNull(generated.diffReport),
                branchExtractedThrough = generated.knowledge?.branchExtractedThrough
                    ?: current.branchExtractedThrough,
                knowledgeStatus = generated.knowledgeStatus,
                updatedAt = Instant.now().toString(),
            )
            current = worldlineStore.save(book.storageDir, updated)
            onProgress(index + 1, total)
        }
        return Result.success(current)
    }

    suspend fun regenerateLastChapter(
        book: BookEntity,
        id: String,
        lengthMode: String? = null,
        creativity: String? = null,
        directive: String? = null,
    ): Result<WorldlineFile> {
        val loaded = worldlineStore.load(book.storageDir, id)
            ?: return Result.failure(IllegalStateException("分支不存在"))
        val target = loaded.chapters.lastOrNull()
            ?: return Result.failure(IllegalStateException("分支还没有章节"))
        var current = applyOptions(loaded, lengthMode, creativity, directive)
        if (current != loaded) {
            current = worldlineStore.save(book.storageDir, current)
        }
        val previousChapters = current.chapters.dropLast(1)
        val previousStates = current.chapterStates.take(previousChapters.size)
        val trimmed = current.copy(
            chapters = previousChapters,
            chapterStates = previousStates,
            state = previousStates.lastOrNull() ?: BranchState(),
            divergences = current.divergences.dropLast(1),
            diffReports = current.diffReports.filterNot { it.chapter == target.index },
        )
        val oldKnowledge = worldlineStore.loadKnowledge(book.storageDir, id)
        worldlineStore.removeKnowledgeChapter(book.storageDir, id, target.index)
        val previous = previousChapters.lastOrNull()
        val generated = generateChapter(
            book = book,
            worldline = trimmed,
            chapterIndex = target.index,
            previousSummary = previous?.summary.orEmpty(),
            previousTail = previous?.text?.takeLast(600).orEmpty(),
        ).getOrElse {
            oldKnowledge?.let { worldlineStore.saveKnowledge(book.storageDir, it) }
            return Result.failure(it)
        }
        val updated = trimmed.copy(
            chapters = previousChapters + generated.chapter,
            chapterStates = previousStates + generated.state,
            state = generated.state,
            divergences = trimmed.divergences + generated.divergence,
            diffReports = trimmed.diffReports + listOfNotNull(generated.diffReport),
            branchExtractedThrough = generated.knowledge?.branchExtractedThrough
                ?: trimmed.branchExtractedThrough,
            knowledgeStatus = generated.knowledgeStatus,
            updatedAt = Instant.now().toString(),
        )
        return Result.success(worldlineStore.save(book.storageDir, updated))
    }

    private fun applyOptions(
        current: WorldlineFile,
        lengthMode: String?,
        creativity: String?,
        directive: String?,
    ): WorldlineFile = current.copy(
        lengthMode = WorldlineGeneration.normalizeLength(lengthMode ?: current.lengthMode),
        creativity = WorldlineGeneration.normalizeCreativity(creativity ?: current.creativity),
        directive = WorldlineGeneration.normalizeDirective(directive ?: current.directive),
    )

    private suspend fun generateChapter(
        book: BookEntity,
        worldline: WorldlineFile,
        chapterIndex: Int,
        previousSummary: String,
        previousTail: String,
    ): Result<GeneratedChapter> {
        val model = client() ?: return Result.failure(IllegalStateException("未配置翻译 API Key"))
        val branchKnowledge = worldlineStore.loadKnowledge(book.storageDir, worldline.id)
        val profile = WorldlineGeneration.length(worldline.lengthMode)
        val creativity = WorldlineGeneration.creativity(worldline.creativity)
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
            futureTerms = futureTerms,
            forbidden = forbidden,
        ).getOrElse { return Result.failure(it) }
        val planText = buildString {
            appendLine(plan.intendedDivergence)
            if (plan.characters.isNotEmpty()) {
                appendLine("涉及角色：${plan.characters.joinToString("、")}")
            }
            plan.beats.forEachIndexed { index, beat -> appendLine("${index + 1}. $beat") }
            if (plan.stateChanges.isNotEmpty()) {
                appendLine("状态变化：${plan.stateChanges.joinToString("；")}")
            }
            if (plan.futureRisks.isNotEmpty()) {
                appendLine("后续风险：${plan.futureRisks.joinToString("；")}")
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
            profile = profile,
            temperature = creativity.temperature,
        ).getOrElse { return Result.failure(it) }

        var violations = validateProse(
            model = model,
            book = book,
            worldline = worldline,
            branchKnowledge = branchKnowledge,
            draft = draft,
            comparison = comparison,
            forbidden = forbidden,
            futureTerms = futureTerms,
            profile = profile,
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
                profile = profile,
                temperature = creativity.temperature,
            ).getOrElse { return Result.failure(it) }
            violations = validateProse(
                model = model,
                book = book,
                worldline = worldline,
                branchKnowledge = branchKnowledge,
                draft = draft,
                comparison = comparison,
                forbidden = forbidden,
                futureTerms = futureTerms,
                profile = profile,
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
        val state = if (draft.state.summary.isBlank()) {
            draft.state.copy(summary = draft.summary)
        } else {
            draft.state
        }
        val divergence = if (draft.divergence.summary.isBlank()) {
            draft.divergence.copy(
                summary = plan.intendedDivergence.ifBlank { draft.summary },
                causedByIntervention = true,
            )
        } else {
            draft.divergence
        }
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
                state = state,
                divergence = divergence,
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
        futureTerms: List<String>,
        forbidden: List<String>,
    ): Result<PlanOutput> {
        var lastError = ""
        repeat(3) { attempt ->
            val correction = if (attempt == 0) {
                ""
            } else {
                "\n【上一次输出有问题，必须修复】" +
                    lastError.take(240) +
                    "\nbeats 必须是字符串数组；不要使用分叉点之后才出现的实体或禁用词；" +
                    "不要 Markdown，只输出一个合法 JSON 对象。"
            }
            val reply = try {
                completeWithRetry(
                    model = model,
                    messages = listOf(
                        ChatMessage("system", PLANNER_PROMPT),
                        ChatMessage(
                            "user",
                            "$context$correction\n【任务】写第 $chapterIndex 章的分支 plan，只输出 JSON。",
                        ),
                    ),
                    maxTokens = 4_096,
                    temperature = when (attempt) {
                        0 -> 0.7
                        1 -> 0.3
                        else -> 0.1
                    },
                )
            } catch (error: TranslationException) {
                return Result.failure(error)
            }
            val parsed = parsePlan(reply.content)
            if (parsed.isFailure) {
                lastError = "plan JSON 解析失败：" + (
                    parsed.exceptionOrNull()?.message.orEmpty().take(160)
                    )
                return@repeat
            }
            val plan = parsed.getOrThrow()
            val invalid = validatePlan(plan, futureTerms, forbidden)
            if (invalid == null) return Result.success(plan)
            lastError = invalid
        }
        return Result.failure(
            IllegalStateException(
                "plan 生成失败：" + lastError.ifBlank { "模型没有返回可用的 plan" },
            ),
        )
    }

    private fun parsePlan(raw: String): Result<PlanOutput> = runCatching {
        val root = json.parseToJsonElement(cleanJson(raw))
        if (root is JsonArray) {
            return@runCatching PlanOutput(beats = normalizeBeats(root.textList()))
        }
        val objectRoot = (root as? JsonObject)?.let {
            (it["plan"] as? JsonObject) ?: it
        } ?: error("plan 不是 JSON 对象")
        val beats = objectRoot["beats"]
            ?: objectRoot["plot"]
            ?: objectRoot["outline"]
            ?: objectRoot["scenes"]
        PlanOutput(
            beats = normalizeBeats(beats?.textList().orEmpty()),
            characters = objectRoot["characters"]?.textList().orEmpty(),
            intendedDivergence = (
                objectRoot["intendedDivergence"]
                    ?: objectRoot["divergence"]
                    ?: objectRoot["summary"]
                )?.textValue().orEmpty(),
            futureRisks = objectRoot["futureRisks"]?.textList().orEmpty(),
            stateChanges = objectRoot["stateChanges"]?.textList().orEmpty(),
        ).also {
            if (it.beats.isEmpty()) error("beats 没有可用内容")
        }
    }

    private fun normalizeBeats(values: List<String>): List<String> = values
        .flatMap { value -> value.split('\n') }
        .map { line ->
            line.trim().replace(Regex("^\\s*(?:[-*•]|\\d+[.、)])\\s*"), "")
        }
        .filter(String::isNotBlank)
        .distinct()

    private fun JsonElement.textList(): List<String> = when (this) {
        is JsonPrimitive -> listOfNotNull(contentOrNull?.trim()?.takeIf(String::isNotBlank))
        is JsonArray -> flatMap { it.textList() }
        is JsonObject -> {
            val preferred = listOf(
                "beat", "text", "summary", "event", "description",
                "content", "action", "goal", "name",
            )
            preferred.firstNotNullOfOrNull { key -> this[key]?.textList()?.firstOrNull() }
                ?.let(::listOf)
                ?: entries.flatMap { it.value.textList() }
        }
    }

    private fun JsonElement.textValue(): String? = when (this) {
        is JsonPrimitive -> contentOrNull?.trim()?.takeIf(String::isNotBlank)
        is JsonArray -> textList().joinToString("\n\n").takeIf(String::isNotBlank)
        is JsonObject -> listOf("text", "summary", "description", "value")
            .firstNotNullOfOrNull { this[it]?.textValue() }
            ?: textList().joinToString("\n\n").takeIf(String::isNotBlank)
    }

    private suspend fun writer(
        model: ModelClient,
        context: String,
        chapterIndex: Int,
        repairNotes: List<String>,
        profile: WorldlineLengthOption,
        temperature: Double,
    ): Result<ChapterOutput> {
        var lastError = ""
        repeat(3) { attempt ->
            val repair = buildString {
                if (repairNotes.isNotEmpty()) {
                    appendLine("【上一次校验问题，必须修复】")
                    repairNotes.forEach(::appendLine)
                }
                if (attempt > 0) {
                    appendLine("【格式纠正】上一次输出无法解析或缺少正文。")
                    appendLine("text 必须是完整字符串；state/divergence 必须是对象。")
                    appendLine("不要 Markdown，只输出一个合法 JSON 对象。")
                }
                appendLine(
                    "【本章长度】目标 ${profile.targetChars} 字，通常 " +
                        "${profile.promptMin}–${profile.promptMax} 字。",
                )
                appendLine("【续写要求】从本分支前文最后一段之后继续，不复述、不总结；" +
                    "写完整场景、动作、对白和情绪推进，结尾留自然钩子。")
            }
            val reply = try {
                completeWithRetry(
                    model = model,
                    messages = listOf(
                        ChatMessage("system", WRITER_PROMPT),
                        ChatMessage(
                            "user",
                            "$context$repair\n【任务】写分支第 $chapterIndex 章，只输出 JSON。",
                        ),
                    ),
                    maxTokens = profile.maxTokens,
                    temperature = if (attempt == 0) {
                        temperature
                    } else {
                        (temperature * 0.45).coerceAtLeast(0.2)
                    },
                )
            } catch (error: TranslationException) {
                return Result.failure(error)
            }
            val parsed = parseChapter(reply.content, chapterIndex)
            if (parsed.isSuccess) return parsed
            lastError = parsed.exceptionOrNull()?.message.orEmpty().take(200)
        }
        return Result.failure(
            IllegalStateException(
                "正文生成失败：" + lastError.ifBlank { "模型没有返回可用的正文" },
            ),
        )
    }

    private fun parseChapter(raw: String, chapterIndex: Int): Result<ChapterOutput> = runCatching {
        val root = json.parseToJsonElement(cleanJson(raw))
        if (root is JsonArray) {
            val text = root.textValue().orEmpty()
            if (text.isBlank()) error("正文为空")
            return@runCatching ChapterOutput(
                title = "分支第 $chapterIndex 章",
                text = text,
                summary = text.take(180).replace('\n', ' '),
            )
        }
        val objectRoot = (root as? JsonObject)?.let {
            (it["chapter"] as? JsonObject) ?: it
        } ?: error("正文不是 JSON 对象")
        val text = (
            objectRoot["text"]
                ?: objectRoot["content"]
                ?: objectRoot["body"]
                ?: objectRoot["chapterText"]
            )?.textValue().orEmpty()
        if (text.isBlank()) error("正文为空")
        ChapterOutput(
            title = objectRoot["title"]?.textValue().orEmpty()
                .ifBlank { "分支第 $chapterIndex 章" },
            text = text,
            summary = objectRoot["summary"]?.textValue().orEmpty()
                .ifBlank { text.take(180).replace('\n', ' ') },
            state = objectRoot["state"].asBranchState(),
            divergence = objectRoot["divergence"].asDivergence(),
        )
    }

    private fun JsonElement?.asBranchState(): BranchState {
        val obj = this as? JsonObject ?: return BranchState()
        return BranchState(
            time = obj["time"]?.textValue().orEmpty(),
            location = obj["location"]?.textValue().orEmpty(),
            summary = obj["summary"]?.textValue().orEmpty(),
            facts = obj["facts"]?.textList().orEmpty(),
            openThreads = obj["openThreads"]?.textList().orEmpty(),
        )
    }

    private fun JsonElement?.asDivergence(): Divergence {
        val obj = this as? JsonObject ?: return Divergence()
        return Divergence(
            type = obj["type"]?.textValue()?.ifBlank { "event" } ?: "event",
            summary = obj["summary"]?.textValue().orEmpty(),
            canonSummary = obj["canonSummary"]?.textValue(),
            causedByIntervention = (obj["causedByIntervention"] as? JsonPrimitive)
                ?.contentOrNull
                ?.toBooleanStrictOrNull()
                ?: true,
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
        futureTerms: List<String>,
        profile: WorldlineLengthOption,
    ): List<Violation> {
        val deterministic = mutableListOf<Violation>()
        if (draft.text.length < profile.minChars || draft.text.length > profile.maxChars) {
            deterministic += Violation(
                "length",
                "",
                "正文长度 ${draft.text.length} 字，要求 ${profile.rangeLabel}",
            )
        }
        if (!TranslationValidators.detectChinese(draft.text)) {
            deterministic += Violation("length", "", "正文不是中文")
        }
        forbidden.firstOrNull { it.isNotBlank() && it in draft.text }?.let {
            deterministic += Violation("term", it, "正文提前出现禁用词：$it")
        }
        futureTerms.firstOrNull { it.isNotBlank() && it in draft.text }?.let {
            deterministic += Violation("term", it, "正文提前出现未来实体：$it")
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
            completeWithRetry(
                model = model,
                messages = listOf(
                    ChatMessage("system", VALIDATOR_PROMPT),
                    ChatMessage("user", prompt),
                ),
                maxTokens = 2_048,
                temperature = 0.1,
            )
        } catch (_: TranslationException) {
            return emptyList()
        }
        val output = runCatching {
            json.decodeFromString(ValidationOutput.serializer(), cleanJson(reply.content))
        }.getOrNull() ?: return emptyList()
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
            completeWithRetry(
                model = model,
                messages = listOf(
                    ChatMessage("system", DIFF_PROMPT),
                    ChatMessage("user", prompt),
                ),
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

    private suspend fun completeWithRetry(
        model: ModelClient,
        messages: List<ChatMessage>,
        maxTokens: Int,
        temperature: Double,
    ): ChatResult {
        var lastError: TranslationException? = null
        repeat(3) { attempt ->
            try {
                return model.client.complete(
                    messages = messages,
                    model = model.model,
                    maxTokens = maxTokens,
                    temperature = temperature,
                )
            } catch (error: TranslationException) {
                lastError = error
                if (!error.retryable || attempt == 2) throw error
                delay(2_000L * (attempt + 1))
            } catch (error: IOException) {
                val wrapped = TranslationException(
                    statusCode = 0,
                    message = "调用 API 失败：${error.message ?: error.javaClass.simpleName}",
                    retryable = true,
                )
                lastError = wrapped
                if (attempt == 2) throw wrapped
                delay(2_000L * (attempt + 1))
            }
        }
        throw lastError ?: TranslationException(0, "调用 API 失败", true)
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
        val text = (
            plan.beats +
                plan.characters +
                plan.intendedDivergence +
                plan.stateChanges +
                plan.futureRisks
            ).joinToString("\n")
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
        val fenced = Regex("(?s)```(?:json)?\\s*(.*?)```").find(text)
        if (fenced != null) text = fenced.groupValues[1].trim()
        if (text.startsWith("```")) {
            text = text.removePrefix("```json").removePrefix("```")
                .removeSuffix("```").trim()
        }
        val objectStart = text.indexOf('{')
        val arrayStart = text.indexOf('[')
        val start = when {
            objectStart >= 0 -> objectStart
            arrayStart >= 0 -> arrayStart
            else -> -1
        }
        val end = if (start >= 0 && text[start] == '{') {
            text.lastIndexOf('}')
        } else {
            text.lastIndexOf(']')
        }
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
            "你是轻小说分支剧情规划师。只使用给定的分叉前知识、分支前文、分支状态、作者备注和用户介入。" +
                "不得使用分叉点之后的 canon 事件，不得提前揭示秘密。" +
                "作者备注是长期导演指令，不能违背 canon 安全边界。" +
                "若用户修改了分叉正文，把修改后的文本视为已经发生的 canon，从它的末尾继续，不重写它。" +
                "输出 4-6 个有因果链的 beats，每个 beat 写清谁做了什么、地点或时间推进、造成什么后果；" +
                "同时给出涉及角色、预期偏离、未来风险和状态变化。" +
                "beats 必须是字符串数组，每个元素只能是一句字符串，不能是对象；不要 Markdown。" +
                "只输出 JSON，格式：" +
                "{\"beats\":[\"第一句剧情节点\",\"第二句剧情节点\"]," +
                "\"characters\":[\"角色名\"],\"intendedDivergence\":\"一句话说明偏离\"," +
                "\"futureRisks\":[\"未来风险\"],\"stateChanges\":[\"状态变化\"]}。"

        const val WRITER_PROMPT =
            "你是轻小说分支续写作者，像角色扮演主持人一样写下一章。只写分支正文，不写元叙述。" +
                "必须遵守 plan、作者备注、用户介入和约束，保持角色声音、称呼、关系、锁定译名和已有设定。" +
                "作者备注是长期导演指令，优先级高于 plan 的文学风格，但不能违背 canon 安全。" +
                "从本分支前文最后一段之后继续，不要复述、总结或重写前文；" +
                "优先写介入角色的行动、对白、感知和情绪，对白要像角色本人。" +
                "用户修改后的分叉正文已经发生，不要重写它，只从它之后续写。" +
                "不得引用分叉点之后的 canon 事件，不得提前揭示秘密，不得新增原文没有的世界规则。" +
                "正文用简体中文，写完整场景、动作、对白和情绪推进，保留段落空行；" +
                "只输出 JSON，text/content 字段放完整正文，不要 Markdown。"

        const val VALIDATOR_PROMPT =
            "你是分支一致性校对员。检查正文是否让角色知道了角色未知的信息、" +
                "是否与 canon 参照矛盾、是否 OOC、是否用错锁定译名、是否出现禁止词。" +
                "canon 参照只能用于判断矛盾，不能当作角色已知。只输出 JSON。"

        const val DIFF_PROMPT =
            "你是世界线差异分析员。对照 canon 参照和分支章节，列出本分支改变了什么、" +
                "哪些 canon 事件不会发生、影响是什么。不要重写正文。只输出 JSON。"
    }
}
