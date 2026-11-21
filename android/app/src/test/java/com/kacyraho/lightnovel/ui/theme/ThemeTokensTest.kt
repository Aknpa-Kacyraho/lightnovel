package com.kacyraho.lightnovel.ui.theme

import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import org.junit.Assert.assertEquals
import org.junit.Test

class ThemeTokensTest {
    @Test
    fun bodyUsesChineseLineHeight() {
        assertEquals(16.sp, LnTypography.bodyLarge.fontSize)
        assertEquals(26.sp, LnTypography.bodyLarge.lineHeight)
        assertEquals(14.sp, LnTypography.bodyMedium.fontSize)
        assertEquals(22.sp, LnTypography.bodyMedium.lineHeight)
    }

    @Test
    fun titleIsCompactAndSemiBold() {
        assertEquals(20.sp, LnTypography.titleLarge.fontSize)
        assertEquals(28.sp, LnTypography.titleLarge.lineHeight)
        assertEquals(FontWeight.SemiBold, LnTypography.titleLarge.fontWeight)
    }

    @Test
    fun labelsDoNotCompressChineseTracking() {
        assertEquals(0.sp, LnTypography.labelLarge.letterSpacing)
        assertEquals(0.sp, LnTypography.labelMedium.letterSpacing)
        assertEquals(12.sp, LnTypography.labelMedium.fontSize)
    }
}
