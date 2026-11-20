package com.kacyraho.lightnovel.feature.reader

import org.junit.Assert.assertEquals
import org.junit.Test

class ReaderProgressTest {
    @Test
    fun pagedProgressUsesCurrentPage() {
        assertEquals(
            0.25f,
            readerChapterProgress(
                scrollMode = false,
                pageIndex = 0,
                pageCount = 4,
                scrollParagraph = 0,
                blockCount = 0,
            ),
            0.001f,
        )
        assertEquals(
            1f,
            readerChapterProgress(
                scrollMode = false,
                pageIndex = 3,
                pageCount = 4,
                scrollParagraph = 0,
                blockCount = 0,
            ),
            0.001f,
        )
    }

    @Test
    fun scrollProgressUsesCurrentParagraph() {
        assertEquals(
            0.5f,
            readerChapterProgress(
                scrollMode = true,
                pageIndex = 0,
                pageCount = 0,
                scrollParagraph = 4,
                blockCount = 10,
            ),
            0.001f,
        )
    }

    @Test
    fun emptyChapterReturnsZero() {
        assertEquals(
            0f,
            readerChapterProgress(
                scrollMode = false,
                pageIndex = 0,
                pageCount = 0,
                scrollParagraph = 0,
                blockCount = 0,
            ),
            0.001f,
        )
        assertEquals(
            0f,
            readerChapterProgress(
                scrollMode = true,
                pageIndex = 0,
                pageCount = 3,
                scrollParagraph = 0,
                blockCount = 0,
            ),
            0.001f,
        )
    }

    @Test
    fun outOfRangeValuesAreClamped() {
        assertEquals(
            1f,
            readerChapterProgress(
                scrollMode = false,
                pageIndex = 99,
                pageCount = 4,
                scrollParagraph = 0,
                blockCount = 0,
            ),
            0.001f,
        )
    }

    @Test
    fun shelfProgressHandlesUnknownEpisodes() {
        assertEquals(0f, shelfProgress(progressIdx = 3, episodes = 0), 0.001f)
        assertEquals(0f, shelfProgress(progressIdx = 0, episodes = 20), 0.001f)
        assertEquals(0.5f, shelfProgress(progressIdx = 10, episodes = 20), 0.001f)
        assertEquals(1f, shelfProgress(progressIdx = 25, episodes = 20), 0.001f)
    }

    @Test
    fun progressToPageHandlesEdges() {
        assertEquals(0, progressToPage(0f, 0))
        assertEquals(0, progressToPage(0.5f, 1))
        assertEquals(0, progressToPage(0f, 10))
        assertEquals(9, progressToPage(1f, 10))
        assertEquals(5, progressToPage(0.5f, 10))
    }

    @Test
    fun pageToProgressHandlesEdges() {
        assertEquals(0f, pageToProgress(0, 0), 0.001f)
        assertEquals(0f, pageToProgress(3, 1), 0.001f)
        assertEquals(0f, pageToProgress(0, 10), 0.001f)
        assertEquals(1f, pageToProgress(9, 10), 0.001f)
    }

    @Test
    fun progressRoundTripIsStable() {
        val pages = 37
        for (page in 0 until pages) {
            val progress = pageToProgress(page, pages)
            assertEquals(page, progressToPage(progress, pages))
        }
    }
}
