package com.kacyraho.lightnovel.data.source

import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.BookTags
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LibraryDao
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import java.time.Instant
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

class DirectLibraryService(
    sources: List<WebSource>,
    private val dao: LibraryDao,
    private val contentStore: ContentStore,
) : ChapterFetcher {
    val sources: List<WebSource> = sources
    private val byId = sources.associateBy { it.id }
    private val details = ConcurrentHashMap<String, SourceDetail>()
    private val chapterMutex = Mutex()

    suspend fun shelfKeys(): Set<String> = dao.onlineKeys().toSet()

    suspend fun addToShelf(book: SourceBook): BookEntity {
        val source = byId[book.provider] ?: error("不支持的书源：${book.provider}")
        val detail = source.detail(book.id)
        details[key(book.provider, book.id)] = detail
        val chapters = detail.chapters
        require(chapters.isNotEmpty()) { "这本书没有可阅读章节" }

        val bookId = "${book.provider}-${book.id}".replace(Regex("[^A-Za-z0-9._-]"), "_")
        val now = Instant.now().toString()
        val old = dao.book(bookId)
        if (old?.local == true) {
            return old
        }
        val oldChapters = dao.chapters(bookId).associateBy { it.idx }
        val entity = BookEntity(
            id = bookId,
            storageDir = bookId,
            slug = bookId,
            source = book.provider,
            sourceId = book.id,
            title = detail.book.title.ifBlank { book.title },
            titleZh = null,
            author = detail.book.author.ifBlank { book.author }.takeIf { it.isNotBlank() },
            tagsJson = BookTags.encode(detail.book.tags),
            genre = null,
            episodes = chapters.size,
            local = false,
            createdAt = old?.createdAt ?: now,
            legacyJson = null,
        )
        val rows = chapters.mapIndexed { index, chapter ->
            val idx = index + 1
            oldChapters[idx]?.copy(
                title = chapter.title,
                updatedAt = now,
            ) ?: ChapterEntity(
                bookId = bookId,
                idx = idx,
                title = chapter.title,
                titleZh = null,
                rawPath = null,
                zhPath = null,
                status = "online",
                tokenIn = 0,
                tokenOut = 0,
                model = null,
                updatedAt = now,
            )
        }
        dao.upsertBooks(listOf(entity))
        if (dao.readState(bookId) == null) {
            dao.upsertReadStates(
                listOf(
                    ReadStateEntity(
                        bookId = bookId,
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
        dao.upsertChapters(rows)
        return entity
    }

    suspend fun detail(book: BookEntity): SourceDetail {
        if (book.local) error("本地书没有在线详情")
        val source = byId[book.source] ?: error("未知书源：${book.source}")
        return details[key(book.source, book.sourceId)]
            ?: source.detail(book.sourceId).also { detail ->
                details[key(book.source, book.sourceId)] = detail
                val tags = BookTags.encode(detail.book.tags)
                if (tags != null && tags != book.tagsJson) {
                    dao.upsertBooks(
                        listOf(
                            book.copy(
                                tagsJson = tags,
                                episodes = detail.book.episodes.takeIf { it > 0 }
                                    ?: book.episodes,
                            ),
                        ),
                    )
                }
            }
    }

    override suspend fun ensureChapter(book: BookEntity, idx: Int): Boolean {
        if (book.local) return false
        if (contentStore.readRaw(book.storageDir, idx) != null ||
            contentStore.readZh(book.storageDir, idx) != null
        ) {
            return true
        }
        chapterMutex.withLock {
            if (contentStore.readRaw(book.storageDir, idx) != null ||
                contentStore.readZh(book.storageDir, idx) != null
            ) {
                return@withLock true
            }
            val source = byId[book.source] ?: error("未知书源：${book.source}")
            val detail = details[key(book.source, book.sourceId)]
                ?: source.detail(book.sourceId).also {
                    details[key(book.source, book.sourceId)] = it
                }
            val chapter = detail.chapters.getOrNull(idx - 1)
                ?: error("目录里找不到第 $idx 话")
            val text = source.chapter(book.sourceId, chapter.id)
                .replace("\r\n", "\n")
                .trim()
            if (text.isBlank()) error("这一话没有正文")
            contentStore.writeRawAtomic(book.storageDir, idx, text)
            dao.updateChapterTranslation(
                bookId = book.id,
                idx = idx,
                status = "raw",
                model = "source-${book.source}",
                tokenIn = 0,
                tokenOut = 0,
                updatedAt = Instant.now().toString(),
            )
        }
        return true
    }

    suspend fun downloadAll(book: BookEntity, onProgress: (Int, Int) -> Unit): Int {
        val chapters = dao.chapters(book.id)
        var done = 0
        for (chapter in chapters) {
            if (ensureChapter(book, chapter.idx)) done++
            onProgress(done, chapters.size)
        }
        return done
    }

    private fun key(provider: String, id: String): String = "$provider/$id"
}
