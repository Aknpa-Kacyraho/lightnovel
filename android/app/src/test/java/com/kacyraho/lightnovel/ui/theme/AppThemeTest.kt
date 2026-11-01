package com.kacyraho.lightnovel.ui.theme

import org.junit.Assert.assertEquals
import org.junit.Test

class AppThemeTest {
    @Test
    fun fallsBackToAmberForUnknownTheme() {
        assertEquals(AppTheme.AMBER, AppTheme.fromId("unknown"))
        assertEquals(AppTheme.LAVENDER, AppTheme.fromId("lavender"))
        assertEquals(AppTheme.SAKURA, AppTheme.fromId("sakura"))
        assertEquals(AppTheme.MATCHA, AppTheme.fromId("matcha"))
        assertEquals(AppTheme.AMBER, AppTheme.fromId("amber"))
        assertEquals(AppTheme.INDIGO, AppTheme.fromId("indigo"))
        assertEquals(AppTheme.SLATE, AppTheme.fromId("slate"))
        assertEquals(AppTheme.EMBER, AppTheme.fromId("ember"))
    }
}
