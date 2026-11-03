package com.kacyraho.lightnovel.data.repository

import androidx.room.withTransaction
import com.kacyraho.lightnovel.core.model.ReaderAnchor
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.BookTags
import com.kacyraho.lightnovel.data.local.BookWithState
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import java.time.Instant
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

data class ShelfFilter(
    val shelf: String? = null,
    val query: String = "",
    val removedOnly: Boolean = false,
)

interface LibraryRepository {
    fun observeBooks(filter: ShelfFilter = ShelfFilter()): Flow<List<BookEntity>>

    fun observeLibrary(filter: ShelfFilter = ShelfFilter()): Flow<List<BookWithState>>

    fun observeChapters(bookId: String): Flow<List<ChapterEntity>>

    suspend fun book(bookId: String): BookEntity?

    suspend fun readState(bookId: String): ReadStateEntity?

    suspend fun updateProgress(bookId: String, anchor: ReaderAnchor)

    suspend fun setFavorite(bookId: String, favorite: Boolean)

    suspend fun removeBook(bookId: String)

    suspend fun restoreBook(bookId: String)
}

class RoomLibraryRepository(
    private val db: LightnovelDatabase,
) : LibraryRepository {
    private val dao = db.libraryDao()

    override fun observeBooks(filter: ShelfFilter): Flow<List<BookEntity>> {
        val query = filter.query.trim()
        return dao.observeBooks(filter.shelf, filter.removedOnly).map { books ->
            if (query.isEmpty()) {
                books
            } else {
                books.filter { book ->
                    book.title.contains(query, ignoreCase = true) ||
                        book.titleZh?.contains(query, ignoreCase = true) == true ||
                        book.author?.contains(query, ignoreCase = true) == true
                }
            }
        }
    }

    override fun observeLibrary(filter: ShelfFilter): Flow<List<BookWithState>> {
        val query = filter.query.trim()
        return dao.observeLibrary(filter.shelf, filter.removedOnly).map { books ->
            if (query.isEmpty()) {
                books
            } else {
                books.filter { item ->
                    item.book.title.contains(query, ignoreCase = true) ||
                        item.book.titleZh?.contains(query, ignoreCase = true) == true ||
                        item.book.author?.contains(query, ignoreCase = true) == true ||
                        BookTags.decode(item.book.tagsJson).any {
                            it.contains(query, ignoreCase = true)
                        }
                }
            }
        }
    }

    override fun observeChapters(bookId: String): Flow<List<ChapterEntity>> =
        dao.observeChapters(bookId)

    override suspend fun book(bookId: String): BookEntity? = dao.book(bookId)

    override suspend fun readState(bookId: String): ReadStateEntity? = dao.readState(bookId)

    override suspend fun setFavorite(bookId: String, favorite: Boolean) {
        val now = Instant.now().toString()
        if (dao.updateFavorite(bookId, favorite, now) == 0) {
            dao.upsertReadStates(
                listOf(
                    ReadStateEntity(
                        bookId = bookId,
                        shelf = null,
                        favorite = favorite,
                        hidden = false,
                        progressIdx = 0,
                        openedAt = null,
                        finishedAt = null,
                        updatedAt = now,
                    ),
                ),
            )
        }
    }

    override suspend fun updateProgress(bookId: String, anchor: ReaderAnchor) {
        db.withTransaction {
            val now = Instant.now().toString()
            val changed = dao.updateProgress(
                bookId = bookId,
                chapterIndex = anchor.chapterIndex,
                paragraphId = anchor.paragraphId,
                charOffset = anchor.charOffset,
                updatedAt = now,
            )
            if (changed == 0) {
                dao.upsertReadStates(
                    listOf(
                        ReadStateEntity(
                            bookId = bookId,
                            shelf = null,
                            favorite = false,
                            hidden = false,
                            progressIdx = anchor.chapterIndex,
                            progressBlock = anchor.paragraphId,
                            progressChar = anchor.charOffset,
                            openedAt = null,
                            finishedAt = null,
                            updatedAt = now,
                        ),
                    ),
                )
            }
        }
    }

    override suspend fun removeBook(bookId: String) {
        setHidden(bookId, hidden = true)
    }

    override suspend fun restoreBook(bookId: String) {
        setHidden(bookId, hidden = false)
    }

    private suspend fun setHidden(bookId: String, hidden: Boolean) {
        if (dao.book(bookId) == null) return
        val now = Instant.now().toString()
        if (dao.updateHidden(bookId, hidden, now) == 0) {
            dao.upsertReadStates(
                listOf(
                    ReadStateEntity(
                        bookId = bookId,
                        shelf = if (hidden) null else "reading",
                        favorite = false,
                        hidden = hidden,
                        progressIdx = 0,
                        openedAt = null,
                        finishedAt = null,
                        updatedAt = now,
                    ),
                ),
            )
        }
    }
}
