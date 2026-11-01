package com.kacyraho.lightnovel.feature.settings

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kacyraho.lightnovel.AppContainer
import com.kacyraho.lightnovel.core.settings.TranslationProviders
import com.kacyraho.lightnovel.reader.engine.ReaderTheme
import com.kacyraho.lightnovel.ui.components.BrandFilterChip
import com.kacyraho.lightnovel.ui.theme.AppTheme
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun SettingsRoute(
    container: AppContainer,
    onBack: (() -> Unit)? = null,
) {
    val viewModel: SettingsViewModel = viewModel {
        SettingsViewModel(
            settingsStore = container.settingsStore,
            apiKeyStore = container.apiKeyStore,
            backupExporter = container.backupExporter,
            noveliaClient = container.noveliaClient,
            accountService = container.noveliaAccountService,
            cacheManager = container.cacheManager,
        )
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.CreateDocument("application/zip"),
    ) { uri ->
        uri?.let { viewModel.exportBackup(it, context.contentResolver) }
    }
    SettingsScreen(
        state = state,
        onBack = onBack,
        onAppThemeChange = viewModel::setAppTheme,
        onThemeModeChange = viewModel::setThemeMode,
        onProviderSelect = viewModel::selectProvider,
        onBaseUrlChange = viewModel::setBaseUrl,
        onModelChange = viewModel::setModel,
        onTranslationModeChange = viewModel::setTranslationMode,
        onMaxTokensChange = viewModel::setMaxTokens,
        onKeyChange = viewModel::setKey,
        onTestConnection = viewModel::testConnection,
        onRecalibrate = viewModel::recalibrate,
        onFontSizeChange = viewModel::setReaderFontSize,
        onLineHeightChange = viewModel::setReaderLineHeight,
        onMarginChange = viewModel::setReaderMargin,
        onParagraphSpacingChange = viewModel::setReaderParagraphSpacing,
        onFontFamilyChange = viewModel::setReaderFontFamily,
        onKeepScreenOnChange = viewModel::setReaderKeepScreenOn,
        onThemeChange = viewModel::setReaderTheme,
        onDisplayModeChange = viewModel::setReaderDisplayMode,
        onReaderModeChange = viewModel::setReaderMode,
        onNoveliaBaseUrlChange = viewModel::setNoveliaBaseUrl,
        onUsernameChange = viewModel::setUsername,
        onPasswordChange = viewModel::setPassword,
        onLogin = viewModel::login,
        onLogout = viewModel::logout,
        onImportFavorites = viewModel::importFavorites,
        onImportHistory = viewModel::importHistory,
        onSave = { viewModel.save() },
        onExport = { launcher.launch("lightnovel-backup-${System.currentTimeMillis()}.zip") },
        onClearCache = viewModel::clearCache,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    state: SettingsUiState,
    onBack: (() -> Unit)?,
    onAppThemeChange: (String) -> Unit,
    onThemeModeChange: (String) -> Unit,
    onProviderSelect: (String) -> Unit,
    onBaseUrlChange: (String) -> Unit,
    onModelChange: (String) -> Unit,
    onTranslationModeChange: (String) -> Unit,
    onMaxTokensChange: (String) -> Unit,
    onKeyChange: (String) -> Unit,
    onTestConnection: () -> Unit,
    onRecalibrate: () -> Unit,
    onFontSizeChange: (Float) -> Unit,
    onLineHeightChange: (Float) -> Unit,
    onMarginChange: (Float) -> Unit,
    onParagraphSpacingChange: (Float) -> Unit,
    onFontFamilyChange: (String) -> Unit,
    onKeepScreenOnChange: (Boolean) -> Unit,
    onThemeChange: (String) -> Unit,
    onDisplayModeChange: (String) -> Unit,
    onReaderModeChange: (String) -> Unit,
    onNoveliaBaseUrlChange: (String) -> Unit,
    onUsernameChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onLogin: () -> Unit,
    onLogout: () -> Unit,
    onImportFavorites: () -> Unit,
    onImportHistory: () -> Unit,
    onSave: () -> Unit,
    onExport: () -> Unit,
    onClearCache: () -> Unit,
) {
    var advanced by rememberSaveable { mutableStateOf(false) }
    var confirmClear by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("设置") },
                navigationIcon = {
                    onBack?.let { back ->
                        TextButton(onClick = back) { Text("返回") }
                    }
                },
            )
        },
        modifier = Modifier.testTag("settings-screen"),
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            SettingsGroup("外观") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BrandFilterChip(
                        selected = state.themeMode == "system",
                        onClick = { onThemeModeChange("system") },
                        label = { Text("跟随系统") },
                    )
                    BrandFilterChip(
                        selected = state.themeMode == "light",
                        onClick = { onThemeModeChange("light") },
                        label = { Text("浅色") },
                    )
                    BrandFilterChip(
                        selected = state.themeMode == "dark",
                        onClick = { onThemeModeChange("dark") },
                        label = { Text("深色") },
                    )
                }
                Text(
                    "选择一套适合当前阅读心情的配色；标签和状态色会一起变化。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                AppTheme.entries.chunked(2).forEach { rowThemes ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        rowThemes.forEach { theme ->
                            ThemePreviewCard(
                                theme = theme,
                                selected = state.appTheme == theme.id,
                                onClick = { onAppThemeChange(theme.id) },
                                modifier = Modifier.weight(1f),
                            )
                        }
                        if (rowThemes.size == 1) Spacer(Modifier.weight(1f))
                    }
                }
            }

            SettingsGroup("阅读") {
                Text("阅读纸色", style = MaterialTheme.typography.titleSmall)
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    ReaderTheme.entries.forEach { theme ->
                        BrandFilterChip(
                            selected = state.readerTheme == theme.id,
                            onClick = { onThemeChange(theme.id) },
                            label = { Text(theme.label) },
                        )
                    }
                }
                SliderRow(
                    label = "字号",
                    value = state.readerFontSizeSp,
                    valueText = "${state.readerFontSizeSp.toInt()} sp",
                    range = 12f..30f,
                    onValueChange = onFontSizeChange,
                )
                SliderRow(
                    label = "行距",
                    value = state.readerLineHeight,
                    valueText = String.format(java.util.Locale.US, "%.1f", state.readerLineHeight),
                    range = 1.2f..2.4f,
                    onValueChange = onLineHeightChange,
                )
                SliderRow(
                    label = "页边距",
                    value = state.readerMarginDp,
                    valueText = "${state.readerMarginDp.toInt()} dp",
                    range = 8f..48f,
                    onValueChange = onMarginChange,
                )
                SliderRow(
                    label = "段距",
                    value = state.readerParagraphSpacing,
                    valueText = "${state.readerParagraphSpacing.toInt()} dp",
                    range = 0f..32f,
                    onValueChange = onParagraphSpacingChange,
                )
                Text("字体", style = MaterialTheme.typography.titleSmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("serif" to "宋体", "sans" to "黑体", "mono" to "等宽").forEach {
                        (id, label) ->
                        BrandFilterChip(
                            selected = state.readerFontFamily == id,
                            onClick = { onFontFamilyChange(id) },
                            label = { Text(label) },
                        )
                    }
                }
                Text("显示", style = MaterialTheme.typography.titleSmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(
                        "translated" to "译文",
                        "raw" to "原文",
                        "bilingual" to "双语",
                    ).forEach { (id, label) ->
                        BrandFilterChip(
                            selected = state.readerDisplayMode == id,
                            onClick = { onDisplayModeChange(id) },
                            label = { Text(label) },
                        )
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BrandFilterChip(
                        selected = state.readerMode == "page",
                        onClick = { onReaderModeChange("page") },
                        label = { Text("左右翻页") },
                    )
                    BrandFilterChip(
                        selected = state.readerMode == "scroll",
                        onClick = { onReaderModeChange("scroll") },
                        label = { Text("上下滚动") },
                    )
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        "阅读时保持屏幕常亮",
                        modifier = Modifier.weight(1f),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Switch(
                        checked = state.readerKeepScreenOn,
                        onCheckedChange = onKeepScreenOnChange,
                    )
                }
            }

            SettingsGroup("翻译 API") {
                val preset = TranslationProviders.preset(state.providerId)
                Text(
                    when {
                        preset.local -> "本地端点通常不需要 Key"
                        state.hasKey -> "已配置 Key"
                        else -> "还没有配置 Key"
                    },
                    style = MaterialTheme.typography.titleSmall,
                    color = if (preset.local || state.hasKey) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.tertiary,
                )
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    TranslationProviders.presets.forEach { item ->
                        BrandFilterChip(
                            selected = state.providerId == item.id,
                            onClick = { onProviderSelect(item.id) },
                            label = { Text(item.label) },
                        )
                    }
                }
                Text(
                    preset.hint,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedTextField(
                    value = state.keyInput,
                    onValueChange = onKeyChange,
                    modifier = Modifier.fillMaxWidth(),
                    label = {
                        Text(
                            when {
                                preset.local -> "API Key（本地可留空）"
                                state.hasKey -> "API Key（已配置，留空不改）"
                                else -> "API Key"
                            },
                        )
                    },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                )
                TextButton(onClick = { advanced = !advanced }) {
                    Text(if (advanced) "收起高级设置" else "高级设置")
                }
                if (advanced) {
                    OutlinedTextField(
                        value = state.baseUrl,
                        onValueChange = onBaseUrlChange,
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Base URL") },
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = state.model,
                        onValueChange = onModelChange,
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("模型") },
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = state.maxTokensInput,
                        onValueChange = onMaxTokensChange,
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("最大输出 tokens") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    )
                    Text(
                        "协议",
                        style = MaterialTheme.typography.titleSmall,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(
                            "auto" to "自动识别",
                            "batch" to "编号批量",
                            "sakura" to "Sakura",
                        ).forEach { (id, label) ->
                            BrandFilterChip(
                                selected = state.translationMode == id,
                                onClick = { onTranslationModeChange(id) },
                                label = { Text(label) },
                            )
                        }
                    }
                    Text(
                        "推理模型或长章节可把输出上限调到 16384～32768；" +
                            "部分供应商上限更低，校准会报错。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (state.calibratedAt.isNotBlank()) {
                    Text(
                        "已校准：${state.calibratedMaxChars} 字/块 · " +
                            state.calibrationNote,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (state.calibrating || state.testing) {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                    state.calibrationMessage?.let {
                        Text(
                            it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(
                        onClick = onTestConnection,
                        enabled = !state.saving && !state.calibrating && !state.testing,
                    ) {
                        Text(if (state.testing) "测试中…" else "测试连接")
                    }
                    OutlinedButton(
                        onClick = onRecalibrate,
                        enabled = !state.saving && !state.calibrating && !state.testing,
                    ) {
                        Text("重新校准")
                    }
                }
                state.message?.let {
                    Text(it, color = MaterialTheme.colorScheme.primary)
                }
                state.error?.let {
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
                Button(
                    onClick = onSave,
                    enabled = !state.saving && !state.calibrating && !state.testing,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        when {
                            state.saving -> "保存中…"
                            state.calibrating -> "校准中…"
                            else -> "保存并校准"
                        },
                    )
                }
                Text(
                    "首次接入新端点/模型会自动测安全块大小，只发内置样章、不碰你的书；" +
                        "Key 只保存在本机 Keystore。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            SettingsGroup("数据") {
                Text(
                    text = state.lastBackupAt?.let { "上次备份：${formatBackupTime(it)}" }
                        ?: "还没有备份；卸载 App 会丢失本地书库。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedButton(
                    onClick = onExport,
                    enabled = !state.exporting,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(if (state.exporting) "导出中…" else "导出备份 zip")
                }
                HorizontalDivider()
                Text(
                    "翻译缓存 / 旧版本：${formatBytes(state.cacheBytes)} · ${state.cacheFiles} 个文件",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedButton(
                    onClick = { confirmClear = true },
                    enabled = !state.clearingCache && state.cacheFiles > 0,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(if (state.clearingCache) "清理中…" else "清理缓存")
                }
            }

            SettingsGroup("关于") {
                Text("Ka小说家", style = MaterialTheme.typography.titleMedium)
                Text(
                    "本地优先的日文轻小说阅读与翻译工具。直连 Kakuyomu / 成为小说家吧；不登录、不上传书库。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }

    if (confirmClear) {
        AlertDialog(
            onDismissRequest = { confirmClear = false },
            title = { Text("清理翻译缓存？") },
            text = { Text("只删除翻译缓存和旧版本，不会删除书、阅读进度或 API Key。") },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmClear = false
                        onClearCache()
                    },
                ) {
                    Text("清理缓存")
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmClear = false }) { Text("取消") }
            },
        )
    }
}

@Composable
private fun SettingsGroup(
    title: String,
    content: @Composable () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            content()
        }
    }
}

@Composable
private fun ThemePreviewCard(
    theme: AppTheme,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val preview = theme.preview
    Card(
        modifier = modifier,
        onClick = onClick,
        shape = RoundedCornerShape(12.dp),
        border = BorderStroke(
            if (selected) 2.dp else 1.dp,
            if (selected) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.outlineVariant,
        ),
        colors = CardDefaults.cardColors(containerColor = preview.background),
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                listOf(preview.primary, preview.secondary, preview.tertiary).forEach { color ->
                    Box(
                        modifier = Modifier
                            .size(22.dp)
                            .clip(RoundedCornerShape(6.dp))
                            .background(color),
                    )
                }
            }
            Spacer(Modifier.height(6.dp))
            Text(
                text = theme.label,
                color = preview.onBackground,
                style = MaterialTheme.typography.titleSmall,
            )
            Text(
                text = theme.description,
                color = preview.onBackground.copy(alpha = 0.65f),
                style = MaterialTheme.typography.labelSmall,
                maxLines = 1,
            )
            Text(
                text = "Aa",
                color = preview.primary,
                style = MaterialTheme.typography.titleLarge,
            )
        }
    }
}

@Composable
private fun SliderRow(
    label: String,
    value: Float,
    valueText: String,
    range: ClosedFloatingPointRange<Float>,
    onValueChange: (Float) -> Unit,
) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(label, style = MaterialTheme.typography.bodyMedium)
            Text(valueText, style = MaterialTheme.typography.bodySmall)
        }
        Slider(
            value = value.coerceIn(range.start, range.endInclusive),
            onValueChange = onValueChange,
            valueRange = range,
        )
    }
}

private fun formatBackupTime(value: String): String = runCatching {
    DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")
        .withZone(ZoneId.systemDefault())
        .format(Instant.parse(value))
}.getOrDefault(value)
