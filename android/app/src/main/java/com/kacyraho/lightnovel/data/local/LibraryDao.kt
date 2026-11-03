package com.kacyraho.lightnovel.data.local

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Transaction
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface LibraryDao {
    @Upsert
    suspend fun upsertBooks(books: List<BookEntity>)

    @Upsert
    suspend fun upsertReadStates(states: List<ReadStateEntity>)

    @Upsert
    suspend fun upsertAliases(aliases: List<AliasEntity>)

    @Upsert
    suspend fun upsertChapters(chapters: List<ChapterEntity>)

    @Query("SELECT COUNT(*) FROM books")
    suspend fun bookCount(): Int

    @Query("SELECT * FROM books ORDER BY title")
    suspend fun books(): List<BookEntity>

    @Query(
        """
        SELECT b.source || '/' || b.source_id
        FROM books b
        LEFT JOIN read_state r ON r.book_id = b.id
        WHERE b.local = 0 AND COALESCE(r.hidden, 0) = 0
        """,
    )
    suspend fun onlineKeys(): List<String>

    @Query("SELECT * FROM books WHERE id = :bookId")
    suspend fun book(bookId: String): BookEntity?

    @Query("SELECT * FROM books WHERE source = :source AND source_id = :sourceId LIMIT 1")
    suspend fun bookBySource(source: String, sourceId: String): BookEntity?

    @Query(
        """
        UPDATE read_state
        SET hidden = :hidden,
            shelf = CASE
                WHEN :hidden = 0 AND shelf IS NULL THEN 'reading'
                ELSE shelf
            END,
            updated_at = :updatedAt
        WHERE book_id = :bookId
        """,
    )
    suspend fun updateHidden(bookId: String, hidden: Boolean, updatedAt: String): Int

    @Query(
        """
        SELECT b.* FROM books b
        LEFT JOIN read_state r ON r.book_id = b.id
        WHERE (
            (:removedOnly = 0 AND COALESCE(r.hidden, 0) = 0) OR
            (:removedOnly = 1 AND COALESCE(r.hidden, 0) = 1)
        )
          AND (:shelf IS NULL OR r.shelf = :shelf)
        ORDER BY b.title
        """,
    )
    fun observeBooks(shelf: String?, removedOnly: Boolean): Flow<List<BookEntity>>

    @Transaction
    @Query(
        """
        SELECT b.* FROM books b
        LEFT JOIN read_state r ON r.book_id = b.id
        WHERE (
            (:removedOnly = 0 AND COALESCE(r.hidden, 0) = 0) OR
            (:removedOnly = 1 AND COALESCE(r.hidden, 0) = 1)
        )
          AND (:shelf IS NULL OR r.shelf = :shelf)
        ORDER BY b.title
        """,
    )
    fun observeLibrary(shelf: String?, removedOnly: Boolean): Flow<List<BookWithState>>

    @Query("UPDATE books SET title_zh = :titleZh WHERE id = :bookId")
    suspend fun updateBookTitle(bookId: String, titleZh: String)

    @Query("UPDATE chapters SET title_zh = :titleZh WHERE book_id = :bookId AND idx = :idx")
    suspend fun updateChapterTitle(bookId: String, idx: Int, titleZh: String)

    @Query(
        """
        UPDATE chapters SET title = :title
        WHERE book_id = :bookId AND idx = :idx
          AND (title IS NULL OR title = '')
        """,
    )
    suspend fun fillChapterTitle(bookId: String, idx: Int, title: String)

    @Query("SELECT * FROM read_state WHERE book_id = :bookId")
    suspend fun readState(bookId: String): ReadStateEntity?

    @Query(
        """
        UPDATE read_state
        SET favorite = :favorite,
            updated_at = :updatedAt
        WHERE book_id = :bookId
        """,
    )
    suspend fun updateFavorite(
        bookId: String,
        favorite: Boolean,
        updatedAt: String,
    ): Int

    @Query(
        """
        UPDATE read_state
        SET progress_idx = :chapterIndex,
            progress_block = :paragraphId,
            progress_char = :charOffset,
            updated_at = :updatedAt
        WHERE book_id = :bookId
        """,
    )
    suspend fun updateProgress(
        bookId: String,
        chapterIndex: Int,
        paragraphId: Int,
        charOffset: Int,
        updatedAt: String,
    ): Int

    @Query("SELECT * FROM aliases")
    suspend fun aliases(): List<AliasEntity>

    @Query("SELECT COUNT(*) FROM chapters")
    suspend fun chapterCount(): Int

    @Query(
        """
        UPDATE chapters
        SET status = 'failed',
            updated_at = :updatedAt
        WHERE status = 'translating'
        """,
    )
    suspend fun resetInterruptedTranslations(updatedAt: String): Int

    @Query("SELECT * FROM chapters WHERE book_id = :bookId ORDER BY idx")
    suspend fun chapters(bookId: String): List<ChapterEntity>

    @Query("SELECT * FROM chapters WHERE book_id = :bookId ORDER BY idx")
    fun observeChapters(bookId: String): Flow<List<ChapterEntity>>

    @Query(
        """
        SELECT c.book_id AS book_id,
               c.idx AS idx,
               c.title AS chapter_title,
               c.title_zh AS chapter_title_zh,
               c.status AS status,
               b.title AS book_title,
               b.title_zh AS book_title_zh,
               c.updated_at AS updated_at
        FROM chapters c
        JOIN books b ON b.id = c.book_id
        LEFT JOIN read_state r ON r.book_id = c.book_id
        WHERE COALESCE(r.hidden, 0) = 0
          AND c.status IN ('translating', 'failed', 'partial')
        ORDER BY c.updated_at DESC
        LIMIT 100
        """,
    )
    fun observeActiveTasks(): Flow<List<ChapterTaskRow>>

    @Query(
        """
        UPDATE chapters
        SET status = :status,
            model = :model,
            token_in = :tokenIn,
            token_out = :tokenOut,
            updated_at = :updatedAt
        WHERE book_id = :bookId AND idx = :idx
        """,
    )
    suspend fun updateChapterTranslation(
        bookId: String,
        idx: Int,
        status: String,
        model: String,
        tokenIn: Int,
        tokenOut: Int,
        updatedAt: String,
    ): Int
}
