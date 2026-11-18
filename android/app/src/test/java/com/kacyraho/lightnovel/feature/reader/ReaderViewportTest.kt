package com.kacyraho.lightnovel.feature.reader

import org.junit.Assert.assertEquals
import org.junit.Test

class ReaderViewportTest {
    @Test
    fun phoneWidthKeepsCurrentBehaviour() {
        assertEquals(328f, readerContentWidthDp(360f, 16f))
    }

    @Test
    fun exactLimitIsNotShrunk() {
        assertEquals(648f, readerContentWidthDp(680f, 16f))
    }

    @Test
    fun tabletStopsAtContentLimit() {
        assertEquals(648f, readerContentWidthDp(1024f, 16f))
        assertEquals(628f, readerContentWidthDp(1024f, 26f))
    }

    @Test
    fun zeroMarginUsesFullContentWidth() {
        assertEquals(680f, readerContentWidthDp(900f, 0f))
    }

    @Test
    fun extremeMarginNeverGoesNegative() {
        assertEquals(1f, readerContentWidthDp(360f, 400f))
    }
}
