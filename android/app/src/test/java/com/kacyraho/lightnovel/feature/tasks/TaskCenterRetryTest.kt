package com.kacyraho.lightnovel.feature.tasks

import com.kacyraho.lightnovel.data.local.ChapterTaskRow
import org.junit.Assert.assertEquals
import org.junit.Test

class TaskCenterRetryTest {
    @Test
    fun selectsFailedAndPartialOnly() {
        val tasks = listOf(
            row("book", 1, "failed"),
            row("book", 2, "partial"),
            row("book", 3, "translating"),
            row("book", 4, "complete"),
        )

        val selected = retryableRows(tasks, ignoredKeys = emptySet())

        assertEquals(listOf(1, 2), selected.map { it.idx })
    }

    @Test
    fun excludesIgnoredKeys() {
        val tasks = listOf(
            row("book", 1, "failed"),
            row("book", 2, "partial"),
        )

        val selected = retryableRows(tasks, ignoredKeys = setOf("book/1"))

        assertEquals(listOf(2), selected.map { it.idx })
    }

    @Test
    fun ignoresCurrentFilterBecauseItHasNoFilterParameter() {
        // The function only receives the full task list; the UI filter cannot shrink it.
        val tasks = (1..5).map { row("book", it, "failed") }

        val selected = retryableRows(tasks, ignoredKeys = emptySet())

        assertEquals(5, selected.size)
    }

    private fun row(bookId: String, idx: Int, status: String) = ChapterTaskRow(
        bookId = bookId,
        idx = idx,
        chapterTitle = null,
        chapterTitleZh = null,
        status = status,
        bookTitle = "Book",
        bookTitleZh = null,
        updatedAt = null,
    )
}
