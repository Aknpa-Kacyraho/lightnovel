package com.kacyraho.lightnovel.core.settings

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

data class AppSettings(
    val appTheme: String = "amber",
    val themeMode: String = "system",
    val readerFontSizeSp: Float = 18f,
    val readerLineHeight: Float = 1.7f,
    val readerMarginDp: Float = 16f,
    val readerParagraphSpacing: Float = 8f,
    val readerFontFamily: String = "serif",
    val readerKeepScreenOn: Boolean = false,
    val readerTheme: String = "paper",
    val readerDisplayMode: String = "translated",
    val readerMode: String = "page",
    val deepSeekBaseUrl: String = "https://api.deepseek.com/chat/completions",
    val deepSeekModel: String = "deepseek-flash",
    val translationProviderId: String = "deepseek",
    val translationMode: String = TranslationMode.AUTO.wire,
    val translationMaxChars: Int = 3_000,
    val translationMaxTokens: Int = 8_192,
    val translationCalibrationKey: String = "",
    val translationCalibratedAt: String = "",
    val translationCalibrationNote: String = "",
    val noveliaBaseUrl: String = "https://n.novelia.cc/api/",
    val lastBackupAt: String? = null,
    val catalogCrawlAt: Long = 0L,
)

private val Context.lightnovelSettings: DataStore<Preferences> by preferencesDataStore(
    name = "lightnovel_settings",
)

class SettingsStore(
    private val context: Context,
) {
    val settings: Flow<AppSettings> = context.lightnovelSettings.data.map { it.toSettings() }

    suspend fun update(transform: (AppSettings) -> AppSettings) {
        context.lightnovelSettings.edit { prefs ->
            val merged = transform(prefs.toSettings())
            prefs[Keys.APP_THEME] = merged.appTheme
            prefs[Keys.THEME_MODE] = merged.themeMode
            prefs[Keys.FONT_SIZE] = merged.readerFontSizeSp
            prefs[Keys.LINE_HEIGHT] = merged.readerLineHeight
            prefs[Keys.MARGIN] = merged.readerMarginDp
            prefs[Keys.PARAGRAPH_SPACING] = merged.readerParagraphSpacing
            prefs[Keys.FONT_FAMILY] = merged.readerFontFamily
            prefs[Keys.KEEP_SCREEN_ON] = merged.readerKeepScreenOn
            prefs[Keys.THEME] = merged.readerTheme
            prefs[Keys.DISPLAY_MODE] = merged.readerDisplayMode
            prefs[Keys.READER_MODE] = merged.readerMode
            prefs[Keys.BASE_URL] = merged.deepSeekBaseUrl
            prefs[Keys.MODEL] = merged.deepSeekModel
            prefs[Keys.TRANSLATION_PROVIDER] = merged.translationProviderId
            prefs[Keys.TRANSLATION_MODE] = merged.translationMode
            prefs[Keys.TRANSLATION_MAX_CHARS] = merged.translationMaxChars
            prefs[Keys.TRANSLATION_MAX_TOKENS] = merged.translationMaxTokens
            prefs[Keys.TRANSLATION_CALIBRATION_KEY] = merged.translationCalibrationKey
            prefs[Keys.TRANSLATION_CALIBRATED_AT] = merged.translationCalibratedAt
            prefs[Keys.TRANSLATION_CALIBRATION_NOTE] = merged.translationCalibrationNote
            prefs[Keys.NOVELIA_BASE_URL] = merged.noveliaBaseUrl
            prefs[Keys.CATALOG_CRAWL_AT] = merged.catalogCrawlAt
            merged.lastBackupAt?.let { prefs[Keys.LAST_BACKUP_AT] = it }
                ?: prefs.remove(Keys.LAST_BACKUP_AT)
        }
    }

    private fun Preferences.toSettings(): AppSettings = AppSettings(
        appTheme = this[Keys.APP_THEME] ?: "amber",
        themeMode = this[Keys.THEME_MODE] ?: "system",
        readerFontSizeSp = this[Keys.FONT_SIZE] ?: 18f,
        readerLineHeight = this[Keys.LINE_HEIGHT] ?: 1.7f,
        readerMarginDp = this[Keys.MARGIN] ?: 16f,
        readerParagraphSpacing = this[Keys.PARAGRAPH_SPACING] ?: 8f,
        readerFontFamily = this[Keys.FONT_FAMILY] ?: "serif",
        readerKeepScreenOn = this[Keys.KEEP_SCREEN_ON] ?: false,
        readerTheme = this[Keys.THEME] ?: "paper",
        readerDisplayMode = this[Keys.DISPLAY_MODE] ?: "translated",
        readerMode = this[Keys.READER_MODE] ?: "page",
        deepSeekBaseUrl = this[Keys.BASE_URL]
            ?: "https://api.deepseek.com/chat/completions",
        deepSeekModel = this[Keys.MODEL] ?: "deepseek-flash",
        translationProviderId = this[Keys.TRANSLATION_PROVIDER] ?: "deepseek",
        translationMode = this[Keys.TRANSLATION_MODE] ?: TranslationMode.AUTO.wire,
        translationMaxChars = this[Keys.TRANSLATION_MAX_CHARS] ?: 3_000,
        translationMaxTokens = this[Keys.TRANSLATION_MAX_TOKENS] ?: 8_192,
        translationCalibrationKey = this[Keys.TRANSLATION_CALIBRATION_KEY] ?: "",
        translationCalibratedAt = this[Keys.TRANSLATION_CALIBRATED_AT] ?: "",
        translationCalibrationNote = this[Keys.TRANSLATION_CALIBRATION_NOTE] ?: "",
        noveliaBaseUrl = this[Keys.NOVELIA_BASE_URL] ?: "https://n.novelia.cc/api/",
        lastBackupAt = this[Keys.LAST_BACKUP_AT],
        catalogCrawlAt = this[Keys.CATALOG_CRAWL_AT] ?: 0L,
    )

    private object Keys {
        val APP_THEME = stringPreferencesKey("app_theme")
        val THEME_MODE = stringPreferencesKey("theme_mode")
        val FONT_SIZE = floatPreferencesKey("reader_font_size_sp")
        val LINE_HEIGHT = floatPreferencesKey("reader_line_height")
        val MARGIN = floatPreferencesKey("reader_margin_dp")
        val PARAGRAPH_SPACING = floatPreferencesKey("reader_paragraph_spacing")
        val FONT_FAMILY = stringPreferencesKey("reader_font_family")
        val KEEP_SCREEN_ON = booleanPreferencesKey("reader_keep_screen_on")
        val THEME = stringPreferencesKey("reader_theme")
        val DISPLAY_MODE = stringPreferencesKey("reader_display_mode")
        val READER_MODE = stringPreferencesKey("reader_mode")
        val BASE_URL = stringPreferencesKey("deepseek_base_url")
        val MODEL = stringPreferencesKey("deepseek_model")
        val TRANSLATION_PROVIDER = stringPreferencesKey("translation_provider")
        val TRANSLATION_MODE = stringPreferencesKey("translation_mode")
        val TRANSLATION_MAX_CHARS = intPreferencesKey("translation_max_chars")
        val TRANSLATION_MAX_TOKENS = intPreferencesKey("translation_max_tokens")
        val TRANSLATION_CALIBRATION_KEY = stringPreferencesKey("translation_calibration_key")
        val TRANSLATION_CALIBRATED_AT = stringPreferencesKey("translation_calibrated_at")
        val TRANSLATION_CALIBRATION_NOTE = stringPreferencesKey("translation_calibration_note")
        val NOVELIA_BASE_URL = stringPreferencesKey("novelia_base_url")
        val LAST_BACKUP_AT = stringPreferencesKey("last_backup_at")
        val CATALOG_CRAWL_AT = longPreferencesKey("catalog_crawl_at")
    }
}
