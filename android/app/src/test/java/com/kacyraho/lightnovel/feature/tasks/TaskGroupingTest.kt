package com.kacyraho.lightnovel.feature.tasks

import com.kacyraho.lightnovel.data.local.ChapterTaskRow
import org.junit.Assert.assertEquals
import org.junit.Test

class TaskGroupingTest {
    private fun row(
        bookId: String,
        title: String,
        idx: Int,
        status: String,
        updatedAt: String = "2026-10-30T10:00:00Z",
    ) = ChapterTaskRow(
        bookId = bookId,
        idx = idx,
        chapterTitle = "chapter-$idx",
        chapterTitleZh = null,
        status = status,
        bookTitle = title,
        bookTitleZh = null,
        updatedAt = updatedAt,
    )

    @Test
    fun groupsByBookAndSortsChapters() {
        val tasks = listOf(
            row("b1", "Book One", 3, "failed"),
            row("b1", "Book One", 1, "partial"),
            row("b2", "Book Two", 2, "translating"),
        )

        val groups = TaskGrouping.group(tasks, TaskFilter.ALL)

        assertEquals(listOf("b1", "b2"), groups.map { it.bookId })
        assertEquals(listOf(1, 3), groups.first().tasks.map { it.idx })
    }

    @Test
    fun filtersByStatus() {
        val tasks = listOf(
            row("b1", "Book One", 1, "failed"),
            row("b1", "Book One", 2, "partial"),
            row("b2", "Book Two", 3, "translating"),
        )

        assertEquals(1, TaskGrouping.group(tasks, TaskFilter.FAILED).size)
        assertEquals("b2", TaskGrouping.group(tasks, TaskFilter.TRANSLATING).single().bookId)
        assertEquals(1, TaskGrouping.group(tasks, TaskFilter.PARTIAL).single().tasks.size)
    }
}
