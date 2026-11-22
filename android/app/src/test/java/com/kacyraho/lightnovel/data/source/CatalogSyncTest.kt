package com.kacyraho.lightnovel.data.source

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CatalogSyncTest {
    @Test
    fun appendsEveryChapterForAnEmptyShelf() {
        val plan = planCatalogAppend(
            existingIndices = emptySet(),
            sourceTitles = (1..12).map { "第 $it 话" },
        )

        assertEquals((1..12).toList(), plan.map { it.index })
        assertEquals("第 3 话", plan[2].title)
    }

    @Test
    fun appendsOnlyNewTailChapters() {
        val plan = planCatalogAppend(
            existingIndices = (1..10).toSet(),
            sourceTitles = (1..12).map { "第 $it 话" },
        )

        assertEquals(listOf(11, 12), plan.map { it.index })
    }

    @Test
    fun sourceShrinkNeverDeletesOrShortensLocalBook() {
        val plan = planCatalogAppend(
            existingIndices = (1..10).toSet(),
            sourceTitles = (1..8).map { "第 $it 话" },
        )

        assertTrue(plan.isEmpty())
        assertEquals(10, catalogEpisodeCount(existingMax = 10, sourceSize = 8))
    }

    @Test
    fun fillsSparseIndicesFromEarlierPartialRestores() {
        val plan = planCatalogAppend(
            existingIndices = setOf(1, 2, 5),
            sourceTitles = (1..8).map { "第 $it 话" },
        )

        assertEquals(listOf(3, 4, 6, 7, 8), plan.map { it.index })
    }

    @Test
    fun blankSourceTitlesStayBlankForLaterFill() {
        val plan = planCatalogAppend(
            existingIndices = emptySet(),
            sourceTitles = listOf("第一章", "", "第三章"),
        )

        assertEquals(3, plan.size)
        assertEquals("", plan[1].title)
    }

    @Test
    fun episodesTakeTheLargerOfLocalAndSource() {
        assertEquals(12, catalogEpisodeCount(existingMax = 10, sourceSize = 12))
        assertEquals(10, catalogEpisodeCount(existingMax = 10, sourceSize = 10))
        assertEquals(8, catalogEpisodeCount(existingMax = null, sourceSize = 8))
    }
}
