package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.data.local.ChapterEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReadingTranslationPlannerTest {
    @Test
    fun plansAheadAndNearbyGapsWithoutTranslatingWholeBook() {
        val chapters = (1..20).map { index ->
            chapter(index, if (index == 10) "translated" else "raw")
        }
        val targets = ReadingTranslationPlanner.plan(
            currentIndex = 12,
            chapters = chapters,
            ahead = 2,
            backfill = 5,
        )
        assertEquals(listOf(13, 14, 11), targets)
    }

    @Test
    fun backfillStopsAtTranslatedBoundary() {
        val chapters = (1..10).map { index ->
            chapter(index, if (index == 6) "translated" else "raw")
        }
        val targets = ReadingTranslationPlanner.plan(8, chapters, ahead = 0, backfill = 5)
        assertEquals(listOf(7), targets)
    }

    @Test
    fun currentChapterAndAlreadyTranslatedAheadAreSkipped() {
        val chapters = (1..8).map { index ->
            chapter(
                index,
                when (index) {
                    4 -> "complete"
                    5 -> "translating"
                    else -> "raw"
                },
            )
        }
        val targets = ReadingTranslationPlanner.plan(4, chapters, ahead = 3, backfill = 0)
        assertEquals(listOf(6, 7), targets)
        assertFalse(4 in targets)
        assertFalse(5 in targets)
    }

    @Test
    fun retriesPartialChapterAhead() {
        val chapters = (1..3).map { index ->
            chapter(
                index,
                when (index) {
                    2 -> "partial"
                    3 -> "complete"
                    else -> "raw"
                },
            )
        }
        val targets = ReadingTranslationPlanner.plan(1, chapters, ahead = 2, backfill = 0)
        assertEquals(listOf(2), targets)
    }

    @Test
    fun boundsAheadAndBackfill() {
        val chapters = (1..30).map { chapter(it, "raw") }
        val targets = ReadingTranslationPlanner.plan(20, chapters, ahead = 50, backfill = 50)
        assertEquals(10, targets.count { it > 20 })
        assertTrue(targets.size <= 20)
    }

    private fun chapter(index: Int, status: String) = ChapterEntity(
        bookId = "book",
        idx = index,
        title = null,
        titleZh = null,
        rawPath = null,
        zhPath = null,
        status = status,
        model = null,
        tokenIn = 0,
        tokenOut = 0,
        updatedAt = null,
    )
}
