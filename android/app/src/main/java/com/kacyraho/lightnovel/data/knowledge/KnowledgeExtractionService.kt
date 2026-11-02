package com.kacyraho.lightnovel.data.knowledge

import com.kacyraho.lightnovel.core.settings.ApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.glossary.GlossaryEntry
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.story.StoryMemoryStore
import com.kacyraho.lightnovel.data.translation.ChatMessage
import com.kacyraho.lightnovel.data.translation.DeepSeekClient
import com.kacyraho.lightnovel.data.translation.Hashes
import com.kacyraho.lightnovel.data.translation.TranslationClient
import com.kacyraho.lightnovel.data.translation.TranslationException
import com.kacyraho.lightnovel.data.translation.translationKeyScope
import com.kacyraho.lightnovel.data.translation.translationRequiresKey
import java.time.Instant
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

class KnowledgeExtractionService(
    private val contentStore: ContentStore,
    private val knowledgeStore: KnowledgeStore,
    private val settingsStore: SettingsStore,
    private val apiKeyStore: ApiKeyStore,
    private val storyMemoryStore: StoryMemoryStore? = null,
    private val clientFactory: (String, String) -> TranslationClient = { base, key ->
        DeepSeekClient(base, key)
    },
) {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        explicitNulls = false
    }

    suspend fun extractChapter(
        book: BookEntity,
        chapterIndex: Int,
        force: Boolean = false,
    ): Result<KnowledgeFile> {
        val raw = contentStore.readRaw(book.storageDir, chapterIndex)
            ?: return Result.failure(IllegalStateException("这一章没有原文"))
        val zh = contentStore.readZh(book.storageDir, chapterIndex)
            ?: return Result.failure(IllegalStateException("这一章还没有译文"))
        if (raw.isBlank() || zh.isBlank()) {
            return Result.failure(IllegalStateException("原文或译文为空"))
        }
        val current = knowledgeStore.load(book.storageDir, book.id, book.title)
        if (!force && current.extractedChapters.contains(chapterIndex)) {
            return Result.success(current)
        }
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) {
            return Result.failure(IllegalStateException("未配置翻译 API Key"))
        }
        val client = clientFactory(settings.deepSeekBaseUrl, key)
        val memory = storyMemoryStore?.load(book.storageDir, book.id, book.title)
        val output = try {
            val reply = client.complete(
                messages = listOf(
                    ChatMessage("system", SYSTEM_PROMPT),
                    ChatMessage(
                        "user",
                        userPrompt(
                            raw = raw,
                            zh = zh,
                            existingEntities = current.entities,
                            glossary = memory?.glossary.orEmpty()
                                .map { "${it.source}=${it.target}" },
                        ),
                    ),
                ),
                model = settings.deepSeekModel,
                maxTokens = 8_192,
                temperature = 0.1,
            )
            json.decodeFromString(ExtractionOutput.serializer(), cleanJson(reply.content))
        } catch (error: TranslationException) {
            return Result.failure(error)
        } catch (error: Exception) {
            return Result.failure(IllegalStateException("知识抽取返回无法解析：${error.message}"))
        }
        return runCatching {
            merge(book, chapterIndex, raw, zh, current, output)
                .also { seedGlossary(book, output) }
        }.fold(
            onSuccess = { Result.success(it) },
            onFailure = { Result.failure(it) },
        )
    }

    suspend fun extractAll(
        book: BookEntity,
        chapters: List<com.kacyraho.lightnovel.data.local.ChapterEntity>,
        onProgress: (done: Int, total: Int) -> Unit = { _, _ -> },
    ): Result<Int> {
        val eligible = chapters.sortedBy { it.idx }.filter {
            contentStore.readZh(book.storageDir, it.idx) != null
        }
        var done = 0
        var failed = 0
        eligible.forEachIndexed { index, chapter ->
            val result = extractChapter(book, chapter.idx)
            if (result.isSuccess) done++ else failed++
            onProgress(index + 1, eligible.size)
        }
        return if (done == 0 && failed > 0) {
            Result.failure(IllegalStateException("没有章节抽取成功"))
        } else {
            Result.success(done)
        }
    }

    private fun merge(
        book: BookEntity,
        chapter: Int,
        raw: String,
        zh: String,
        current: KnowledgeFile,
        output: ExtractionOutput,
    ): KnowledgeFile {
        val now = Instant.now().toString()
        val entities = current.entities.toMutableList()
        val nameToId = mutableMapOf<String, String>()
        for (entity in entities) {
            entity.names().forEach { nameToId[it] = entity.id }
        }
        var accepted = 0
        val candidateCount = output.entities.size + output.facts.size +
            output.relations.size + output.voiceFacts.size + output.secrets.size

        for (item in output.entities) {
            val source = item.source.trim()
            if (source.isBlank()) continue
            val quote = item.sourceQuote.ifBlank { source }
            val anchor = locate(raw, chapter, quote, source) ?: continue
            val existingIndex = entities.indexOfFirst {
                it.id == nameToId[source] ||
                    it.canonicalName == source ||
                    source in it.aliases
            }
            val id = if (existingIndex >= 0) {
                entities[existingIndex].id
            } else {
                "ent-" + Hashes.sha256(FactAnchorMapper.normalize(source)).take(16)
            }
            val old = entities.getOrNull(existingIndex)
            val canonical = item.canonicalName.trim().ifBlank {
                old?.canonicalName ?: source
            }
            val merged = (old ?: Entity(id = id)).copy(
                type = item.type.ifBlank { old?.type ?: "character" },
                canonicalName = canonical,
                aliases = ((old?.aliases.orEmpty()) + item.aliases + source)
                    .map(String::trim)
                    .filter(String::isNotBlank)
                    .distinct(),
                sourceQuote = quote,
                sourceAnchor = anchor,
                displayQuote = item.displayQuote,
                displayAnchor = display(zh, chapter, item.displayQuote),
                readerKnown = (old?.readerKnown ?: false) || item.readerKnown,
                knownBy = (old?.knownBy.orEmpty() + item.knownBy).distinct(),
                firstSeenChapter = old?.firstSeenChapter ?: chapter,
                lastConfirmedChapter = chapter,
                status = "active",
                createdAt = old?.createdAt ?: now,
                updatedAt = now,
            )
            if (existingIndex >= 0) entities[existingIndex] = merged else entities += merged
            merged.names().forEach { nameToId[it] = merged.id }
            accepted++
        }

        fun resolveNames(names: List<String>): List<String> =
            names.mapNotNull { raw ->
                val value = raw.trim()
                nameToId[value] ?: value.takeIf { id -> entities.any { it.id == id } }
            }.distinct()

        for (index in entities.indices) {
            val entity = entities[index]
            entities[index] = entity.copy(knownBy = resolveNames(entity.knownBy))
        }

        val facts = current.facts.toMutableList()
        for (item in output.facts) {
            val entityId = nameToId[item.entity.trim()] ?: continue
            val text = item.text.trim()
            if (text.isBlank()) continue
            val anchor = locate(raw, chapter, item.sourceQuote, item.entity) ?: continue
            val kind = item.kind.takeIf {
                it in setOf("persona", "direction", "reveal_constraint", "reveal_content", "event")
            } ?: "persona"
            val factKey = item.key.ifBlank { kind }
            val id = id("fact", book.id, chapter, kind, entityId, factKey, text)
            val old = facts.firstOrNull { it.id == id }
            val conflictIndex = facts.indexOfFirst {
                it.id != id && it.scope == "canon" && it.entityId == entityId &&
                    it.factKey == factKey && it.validUntilChapter == null &&
                    it.kind == kind
            }
            val conflict = facts.getOrNull(conflictIndex)
            if (conflict != null) {
                facts[conflictIndex] = conflict.copy(
                    validUntilChapter = (chapter - 1).coerceAtLeast(conflict.firstSeenChapter),
                    supersededBy = id,
                    updatedAt = now,
                )
            }
            val merged = Fact(
                id = id,
                entityId = entityId,
                kind = kind,
                factKey = factKey,
                text = text,
                participantEntityIds = resolveNames(item.participantEntities),
                sourceQuote = item.sourceQuote,
                sourceAnchor = anchor,
                displayQuote = item.displayQuote,
                displayAnchor = display(zh, chapter, item.displayQuote),
                secretId = null,
                readerKnown = item.readerKnown,
                knownBy = resolveNames(item.knownBy),
                firstSeenChapter = old?.firstSeenChapter ?: chapter,
                lastConfirmedChapter = chapter,
                validFromChapter = old?.validFromChapter ?: chapter,
                validUntilChapter = null,
                supersedes = conflict?.id,
                supersededBy = null,
                confidence = item.confidence.coerceIn(0.0, 1.0),
                status = if (item.displayQuote.isNullOrBlank() ||
                    display(zh, chapter, item.displayQuote) == null
                ) "display_stale" else "active",
                forbiddenTerms = item.forbiddenTerms,
                createdAt = old?.createdAt ?: now,
                updatedAt = now,
            )
            if (old != null) {
                facts[facts.indexOfFirst { it.id == id }] = merged
            } else {
                facts += merged
            }
            accepted++
        }

        val relations = current.relations.toMutableList()
        for (item in output.relations) {
            val from = nameToId[item.from.trim()] ?: continue
            val to = nameToId[item.to.trim()] ?: continue
            val anchor = locate(raw, chapter, item.sourceQuote, item.from) ?: continue
            val id = id("rel", book.id, chapter, item.type, from, to, item.label)
            val old = relations.firstOrNull { it.id == id }
            val conflictIndex = relations.indexOfFirst {
                it.id != id && it.fromEntityId == from && it.toEntityId == to &&
                    it.type == item.type && it.validUntilChapter == null
            }
            val conflict = relations.getOrNull(conflictIndex)
            if (conflict != null) {
                relations[conflictIndex] = conflict.copy(
                    validUntilChapter = (chapter - 1).coerceAtLeast(conflict.firstSeenChapter),
                    supersededBy = id,
                    updatedAt = now,
                )
            }
            val merged = Relation(
                id = id,
                fromEntityId = from,
                toEntityId = to,
                type = item.type.ifBlank { "other" },
                label = item.label,
                sourceQuote = item.sourceQuote,
                sourceAnchor = anchor,
                displayQuote = item.displayQuote,
                displayAnchor = display(zh, chapter, item.displayQuote),
                readerKnown = item.readerKnown,
                knownBy = resolveNames(item.knownBy),
                firstSeenChapter = old?.firstSeenChapter ?: chapter,
                lastConfirmedChapter = chapter,
                validFromChapter = old?.validFromChapter ?: chapter,
                validUntilChapter = null,
                supersedes = conflict?.id,
                confidence = item.confidence.coerceIn(0.0, 1.0),
                status = if (item.displayQuote.isNullOrBlank() ||
                    display(zh, chapter, item.displayQuote) == null
                ) "display_stale" else "active",
                createdAt = old?.createdAt ?: now,
                updatedAt = now,
            )
            if (old != null) {
                relations[relations.indexOfFirst { it.id == id }] = merged
            } else {
                relations += merged
            }
            accepted++
        }

        val voices = current.voiceFacts.toMutableList()
        for (item in output.voiceFacts) {
            val entityId = nameToId[item.entity.trim()] ?: continue
            val text = item.text.trim()
            if (text.isBlank()) continue
            val anchor = locate(raw, chapter, item.sourceQuote, item.entity) ?: continue
            val id = id("voice", book.id, chapter, item.dimension, entityId, text)
            val old = voices.firstOrNull { it.id == id }
            val merged = VoiceFact(
                id = id,
                entityId = entityId,
                dimension = item.dimension.ifBlank { "voice" },
                text = text,
                exampleQuote = item.exampleQuote,
                sourceQuote = item.sourceQuote,
                sourceAnchor = anchor,
                displayQuote = item.displayQuote,
                displayAnchor = display(zh, chapter, item.displayQuote),
                readerKnown = item.readerKnown,
                knownBy = resolveNames(item.knownBy),
                firstSeenChapter = old?.firstSeenChapter ?: chapter,
                lastConfirmedChapter = chapter,
                confidence = item.confidence.coerceIn(0.0, 1.0),
                status = if (item.displayQuote.isNullOrBlank() ||
                    display(zh, chapter, item.displayQuote) == null
                ) "display_stale" else "active",
                createdAt = old?.createdAt ?: now,
                updatedAt = now,
            )
            if (old != null) {
                voices[voices.indexOfFirst { it.id == id }] = merged
            } else {
                voices += merged
            }
            accepted++
        }

        val secrets = current.secrets.toMutableList()
        for (item in output.secrets) {
            val subject = nameToId[item.subject.trim()] ?: continue
            val content = item.contentFacts.mapNotNull { contentItem ->
                val anchor = locate(raw, chapter, contentItem.sourceQuote, item.subject) ?: return@mapNotNull null
                val text = contentItem.text.trim()
                if (text.isBlank()) return@mapNotNull null
                val id = id("fact", book.id, chapter, "reveal_content", subject, "secret", text)
                Fact(
                    id = id,
                    entityId = subject,
                    kind = "reveal_content",
                    factKey = "secret",
                    text = text,
                    sourceQuote = contentItem.sourceQuote,
                    sourceAnchor = anchor,
                    displayQuote = contentItem.displayQuote,
                    displayAnchor = display(zh, chapter, contentItem.displayQuote),
                    secretId = id("secret", book.id, subject, item.forbiddenTerms.joinToString(",")),
                    readerKnown = false,
                    knownBy = emptyList(),
                    firstSeenChapter = chapter,
                    lastConfirmedChapter = chapter,
                    validFromChapter = chapter,
                    confidence = 0.8,
                    status = "active",
                    forbiddenTerms = contentItem.forbiddenTerms,
                    createdAt = now,
                    updatedAt = now,
                )
            }
            if (content.isEmpty()) continue
            val secretId = id("secret", book.id, subject, item.forbiddenTerms.joinToString(","))
            val old = secrets.firstOrNull { it.id == secretId }
            val merged = Secret(
                id = secretId,
                subjectEntityId = subject,
                contentFactIds = content.map { it.id },
                canonRevealChapter = item.canonRevealChapter,
                allowedHints = item.allowedHints,
                hintNotes = item.hintNotes,
                forbiddenTerms = item.forbiddenTerms,
            )
            if (old != null) {
                secrets[secrets.indexOfFirst { it.id == secretId }] = merged
            } else {
                secrets += merged
            }
            facts += content
            accepted += content.size
        }

        if (candidateCount > 0 && accepted == 0) {
            error("所有抽取条目都未通过出处校验")
        }
        val chapters = (current.extractedChapters + chapter).distinct().sorted()
        return knowledgeStore.save(
            book.storageDir,
            current.copy(
                entities = entities,
                facts = facts,
                relations = relations,
                voiceFacts = voices,
                secrets = secrets,
                extractedChapters = chapters,
            ),
        )
    }

    private fun seedGlossary(book: BookEntity, output: ExtractionOutput) {
        val store = storyMemoryStore ?: return
        val memory = store.load(book.storageDir, book.id, book.title)
        val entries = memory.glossary.toMutableList()
        var changed = false
        for (item in output.entities) {
            val source = item.source.trim()
            val target = item.canonicalName.trim().ifBlank {
                item.aliases.firstOrNull { it.trim().isNotBlank() }.orEmpty().trim()
            }
            if (source.isBlank() || target.isBlank() || source == target) continue
            val index = entries.indexOfFirst { it.source == source }
            if (index < 0) {
                entries += GlossaryEntry(
                    id = source,
                    source = source,
                    target = target,
                    aliases = item.aliases.map(String::trim)
                        .filter(String::isNotBlank)
                        .distinct(),
                )
                changed = true
            }
        }
        if (changed) store.save(book.storageDir, memory.copy(glossary = entries))
    }

    private fun locate(
        raw: String,
        chapter: Int,
        quote: String,
        fallback: String = "",
    ): FactAnchor? {
        val candidates = listOf(quote, quote.replace(Regex("\\s+"), ""), fallback)
            .map(String::trim)
            .filter(String::isNotBlank)
            .distinct()
        for (candidate in candidates) {
            val location = FactAnchorMapper.locate(raw, candidate) ?: continue
            return FactAnchor(
                chapter = chapter,
                paragraph = location.first,
                charOffset = location.second,
                quoteHash = FactAnchorMapper.quoteHash(candidate),
            )
        }
        if (raw.isBlank()) return null
        return FactAnchor(
            chapter = chapter,
            paragraph = 0,
            charOffset = 0,
            quoteHash = FactAnchorMapper.quoteHash(candidates.firstOrNull().orEmpty()),
        )
    }

    private fun display(zh: String, chapter: Int, quote: String?): DisplayAnchor? {
        if (quote.isNullOrBlank()) return null
        val location = FactAnchorMapper.locate(zh, quote) ?: return null
        return DisplayAnchor(
            chapter = chapter,
            paragraph = location.first,
            charOffset = location.second,
            quoteHash = FactAnchorMapper.quoteHash(quote),
        )
    }

    private fun id(vararg parts: Any?): String =
        parts.joinToString("|") { it?.toString().orEmpty() }
            .let { "item-" + Hashes.sha256(it).take(16) }

    private fun userPrompt(
        raw: String,
        zh: String,
        existingEntities: List<Entity>,
        glossary: List<String>,
    ): String = buildString {
        appendLine("【已有实体】")
        if (existingEntities.isEmpty()) {
            appendLine("（无）")
        } else {
            existingEntities.take(60).forEach {
                appendLine("${it.canonicalName} / ${it.aliases.joinToString("、")}")
            }
        }
        if (glossary.isNotEmpty()) {
            appendLine("【术语表译名（优先使用）】")
            glossary.take(40).forEach(::appendLine)
        }
        appendLine("【本章原文（sourceQuote 只能从这里逐字复制）】")
        appendLine(raw.take(9_000))
        appendLine("【本章译文（仅帮助理解，不能作为 sourceQuote）】")
        appendLine(zh.take(9_000))
        appendLine("只输出 JSON。")
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
    private data class ExtractionOutput(
        val entities: List<ExtractionEntity> = emptyList(),
        val facts: List<ExtractionFact> = emptyList(),
        val relations: List<ExtractionRelation> = emptyList(),
        val voiceFacts: List<ExtractionVoice> = emptyList(),
        val secrets: List<ExtractionSecret> = emptyList(),
    )

    @Serializable
    private data class ExtractionEntity(
        val source: String = "",
        val aliases: List<String> = emptyList(),
        val type: String = "character",
        val canonicalName: String = "",
        val sourceQuote: String = "",
        val displayQuote: String? = null,
        val readerKnown: Boolean = true,
        val knownBy: List<String> = emptyList(),
    )

    @Serializable
    private data class ExtractionFact(
        val entity: String = "",
        val key: String = "",
        val kind: String = "persona",
        val text: String = "",
        val participantEntities: List<String> = emptyList(),
        val sourceQuote: String = "",
        val displayQuote: String? = null,
        val readerKnown: Boolean = true,
        val knownBy: List<String> = emptyList(),
        val confidence: Double = 0.7,
        val forbiddenTerms: List<String> = emptyList(),
    )

    @Serializable
    private data class ExtractionRelation(
        val from: String = "",
        val to: String = "",
        val type: String = "other",
        val label: String = "",
        val sourceQuote: String = "",
        val displayQuote: String? = null,
        val readerKnown: Boolean = true,
        val knownBy: List<String> = emptyList(),
        val confidence: Double = 0.7,
    )

    @Serializable
    private data class ExtractionVoice(
        val entity: String = "",
        val dimension: String = "voice",
        val text: String = "",
        val exampleQuote: String? = null,
        val sourceQuote: String = "",
        val displayQuote: String? = null,
        val readerKnown: Boolean = true,
        val knownBy: List<String> = emptyList(),
        val confidence: Double = 0.7,
    )

    @Serializable
    private data class ExtractionSecret(
        val subject: String = "",
        val contentFacts: List<ExtractionSecretFact> = emptyList(),
        val canonRevealChapter: Int? = null,
        val allowedHints: List<String> = emptyList(),
        val hintNotes: String? = null,
        val forbiddenTerms: List<String> = emptyList(),
    )

    @Serializable
    private data class ExtractionSecretFact(
        val text: String = "",
        val sourceQuote: String = "",
        val displayQuote: String? = null,
        val forbiddenTerms: List<String> = emptyList(),
    )

    private companion object {
        const val SYSTEM_PROMPT =
            "你从日文轻小说原文和中文译文中抽取可查询的设定事实。" +
                "只抽取本章明确出现或确认的信息，不推测后文。" +
                "每条事实必须附原文短句 sourceQuote；sourceQuote 必须逐字复制【本章原文】中的日文子串，" +
                "禁止使用中文译文、改写或概括；找不到可逐字复制的原文就留空。" +
                "区分 readerKnown（读者是否已看到）与 knownBy（哪些角色知道）；" +
                "叙述者展示给读者但角色不知道的信息，readerKnown=true、knownBy 留空。" +
                "persona/direction 必须是抽象倾向，不得写具体揭示事件。" +
                "对白语气放 voiceFacts，附对白例句。秘密放 secrets，附 forbiddenTerms。" +
                "source/entity/from/to/subject 必须填日文原名；canonicalName 填中文译名。" +
                "只输出 JSON，字段名必须严格使用下面格式：" +
                "{\"entities\":[{\"source\":\"日文名\",\"aliases\":[\"日文别名\"]," +
                "\"type\":\"character|place|organization|item|skill|concept\"," +
                "\"canonicalName\":\"中文名\",\"sourceQuote\":\"日文原文\"," +
                "\"displayQuote\":\"中文译文\",\"readerKnown\":true,\"knownBy\":[\"角色名\"]}]," +
                "\"facts\":[{\"entity\":\"日文名\",\"key\":\"稳定键\"," +
                "\"kind\":\"persona|direction|event|reveal_constraint|reveal_content\"," +
                "\"text\":\"中文事实\",\"participantEntities\":[],\"sourceQuote\":\"日文原文\"," +
                "\"displayQuote\":\"中文译文\",\"readerKnown\":true,\"knownBy\":[]," +
                "\"confidence\":0.8,\"forbiddenTerms\":[]}]," +
                "\"relations\":[{\"from\":\"日文名\",\"to\":\"日文名\",\"type\":\"relation\"," +
                "\"label\":\"中文关系\",\"sourceQuote\":\"日文原文\",\"displayQuote\":\"中文译文\"," +
                "\"readerKnown\":true,\"knownBy\":[],\"confidence\":0.8}]," +
                "\"voiceFacts\":[{\"entity\":\"日文名\",\"dimension\":\"语气\",\"text\":\"中文描述\"," +
                "\"exampleQuote\":\"中文例句\",\"sourceQuote\":\"日文原文\",\"displayQuote\":\"中文译文\"," +
                "\"readerKnown\":true,\"knownBy\":[],\"confidence\":0.8}]," +
                "\"secrets\":[{\"subject\":\"日文名\",\"contentFacts\":[{\"text\":\"中文秘密\"," +
                "\"sourceQuote\":\"日文原文\",\"displayQuote\":\"中文译文\"}]," +
                "\"canonRevealChapter\":null,\"allowedHints\":[],\"forbiddenTerms\":[]}]}。"
    }
}
