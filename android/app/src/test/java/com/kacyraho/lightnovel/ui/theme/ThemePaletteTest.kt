package com.kacyraho.lightnovel.ui.theme

import androidx.compose.ui.graphics.Color
import kotlin.math.pow
import org.junit.Assert.assertTrue
import org.junit.Test

class ThemePaletteTest {
    @Test
    fun allThemesHaveReadableTextAndOutlines() {
        for (theme in AppTheme.entries) {
            for (dark in listOf(false, true)) {
                val colors = colorSchemeFor(theme, dark)
                val pairs = listOf(
                    "onPrimary/primary" to (colors.onPrimary to colors.primary),
                    "onPrimaryContainer/primaryContainer" to
                        (colors.onPrimaryContainer to colors.primaryContainer),
                    "onSecondary/secondary" to (colors.onSecondary to colors.secondary),
                    "onSecondaryContainer/secondaryContainer" to
                        (colors.onSecondaryContainer to colors.secondaryContainer),
                    "onTertiary/tertiary" to (colors.onTertiary to colors.tertiary),
                    "onTertiaryContainer/tertiaryContainer" to
                        (colors.onTertiaryContainer to colors.tertiaryContainer),
                    "onSurface/surface" to (colors.onSurface to colors.surface),
                    "onSurfaceVariant/surfaceVariant" to
                        (colors.onSurfaceVariant to colors.surfaceVariant),
                    "onError/error" to (colors.onError to colors.error),
                    "onErrorContainer/errorContainer" to
                        (colors.onErrorContainer to colors.errorContainer),
                )
                for ((label, pair) in pairs) {
                    val ratio = contrast(pair.first, pair.second)
                    assertTrue(
                        "$theme dark=$dark $label ratio=$ratio",
                        ratio >= 4.5,
                    )
                }
                val outlineRatio = contrast(colors.outline, colors.surface)
                assertTrue(
                    "$theme dark=$dark outline ratio=$outlineRatio",
                    outlineRatio >= 3.0,
                )
            }
        }
    }

    private fun contrast(a: Color, b: Color): Double {
        val la = luminance(a)
        val lb = luminance(b)
        val high = maxOf(la, lb)
        val low = minOf(la, lb)
        return (high + 0.05) / (low + 0.05)
    }

    private fun luminance(color: Color): Double {
        fun channel(value: Float): Double {
            val c = value.toDouble()
            return if (c <= 0.03928) c / 12.92 else ((c + 0.055) / 1.055).pow(2.4)
        }
        return 0.2126 * channel(color.red) +
            0.7152 * channel(color.green) +
            0.0722 * channel(color.blue)
    }
}
