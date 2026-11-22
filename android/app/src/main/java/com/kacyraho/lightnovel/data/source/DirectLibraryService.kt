package com.kacyraho.lightnovel.data.source

import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.BookTags
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LibraryDao
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import java.time.Instant
import java.util.concurrent.ConcurrentHashMap
import androidx.room.withTransaction
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class CatalogSyncResult(
    val added: Int,
    val total: Int,
    val newIndices: List<Int>,
)

class DirectLibraryService(
    sources: List<WebSource>,
    private val dao: LibraryDao,
    private val database: LightnovelDatabase,
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

        val generatedId = "${book.provider}-${book.id}".replace(Regex("[^A-Za-z0-9._-]"), "_")
        val now = Instant.now().toString()
        val old = dao.book(generatedId) ?: dao.bookBySource(book.provider, book.id)
        if (old?.local == true) {
            return old
        }
        val bookId = old?.id ?: generatedId
        val storageDir = old?.storageDir ?: generatedId
        val oldChapters = dao.chapters(bookId).associateBy { it.idx }
        val entity = BookEntity(
            id = bookId,
            storageDir = storageDir,
            slug = old?.slug ?: bookId,
            source = book.provider,
            sourceId = book.id,
            title = detail.book.title.ifBlank { book.title },
            titleZh = old?.titleZh,
            author = detail.book.author.ifBlank { book.author }.takeIf { it.isNotBlank() },
            tagsJson = BookTags.encode(detail.book.tags),
            genre = old?.genre,
            episodes = chapters.size,
            local = false,
            createdAt = old?.createdAt ?: now,
            legacyJson = old?.legacyJson,
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
        database.withTransaction {
            dao.upsertBooks(listOf(entity))
            val state = dao.readState(bookId)
            if (state == null) {
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
            } else if (state.hidden) {
                dao.updateHidden(bookId, hidden = false, updatedAt = now)
            }
            dao.upsertChapters(rows)
        }
        return entity
    }

    suspend fun detail(book: BookEntity, force: Boolean = false): SourceDetail {
        if (book.local) error("本地书没有在线详情")
        val source = byId[book.source] ?: error("未知书源：${book.source}")
        val cacheKey = key(book.source, book.sourceId)
        val cached = details[cacheKey]
        val detail = if (!force && cached != null) {
            cached
        } else {
            source.detail(book.sourceId).also { details[cacheKey] = it }
        }
        val latest = dao.book(book.id) ?: book
        val tags = BookTags.encode(detail.book.tags)
        val episodes = maxOf(
            latest.episodes,
            detail.book.episodes,
            detail.chapters.size,
        )
        if ((tags != null && tags != latest.tagsJson) || episodes != latest.episodes) {
            dao.upsertBooks(
                listOf(
                    latest.copy(
                        tagsJson = tags ?: latest.tagsJson,
                        episodes = episodes,
                    ),
                ),
            )
        }
        return detail
    }

    /**
     * Appends chapters that exist on the source but not in the local shelf.
     * Existing chapters, reading progress, translations and bookmarks are
     * left untouched; missing local files are fetched on demand later.
     */
    suspend fun syncCatalog(book: BookEntity, force: Boolean = false): CatalogSyncResult =
        syncCatalog(book, detail(book, force))

    suspend fun syncCatalog(book: BookEntity, detail: SourceDetail): CatalogSyncResult {
        if (book.local) return CatalogSyncResult(0, 0, emptyList())
        val existing = dao.chapters(book.id)
        val byIndex = existing.associateBy { it.idx }
        val titles = detail.chapters.map { it.title.trim() }
        val appends = planCatalogAppend(byIndex.keys, titles)
        val now = Instant.now().toString()
        val rows = appends.map { entry ->
            ChapterEntity(
                bookId = book.id,
                idx = entry.index,
                title = entry.title.takeIf(String::isNotBlank),
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
        val titleFills = (1..titles.size).mapNotNull { index ->
            val chapter = byIndex[index] ?: return@mapNotNull null
            val title = titles[index - 1]
            if (!chapter.title.isNullOrBlank() || title.isBlank()) {
                null
            } else {
                index to title
            }
        }
        val episodes = catalogEpisodeCount(byIndex.keys.maxOrNull(), titles.size)
        database.withTransaction {
            if (rows.isNotEmpty()) dao.upsertChapters(rows)
            titleFills.forEach { (index, title) ->
                dao.fillChapterTitle(book.id, index, title)
            }
            val latest = dao.book(book.id)
            if (latest != null && latest.episodes < episodes) {
                // Never copy the stale caller row: detail() may have refreshed tags.
                dao.upsertBooks(listOf(latest.copy(episodes = episodes)))
            }
        }
        return CatalogSyncResult(
            added = rows.size,
            total = byIndex.size + rows.size,
            newIndices = rows.map { it.idx },
        )
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
