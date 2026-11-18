package com.kacyraho.lightnovel.feature.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SettingsFocusTest {
    @Test
    fun acceptsBackup() {
        assertEquals(SettingsFocus.BACKUP, SettingsFocus.parse("backup"))
    }

    @Test
    fun trimsWhitespace() {
        assertEquals(SettingsFocus.BACKUP, SettingsFocus.parse(" backup "))
    }

    @Test
    fun ignoresUnknownTarget() {
        assertNull(SettingsFocus.parse("network"))
        assertNull(SettingsFocus.parse(""))
        assertNull(SettingsFocus.parse(null))
    }
}
