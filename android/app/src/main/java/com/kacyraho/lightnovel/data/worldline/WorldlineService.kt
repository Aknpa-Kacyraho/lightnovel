package com.kacyraho.lightnovel.data.worldline

import com.kacyraho.lightnovel.core.settings.ApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.knowledge.FactAnchor
import com.kacyraho.lightnovel.data.knowledge.FactAnchorMapper
import com.kacyraho.lightnovel.data.knowledge.KnowledgeFile
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

    suspend fun createBranch(
        book: BookEntity,
        title: String,
        forkChapter: Int,
        forkParagraph: Int,
        intervention: Intervention,
    ): Result<WorldlineFile> {
        if (intervention.character.isBlank() || intervention.action.isBlank()) {
            return Result.failure(IllegalArgumentException("角色和行动不能为空"))
        }
        val context = buildContext(book, forkChapter, forkParagraph)
            ?: return Result.failure(IllegalStateException("还没有可用的知识库"))
        val generated = generate(
            context = context,
            intervention = intervention,
            state = BranchState(),
            previousSummary = "",
            previousTail = "",
            chapterIndex = 1,
            forbiddenTerms = forbiddenTerms(book, forkChapter),
        ).getOrElse { return Result.failure(it) }
        val now = Instant.now().toString()
        val worldline = WorldlineFile(
            id = worldlineStore.newId(book.id, forkChapter, forkParagraph),
            bookId = book.id,
            title = title.ifBlank { "从第 $forkChapter 章开始的分支" },
            forkChapter = forkChapter,
            forkParagraph = forkParagraph,
            intervention = intervention,
            mode = "exploration",
            chapters = listOf(
                BranchChapter(
                    index = 1,
                    title = generated.title,
                    text = generated.text,
                    summary = generated.summary,
                    createdAt = now,
                ),
            ),
            state = generated.state,
            divergences = listOf(generated.divergence),
            createdAt = now,
            updatedAt = now,
        )
        return Result.success(worldlineStore.save(book.storageDir, worldline))
    }

    suspend fun continueBranch(book: BookEntity, id: String): Result<WorldlineFile> {
        val current = worldlineStore.load(book.storageDir, id)
            ?: return Result.failure(IllegalStateException("分支不存在"))
        val context = buildContext(book, current.forkChapter, current.forkParagraph)
            ?: return Result.failure(IllegalStateException("还没有可用的知识库"))
        val previous = current.chapters.lastOrNull()
        val generated = generate(
            context = context,
            intervention = current.intervention,
            state = current.state,
            previousSummary = previous?.summary.orEmpty(),
            previousTail = previous?.text?.takeLast(600).orEmpty(),
            chapterIndex = current.chapters.size + 1,
            forbiddenTerms = forbiddenTerms(book, current.forkChapter),
        ).getOrElse { return Result.failure(it) }
        val now = Instant.now().toString()
        val updated = current.copy(
            chapters = current.chapters + BranchChapter(
                index = current.chapters.size + 1,
                title = generated.title,
                text = generated.text,
                summary = generated.summary,
                createdAt = now,
            ),
            state = generated.state,
            divergences = current.divergences + generated.divergence,
            updatedAt = now,
        )
        return Result.success(worldlineStore.save(book.storageDir, updated))
    }

    fun buildContext(book: BookEntity, forkChapter: Int, forkParagraph: Int): String? {
        val knowledge = knowledgeStore.load(book.storageDir, book.id, book.title)
        if (knowledge.canonExtractedThrough <= 0 && knowledge.entities.isEmpty()) return null
        val fork = FactAnchor(
            chapter = forkChapter,
            paragraph = forkParagraph,
            charOffset = Int.MAX_VALUE,
            quoteHash = "",
        )
        val memory = storyMemoryStore?.load(book.storageDir, book.id, book.title)
        return buildString {
            appendLine("【作品】${book.titleZh ?: book.title}")
            appendLine("【分叉点】第 $forkChapter 章第 $forkParagraph 段")
            if (memory?.glossary?.isNotEmpty() == true) {
                appendLine("【锁定译名】")
                memory.glossary.take(40).forEach { appendLine("${it.source}=${it.target}") }
            }
            if (memory?.style != null) {
                val style = memory.style
                val lines = listOf(
                    style.general,
                    style.narrator,
                    style.honorifics,
                    style.notes,
                    style.guide,
                ).filter(String::isNotBlank)
                if (lines.isNotEmpty()) {
                    appendLine("【本书风格】")
                    lines.forEach { appendLine(it.take(300)) }
                }
            }
            val entities = knowledge.entities.filter {
                it.readerKnown && visible(it.sourceAnchor, fork)
            }
            if (entities.isNotEmpty()) {
                appendLine("【已知实体】")
                entities.take(40).forEach { appendLine("${it.canonicalName}（${it.type}）") }
            }
            val facts = knowledge.facts.filter {
                it.readerKnown && it.kind != "reveal_content" &&
                    it.status != "source_stale" && it.status != "low_confidence" &&
                    visible(it.sourceAnchor, fork) &&
                    (it.validUntilChapter == null || forkChapter < it.validUntilChapter)
            }
            if (facts.isNotEmpty()) {
                appendLine("【分叉点前已知事实】")
                facts.take(50).forEach {
                    appendLine("${it.kind}/${it.factKey}: ${it.text}")
                }
            }
            val relations = knowledge.relations.filter {
                it.readerKnown && visible(it.sourceAnchor, fork)
            }
            if (relations.isNotEmpty()) {
                appendLine("【关系】")
                relations.take(20).forEach {
                    val from = knowledge.entity(it.fromEntityId)?.canonicalName ?: "?"
                    val to = knowledge.entity(it.toEntityId)?.canonicalName ?: "?"
                    appendLine("$from → $to：${it.label}")
                }
            }
            val voices = knowledge.voiceFacts.filter {
                it.readerKnown && visible(it.sourceAnchor, fork)
            }
            if (voices.isNotEmpty()) {
                appendLine("【角色声音】")
                voices.take(20).forEach {
                    val name = knowledge.entity(it.entityId)?.canonicalName ?: "?"
                    appendLine("$name/${it.dimension}：${it.text}")
                }
            }
        }
    }

    fun forbiddenTerms(book: BookEntity, forkChapter: Int): List<String> {
        val knowledge = knowledgeStore.load(book.storageDir, book.id, book.title)
        return knowledge.secrets
            .filter { it.canonRevealChapter == null || it.canonRevealChapter > forkChapter }
            .flatMap { it.forbiddenTerms }
            .map(String::trim)
            .filter(String::isNotBlank)
            .distinct()
    }

    private suspend fun generate(
        context: String,
        intervention: Intervention,
        state: BranchState,
        previousSummary: String,
        previousTail: String,
        chapterIndex: Int,
        forbiddenTerms: List<String>,
    ): Result<GeneratedChapter> {
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) {
            return Result.failure(IllegalStateException("未配置翻译 API Key"))
        }
        val client = clientFactory(settings.deepSeekBaseUrl, key)
        val reply = try {
            client.complete(
                messages = listOf(
                    ChatMessage("system", SYSTEM_PROMPT),
                    ChatMessage(
                        "user",
                        userPrompt(
                            context = context,
                            intervention = intervention,
                            state = state,
                            previousSummary = previousSummary,
                            previousTail = previousTail,
                            chapterIndex = chapterIndex,
                            forbiddenTerms = forbiddenTerms,
                        ),
                    ),
                ),
                model = settings.deepSeekModel,
                maxTokens = 8_192,
                temperature = 0.8,
            )
        } catch (error: TranslationException) {
            return Result.failure(error)
        }
        val output = runCatching {
            json.decodeFromString(GeneratedOutput.serializer(), cleanJson(reply.content))
        }.getOrElse {
            return Result.failure(IllegalStateException("分支生成返回无法解析：${it.message}"))
        }
        val text = output.text.trim()
        if (text.length < 500 || text.length > 12_000) {
            return Result.failure(IllegalStateException("分支正文长度异常"))
        }
        if (!TranslationValidators.detectChinese(text)) {
            return Result.failure(IllegalStateException("分支正文不是中文"))
        }
        val hit = forbiddenTerms.firstOrNull { it.isNotBlank() && it in text }
        if (hit != null) {
            return Result.failure(IllegalStateException("分支正文提前出现禁用词：$hit"))
        }
        return Result.success(
            GeneratedChapter(
                title = output.title.trim().ifBlank { "分支第 $chapterIndex 章" },
                text = text,
                summary = output.summary.trim().ifBlank { text.take(120) },
                state = output.state,
                divergence = output.divergence,
            ),
        )
    }

    private fun visible(anchor: FactAnchor, fork: FactAnchor): Boolean =
        FactAnchorMapper.visible(anchor, fork)

    private fun userPrompt(
        context: String,
        intervention: Intervention,
        state: BranchState,
        previousSummary: String,
        previousTail: String,
        chapterIndex: Int,
        forbiddenTerms: List<String>,
    ): String = buildString {
        appendLine(context)
        appendLine("【用户介入】")
        appendLine("角色：${intervention.character}")
        appendLine("行动：${intervention.action}")
        appendLine("约束：${intervention.constraint}")
        if (state.summary.isNotBlank()) {
            appendLine("【当前分支状态】")
            appendLine("时间：${state.time}；地点：${state.location}")
            appendLine(state.summary)
            if (state.openThreads.isNotEmpty()) {
                appendLine("未解决线索：${state.openThreads.joinToString("；")}")
            }
        }
        if (previousSummary.isNotBlank()) {
            appendLine("【上一章梗概】$previousSummary")
        }
        if (previousTail.isNotBlank()) {
            appendLine("【上一章结尾】$previousTail")
        }
        if (forbiddenTerms.isNotEmpty()) {
            appendLine("【禁止提前出现】${forbiddenTerms.joinToString("、")}")
        }
        appendLine("【任务】写分支第 $chapterIndex 章。只写这一章，不要总结全书。")
        appendLine("输出 JSON：{\"title\":\"\",\"text\":\"\",\"summary\":\"\",\"state\":{\"time\":\"\",\"location\":\"\",\"summary\":\"\",\"facts\":[],\"openThreads\":[]},\"divergence\":{\"type\":\"event\",\"summary\":\"\",\"canonSummary\":null,\"causedByIntervention\":true}}")
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

    @Serializable
    private data class GeneratedOutput(
        val title: String = "",
        val text: String = "",
        val summary: String = "",
        val state: BranchState = BranchState(),
        val divergence: Divergence = Divergence(),
    )

    private data class GeneratedChapter(
        val title: String,
        val text: String,
        val summary: String,
        val state: BranchState,
        val divergence: Divergence,
    )

    private companion object {
        const val SYSTEM_PROMPT =
            "你是轻小说分支续写作者。只写用户介入后的分支下一章，不写元叙述。" +
                "必须遵守用户介入和约束，保持角色声音、称呼、锁定译名和已有设定。" +
                "不得引用分叉点之后的 canon 事件，不得提前揭示秘密，不得新增原文没有的世界规则。" +
                "正文用简体中文，500-12000 字，保留段落空行；只输出 JSON。"
    }
}
