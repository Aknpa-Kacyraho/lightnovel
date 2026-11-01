package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.settings.ApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LibraryDao
import com.kacyraho.lightnovel.data.source.SourceBook
import com.kacyraho.lightnovel.data.source.SourceDetail
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

@Serializable
data class BookMetadata(
    val titleZh: String = "",
    val synopsisZh: String = "",
    val tagsZh: List<String> = emptyList(),
    val chapterTitlesZh: List<String> = emptyList(),
)

@Serializable
private data class CachedBookMetadata(
    val sourceHash: String = "",
    val promptVersion: String = "",
    val metadata: BookMetadata = BookMetadata(),
)

@Serializable
private data class MetaInput(
    val title: String,
    val synopsis: String,
    val tags: List<String>,
    val chapters: List<String>,
)

@Serializable
private data class MetaOutput(
    val titleZh: String = "",
    val synopsisZh: String = "",
    val tagsZh: List<String> = emptyList(),
    val chaptersZh: List<String> = emptyList(),
)

@Serializable
private data class CardInput(
    val key: String,
    val title: String,
    val synopsis: String = "",
    val tags: List<String> = emptyList(),
)

@Serializable
private data class CardOutput(
    val key: String = "",
    val titleZh: String = "",
    val synopsisZh: String = "",
    val tagsZh: List<String> = emptyList(),
)

@Serializable
private data class CardBatchOutput(
    val items: List<CardOutput> = emptyList(),
)

@Serializable
private data class CardCacheFile(
    val items: Map<String, BookMetadata> = emptyMap(),
)

class MetadataTranslationService(
    private val contentStore: ContentStore,
    private val dao: LibraryDao,
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
    private val store = MetadataStore(contentStore, json)
    private val cardCache = ConcurrentHashMap<String, BookMetadata>().apply {
        putAll(store.loadCards().filterKeys { it.contains("/") })
    }

    suspend fun translateSummary(
        book: BookEntity,
        detail: SourceDetail?,
    ): BookMetadata? {
        val title = detail?.book?.title?.ifBlank { book.title } ?: book.title
        val synopsis = detail?.synopsis.orEmpty().ifBlank { detail?.book?.synopsis.orEmpty() }
        val tags = detail?.book?.tags.orEmpty()
        val sourceHash = Hashes.sha256(
            listOf(title, synopsis, tags.joinToString("|")).joinToString("\n"),
        )
        val cached = store.loadBook(book.id)
        if (cached != null && cached.metadata.titleZh.isNotBlank() &&
            cached.metadata.synopsisZh.isNotBlank()
        ) {
            return cached.metadata
        }
        if (cached?.sourceHash == sourceHash && cached.metadata.titleZh.isNotBlank()) {
            return cached.metadata
        }
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) return null
        val client = clientFactory(settings.deepSeekBaseUrl, key)
        val result = runCatching {
            client.complete(
                messages = listOf(
                    ChatMessage("system", SYSTEM_PROMPT),
                    ChatMessage(
                        "user",
                        json.encodeToString(
                            MetaInput.serializer(),
                            MetaInput(title, synopsis, tags, emptyList()),
                        ),
                    ),
                ),
                model = settings.deepSeekModel,
                maxTokens = 4_096,
                temperature = 0.2,
            )
        }.getOrNull() ?: return null
        val output = runCatching {
            json.decodeFromString(MetaOutput.serializer(), cleanJson(result.content))
        }.getOrNull() ?: return null
        val metadata = BookMetadata(
            titleZh = book.titleZh?.takeIf { it.isNotBlank() } ?: output.titleZh.trim(),
            synopsisZh = output.synopsisZh.trim(),
            tagsZh = output.tagsZh.map(String::trim).filter(String::isNotBlank),
            chapterTitlesZh = emptyList(),
        )
        if (metadata.titleZh.isBlank() && metadata.synopsisZh.isBlank()) return null
        store.saveBook(
            book.id,
            CachedBookMetadata(sourceHash, PROMPT_VERSION, metadata),
        )
        dao.updateBookTitle(book.id, metadata.titleZh.ifBlank { book.titleZh }.orEmpty())
        return metadata
    }

    suspend fun translateChapterTitles(
        book: BookEntity,
        chapters: List<ChapterEntity>,
    ): List<String> {
        if (chapters.isEmpty()) return emptyList()
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) return emptyList()
        val client = clientFactory(settings.deepSeekBaseUrl, key)
        val input = chapters.mapIndexed { index, chapter ->
            CardInput(key = index.toString(), title = chapter.title.orEmpty())
        }
        val result = runCatching {
            client.complete(
                messages = listOf(
                    ChatMessage("system", TITLE_PROMPT),
                    ChatMessage(
                        "user",
                        json.encodeToString(
                            kotlinx.serialization.builtins.ListSerializer(CardInput.serializer()),
                            input,
                        ),
                    ),
                ),
                model = settings.deepSeekModel,
                maxTokens = 4_096,
                temperature = 0.2,
            )
        }.getOrNull() ?: return emptyList()
        val outputs = parseCards(result.content)
        val keys = chapters.indices.map { it.toString() }
        val byKey = alignCards(outputs, keys)
        val titles = keys.map { key ->
            byKey[key]?.titleZh?.trim().orEmpty()
        }
        if (titles.any(String::isNotBlank)) {
            chapters.forEachIndexed { index, chapter ->
                titles.getOrNull(index)?.takeIf(String::isNotBlank)?.let { title ->
                    dao.updateChapterTitle(book.id, chapter.idx, title)
                }
            }
        }
        return titles
    }

    suspend fun translateBook(
        book: BookEntity,
        detail: SourceDetail?,
        chapters: List<ChapterEntity>,
    ): BookMetadata? {
        val title = detail?.book?.title?.ifBlank { book.title } ?: book.title
        val synopsis = detail?.synopsis.orEmpty().ifBlank { detail?.book?.synopsis.orEmpty() }
        val tags = detail?.book?.tags.orEmpty()
        val chapterTitles = chapters.map { it.title.orEmpty() }
        val sourceHash = Hashes.sha256(
            listOf(title, synopsis, tags.joinToString("|"), chapterTitles.joinToString("|"))
                .joinToString("\n"),
        )
        val cached = store.loadBook(book.id)
        if (cached?.sourceHash == sourceHash && cached.metadata.titleZh.isNotBlank()) {
            return cached.metadata
        }
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) return null
        val client = clientFactory(settings.deepSeekBaseUrl, key)
        val input = MetaInput(
            title = title,
            synopsis = synopsis,
            tags = tags,
            chapters = chapterTitles,
        )
        val result = runCatching {
            client.complete(
                messages = listOf(
                    ChatMessage("system", SYSTEM_PROMPT),
                    ChatMessage("user", json.encodeToString(MetaInput.serializer(), input)),
                ),
                model = settings.deepSeekModel,
                maxTokens = 8_192,
                temperature = 0.2,
            )
        }.getOrNull() ?: return null
        val output = runCatching {
            json.decodeFromString(MetaOutput.serializer(), cleanJson(result.content))
        }.getOrNull() ?: return null
        val metadata = BookMetadata(
            titleZh = book.titleZh?.takeIf { it.isNotBlank() }
                ?: output.titleZh.trim(),
            synopsisZh = output.synopsisZh.trim(),
            tagsZh = output.tagsZh.map(String::trim).filter(String::isNotBlank),
            chapterTitlesZh = output.chaptersZh.map(String::trim),
        )
        if (metadata.titleZh.isBlank() && metadata.synopsisZh.isBlank()) return null
        store.saveBook(book.id, CachedBookMetadata(sourceHash, PROMPT_VERSION, metadata))
        dao.updateBookTitle(book.id, metadata.titleZh.ifBlank { book.titleZh }.orEmpty())
        if (chapters.isNotEmpty() && metadata.chapterTitlesZh.isNotEmpty()) {
            chapters.forEachIndexed { index, chapter ->
                metadata.chapterTitlesZh.getOrNull(index)?.takeIf(String::isNotBlank)?.let { title ->
                    dao.updateChapterTitle(book.id, chapter.idx, title)
                }
            }
        }
        return metadata
    }

    suspend fun translateCards(items: List<SourceBook>): List<SourceBook> {
        if (items.isEmpty()) return items
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) {
            return items.map { item ->
                val cached = cardCache[item.cacheKey()] ?: return@map item
                item.copy(
                    titleZh = cached.titleZh,
                    synopsisZh = cached.synopsisZh,
                    tagsZh = cached.tagsZh,
                )
            }
        }
        val missing = items.filter { cardCache[it.cacheKey()] == null }.take(24)
        if (missing.isNotEmpty()) {
            val client = clientFactory(settings.deepSeekBaseUrl, key)
            coroutineScope {
                missing.chunked(8).map { batch ->
                    async {
                        val input = batch.map {
                            CardInput(
                                key = it.cacheKey(),
                                title = it.title,
                                synopsis = it.synopsis,
                                tags = it.tags,
                            )
                        }
                        val result = runCatching {
                            client.complete(
                                messages = listOf(
                                    ChatMessage("system", CARD_PROMPT),
                                    ChatMessage(
                                        "user",
                                        json.encodeToString(
                                            kotlinx.serialization.builtins.ListSerializer(CardInput.serializer()),
                                            input,
                                        ),
                                    ),
                                ),
                                model = settings.deepSeekModel,
                                maxTokens = 8_192,
                                temperature = 0.2,
                            )
                        }.getOrNull() ?: return@async
                        val outputs = parseCards(result.content)
                        val byKey = alignCards(outputs, batch.map { it.cacheKey() })
                        batch.forEach { item ->
                            val output = byKey[item.cacheKey()] ?: return@forEach
                            if (output.titleZh.isNotBlank()) {
                                cardCache[item.cacheKey()] = BookMetadata(
                                    titleZh = output.titleZh,
                                    synopsisZh = output.synopsisZh,
                                    tagsZh = output.tagsZh,
                                )
                            }
                        }
                    }
                }.awaitAll()
            }
            store.saveCards(cardCache)
        }
        return items.map { item ->
            val cached = cardCache[item.cacheKey()] ?: return@map item
            item.copy(
                titleZh = cached.titleZh,
                synopsisZh = cached.synopsisZh,
                tagsZh = cached.tagsZh,
            )
        }
    }

    suspend fun translateTitles(books: List<BookEntity>): Map<String, String> {
        if (books.isEmpty()) return emptyMap()
        val settings = settingsStore.settings.first()
        val key = apiKeyStore.load(settings.translationKeyScope())?.trim().orEmpty()
        if (key.isBlank() && settings.translationRequiresKey()) return emptyMap()
        val client = clientFactory(settings.deepSeekBaseUrl, key)
        val input = books.map {
            CardInput(key = it.id, title = it.title)
        }
        val result = runCatching {
            client.complete(
                messages = listOf(
                    ChatMessage("system", TITLE_PROMPT),
                    ChatMessage(
                        "user",
                        json.encodeToString(
                            kotlinx.serialization.builtins.ListSerializer(CardInput.serializer()),
                            input,
                        ),
                    ),
                ),
                model = settings.deepSeekModel,
                maxTokens = 4_096,
                temperature = 0.2,
            )
        }.getOrNull() ?: return emptyMap()
        val outputs = parseCards(result.content)
        val byKey = alignCards(outputs, books.map { it.id })
        val translated = books.mapNotNull { book ->
            byKey[book.id]
                ?.titleZh
                ?.trim()
                ?.takeIf(String::isNotBlank)
                ?.let { book.id to it }
        }.toMap()
        if (translated.isNotEmpty()) {
            translated.forEach { (bookId, title) ->
                dao.updateBookTitle(bookId, title)
            }
        }
        return translated
    }

    private fun SourceBook.cacheKey(): String = "$provider/$id"

    private fun alignCards(
        outputs: List<CardOutput>,
        keys: List<String>,
    ): Map<String, CardOutput> {
        if (outputs.isEmpty()) return emptyMap()
        val keyed = outputs.filter { it.key.isNotBlank() }.associateBy { it.key }
        if (keyed.keys.containsAll(keys)) return keyed
        if (outputs.all { it.key.isBlank() } && outputs.size == keys.size) {
            return keys.mapIndexedNotNull { index, key -> outputs.getOrNull(index)?.let { key to it } }
                .toMap()
        }
        return emptyMap()
    }

    private fun parseCards(value: String): List<CardOutput> {
        val clean = cleanJson(value)
        runCatching {
            json.decodeFromString(
                kotlinx.serialization.builtins.ListSerializer(CardOutput.serializer()),
                clean,
            )
        }.getOrNull()?.let { return it }
        runCatching {
            json.decodeFromString(CardBatchOutput.serializer(), clean).items
        }.getOrNull()?.let { return it }
        return runCatching {
            json.parseToJsonElement(clean).jsonObject.entries.mapNotNull { (key, element) ->
                val obj = element.jsonObject
                CardOutput(
                    key = key,
                    titleZh = obj["titleZh"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                    synopsisZh = obj["synopsisZh"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                    tagsZh = (obj["tagsZh"] as? kotlinx.serialization.json.JsonArray)
                        ?.mapNotNull { it.jsonPrimitive.contentOrNull }
                        .orEmpty(),
                )
            }
        }.getOrDefault(emptyList())
    }

    private fun cleanJson(value: String): String =
        value.trim()
            .removePrefix("```json")
            .removePrefix("```")
            .removeSuffix("```")
            .trim()

    private companion object {
        const val PROMPT_VERSION = "android-meta-v1"
        const val SYSTEM_PROMPT =
            "你是日文轻小说元数据翻译器。把输入的 title、synopsis、tags、chapters 翻译成简体中文。" +
                "书名和章节名要自然、简洁；简介要忠实，不添加原文没有的信息；标签翻译成中文常用标签。" +
                "保留人名、作品名中的专有名词一致性。只输出合法 JSON，不要 Markdown、解释或原文。\n" +
                "输出格式：{\"titleZh\":\"\",\"synopsisZh\":\"\",\"tagsZh\":[],\"chaptersZh\":[]}，" +
                "chaptersZh 的顺序和数量必须与输入 chapters 完全一致。"
        const val CARD_PROMPT =
            "你是日文轻小说元数据翻译器。输入是 JSON 数组，每项有 key/title/synopsis/tags。" +
                "逐项翻译成简体中文，输出同样长度的 JSON 数组，字段为 key/titleZh/synopsisZh/tagsZh。" +
                "不要合并、遗漏或新增 key；只输出 JSON。"
        const val TITLE_PROMPT =
            "你是日文轻小说书名翻译器。输入是 JSON 数组，每项有 key/title。" +
                "逐项翻译成简体中文，输出同样长度的 JSON 数组，字段为 key/titleZh。" +
                "不要遗漏或新增 key；只输出 JSON。"
    }
}

private class MetadataStore(
    private val contentStore: ContentStore,
    private val json: Json,
) {
    fun loadBook(bookId: String): CachedBookMetadata? {
        val file = file(bookId)
        if (!Files.isRegularFile(file)) return null
        return runCatching {
            json.decodeFromString(
                CachedBookMetadata.serializer(),
                Files.readAllBytes(file).toString(Charsets.UTF_8),
            )
        }.getOrNull()
    }

    fun saveBook(bookId: String, value: CachedBookMetadata) {
        val file = file(bookId)
        Files.createDirectories(file.parent)
        val tmp = file.resolveSibling("${file.fileName}.tmp-${System.nanoTime()}")
        try {
            Files.write(
                tmp,
                json.encodeToString(CachedBookMetadata.serializer(), value)
                    .toByteArray(Charsets.UTF_8),
            )
            try {
                Files.move(
                    tmp,
                    file,
                    StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.ATOMIC_MOVE,
                )
            } catch (_: AtomicMoveNotSupportedException) {
                Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING)
            }
        } finally {
            Files.deleteIfExists(tmp)
        }
    }

    fun loadCards(): Map<String, BookMetadata> {
        val file = cardFile()
        if (!Files.isRegularFile(file)) return emptyMap()
        return runCatching {
            json.decodeFromString(
                CardCacheFile.serializer(),
                Files.readAllBytes(file).toString(Charsets.UTF_8),
            ).items
        }.getOrDefault(emptyMap())
    }

    fun saveCards(items: Map<String, BookMetadata>) {
        val file = cardFile()
        Files.createDirectories(file.parent)
        val tmp = file.resolveSibling("${file.fileName}.tmp-${System.nanoTime()}")
        try {
            Files.write(
                tmp,
                json.encodeToString(
                    CardCacheFile.serializer(),
                    CardCacheFile(items),
                ).toByteArray(Charsets.UTF_8),
            )
            try {
                Files.move(
                    tmp,
                    file,
                    StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.ATOMIC_MOVE,
                )
            } catch (_: AtomicMoveNotSupportedException) {
                Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING)
            }
        } finally {
            Files.deleteIfExists(tmp)
        }
    }

    private fun cardFile(): Path =
        contentStore.paths("_metadata").cacheDir()
            .resolve("cards.json")

    private fun file(bookId: String): Path =
        contentStore.paths("_metadata").cacheDir()
            .resolve("books")
            .resolve("$bookId.json")
}
