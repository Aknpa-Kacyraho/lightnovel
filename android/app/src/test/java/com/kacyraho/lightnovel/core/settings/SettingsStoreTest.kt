package com.kacyraho.lightnovel.core.settings

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class SettingsStoreTest {
    @Test
    fun updatesSettingsAndKeepsCurrentValues() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val store = SettingsStore(context)

        val initial = store.settings.first()
        assertEquals("deepseek-flash", initial.deepSeekModel)
        assertEquals("amber", initial.appTheme)
        assertEquals("system", initial.themeMode)
        assertNull(initial.lastBackupAt)

        store.update {
            it.copy(
                appTheme = "sakura",
                readerFontSizeSp = 22f,
                deepSeekModel = "custom-model",
                translationMode = "sakura",
                translationMaxChars = 5_400,
                translationMaxTokens = 16_384,
                translationCalibrationKey = "endpoint|model",
                translationCalibratedAt = "2026-11-01T00:00:00Z",
                translationCalibrationNote = "tested 6000",
                lastBackupAt = "2026-10-28T00:00:00Z",
            )
        }
        store.update { it.copy(readerLineHeight = 1.9f) }

        val updated = store.settings.first()
        assertEquals("sakura", updated.appTheme)
        assertEquals(22f, updated.readerFontSizeSp)
        assertEquals(1.9f, updated.readerLineHeight)
        assertEquals("custom-model", updated.deepSeekModel)
        assertEquals("sakura", updated.translationMode)
        assertEquals(5_400, updated.translationMaxChars)
        assertEquals(16_384, updated.translationMaxTokens)
        assertEquals("endpoint|model", updated.translationCalibrationKey)
        assertEquals("2026-11-01T00:00:00Z", updated.translationCalibratedAt)
        assertEquals("tested 6000", updated.translationCalibrationNote)
        assertEquals("2026-10-28T00:00:00Z", updated.lastBackupAt)
    }
}
