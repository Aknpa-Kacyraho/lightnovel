package com.kacyraho.lightnovel.ui.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import com.kacyraho.lightnovel.feature.reader.contrastRatio
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class ThemeContrastTest {
    private fun ratio(foreground: Color, background: Color): Double = contrastRatio(
        foreground.toArgb().toLong() and 0xFFFFFFFFL,
        background.toArgb().toLong() and 0xFFFFFFFFL,
    )

    @Test
    fun darkSecondaryTextIsSoftButReadable() {
        AppTheme.entries.forEach { theme ->
            val colors = colorSchemeFor(theme, dark = true)
            val ratio = ratio(colors.onSurfaceVariant, colors.surface)

            assertTrue(
                "$theme 深色次要文字应在 7–10:1，实际 $ratio",
                ratio in 7.0..10.0,
            )
        }
    }

    @Test
    fun darkPrimaryTextKeepsStrongContrast() {
        AppTheme.entries.forEach { theme ->
            val colors = colorSchemeFor(theme, dark = true)
            val ratio = ratio(colors.onSurface, colors.surface)

            assertTrue("$theme 深色主文字应 ≥12:1，实际 $ratio", ratio >= 12.0)
        }
    }

    @Test
    fun darkTagTextStaysAboveMinimum() {
        AppTheme.entries.forEach { theme ->
            val colors = colorSchemeFor(theme, dark = true)
            val ratio = ratio(colors.onSurfaceVariant, colors.surfaceVariant)

            assertTrue("$theme 深色标签文字应 ≥4.5:1，实际 $ratio", ratio >= 4.5)
        }
    }
}
