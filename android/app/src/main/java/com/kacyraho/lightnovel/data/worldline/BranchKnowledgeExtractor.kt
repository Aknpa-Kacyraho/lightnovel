package com.kacyraho.lightnovel.data.worldline

import com.kacyraho.lightnovel.core.settings.ApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.data.knowledge.Entity
import com.kacyraho.lightnovel.data.knowledge.Fact
import com.kacyraho.lightnovel.data.knowledge.FactAnchor
import com.kacyraho.lightnovel.data.knowledge.FactAnchorMapper
import com.kacyraho.lightnovel.data.knowledge.KnowledgeStore
import com.kacyraho.lightnovel.data.knowledge.Relation
import com.kacyraho.lightnovel.data.knowledge.Secret
import com.kacyraho.lightnovel.data.knowledge.VoiceFact
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.translation.ChatMessage
import com.kacyraho.lightnovel.data.translation.ChatResult
import com.kacyraho.lightnovel.data.translation.DeepSeekClient
import com.kacyraho.lightnovel.data.translation.Hashes
import com.kacyraho.lightnovel.data.translation.TranslationClient
import com.kacyraho.lightnovel.data.translation.TranslationException
import com.kacyraho.lightnovel.data.translation.translationKeyScope
import com.kacyraho.lightnovel.data.translation.translationRequiresKey
import java.io.IOException
import java.time.Instant
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

class BranchKnowledgeExtractor(
    private val worldlineStore: WorldlineStore,
    private val knowledgeStore: KnowledgeStore,
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

    suspend fun extract(
        book: BookEntity,
        worldline: WorldlineFile,
        chapterIndex: Int,
    ): Result<BranchKnowledgeFile> {
        val chapter = worldline.chapters.firstOrNull { it.index == chapterIndex }
            ?: return Result.failure(IllegalStateException("分支章节不存在"))
        val current = worldlineStore.loadKnowledge(book.storageDir, worldline.id)
            ?: BranchKnowledgeFile(worldlineId = worldline.id)
        if (current.extractedChapters.contains(chapterIndex)) return Result.success(current)
        val canon = knowledgeStore.load(book.storageDir, book.id, book.title)
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) {
            return Result.failure(IllegalStateException("未配置翻译 API Key"))
        }
        val client = clientFactory(settings.deepSeekBaseUrl, key)
        val reply = try {
            completeWithRetry(
                client = client,
                model = settings.deepSeekModel,
                messages = listOf(
                    ChatMessage("system", SYSTEM_PROMPT),
                    ChatMessage(
                        "user",
                        userPrompt(
                            text = chapter.text,
                            entities = canon.entities + current.entities,
                        ),
                    ),
                ),
                maxTokens = 8_192,
                temperature = 0.1,
            )
        } catch (error: TranslationException) {
            return Result.failure(error)
        }
        val output = runCatching {
            json.decodeFromString(ExtractionOutput.serializer(), cleanJson(reply.content))
        }.getOrElse {
            return Result.failure(IllegalStateException("分支知识抽取无法解析：${it.message}"))
        }
        return runCatching {
            merge(book, worldline, chapter, current, canon.entities, output)
        }.fold(
            onSuccess = { Result.success(it) },
            onFailure = { Result.failure(it) },
        )
    }

    private fun merge(
        book: BookEntity,
        worldline: WorldlineFile,
        chapter: BranchChapter,
        current: BranchKnowledgeFile,
        canonEntities: List<Entity>,
        output: ExtractionOutput,
    ): BranchKnowledgeFile {
        val now = Instant.now().toString()
        val entities = current.entities.toMutableList()
        val nameToId = mutableMapOf<String, String>()
        (canonEntities + entities).forEach { entity ->
            entity.names().forEach { name -> nameToId[name] = entity.id }
        }
        var acceptedFacts = 0
        val factCandidates = output.facts.size +
            output.relations.size + output.voiceFacts.size

        for (item in output.entities) {
            val source = item.source.trim()
            if (source.isBlank()) continue
            val quote = item.sourceQuote.ifBlank { source }
            val location = FactAnchorMapper.locate(chapter.text, quote) ?: continue
            val existingIndex = entities.indexOfFirst {
                it.id == nameToId[source] || it.canonicalName == source || source in it.aliases
            }
            val id = if (existingIndex >= 0) entities[existingIndex].id
            else nameToId[source] ?: "bent-" + Hashes.sha256(source).take(16)
            val old = entities.getOrNull(existingIndex)
            val merged = (old ?: Entity(id = id, scope = "branch", branchId = worldline.id))
                .copy(
                    scope = "branch",
                    branchId = worldline.id,
                    type = item.type.ifBlank { old?.type ?: "character" },
                    canonicalName = item.canonicalName.trim()
                        .ifBlank { old?.canonicalName ?: source },
                    aliases = (old?.aliases.orEmpty() + item.aliases + source)
                        .map(String::trim).filter(String::isNotBlank).distinct(),
                    sourceLang = "zh",
                    sourceQuote = quote,
                    sourceAnchor = FactAnchor(
                        chapter = chapter.index,
                        paragraph = location.first,
                        charOffset = location.second,
                        quoteHash = FactAnchorMapper.quoteHash(quote),
                    ),
                    displayQuote = quote,
                    displayAnchor = null,
                    readerKnown = (old?.readerKnown ?: false) || item.readerKnown,
                    knownBy = (old?.knownBy.orEmpty() + item.knownBy).distinct(),
                    firstSeenChapter = old?.firstSeenChapter ?: chapter.index,
                    lastConfirmedChapter = chapter.index,
                    status = "active",
                    createdAt = old?.createdAt ?: now,
                    updatedAt = now,
                )
            if (existingIndex >= 0) entities[existingIndex] = merged else entities += merged
            merged.names().forEach { nameToId[it] = merged.id }
        }

        fun resolveNames(names: List<String>): List<String> =
            names.mapNotNull { raw ->
                val value = raw.trim()
                nameToId[value] ?: value.takeIf { id -> entities.any { it.id == id } }
            }.distinct()

        val facts = current.facts.toMutableList()
        for (item in output.facts) {
            val entityId = nameToId[item.entity.trim()] ?: continue
            val text = item.text.trim()
            if (text.isBlank()) continue
            val location = FactAnchorMapper.locate(chapter.text, item.sourceQuote) ?: continue
            val kind = item.kind.takeIf {
                it in setOf("persona", "direction", "reveal_constraint", "reveal_content", "event")
            } ?: "persona"
            val id = "bfact-" + Hashes.sha256(
                "${worldline.id}|${chapter.index}|$kind|$entityId|${item.key}|$text",
            ).take(16)
            val old = facts.firstOrNull { it.id == id }
            val merged = Fact(
                id = id,
                scope = "branch",
                branchId = worldline.id,
                entityId = entityId,
                kind = kind,
                factKey = item.key.ifBlank { kind },
                text = text,
                sourceLang = "zh",
                sourceQuote = item.sourceQuote,
                sourceAnchor = FactAnchor(
                    chapter = chapter.index,
                    paragraph = location.first,
                    charOffset = location.second,
                    quoteHash = FactAnchorMapper.quoteHash(item.sourceQuote),
                ),
                displayQuote = item.sourceQuote,
                displayAnchor = null,
                readerKnown = item.readerKnown,
                knownBy = resolveNames(item.knownBy),
                firstSeenChapter = chapter.index,
                lastConfirmedChapter = chapter.index,
                validFromChapter = chapter.index,
                confidence = item.confidence.coerceIn(0.0, 1.0),
                status = "active",
                createdAt = old?.createdAt ?: now,
                updatedAt = now,
            )
            if (old != null) facts[facts.indexOfFirst { it.id == id }] = merged else facts += merged
            acceptedFacts++
        }

        val relations = current.relations.toMutableList()
        for (item in output.relations) {
            val from = nameToId[item.from.trim()] ?: continue
            val to = nameToId[item.to.trim()] ?: continue
            val location = FactAnchorMapper.locate(chapter.text, item.sourceQuote) ?: continue
            val id = "brel-" + Hashes.sha256(
                "${worldline.id}|${chapter.index}|$from|$to|${item.type}|${item.label}",
            ).take(16)
            val old = relations.firstOrNull { it.id == id }
            val merged = Relation(
                id = id,
                scope = "branch",
                branchId = worldline.id,
                fromEntityId = from,
                toEntityId = to,
                type = item.type.ifBlank { "other" },
                label = item.label,
                sourceLang = "zh",
                sourceQuote = item.sourceQuote,
                sourceAnchor = FactAnchor(
                    chapter = chapter.index,
                    paragraph = location.first,
                    charOffset = location.second,
                    quoteHash = FactAnchorMapper.quoteHash(item.sourceQuote),
                ),
                displayQuote = item.sourceQuote,
                readerKnown = item.readerKnown,
                knownBy = resolveNames(item.knownBy),
                firstSeenChapter = chapter.index,
                lastConfirmedChapter = chapter.index,
                validFromChapter = chapter.index,
                confidence = item.confidence.coerceIn(0.0, 1.0),
                status = "active",
                createdAt = old?.createdAt ?: now,
                updatedAt = now,
            )
            if (old != null) relations[relations.indexOfFirst { it.id == id }] = merged
            else relations += merged
            acceptedFacts++
        }

        val voices = current.voiceFacts.toMutableList()
        for (item in output.voiceFacts) {
            val entityId = nameToId[item.entity.trim()] ?: continue
            val text = item.text.trim()
            if (text.isBlank()) continue
            val location = FactAnchorMapper.locate(chapter.text, item.sourceQuote) ?: continue
            val id = "bvoice-" + Hashes.sha256(
                "${worldline.id}|${chapter.index}|$entityId|${item.dimension}|$text",
            ).take(16)
            val old = voices.firstOrNull { it.id == id }
            val merged = VoiceFact(
                id = id,
                scope = "branch",
                branchId = worldline.id,
                entityId = entityId,
                dimension = item.dimension.ifBlank { "voice" },
                text = text,
                exampleQuote = item.exampleQuote,
                sourceLang = "zh",
                sourceQuote = item.sourceQuote,
                sourceAnchor = FactAnchor(
                    chapter = chapter.index,
                    paragraph = location.first,
                    charOffset = location.second,
                    quoteHash = FactAnchorMapper.quoteHash(item.sourceQuote),
                ),
                displayQuote = item.sourceQuote,
                readerKnown = item.readerKnown,
                knownBy = resolveNames(item.knownBy),
                firstSeenChapter = chapter.index,
                lastConfirmedChapter = chapter.index,
                confidence = item.confidence.coerceIn(0.0, 1.0),
                status = "active",
                createdAt = old?.createdAt ?: now,
                updatedAt = now,
            )
            if (old != null) voices[voices.indexOfFirst { it.id == id }] = merged
            else voices += merged
            acceptedFacts++
        }

        if (factCandidates > 0 && acceptedFacts == 0) {
            error("分支知识条目都未通过出处校验")
        }
        val chapters = (current.extractedChapters + chapter.index).distinct().sorted()
        return worldlineStore.saveKnowledge(
            book.storageDir,
            current.copy(
                entities = entities,
                facts = facts,
                relations = relations,
                voiceFacts = voices,
                secrets = current.secrets,
                extractedChapters = chapters,
            ),
        )
    }

    private suspend fun completeWithRetry(
        client: TranslationClient,
        model: String,
        messages: List<ChatMessage>,
        maxTokens: Int,
        temperature: Double,
    ): ChatResult {
        var lastError: TranslationException? = null
        repeat(3) { attempt ->
            try {
                return client.complete(
                    messages = messages,
                    model = model,
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

    private fun userPrompt(text: String, entities: List<Entity>): String = buildString {
        appendLine("【已有实体】")
        entities.take(60).forEach {
            appendLine("${it.canonicalName} / ${it.aliases.joinToString("、")}")
        }
        appendLine("【分支章节正文】")
        appendLine(text.take(12_000))
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
    )

    @Serializable
    private data class ExtractionEntity(
        val source: String = "",
        val aliases: List<String> = emptyList(),
        val type: String = "character",
        val canonicalName: String = "",
        val sourceQuote: String = "",
        val readerKnown: Boolean = true,
        val knownBy: List<String> = emptyList(),
    )

    @Serializable
    private data class ExtractionFact(
        val entity: String = "",
        val key: String = "",
        val kind: String = "persona",
        val text: String = "",
        val sourceQuote: String = "",
        val readerKnown: Boolean = true,
        val knownBy: List<String> = emptyList(),
        val confidence: Double = 0.7,
    )

    @Serializable
    private data class ExtractionRelation(
        val from: String = "",
        val to: String = "",
        val type: String = "other",
        val label: String = "",
        val sourceQuote: String = "",
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
        val readerKnown: Boolean = true,
        val knownBy: List<String> = emptyList(),
        val confidence: Double = 0.7,
    )

    private companion object {
        const val SYSTEM_PROMPT =
            "你从分支章节正文中抽取可查询的设定事实。" +
                "只抽取本章明确出现的信息，不推测后文。" +
                "每条事实必须附 sourceQuote；sourceQuote 必须是本章正文子串。" +
                "区分 readerKnown 与 knownBy；knownBy 用角色名。" +
                "只输出 JSON：{entities:[],facts:[],relations:[],voiceFacts:[]}。"
    }
}
