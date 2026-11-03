package com.kacyraho.lightnovel.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp

data class ThemePreview(
    val background: Color,
    val primary: Color,
    val secondary: Color,
    val tertiary: Color,
    val onBackground: Color,
)

private data class Palette(
    val primary: Color,
    val onPrimary: Color,
    val primaryContainer: Color,
    val onPrimaryContainer: Color,
    val secondary: Color,
    val onSecondary: Color,
    val tertiary: Color,
    val onTertiary: Color,
    val background: Color,
    val surface: Color,
    val surfaceVariant: Color,
    val onSurface: Color,
    val onSurfaceVariant: Color,
    val outline: Color,
    val error: Color,
    val onError: Color,
)

private fun Palette.toScheme(dark: Boolean): ColorScheme {
    val secondaryContainer = lerp(surface, secondary, if (dark) 0.30f else 0.14f)
    val tertiaryContainer = lerp(surface, tertiary, if (dark) 0.30f else 0.14f)
    val errorContainer = lerp(surface, error, if (dark) 0.30f else 0.14f)
    val outlineVariant = lerp(surface, outline, 0.45f)
    val surfaceContainerLowest = if (dark) background else surface
    val surfaceContainerLow = if (dark) lerp(background, surface, 0.55f) else
        lerp(surface, background, 0.10f)
    val surfaceContainer = if (dark) lerp(background, surface, 0.70f) else
        lerp(surface, background, 0.22f)
    val surfaceContainerHigh = if (dark) lerp(background, surface, 0.82f) else
        lerp(surface, background, 0.34f)
    val surfaceContainerHighest = if (dark) lerp(background, surface, 0.92f) else
        lerp(surface, background, 0.46f)
    return if (dark) {
        darkColorScheme(
            primary = primary,
            onPrimary = onPrimary,
            primaryContainer = primaryContainer,
            onPrimaryContainer = onPrimaryContainer,
            secondary = secondary,
            onSecondary = onSecondary,
            secondaryContainer = secondaryContainer,
            onSecondaryContainer = onSurface,
            tertiary = tertiary,
            onTertiary = onTertiary,
            tertiaryContainer = tertiaryContainer,
            onTertiaryContainer = onSurface,
            background = background,
            onBackground = onSurface,
            surface = surface,
            onSurface = onSurface,
            surfaceVariant = surfaceVariant,
            onSurfaceVariant = onSurfaceVariant,
            surfaceContainerLowest = surfaceContainerLowest,
            surfaceContainerLow = surfaceContainerLow,
            surfaceContainer = surfaceContainer,
            surfaceContainerHigh = surfaceContainerHigh,
            surfaceContainerHighest = surfaceContainerHighest,
            surfaceDim = if (dark) background else surfaceContainerHigh,
            surfaceBright = surface,
            inverseSurface = onSurface,
            inverseOnSurface = surface,
            inversePrimary = primaryContainer,
            scrim = Color.Black,
            surfaceTint = primary,
            outline = outline,
            outlineVariant = outlineVariant,
            error = error,
            onError = onError,
            errorContainer = errorContainer,
            onErrorContainer = onSurface,
        )
    } else {
        lightColorScheme(
            primary = primary,
            onPrimary = onPrimary,
            primaryContainer = primaryContainer,
            onPrimaryContainer = onPrimaryContainer,
            secondary = secondary,
            onSecondary = onSecondary,
            secondaryContainer = secondaryContainer,
            onSecondaryContainer = onSurface,
            tertiary = tertiary,
            onTertiary = onTertiary,
            tertiaryContainer = tertiaryContainer,
            onTertiaryContainer = onSurface,
            background = background,
            onBackground = onSurface,
            surface = surface,
            onSurface = onSurface,
            surfaceVariant = surfaceVariant,
            onSurfaceVariant = onSurfaceVariant,
            surfaceContainerLowest = surfaceContainerLowest,
            surfaceContainerLow = surfaceContainerLow,
            surfaceContainer = surfaceContainer,
            surfaceContainerHigh = surfaceContainerHigh,
            surfaceContainerHighest = surfaceContainerHighest,
            surfaceDim = if (dark) background else surfaceContainerHigh,
            surfaceBright = surface,
            inverseSurface = onSurface,
            inverseOnSurface = surface,
            inversePrimary = primaryContainer,
            scrim = Color.Black,
            surfaceTint = primary,
            outline = outline,
            outlineVariant = outlineVariant,
            error = error,
            onError = onError,
            errorContainer = errorContainer,
            onErrorContainer = onSurface,
        )
    }
}

private val Teal = Palette(
    primary = Color(0xFF176077), onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFC7E8F2), onPrimaryContainer = Color(0xFF00343F),
    secondary = Color(0xFF8A5A2B), onSecondary = Color(0xFFFFFFFF),
    tertiary = Color(0xFF8F4E63), onTertiary = Color(0xFFFFFFFF),
    background = Color(0xFFF7F4EC), surface = Color(0xFFFFFCF5),
    surfaceVariant = Color(0xFFE7E0D2), onSurface = Color(0xFF1B2428),
    onSurfaceVariant = Color(0xFF4B5559), outline = Color(0xFF747C7E),
    error = Color(0xFFB3261E), onError = Color(0xFFFFFFFF),
)

private val TealDark = Palette(
    primary = Color(0xFF8BD3E6), onPrimary = Color(0xFF00363F),
    primaryContainer = Color(0xFF0B4E60), onPrimaryContainer = Color(0xFFC7E8F2),
    secondary = Color(0xFFE7BE8D), onSecondary = Color(0xFF442A00),
    tertiary = Color(0xFFF0B3C2), onTertiary = Color(0xFF552434),
    background = Color(0xFF0E1619), surface = Color(0xFF151F23),
    surfaceVariant = Color(0xFF3B474B), onSurface = Color(0xFFE3E2DD),
    onSurfaceVariant = Color(0xFFC0C8C9), outline = Color(0xFF8B9597),
    error = Color(0xFFFFB4AB), onError = Color(0xFF690005),
)

private val Lavender = Palette(
    primary = Color(0xFF5B4B9A), onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFE6DEFF), onPrimaryContainer = Color(0xFF1A1140),
    secondary = Color(0xFF2E6F5E), onSecondary = Color(0xFFFFFFFF),
    tertiary = Color(0xFF9A3F6B), onTertiary = Color(0xFFFFFFFF),
    background = Color(0xFFF8F6FC), surface = Color(0xFFFFFBFE),
    surfaceVariant = Color(0xFFE7E0EE), onSurface = Color(0xFF1D1B22),
    onSurfaceVariant = Color(0xFF4B4553), outline = Color(0xFF77707E),
    error = Color(0xFFB3261E), onError = Color(0xFFFFFFFF),
)

private val LavenderDark = Palette(
    primary = Color(0xFFCFC1FF), onPrimary = Color(0xFF302566),
    primaryContainer = Color(0xFF473A85), onPrimaryContainer = Color(0xFFE6DEFF),
    secondary = Color(0xFFA7D8C8), onSecondary = Color(0xFF0E382D),
    tertiary = Color(0xFFFFB0CE), onTertiary = Color(0xFF5C1136),
    background = Color(0xFF14121B), surface = Color(0xFF1C1925),
    surfaceVariant = Color(0xFF3A3645), onSurface = Color(0xFFE7E1EC),
    onSurfaceVariant = Color(0xFFCAC4D3), outline = Color(0xFF958E9F),
    error = Color(0xFFFFB4AB), onError = Color(0xFF690005),
)

private val Sakura = Palette(
    primary = Color(0xFF9E3F58), onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFFFD9E2), onPrimaryContainer = Color(0xFF3E0018),
    secondary = Color(0xFF6A5A9E), onSecondary = Color(0xFFFFFFFF),
    tertiary = Color(0xFF3F6B5A), onTertiary = Color(0xFFFFFFFF),
    background = Color(0xFFFDF6F4), surface = Color(0xFFFFFBFA),
    surfaceVariant = Color(0xFFF0E2E2), onSurface = Color(0xFF221A1C),
    onSurfaceVariant = Color(0xFF534649), outline = Color(0xFF857278),
    error = Color(0xFFB3261E), onError = Color(0xFFFFFFFF),
)

private val SakuraDark = Palette(
    primary = Color(0xFFFFB1C6), onPrimary = Color(0xFF5F112C),
    primaryContainer = Color(0xFF7E2A44), onPrimaryContainer = Color(0xFFFFD9E2),
    secondary = Color(0xFFCFC1FF), onSecondary = Color(0xFF352A61),
    tertiary = Color(0xFFA8D5C4), onTertiary = Color(0xFF10382B),
    background = Color(0xFF1B1215), surface = Color(0xFF241A1D),
    surfaceVariant = Color(0xFF47383C), onSurface = Color(0xFFF0DFE2),
    onSurfaceVariant = Color(0xFFD7C1C6), outline = Color(0xFFA58C92),
    error = Color(0xFFFFB4AB), onError = Color(0xFF690005),
)

private val Matcha = Palette(
    primary = Color(0xFF3F6B34), onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFBFEFAF), onPrimaryContainer = Color(0xFF0A2004),
    secondary = Color(0xFF59647E), onSecondary = Color(0xFFFFFFFF),
    tertiary = Color(0xFF8F4E3F), onTertiary = Color(0xFFFFFFFF),
    background = Color(0xFFF7F7EE), surface = Color(0xFFFDFCF4),
    surfaceVariant = Color(0xFFE4E5D6), onSurface = Color(0xFF1B1E16),
    onSurfaceVariant = Color(0xFF474B3F), outline = Color(0xFF767A6C),
    error = Color(0xFFB3261E), onError = Color(0xFFFFFFFF),
)

private val MatchaDark = Palette(
    primary = Color(0xFFA5D394), onPrimary = Color(0xFF0C3900),
    primaryContainer = Color(0xFF28511C), onPrimaryContainer = Color(0xFFBFEFAF),
    secondary = Color(0xFFBCC6E0), onSecondary = Color(0xFF262F44),
    tertiary = Color(0xFFF0B6A1), onTertiary = Color(0xFF522014),
    background = Color(0xFF11140E), surface = Color(0xFF191D15),
    surfaceVariant = Color(0xFF3B4034), onSurface = Color(0xFFE3E4D8),
    onSurfaceVariant = Color(0xFFC5C7B8), outline = Color(0xFF8F9383),
    error = Color(0xFFFFB4AB), onError = Color(0xFF690005),
)

private val Amber = Palette(
    primary = Color(0xFF8A5A00), onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFFFDFA0), onPrimaryContainer = Color(0xFF2C1A00),
    secondary = Color(0xFF326B63), onSecondary = Color(0xFFFFFFFF),
    tertiary = Color(0xFF7B4E7E), onTertiary = Color(0xFFFFFFFF),
    background = Color(0xFFFBF6EA), surface = Color(0xFFFFFCF3),
    surfaceVariant = Color(0xFFEDE3D0), onSurface = Color(0xFF201B12),
    onSurfaceVariant = Color(0xFF4E4639), outline = Color(0xFF7E7565),
    error = Color(0xFFB3261E), onError = Color(0xFFFFFFFF),
)

private val AmberDark = Palette(
    primary = Color(0xFFFFC94D), onPrimary = Color(0xFF3C2500),
    primaryContainer = Color(0xFF5C3E00), onPrimaryContainer = Color(0xFFFFDFA0),
    secondary = Color(0xFF9FD6C9), onSecondary = Color(0xFF003731),
    tertiary = Color(0xFFE5BDE6), onTertiary = Color(0xFF48254C),
    background = Color(0xFF16120A), surface = Color(0xFF1F1A11),
    surfaceVariant = Color(0xFF433C2E), onSurface = Color(0xFFEDE4D6),
    onSurfaceVariant = Color(0xFFD0C6B6), outline = Color(0xFF9A9181),
    error = Color(0xFFFFB4AB), onError = Color(0xFF690005),
)

private val Indigo = Palette(
    primary = Color(0xFF2E4E9E), onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFDCE3FF), onPrimaryContainer = Color(0xFF00174B),
    secondary = Color(0xFF9A4528), onSecondary = Color(0xFFFFFFFF),
    tertiary = Color(0xFF6B5E00), onTertiary = Color(0xFFFFFFFF),
    background = Color(0xFFF5F6FB), surface = Color(0xFFFCFBFF),
    surfaceVariant = Color(0xFFE2E2EC), onSurface = Color(0xFF1A1B21),
    onSurfaceVariant = Color(0xFF46464F), outline = Color(0xFF74747E),
    error = Color(0xFFB3261E), onError = Color(0xFFFFFFFF),
)

private val IndigoDark = Palette(
    primary = Color(0xFFB4C5FF), onPrimary = Color(0xFF0B2B6E),
    primaryContainer = Color(0xFF27458F), onPrimaryContainer = Color(0xFFDCE3FF),
    secondary = Color(0xFFFFB59D), onSecondary = Color(0xFF5B1B05),
    tertiary = Color(0xFFE3C74E), onTertiary = Color(0xFF372F00),
    background = Color(0xFF10121A), surface = Color(0xFF181A23),
    surfaceVariant = Color(0xFF383A44), onSurface = Color(0xFFE2E1E8),
    onSurfaceVariant = Color(0xFFC6C5D0), outline = Color(0xFF90909B),
    error = Color(0xFFFFB4AB), onError = Color(0xFF690005),
)

private val Slate = Palette(
    primary = Color(0xFF4A5A66), onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFD3E5F0), onPrimaryContainer = Color(0xFF0A1F29),
    secondary = Color(0xFF8A4F35), onSecondary = Color(0xFFFFFFFF),
    tertiary = Color(0xFF5C5A8A), onTertiary = Color(0xFFFFFFFF),
    background = Color(0xFFF6F5F1), surface = Color(0xFFFCFBF8),
    surfaceVariant = Color(0xFFE3E2DC), onSurface = Color(0xFF1B1C1C),
    onSurfaceVariant = Color(0xFF48494A), outline = Color(0xFF767878),
    error = Color(0xFFB3261E), onError = Color(0xFFFFFFFF),
)

private val SlateDark = Palette(
    primary = Color(0xFFB9C9D5), onPrimary = Color(0xFF23313B),
    primaryContainer = Color(0xFF3A4A56), onPrimaryContainer = Color(0xFFD3E5F0),
    secondary = Color(0xFFE8B7A1), onSecondary = Color(0xFF4F2414),
    tertiary = Color(0xFFC5C0F0), onTertiary = Color(0xFF2D2A57),
    background = Color(0xFF101314), surface = Color(0xFF181C1D),
    surfaceVariant = Color(0xFF3B4042), onSurface = Color(0xFFE3E3E1),
    onSurfaceVariant = Color(0xFFC6C7C5), outline = Color(0xFF909493),
    error = Color(0xFFFFB4AB), onError = Color(0xFF690005),
)

private val Ember = Palette(
    primary = Color(0xFF9A3B25), onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFFFDBD1), onPrimaryContainer = Color(0xFF3A0B00),
    secondary = Color(0xFF4F6350), onSecondary = Color(0xFFFFFFFF),
    tertiary = Color(0xFF5A5E9E), onTertiary = Color(0xFFFFFFFF),
    background = Color(0xFFFBF5EF), surface = Color(0xFFFFFBF6),
    surfaceVariant = Color(0xFFEDE1D7), onSurface = Color(0xFF211A16),
    onSurfaceVariant = Color(0xFF50453D), outline = Color(0xFF80746A),
    error = Color(0xFFB3261E), onError = Color(0xFFFFFFFF),
)

private val EmberDark = Palette(
    primary = Color(0xFFFFB4A0), onPrimary = Color(0xFF5C1906),
    primaryContainer = Color(0xFF7E2C19), onPrimaryContainer = Color(0xFFFFDBD1),
    secondary = Color(0xFFB6CCB4), onSecondary = Color(0xFF223423),
    tertiary = Color(0xFFC4C3F0), onTertiary = Color(0xFF2D2D5F),
    background = Color(0xFF17110D), surface = Color(0xFF201915),
    surfaceVariant = Color(0xFF453A33), onSurface = Color(0xFFEDE0D8),
    onSurfaceVariant = Color(0xFFD2C4BB), outline = Color(0xFF9C8E85),
    error = Color(0xFFFFB4AB), onError = Color(0xFF690005),
)

private val TealPreview = ThemePreview(
    Color(0xFFF7F4EC), Color(0xFF176077), Color(0xFF8A5A2B),
    Color(0xFF8F4E63), Color(0xFF1B2428),
)
private val LavenderPreview = ThemePreview(
    Color(0xFFF8F6FC), Color(0xFF5B4B9A), Color(0xFF2E6F5E),
    Color(0xFF9A3F6B), Color(0xFF1D1B22),
)
private val SakuraPreview = ThemePreview(
    Color(0xFFFDF6F4), Color(0xFF9E3F58), Color(0xFF6A5A9E),
    Color(0xFF3F6B5A), Color(0xFF221A1C),
)
private val MatchaPreview = ThemePreview(
    Color(0xFFF7F7EE), Color(0xFF3F6B34), Color(0xFF59647E),
    Color(0xFF8F4E3F), Color(0xFF1B1E16),
)
private val AmberPreview = ThemePreview(
    Color(0xFFFBF6EA), Color(0xFF8A5A00), Color(0xFF326B63),
    Color(0xFF7B4E7E), Color(0xFF201B12),
)
private val IndigoPreview = ThemePreview(
    Color(0xFFF5F6FB), Color(0xFF2E4E9E), Color(0xFF9A4528),
    Color(0xFF6B5E00), Color(0xFF1A1B21),
)
private val SlatePreview = ThemePreview(
    Color(0xFFF6F5F1), Color(0xFF4A5A66), Color(0xFF8A4F35),
    Color(0xFF5C5A8A), Color(0xFF1B1C1C),
)
private val EmberPreview = ThemePreview(
    Color(0xFFFBF5EF), Color(0xFF9A3B25), Color(0xFF4F6350),
    Color(0xFF5A5E9E), Color(0xFF211A16),
)

enum class AppTheme(
    val id: String,
    val label: String,
    val description: String,
    val preview: ThemePreview,
) {
    TEAL("teal", "青灯", "冷青与铜色，清透纸感", TealPreview),
    LAVENDER("lavender", "紫夜", "灰紫与苔绿，低饱和夜色", LavenderPreview),
    SAKURA("sakura", "樱纸", "绯粉与墨绿，柔和和纸", SakuraPreview),
    MATCHA("matcha", "苔庭", "苔绿与雾蓝，自然安静", MatchaPreview),
    AMBER("amber", "琥珀", "琥珀与松绿，旧书暖光", AmberPreview),
    INDIGO("indigo", "靛蓝", "靛蓝与珊瑚，深夜强对比", IndigoPreview),
    SLATE("slate", "墨灰", "石墨与铁锈，克制工具感", SlatePreview),
    EMBER("ember", "枫烬", "砖红与橄榄，戏剧性", EmberPreview),
    ;

    companion object {
        fun fromId(id: String): AppTheme = entries.firstOrNull { it.id == id } ?: AMBER
    }
}

internal fun colorSchemeFor(theme: AppTheme, dark: Boolean): ColorScheme {
    val palette = when (theme) {
        AppTheme.TEAL -> if (dark) TealDark else Teal
        AppTheme.LAVENDER -> if (dark) LavenderDark else Lavender
        AppTheme.SAKURA -> if (dark) SakuraDark else Sakura
        AppTheme.MATCHA -> if (dark) MatchaDark else Matcha
        AppTheme.AMBER -> if (dark) AmberDark else Amber
        AppTheme.INDIGO -> if (dark) IndigoDark else Indigo
        AppTheme.SLATE -> if (dark) SlateDark else Slate
        AppTheme.EMBER -> if (dark) EmberDark else Ember
    }
    return palette.toScheme(dark)
}

@Composable
fun LightnovelTheme(
    themeId: String = AppTheme.AMBER.id,
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colors = colorSchemeFor(AppTheme.fromId(themeId), darkTheme)
    val extended = LnExtendedColors.from(colors)
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as? Activity)?.window ?: return@SideEffect
            WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = !darkTheme
                isAppearanceLightNavigationBars = !darkTheme
            }
        }
    }
    CompositionLocalProvider(LocalLnColors provides extended) {
        MaterialTheme(
            colorScheme = colors,
            content = content,
        )
    }
}
