package com.kacyraho.lightnovel.feature.settings

import android.content.ContentResolver
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kacyraho.lightnovel.core.settings.ApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.settings.TranslationMode
import com.kacyraho.lightnovel.core.settings.TranslationProviders
import com.kacyraho.lightnovel.core.storage.CacheManager
import com.kacyraho.lightnovel.data.export.BackupExporter
import com.kacyraho.lightnovel.data.online.NoveliaAccountService
import com.kacyraho.lightnovel.data.online.NoveliaClient
import com.kacyraho.lightnovel.data.translation.CalibrationOutcome
import com.kacyraho.lightnovel.data.translation.DeepSeekClient
import com.kacyraho.lightnovel.data.translation.TranslationCalibrator
import com.kacyraho.lightnovel.data.translation.TranslationClient
import java.time.Instant
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class SettingsUiState(
    val loading: Boolean = true,
    val baseUrl: String = "https://api.deepseek.com/chat/completions",
    val model: String = "deepseek-flash",
    val providerId: String = "deepseek",
    val translationMode: String = TranslationMode.AUTO.wire,
    val maxTokensInput: String = "8192",
    val calibratedMaxChars: Int = 3_000,
    val calibratedAt: String = "",
    val calibrationNote: String = "",
    val calibrating: Boolean = false,
    val testing: Boolean = false,
    val calibrationMessage: String? = null,
    val keyInput: String = "",
    val hasKey: Boolean = false,
    val lastBackupAt: String? = null,
    val appTheme: String = "amber",
    val themeMode: String = "system",
    val readerFontSizeSp: Float = 18f,
    val readerLineHeight: Float = 1.7f,
    val readerMarginDp: Float = 16f,
    val readerParagraphSpacing: Float = 8f,
    val readerFontFamily: String = "serif",
    val readerKeepScreenOn: Boolean = false,
    val cacheBytes: Long = 0,
    val cacheFiles: Int = 0,
    val clearingCache: Boolean = false,
    val readerTheme: String = "paper",
    val readerDisplayMode: String = "translated",
    val readerMode: String = "page",
    val autoTranslateWhileReading: Boolean = true,
    val translateAheadChapters: Int = 3,
    val translateBackfillChapters: Int = 5,
    val noveliaBaseUrl: String = "https://n.novelia.cc/api/",
    val loggedIn: Boolean = false,
    val username: String = "",
    val password: String = "",
    val accountMessage: String? = null,
    val accountBusy: Boolean = false,
    val saving: Boolean = false,
    val exporting: Boolean = false,
    val message: String? = null,
    val error: String? = null,
)

class SettingsViewModel(
    private val settingsStore: SettingsStore,
    private val apiKeyStore: ApiKeyStore,
    private val backupExporter: BackupExporter,
    private val noveliaClient: NoveliaClient,
    private val accountService: NoveliaAccountService,
    private val cacheManager: CacheManager,
    private val clientFactory: (String, String) -> TranslationClient = { base, key ->
        DeepSeekClient(base, key)
    },
    private val calibrator: TranslationCalibrator = TranslationCalibrator(),
) : ViewModel() {
    private val _state = MutableStateFlow(SettingsUiState())
    val state: StateFlow<SettingsUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            val settings = settingsStore.settings.first()
            val usage = withContext(Dispatchers.IO) { cacheManager.usage() }
            noveliaClient.setBaseUrl(settings.noveliaBaseUrl)
            val scope = TranslationProviders.keyScope(settings.deepSeekBaseUrl)
            _state.value = SettingsUiState(
                loading = false,
                baseUrl = settings.deepSeekBaseUrl,
                model = settings.deepSeekModel,
                providerId = settings.translationProviderId,
                translationMode = settings.translationMode,
                maxTokensInput = settings.translationMaxTokens.toString(),
                calibratedMaxChars = settings.translationMaxChars,
                calibratedAt = settings.translationCalibratedAt,
                calibrationNote = settings.translationCalibrationNote,
                hasKey = !apiKeyStore.load(scope).isNullOrBlank(),
                lastBackupAt = settings.lastBackupAt,
                appTheme = settings.appTheme,
                themeMode = settings.themeMode,
                readerFontSizeSp = settings.readerFontSizeSp,
                readerLineHeight = settings.readerLineHeight,
                readerMarginDp = settings.readerMarginDp,
                readerParagraphSpacing = settings.readerParagraphSpacing,
                readerFontFamily = settings.readerFontFamily,
                readerKeepScreenOn = settings.readerKeepScreenOn,
                readerTheme = settings.readerTheme,
                readerDisplayMode = settings.readerDisplayMode,
                readerMode = settings.readerMode,
                autoTranslateWhileReading = settings.autoTranslateWhileReading,
                translateAheadChapters = settings.translateAheadChapters,
                translateBackfillChapters = settings.translateBackfillChapters,
                noveliaBaseUrl = settings.noveliaBaseUrl,
                loggedIn = accountService.isLoggedIn(),
                cacheBytes = usage.bytes,
                cacheFiles = usage.files,
            )
        }
    }


    fun clearCache() {
        if (_state.value.clearingCache) return
        viewModelScope.launch {
            _state.value = _state.value.copy(clearingCache = true, message = "正在清理缓存")
            val before = withContext(Dispatchers.IO) { cacheManager.clear() }
            _state.value = _state.value.copy(
                clearingCache = false,
                cacheBytes = 0,
                cacheFiles = 0,
                message = "已清理 ${formatBytes(before.bytes)} 缓存",
            )
        }
    }

    fun setUsername(value: String) {
        _state.value = _state.value.copy(username = value, accountMessage = null)
    }

    fun setPassword(value: String) {
        _state.value = _state.value.copy(password = value, accountMessage = null)
    }

    fun login() {
        val current = _state.value
        if (current.accountBusy) return
        viewModelScope.launch {
            _state.value = current.copy(accountBusy = true, accountMessage = null)
            runCatching { accountService.login(current.username, current.password) }
                .onSuccess {
                    _state.value = _state.value.copy(
                        accountBusy = false,
                        loggedIn = true,
                        password = "",
                        accountMessage = "登录成功",
                    )
                }
                .onFailure {
                    _state.value = _state.value.copy(
                        accountBusy = false,
                        accountMessage = it.message ?: "登录失败",
                    )
                }
        }
    }

    fun logout() {
        accountService.logout()
        _state.value = _state.value.copy(loggedIn = false, accountMessage = "已退出登录")
    }

    fun importFavorites() {
        if (_state.value.accountBusy) return
        viewModelScope.launch {
            _state.value = _state.value.copy(accountBusy = true, accountMessage = "正在导入收藏")
            runCatching { accountService.importFavorites() }
                .onSuccess {
                    _state.value = _state.value.copy(
                        accountBusy = false,
                        accountMessage = it.message,
                    )
                }
                .onFailure {
                    _state.value = _state.value.copy(
                        accountBusy = false,
                        accountMessage = it.message ?: "导入收藏失败",
                    )
                }
        }
    }

    fun importHistory() {
        if (_state.value.accountBusy) return
        viewModelScope.launch {
            _state.value = _state.value.copy(accountBusy = true, accountMessage = "正在导入历史")
            runCatching { accountService.importHistory() }
                .onSuccess {
                    _state.value = _state.value.copy(
                        accountBusy = false,
                        accountMessage = it.message,
                    )
                }
                .onFailure {
                    _state.value = _state.value.copy(
                        accountBusy = false,
                        accountMessage = it.message ?: "导入历史失败",
                    )
                }
        }
    }

    fun setNoveliaBaseUrl(value: String) {
        val normalized = value.trim().trimEnd('/') + "/"
        _state.value = _state.value.copy(noveliaBaseUrl = normalized)
        noveliaClient.setBaseUrl(normalized)
        viewModelScope.launch {
            settingsStore.update { it.copy(noveliaBaseUrl = normalized) }
        }
    }

    fun setAppTheme(value: String) {
        _state.value = _state.value.copy(appTheme = value)
        viewModelScope.launch {
            settingsStore.update { it.copy(appTheme = value) }
        }
    }

    fun setThemeMode(value: String) {
        if (value !in setOf("system", "light", "dark")) return
        _state.value = _state.value.copy(themeMode = value)
        viewModelScope.launch {
            settingsStore.update { it.copy(themeMode = value) }
        }
    }

    fun selectProvider(id: String) {
        val preset = TranslationProviders.preset(id)
        val current = _state.value
        val baseUrl = if (preset.id == "custom") current.baseUrl else preset.baseUrl
        val model = if (preset.id == "custom") current.model else preset.defaultModel
        val scope = TranslationProviders.keyScope(baseUrl)
        _state.value = current.copy(
            providerId = preset.id,
            baseUrl = baseUrl,
            model = model,
            hasKey = !apiKeyStore.load(scope).isNullOrBlank(),
            message = null,
            error = null,
            calibrationMessage = null,
        )
    }

    fun setBaseUrl(value: String) {
        val scope = TranslationProviders.keyScope(value)
        _state.value = _state.value.copy(
            baseUrl = value,
            providerId = TranslationProviders.detectId(value),
            hasKey = !apiKeyStore.load(scope).isNullOrBlank(),
            message = null,
            error = null,
        )
    }

    fun setModel(value: String) {
        _state.value = _state.value.copy(model = value, message = null, error = null)
    }

    fun setTranslationMode(value: String) {
        val mode = TranslationMode.fromWire(value)
        _state.value = _state.value.copy(
            translationMode = mode.wire,
            message = null,
            error = null,
        )
    }

    fun setMaxTokens(value: String) {
        _state.value = _state.value.copy(maxTokensInput = value, message = null, error = null)
    }

    fun setReaderFontSize(value: Float) {
        val size = value.coerceIn(12f, 30f)
        _state.value = _state.value.copy(readerFontSizeSp = size)
        viewModelScope.launch {
            settingsStore.update { it.copy(readerFontSizeSp = size) }
        }
    }

    fun setReaderLineHeight(value: Float) {
        val height = value.coerceIn(1.2f, 2.4f)
        _state.value = _state.value.copy(readerLineHeight = height)
        viewModelScope.launch {
            settingsStore.update { it.copy(readerLineHeight = height) }
        }
    }

    fun setReaderMargin(value: Float) {
        val margin = value.coerceIn(8f, 48f)
        _state.value = _state.value.copy(readerMarginDp = margin)
        viewModelScope.launch { settingsStore.update { it.copy(readerMarginDp = margin) } }
    }

    fun setReaderParagraphSpacing(value: Float) {
        val spacing = value.coerceIn(0f, 32f)
        _state.value = _state.value.copy(readerParagraphSpacing = spacing)
        viewModelScope.launch { settingsStore.update { it.copy(readerParagraphSpacing = spacing) } }
    }

    fun setReaderFontFamily(value: String) {
        _state.value = _state.value.copy(readerFontFamily = value)
        viewModelScope.launch {
            settingsStore.update { it.copy(readerFontFamily = value) }
        }
    }

    fun setReaderKeepScreenOn(value: Boolean) {
        _state.value = _state.value.copy(readerKeepScreenOn = value)
        viewModelScope.launch { settingsStore.update { it.copy(readerKeepScreenOn = value) } }
    }

    fun setReaderTheme(value: String) {
        _state.value = _state.value.copy(readerTheme = value)
        viewModelScope.launch {
            settingsStore.update { it.copy(readerTheme = value) }
        }
    }

    fun setReaderDisplayMode(value: String) {
        _state.value = _state.value.copy(readerDisplayMode = value)
        viewModelScope.launch {
            settingsStore.update { it.copy(readerDisplayMode = value) }
        }
    }

    fun setReaderMode(value: String) {
        _state.value = _state.value.copy(readerMode = value)
        viewModelScope.launch {
            settingsStore.update { it.copy(readerMode = value) }
        }
    }

    fun setAutoTranslateWhileReading(value: Boolean) {
        _state.value = _state.value.copy(autoTranslateWhileReading = value)
        viewModelScope.launch {
            settingsStore.update { it.copy(autoTranslateWhileReading = value) }
        }
    }

    fun setTranslateAheadChapters(value: Int) {
        val count = value.coerceIn(0, 10)
        _state.value = _state.value.copy(translateAheadChapters = count)
        viewModelScope.launch {
            settingsStore.update { it.copy(translateAheadChapters = count) }
        }
    }

    fun setTranslateBackfillChapters(value: Int) {
        val count = value.coerceIn(0, 10)
        _state.value = _state.value.copy(translateBackfillChapters = count)
        viewModelScope.launch {
            settingsStore.update { it.copy(translateBackfillChapters = count) }
        }
    }

    fun setKey(value: String) {
        _state.value = _state.value.copy(keyInput = value, message = null, error = null)
    }

    fun testConnection() {
        val current = _state.value
        val baseUrl = TranslationProviders.normalizeBaseUrl(current.baseUrl)
        val model = current.model.trim()
        val maxTokens = parseMaxTokens(current.maxTokensInput)
        if (baseUrl.isBlank() || model.isBlank()) {
            _state.value = current.copy(error = "端点和模型不能为空")
            return
        }
        val scope = TranslationProviders.keyScope(baseUrl)
        val key = current.keyInput.trim().ifBlank {
            apiKeyStore.load(scope).orEmpty()
        }
        if (TranslationProviders.requiresKey(baseUrl) && key.isBlank()) {
            _state.value = current.copy(error = "请先填写 API Key")
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(
                testing = true,
                message = null,
                error = null,
                calibrationMessage = "正在测试连接…",
            )
            when (
                val outcome = calibrator.probe(
                    client = clientFactory(baseUrl, key),
                    model = model,
                    maxTokens = maxTokens,
                    preferredMode = TranslationMode.fromWire(current.translationMode),
                )
            ) {
                is CalibrationOutcome.Success -> {
                    val result = outcome.result
                    _state.value = _state.value.copy(
                        testing = false,
                        calibrationMessage = null,
                        message = "连接成功：${modeLabel(result.mode)}，" +
                            "${result.latencyMs} ms",
                    )
                }
                is CalibrationOutcome.Failure -> {
                    _state.value = _state.value.copy(
                        testing = false,
                        calibrationMessage = null,
                        error = "连接失败：${outcome.message}",
                    )
                }
            }
        }
    }

    fun recalibrate() {
        save(forceCalibration = true)
    }

    fun save(forceCalibration: Boolean = false) {
        val current = _state.value
        val baseUrl = TranslationProviders.normalizeBaseUrl(current.baseUrl)
        val model = current.model.trim()
        val maxTokens = parseMaxTokens(current.maxTokensInput)
        if (baseUrl.isBlank() || model.isBlank()) {
            _state.value = current.copy(error = "端点和模型不能为空")
            return
        }
        val scope = TranslationProviders.keyScope(baseUrl)
        val key = current.keyInput.trim().ifBlank {
            apiKeyStore.load(scope).orEmpty()
        }
        if (TranslationProviders.requiresKey(baseUrl) && key.isBlank()) {
            _state.value = current.copy(error = "请先填写 API Key")
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(
                saving = true,
                message = null,
                error = null,
                calibrationMessage = null,
            )
            val previous = settingsStore.settings.first()
            val calibrationKey = TranslationProviders.calibrationKey(baseUrl, model)
            val selected = TranslationMode.fromWire(current.translationMode)
            val modeToSave = if (
                selected == TranslationMode.AUTO &&
                previous.translationCalibrationKey == calibrationKey &&
                previous.translationMode != TranslationMode.AUTO.wire
            ) {
                previous.translationMode
            } else {
                current.translationMode
            }
            val saved = runCatching {
                settingsStore.update {
                    it.copy(
                        deepSeekBaseUrl = baseUrl,
                        deepSeekModel = model,
                        translationProviderId = current.providerId,
                        translationMode = modeToSave,
                        translationMaxTokens = maxTokens,
                    )
                }
                if (current.keyInput.isNotBlank()) {
                    apiKeyStore.save(scope, key)
                }
            }
            if (saved.isFailure) {
                _state.value = _state.value.copy(
                    saving = false,
                    error = saved.exceptionOrNull()?.message ?: "保存失败",
                )
                return@launch
            }

            val needsCalibration = forceCalibration ||
                previous.translationCalibrationKey != calibrationKey ||
                previous.translationMode == TranslationMode.AUTO.wire ||
                (selected != TranslationMode.AUTO && selected.wire != previous.translationMode)

            if (!needsCalibration) {
                _state.value = _state.value.copy(
                    saving = false,
                    keyInput = "",
                    hasKey = !apiKeyStore.load(scope).isNullOrBlank(),
                    message = "已保存，沿用上次校准：${modeLabel(TranslationMode.fromWire(modeToSave))} / " +
                        "${previous.translationMaxChars} 字/块",
                )
                return@launch
            }

            _state.value = _state.value.copy(
                saving = false,
                calibrating = true,
                calibrationMessage = "已保存端点，正在识别协议…",
                message = "首次接入会花少量 token 测安全翻译范围",
            )
            val outcome = calibrator.calibrate(
                client = clientFactory(baseUrl, key),
                model = model,
                maxTokens = maxTokens,
                preferredMode = selected,
                isLocal = TranslationProviders.isLocal(baseUrl),
            ) { progress ->
                _state.value = _state.value.copy(calibrationMessage = progress)
            }
            when (outcome) {
                is CalibrationOutcome.Success -> {
                    val result = outcome.result
                    val calibratedAt = Instant.now().toString()
                    settingsStore.update {
                        it.copy(
                            translationMode = result.mode.wire,
                            translationMaxChars = result.maxChars,
                            translationMaxTokens = maxTokens,
                            translationCalibrationKey = calibrationKey,
                            translationCalibratedAt = calibratedAt,
                            translationCalibrationNote = result.note,
                        )
                    }
                    _state.value = _state.value.copy(
                        calibrating = false,
                        calibrationMessage = null,
                        keyInput = "",
                        hasKey = !apiKeyStore.load(scope).isNullOrBlank(),
                        translationMode = result.mode.wire,
                        calibratedMaxChars = result.maxChars,
                        calibratedAt = calibratedAt,
                        calibrationNote = result.note,
                        message = "校准完成：${modeLabel(result.mode)} / " +
                            "${result.maxChars} 字/块 / ${maxTokens} tokens",
                    )
                }
                is CalibrationOutcome.Failure -> {
                    _state.value = _state.value.copy(
                        calibrating = false,
                        calibrationMessage = null,
                        keyInput = "",
                        hasKey = !apiKeyStore.load(scope).isNullOrBlank(),
                        error = "校准失败：${outcome.message}",
                        message = "端点已保存；翻译暂用默认 3000 字/块",
                    )
                }
            }
        }
    }

    private fun parseMaxTokens(value: String): Int =
        value.trim().toIntOrNull()?.coerceIn(1_024, 131_072) ?: 8_192

    private fun modeLabel(mode: TranslationMode): String = when (mode) {
        TranslationMode.SAKURA -> "Sakura"
        TranslationMode.BATCH -> "编号批量"
        TranslationMode.AUTO -> "自动"
    }

    fun exportBackup(uri: Uri, resolver: ContentResolver) {
        if (_state.value.exporting) return
        viewModelScope.launch {
            _state.value = _state.value.copy(
                exporting = true,
                message = "正在导出备份",
                error = null,
            )
            runCatching {
                resolver.openOutputStream(uri)?.use { output ->
                    backupExporter.export(output)
                } ?: error("无法创建备份文件")
                val now = Instant.now().toString()
                settingsStore.update { it.copy(lastBackupAt = now) }
                now
            }.onSuccess { at ->
                _state.value = _state.value.copy(
                    exporting = false,
                    lastBackupAt = at,
                    message = "备份已导出",
                )
            }.onFailure {
                _state.value = _state.value.copy(
                    exporting = false,
                    error = it.message ?: "导出失败",
                )
            }
        }
    }
}

fun formatBytes(value: Long): String {
    val units = listOf("B", "KB", "MB", "GB")
    var amount = value.toDouble()
    var unit = 0
    while (amount >= 1024 && unit < units.lastIndex) {
        amount /= 1024
        unit++
    }
    return if (unit == 0) "${amount.toLong()} ${units[unit]}"
    else String.format(java.util.Locale.US, "%.1f %s", amount, units[unit])
}
