package com.kacyraho.lightnovel.reader.engine

import com.kacyraho.lightnovel.feature.reader.contrastRatio
import androidx.compose.ui.graphics.toArgb
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class ReaderThemeTest {
    @Test
    fun autoFollowsSystemDarkness() {
        assertEquals(ReaderTheme.NIGHT, ReaderTheme.AUTO.resolve(dark = true))
        assertEquals(ReaderTheme.PAPER, ReaderTheme.AUTO.resolve(dark = false))
    }

    @Test
    fun explicitChoiceIgnoresSystem() {
        assertEquals(ReaderTheme.PAPER, ReaderTheme.PAPER.resolve(dark = true))
        assertEquals(ReaderTheme.NIGHT, ReaderTheme.NIGHT.resolve(dark = false))
        assertEquals(ReaderTheme.SEPIA, ReaderTheme.SEPIA.resolve(dark = true))
    }

    @Test
    fun unknownIdFallsBackToPaper() {
        assertEquals(ReaderTheme.PAPER, ReaderTheme.fromId("missing"))
    }

    @Test
    fun nightTextRemainsReadableButSofter() {
        val ratio = contrastRatio(
            ReaderTheme.NIGHT.text.toArgb().toLong() and 0xFFFFFFFFL,
            ReaderTheme.NIGHT.background.toArgb().toLong() and 0xFFFFFFFFL,
        )

        assertTrue("夜间正文对比度应不低于 7:1，实际 $ratio", ratio >= 7.0)
        assertTrue("夜间正文不应超过 10:1，实际 $ratio", ratio < 10.0)
    }

    @Test
    fun lightThemesKeepStrongContrast() {
        listOf(ReaderTheme.PAPER, ReaderTheme.SEPIA, ReaderTheme.GREEN).forEach { theme ->
            val ratio = contrastRatio(
                theme.text.toArgb().toLong() and 0xFFFFFFFFL,
                theme.background.toArgb().toLong() and 0xFFFFFFFFL,
            )
            assertTrue("${theme.label} 正文对比度应不低于 7:1，实际 $ratio", ratio >= 7.0)
        }
    }

    @Test
    fun nightSecondaryTextStaysAboveMinimum() {
        val ratio = contrastRatio(
            ReaderTheme.NIGHT.secondary.toArgb().toLong() and 0xFFFFFFFFL,
            ReaderTheme.NIGHT.background.toArgb().toLong() and 0xFFFFFFFFL,
        )

        assertTrue("夜间次要文字对比度应不低于 3:1，实际 $ratio", ratio >= 3.0)
    }
}
