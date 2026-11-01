package com.kacyraho.lightnovel.ui.theme

import androidx.compose.material3.ColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

@Immutable
data class LnExtendedColors(
    val tagTypeContainer: Color,
    val tagTypeContent: Color,
    val tagKeywordContainer: Color,
    val tagKeywordContent: Color,
    val tagSourceContainer: Color,
    val tagSourceContent: Color,
    val success: Color,
    val warning: Color,
    val info: Color,
    val coverStart: Color,
    val coverEnd: Color,
    val divider: Color,
) {
    companion object {
        fun from(colors: ColorScheme): LnExtendedColors = LnExtendedColors(
            tagTypeContainer = colors.secondaryContainer,
            tagTypeContent = colors.onSecondaryContainer,
            tagKeywordContainer = colors.surfaceVariant,
            tagKeywordContent = colors.onSurfaceVariant,
            tagSourceContainer = colors.surface,
            tagSourceContent = colors.onSurfaceVariant,
            success = colors.primary,
            warning = colors.tertiary,
            info = colors.secondary,
            coverStart = colors.primaryContainer,
            coverEnd = colors.secondaryContainer,
            divider = colors.outlineVariant,
        )
    }
}

val LocalLnColors = staticCompositionLocalOf {
    LnExtendedColors(
        tagTypeContainer = Color(0xFFFFDFA0),
        tagTypeContent = Color(0xFF2C1A00),
        tagKeywordContainer = Color(0xFFEDE3D0),
        tagKeywordContent = Color(0xFF4E4639),
        tagSourceContainer = Color(0xFFFFFCF3),
        tagSourceContent = Color(0xFF4E4639),
        success = Color(0xFF8A5A00),
        warning = Color(0xFF7B4E7E),
        info = Color(0xFF326B63),
        coverStart = Color(0xFFFFDFA0),
        coverEnd = Color(0xFFEDE3D0),
        divider = Color(0xFFBDB3A2),
    )
}

@Composable
fun lnColors(): LnExtendedColors = LocalLnColors.current
