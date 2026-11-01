package com.kacyraho.lightnovel.data.online

import com.kacyraho.lightnovel.core.storage.ChapterCost
import com.kacyraho.lightnovel.core.storage.ChapterSidecar
import com.kacyraho.lightnovel.core.storage.ChapterTokens
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.BookTags
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LibraryDao
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import com.kacyraho.lightnovel.data.source.ChapterFetcher
import java.security.MessageDigest
import java.time.Instant
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

class OnlineBookService(
    private val client: NoveliaClient,
    private val dao: LibraryDao,
    private val contentStore: ContentStore,
) : ChapterFetcher {
    private val detailCache = ConcurrentHashMap<String, NoveliaDetail>()
    private val chapterMutex = Mutex()

    suspend fun addToShelf(outline: NoveliaOutline): BookEntity {
        require(outline.providerId.isNotBlank() && outline.novelId.isNotBlank()) {
            "书源返回的书籍标识为空"
        }
        val detail = client.detail(outline.providerId, outline.novelId)
        detailCache[outline.providerId + "/" + outline.novelId] = detail
        val chapters = detail.toc.filter { !it.chapterId.isNullOrBlank() }
        require(chapters.isNotEmpty()) { "这本书没有可阅读章节" }

        val id = stableId(outline.providerId, outline.novelId)
        val now = Instant.now().toString()
        val existing = dao.book(id)
        val existingChapters = dao.chapters(id).associateBy { it.idx }
        val book = BookEntity(
            id = id,
            storageDir = id,
            slug = id,
            source = outline.providerId,
            sourceId = outline.novelId,
            title = detail.titleJp.ifBlank { outline.titleJp },
            titleZh = detail.titleZh ?: outline.titleZh,
            author = detail.authorNames.takeUnless { it == "未知" },
            tagsJson = BookTags.encode((detail.attentions + detail.keywords).distinct()),
            genre = detail.type.takeIf { it.isNotBlank() },
            episodes = chapters.size,
            local = false,
            createdAt = existing?.createdAt ?: now,
            legacyJson = null,
        )
        val chapterRows = chapters.mapIndexed { index, item ->
            val idx = index + 1
            val old = existingChapters[idx]
            old?.copy(
                title = item.titleJp,
                titleZh = item.titleZh,
                updatedAt = now,
            ) ?: ChapterEntity(
                bookId = id,
                idx = idx,
                title = item.titleJp,
                titleZh = item.titleZh,
                rawPath = null,
                zhPath = null,
                status = "online",
                tokenIn = 0,
                tokenOut = 0,
                model = null,
                updatedAt = now,
            )
        }

        dao.upsertBooks(listOf(book))
        if (dao.readState(id) == null) {
            dao.upsertReadStates(
                listOf(
                    ReadStateEntity(
                        bookId = id,
                        shelf = "reading",
                        favorite = false,
                        hidden = false,
                        progressIdx = 0,
                        openedAt = null,
                        finishedAt = null,
                        updatedAt = now,
                    ),
                ),
            )
        }
        dao.upsertChapters(chapterRows)
        return book
    }

    suspend fun downloadAll(book: BookEntity, onProgress: (Int, Int) -> Unit = { _, _ -> }): Int {
        val chapters = dao.chapters(book.id)
        var done = 0
        for (chapter in chapters) {
            if (ensureChapter(book, chapter.idx)) done++
            onProgress(done, chapters.size)
        }
        return done
    }

    override suspend fun ensureChapter(book: BookEntity, chapterIndex: Int): Boolean {
        if (book.local) return false
        if (contentStore.readZh(book.storageDir, chapterIndex) != null) return true
        if (contentStore.readRaw(book.storageDir, chapterIndex) != null) return true

        chapterMutex.withLock {
            if (contentStore.readZh(book.storageDir, chapterIndex) != null) return true
            if (contentStore.readRaw(book.storageDir, chapterIndex) != null) return true

            val detail = detailCache[book.source + "/" + book.sourceId]
                ?: client.detail(book.source, book.sourceId).also {
                    detailCache[book.source + "/" + book.sourceId] = it
                }
            val item = detail.toc.filter { !it.chapterId.isNullOrBlank() }
                .getOrNull(chapterIndex - 1)
                ?: error("线上目录里找不到第 $chapterIndex 章")
            val chapterId = item.chapterId ?: error("章节没有 chapterId")
            val chapter = client.chapter(book.source, book.sourceId, chapterId)
            val raw = chapter.paragraphs
                .filter { it.isNotBlank() }
                .joinToString("\n\n")
            val translated = chapter.bestTranslation()
                ?.filter { it.isNotBlank() }
                ?.takeIf { it.isNotEmpty() }
                ?.joinToString("\n\n")
            if (raw.isBlank() && translated.isNullOrBlank()) {
                error("这一章没有正文")
            }
            val rawText = raw.ifBlank { translated.orEmpty() }
            contentStore.writeRawAtomic(book.storageDir, chapterIndex, rawText)
            if (!translated.isNullOrBlank()) {
                contentStore.writeZhAtomic(book.storageDir, chapterIndex, translated)
                val now = Instant.now().toString()
                contentStore.writeSidecar(
                    book.storageDir,
                    chapterIndex,
                    ChapterSidecar(
                        status = "complete",
                        sourceSha256 = sha256(rawText),
                        contentSha256 = sha256(translated),
                        translationConfigHash = "novelia-site-v1",
                        modelProvider = "novelia",
                        modelId = chapter.translationModel(),
                        promptVersion = "site",
                        translatedAt = now,
                        tokens = ChapterTokens(),
                        cost = ChapterCost(),
                    ),
                )
                dao.updateChapterTranslation(
                    bookId = book.id,
                    idx = chapterIndex,
                    status = "complete",
                    model = "novelia-${chapter.translationModel()}",
                    tokenIn = 0,
                    tokenOut = 0,
                    updatedAt = now,
                )
            } else {
                dao.updateChapterTranslation(
                    bookId = book.id,
                    idx = chapterIndex,
                    status = "raw",
                    model = "novelia-raw",
                    tokenIn = 0,
                    tokenOut = 0,
                    updatedAt = Instant.now().toString(),
                )
            }
        }
        return true
    }

    suspend fun refreshDetail(book: BookEntity): NoveliaDetail {
        val key = book.source + "/" + book.sourceId
        return detailCache[key]
            ?: client.detail(book.source, book.sourceId).also { detailCache[key] = it }
    }

    fun stableId(provider: String, novelId: String): String =
        "novelia-$provider-$novelId".replace(Regex("[^A-Za-z0-9._-]"), "_")

    private fun sha256(text: String): String =
        MessageDigest.getInstance("SHA-256")
            .digest(text.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
}
