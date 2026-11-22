package com.kacyraho.lightnovel.feature.chapters

import com.kacyraho.lightnovel.data.local.ChapterEntity
import org.junit.Assert.assertEquals
import org.junit.Test

class ChapterSelectionTest {
    @Test
    fun keepsSavedChapterWhenIndicesHaveGaps() {
        val chapters = listOf(chapter(1), chapter(2), chapter(3), chapter(50))

        assertEquals(50, continueChapterIndex(chapters, 50))
    }

    @Test
    fun fallsBackToFirstChapterOnlyWhenSavedOneIsMissing() {
        val chapters = listOf(chapter(2), chapter(4), chapter(6))

        assertEquals(2, continueChapterIndex(chapters, 5))
    }

    @Test
    fun emptyCatalogFallsBackToOne() {
        assertEquals(1, continueChapterIndex(emptyList(), 12))
    }

    private fun chapter(idx: Int) = ChapterEntity(
        bookId = "book",
        idx = idx,
        title = null,
        titleZh = null,
        rawPath = null,
        zhPath = null,
        status = "raw",
        tokenIn = 0,
        tokenOut = 0,
        model = null,
        updatedAt = null,
    )
}
