package com.kacyraho.lightnovel.data.story

import com.kacyraho.lightnovel.core.settings.ApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.glossary.GlossaryEntry
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.translation.ChatMessage
import com.kacyraho.lightnovel.data.translation.DeepSeekClient
import com.kacyraho.lightnovel.data.translation.Hashes
import com.kacyraho.lightnovel.data.translation.TranslationClient
import com.kacyraho.lightnovel.data.translation.TranslationException
import com.kacyraho.lightnovel.data.translation.TranslationValidators
import com.kacyraho.lightnovel.data.translation.translationKeyScope
import com.kacyraho.lightnovel.data.translation.translationRequiresKey
import java.time.Instant
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable
data class NameSuggestion(
    val source: String = "",
    val variants: List<String> = emptyList(),
    val suggested: String = "",
    val evidence: String = "",
)

@Serializable
private data class CharacterExtractionOutput(
    val characters: List<CharacterExtraction> = emptyList(),
)

@Serializable
private data class CharacterExtraction(
    val source: String = "",
    val target: String = "",
    val aliases: List<String> = emptyList(),
    val description: String = "",
    val voice: String = "",
    val address: String = "",
    val lexicon: String = "",
    val syntax: String = "",
    val notes: String = "",
)

@Serializable
private data class NameScanOutput(
    val items: List<NameSuggestion> = emptyList(),
)

class StoryMemoryService(
    private val contentStore: ContentStore,
    private val storyStore: StoryMemoryStore,
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

    suspend fun generateSummary(book: BookEntity, chapterIndex: Int, force: Boolean = false): String? {
        val raw = contentStore.readRaw(book.storageDir, chapterIndex) ?: return null
        val zh = contentStore.readZh(book.storageDir, chapterIndex) ?: return null
        if (raw.isBlank() || zh.isBlank()) return null
        val memory = storyStore.load(book.storageDir, book.id, book.title)
        val sourceHash = Hashes.sha256(raw)
        val existing = memory.summaries[chapterIndex]
        if (!force && existing != null && existing.sourceHash == sourceHash &&
            existing.text.isNotBlank()
        ) {
            return existing.text
        }
        val modelClient = client() ?: return null
        val reply = runCatching {
            modelClient.client.complete(
                messages = listOf(
                    ChatMessage("system", SUMMARY_SYSTEM),
                    ChatMessage(
                        "user",
                        "第${chapterIndex}话原文：\n${raw.take(7000)}\n\n" +
                            "第${chapterIndex}话译文：\n${zh.take(7000)}",
                    ),
                ),
                model = modelClient.model,
                maxTokens = 1_024,
                temperature = 0.2,
            )
        }.getOrNull() ?: return null
        val summary = reply.content.trim()
            .removePrefix("```").removeSuffix("```").trim()
        if (summary.isBlank() || summary.length > 600 ||
            !TranslationValidators.detectChinese(summary)
        ) {
            return null
        }
        val updated = memory.copy(
            summaries = memory.summaries + (
                chapterIndex to ChapterSummary(
                    index = chapterIndex,
                    text = summary,
                    sourceHash = sourceHash,
                    updatedAt = Instant.now().toString(),
                )
                ),
        )
        storyStore.save(book.storageDir, updated)
        return summary
    }

    suspend fun extractCharacters(
        book: BookEntity,
        chapters: List<ChapterEntity>,
        maxChapters: Int = 8,
    ): List<CharacterCard> {
        val samples = chapters.take(maxChapters).mapNotNull { chapter ->
            val raw = contentStore.readRaw(book.storageDir, chapter.idx) ?: return@mapNotNull null
            val zh = contentStore.readZh(book.storageDir, chapter.idx).orEmpty()
            "第${chapter.idx}话原文：\n${raw.take(2500)}\n第${chapter.idx}话译文：\n${zh.take(2500)}"
        }
        if (samples.isEmpty()) return emptyList()
        val modelClient = client() ?: return emptyList()
        val sourceText = samples.joinToString("\n\n").take(14_000)
        val reply = runCatching {
            modelClient.client.complete(
                messages = listOf(
                    ChatMessage("system", CHARACTER_SYSTEM),
                    ChatMessage("user", sourceText),
                ),
                model = modelClient.model,
                maxTokens = 2_048,
                temperature = 0.2,
            )
        }.getOrNull() ?: return emptyList()
        val output = runCatching {
            json.decodeFromString(
                CharacterExtractionOutput.serializer(),
                cleanJson(reply.content),
            )
        }.getOrNull() ?: return emptyList()
        val memory = storyStore.load(book.storageDir, book.id, book.title)
        val combinedRaw = samples.joinToString("\n")
        val cards = memory.characters.toMutableList()
        val glossary = memory.glossary.toMutableList()
        val touched = mutableListOf<CharacterCard>()
        for (item in output.characters) {
            val source = item.source.trim()
            val target = item.target.trim()
            if (source.isBlank() || target.isBlank() || source !in combinedRaw) continue
            val existingIndex = cards.indexOfFirst { card ->
                card.source == source || source in card.aliases || card.target == target
            }
            val merged = if (existingIndex >= 0) {
                val old = cards[existingIndex]
                val auto = old.auto
                old.copy(
                    target = if (auto || old.target.isBlank()) target else old.target,
                    aliases = (old.aliases + item.aliases).map(String::trim)
                        .filter(String::isNotBlank)
                        .distinct(),
                    description = mergeText(old.description, item.description, auto),
                    voice = mergeText(old.voice, item.voice, auto),
                    address = mergeText(old.address, item.address, auto),
                    lexicon = mergeText(old.lexicon, item.lexicon, auto),
                    syntax = mergeText(old.syntax, item.syntax, auto),
                    notes = mergeText(old.notes, item.notes, auto),
                    auto = auto,
                )
            } else {
                CharacterCard(
                    id = source,
                    source = source,
                    target = target,
                    aliases = item.aliases.map(String::trim)
                        .filter(String::isNotBlank)
                        .distinct(),
                    description = item.description.trim(),
                    voice = item.voice.trim(),
                    address = item.address.trim(),
                    lexicon = item.lexicon.trim(),
                    syntax = item.syntax.trim(),
                    notes = item.notes.trim(),
                    auto = true,
                )
            }
            if (existingIndex >= 0) cards[existingIndex] = merged else cards += merged
            touched += merged
            val glossaryIndex = glossary.indexOfFirst { it.source == source }
            if (glossaryIndex < 0) {
                glossary += GlossaryEntry(id = source, source = source, target = merged.target)
            } else if (glossary[glossaryIndex].target.isBlank()) {
                glossary[glossaryIndex] = glossary[glossaryIndex].copy(target = merged.target)
            }
        }
        if (touched.isEmpty()) return emptyList()
        storyStore.save(
            book.storageDir,
            memory.copy(characters = cards, glossary = glossary),
        )
        return touched
    }

    suspend fun scanNames(
        book: BookEntity,
        chapters: List<ChapterEntity>,
        maxChapters: Int = 20,
    ): List<NameSuggestion> {
        val samples = chapters.take(maxChapters).mapNotNull { chapter ->
            val raw = contentStore.readRaw(book.storageDir, chapter.idx) ?: return@mapNotNull null
            val zh = contentStore.readZh(book.storageDir, chapter.idx) ?: return@mapNotNull null
            "第${chapter.idx}话原文：\n${raw.take(1800)}\n第${chapter.idx}话译文：\n${zh.take(1800)}"
        }
        if (samples.isEmpty()) return emptyList()
        val modelClient = client() ?: return emptyList()
        val reply = runCatching {
            modelClient.client.complete(
                messages = listOf(
                    ChatMessage("system", NAME_SCAN_SYSTEM),
                    ChatMessage("user", samples.joinToString("\n\n").take(16_000)),
                ),
                model = modelClient.model,
                maxTokens = 2_048,
                temperature = 0.1,
            )
        }.getOrNull() ?: return emptyList()
        val output = runCatching {
            json.decodeFromString(
                NameScanOutput.serializer(),
                cleanJson(reply.content),
            )
        }.getOrNull() ?: return emptyList()
        return output.items.filter {
            it.source.isNotBlank() &&
                it.suggested.isNotBlank() &&
                (it.variants.size >= 2 || it.variants.any { variant -> variant != it.suggested })
        }.take(20)
    }

    fun applySuggestions(book: BookEntity, suggestions: List<NameSuggestion>): StoryMemory {
        val memory = storyStore.load(book.storageDir, book.id, book.title)
        val glossary = memory.glossary.toMutableList()
        val characters = memory.characters.toMutableList()
        for (suggestion in suggestions) {
            val source = suggestion.source.trim()
            val target = suggestion.suggested.trim()
            if (source.isBlank() || target.isBlank()) continue
            val index = glossary.indexOfFirst { it.source == source }
            if (index >= 0) {
                glossary[index] = glossary[index].copy(target = target)
            } else {
                glossary += GlossaryEntry(id = source, source = source, target = target)
            }
            val characterIndex = characters.indexOfFirst { card ->
                card.source == source || source in card.aliases
            }
            if (characterIndex >= 0) {
                characters[characterIndex] = characters[characterIndex].copy(target = target)
            }
        }
        return storyStore.save(
            book.storageDir,
            memory.copy(glossary = glossary, characters = characters),
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

    private fun mergeText(old: String, new: String, auto: Boolean): String =
        if (old.isBlank() || auto) new.trim().ifBlank { old } else old

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

    private companion object {
        const val SUMMARY_SYSTEM =
            "你是轻小说剧情编辑。用简体中文写 1-3 句本章剧情梗概，保留人名和关键设定，" +
                "不剧透后文，不评价文笔，不输出标题或列表，只输出梗概正文。"

        const val CHARACTER_SYSTEM =
            "你从日文轻小说原文和现有中文译文中提取有名字的人物/重要专有名词。" +
                "只提取原文中确实出现的名字，不要编造；target 优先用现有译名，没有就给出简洁音译。" +
                "voice/address/lexicon/syntax 只写文本能支持的，不确定就留空。" +
                "只输出 JSON：{\"characters\":[{\"source\":\"日文名\",\"target\":\"中文名\"," +
                "\"aliases\":[\"别名\"],\"description\":\"身份\",\"voice\":\"语气\"," +
                "\"address\":\"称呼\",\"lexicon\":\"词汇习惯\",\"syntax\":\"句法习惯\"," +
                "\"notes\":\"注意\"}]}"

        const val NAME_SCAN_SYSTEM =
            "你是译名校对员。下面是一部轻小说的日文原文与中文译文片段。" +
                "找出同一日文人名/术语在译文中出现的不同中文写法；只报告确实出现的，" +
                "不要编造，不要把不同人物当成同一个。只输出 JSON：" +
                "{\"items\":[{\"source\":\"日文名\",\"variants\":[\"译法1\",\"译法2\"]," +
                "\"suggested\":\"推荐译法\",\"evidence\":\"短句证据\"}]}"
    }
}

