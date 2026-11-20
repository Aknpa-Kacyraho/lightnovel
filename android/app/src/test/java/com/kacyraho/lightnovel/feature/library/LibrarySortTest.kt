package com.kacyraho.lightnovel.feature.library

import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.BookWithState
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import org.junit.Assert.assertEquals
import org.junit.Test

class LibrarySortTest {
    private fun book(
        id: String,
        title: String,
        createdAt: String? = "2026-01-01T00:00:00Z",
    ) = BookWithState(
        book = BookEntity(
            id = id,
            storageDir = id,
            slug = id,
            source = "local",
            sourceId = id,
            title = title,
            titleZh = title,
            author = null,
            tagsJson = null,
            genre = null,
            episodes = 10,
            local = true,
            createdAt = createdAt,
            legacyJson = null,
        ),
        state = null,
    )

    private fun withState(item: BookWithState, updatedAt: String?): BookWithState = item.copy(
        state = ReadStateEntity(
            bookId = item.book.id,
            shelf = "reading",
            favorite = false,
            hidden = false,
            progressIdx = 2,
            openedAt = null,
            finishedAt = null,
            updatedAt = updatedAt,
        ),
    )

    @Test
    fun titleSortIsCaseInsensitive() {
        val books = listOf(book("b", "beta"), book("a", "Alpha"), book("c", "樱桃"))

        val sorted = sortLibrary(books, LibrarySort.TITLE)

        assertEquals(listOf("Alpha", "beta", "樱桃"), sorted.map { it.book.title })
    }

    @Test
    fun recentSortUsesLatestTimestampFirst() {
        val books = listOf(
            withState(book("a", "A"), "2026-01-03T00:00:00Z"),
            withState(book("b", "B"), "2026-01-05T00:00:00Z"),
            withState(book("c", "C"), "2026-01-01T00:00:00Z"),
        )

        val sorted = sortLibrary(books, LibrarySort.RECENT)

        assertEquals(listOf("B", "A", "C"), sorted.map { it.book.title })
    }

    @Test
    fun missingTimestampsGoLast() {
        val books = listOf(
            book("a", "A", createdAt = null),
            book("b", "B", createdAt = "2026-01-01T00:00:00Z"),
        )

        val sorted = sortLibrary(books, LibrarySort.ADDED)

        assertEquals(listOf("B", "A"), sorted.map { it.book.title })
    }

    @Test
    fun addedSortUsesCreatedAtDescending() {
        val books = listOf(
            book("a", "A", createdAt = "2026-01-01T00:00:00Z"),
            book("b", "B", createdAt = "2026-02-01T00:00:00Z"),
        )

        val sorted = sortLibrary(books, LibrarySort.ADDED)

        assertEquals(listOf("B", "A"), sorted.map { it.book.title })
    }

    @Test
    fun unknownIdFallsBackToTitle() {
        assertEquals(LibrarySort.TITLE, LibrarySort.fromId("missing"))
        assertEquals(LibrarySort.RECENT, LibrarySort.fromId("recent"))
    }
}
