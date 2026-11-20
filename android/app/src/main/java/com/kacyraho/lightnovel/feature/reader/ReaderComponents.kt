package com.kacyraho.lightnovel.feature.reader

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.kacyraho.lightnovel.reader.engine.ReaderTheme
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun TranslationStatusDot(
    status: TranslationStatus,
    modifier: Modifier = Modifier,
) {
    val color = when (status) {
        TranslationStatus.UNTRANSLATED -> MaterialTheme.colorScheme.onSurfaceVariant
        TranslationStatus.QUEUED -> MaterialTheme.colorScheme.secondary
        TranslationStatus.TRANSLATING -> MaterialTheme.colorScheme.secondary
        TranslationStatus.TRANSLATED -> MaterialTheme.colorScheme.primary
        TranslationStatus.FAILED -> MaterialTheme.colorScheme.error
        TranslationStatus.STALE -> MaterialTheme.colorScheme.tertiary
    }
    val label = when (status) {
        TranslationStatus.UNTRANSLATED -> "未翻译"
        TranslationStatus.QUEUED -> "排队中"
        TranslationStatus.TRANSLATING -> "翻译中"
        TranslationStatus.TRANSLATED -> "已翻译"
        TranslationStatus.FAILED -> "翻译不完整"
        TranslationStatus.STALE -> "译文已过期"
    }
    androidx.compose.foundation.layout.Box(
        modifier = modifier
            .size(10.dp)
            .clip(CircleShape)
            .background(color)
            .semantics { contentDescription = label },
    )
}

@Composable
fun StaleBanner(
    reasons: Set<StaleReason>,
    reason: StaleBannerReason?,
    theme: ReaderTheme,
    enabled: Boolean,
    onRetranslate: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (reasons.isEmpty() || reason == null) return
    var collapsed by remember { mutableStateOf(false) }
    val background = if (theme == ReaderTheme.NIGHT) {
        Color(0xFF3B2A17)
    } else {
        Color(0xFFFFF1DC)
    }
    val foreground = if (theme == ReaderTheme.NIGHT) {
        Color(0xFFFFCC80)
    } else {
        Color(0xFF7A4A00)
    }
    val text = when (if (collapsed) StaleBannerReason.COLLAPSED else reason) {
        StaleBannerReason.GLOSSARY -> "术语表已更新，当前译文需要重译。"
        StaleBannerReason.MODEL_PROMPT -> "模型或提示词已更新，建议重译本章。"
        StaleBannerReason.SOURCE -> "原文已更新，当前译文可能过期。"
        StaleBannerReason.MERGED_SOURCE_GLOSSARY ->
            "原文与术语表都已更新，建议重译本章。"
        StaleBannerReason.MERGED_SOURCE_MODEL ->
            "原文与翻译配置都已更新，建议重译本章。"
        StaleBannerReason.MERGED_GLOSSARY_MODEL ->
            "术语表与翻译配置都已更新，建议重译本章。"
        StaleBannerReason.MERGED_ALL ->
            "原文、术语表和翻译配置都已更新，建议重译本章。"
        StaleBannerReason.ORIGINAL_REFRESH ->
            "原文已更新，当前显示的是新原文。"
        StaleBannerReason.COLLAPSED -> "译文已过期"
    }
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(background)
            .clickable { collapsed = !collapsed }
            .padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = if (collapsed) "译文已过期" else text,
            modifier = Modifier.weight(1f),
            style = MaterialTheme.typography.bodySmall,
            color = foreground,
        )
        if (!collapsed) {
            TextButton(onClick = onRetranslate, enabled = enabled) {
                Text("重译", color = foreground)
            }
        }
        TextButton(onClick = { collapsed = !collapsed }) {
            Text(if (collapsed) "展开" else "收起", color = foreground)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChapterInfoSheet(
    info: ReaderChapterInfo?,
    reasons: Set<StaleReason>,
    theme: ReaderTheme,
    onDismiss: () -> Unit,
    onRetranslate: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = theme.background,
        contentColor = theme.text,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("本章翻译信息", style = MaterialTheme.typography.titleMedium, color = theme.text)
            if (info == null) {
                Text(
                    "本章还没有翻译信息。翻译本章后，这里会显示模型、费用、内容指纹和旧版本差异。",
                    style = MaterialTheme.typography.bodySmall,
                    color = theme.secondary,
                )
            } else {
                InfoRow("模型", info.model, theme)
                InfoRow("翻译时间", formatTime(info.translatedAt), theme)
                InfoRow("Token", "${info.tokensIn} / ${info.tokensOut}", theme)
                InfoRow("估算费用", "¥${"%.4f".format(info.costCny)}", theme)
                InfoRow("未完成段落", info.incompleteParagraphs.toString(), theme)
                InfoRow("内容指纹", info.cacheKey, theme)
                InfoRow(
                    "旧版本",
                    if (info.oldVersionAvailable) {
                        "已保存${info.oldTranslatedAt?.let { " · ${formatTime(it)}" }.orEmpty()}"
                    } else {
                        "无"
                    },
                    theme,
                )
                InfoRow("与旧版差异", "${info.changedParagraphs} 段", theme)
                if (reasons.isNotEmpty()) {
                    InfoRow("过期原因", staleLabels(reasons), theme)
                }
            }
            HorizontalDivider(color = theme.secondary.copy(alpha = 0.3f))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
            ) {
                TextButton(onClick = onDismiss) { Text("关闭", color = theme.text) }
                TextButton(onClick = onRetranslate) { Text("重译本章", color = theme.text) }
            }
        }
    }
}

@Composable
private fun InfoRow(
    label: String,
    value: String,
    theme: ReaderTheme,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = theme.secondary)
        Text(value, style = MaterialTheme.typography.bodySmall, color = theme.text)
    }
}

private fun staleLabels(reasons: Set<StaleReason>): String = buildList {
    if (StaleReason.SOURCE in reasons) add("原文更新")
    if (StaleReason.GLOSSARY in reasons) add("术语表更新")
    if (StaleReason.MODEL_PROMPT in reasons) add("模型/提示词更新")
    if (StaleReason.ORIGINAL_REFRESH in reasons) add("原文刷新")
}.joinToString("、")

private fun formatTime(value: String): String = runCatching {
    DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")
        .withZone(ZoneId.systemDefault())
        .format(Instant.parse(value))
}.getOrDefault(value)

@Composable
fun ReaderTopBar(
    bookTitle: String,
    chapterTitle: String,
    fontSizeSp: Float,
    status: TranslationStatus,
    hasTranslation: Boolean,
    textColor: Color,
    secondaryColor: Color,
    translationRunning: Boolean,
    onBack: () -> Unit,
    onFontSizeChange: (Float) -> Unit,
    onThemeChange: () -> Unit,
    onRetranslate: () -> Unit,
    onPolish: () -> Unit,
    onOpenMemory: (() -> Unit)?,
    onOpenWorldline: () -> Unit,
    onOpenQuery: () -> Unit,
    queryMode: Boolean,
    onToggleQueryMode: () -> Unit,
    onShowInfo: () -> Unit,
    onShowGlossary: () -> Unit,
    onShowParagraph: () -> Unit,
    onToggleImmersive: () -> Unit,
    charCount: Int = 0,
    costLabel: String? = null,
) {
    val buttonColors = androidx.compose.material3.ButtonDefaults.textButtonColors(
        contentColor = textColor,
        disabledContentColor = textColor.copy(alpha = 0.38f),
    )
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        TextButton(onClick = onBack, colors = buttonColors) { Text("返回") }
        TranslationStatusDot(status = status, modifier = Modifier.padding(end = 8.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = bookTitle.ifBlank { "阅读" },
                style = MaterialTheme.typography.titleSmall,
                color = textColor,
                maxLines = 1,
            )
            Text(
                text = chapterTitle,
                style = MaterialTheme.typography.bodySmall,
                color = secondaryColor,
                maxLines = 1,
            )
        }
        TranslationMenu(
            enabled = !translationRunning,
            hasTranslation = hasTranslation,
            textColor = textColor,
            fontSizeSp = fontSizeSp,
            onFontSizeChange = onFontSizeChange,
            onThemeChange = onThemeChange,
            onRetranslate = onRetranslate,
            onPolish = onPolish,
            onOpenMemory = onOpenMemory,
            onOpenWorldline = onOpenWorldline,
            onOpenQuery = onOpenQuery,
            queryMode = queryMode,
            onToggleQueryMode = onToggleQueryMode,
            onShowInfo = onShowInfo,
            onShowGlossary = onShowGlossary,
            onShowParagraph = onShowParagraph,
            onToggleImmersive = onToggleImmersive,
            charCount = charCount,
            costLabel = costLabel,
        )
    }
}

@Composable
fun ReaderBottomBar(
    pageLabel: String?,
    chapterIndex: Int,
    chapterCount: Int,
    kind: String,
    textColor: Color,
    secondaryColor: Color,
    onPrev: () -> Unit,
    onNext: () -> Unit,
    onToc: () -> Unit,
    progress: Float = 0f,
) {
    val buttonColors = androidx.compose.material3.ButtonDefaults.textButtonColors(
        contentColor = textColor,
        disabledContentColor = textColor.copy(alpha = 0.38f),
    )
    Column(modifier = Modifier.fillMaxWidth()) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(2.dp)
                .background(textColor.copy(alpha = 0.10f)),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth(progress.coerceIn(0f, 1f))
                    .fillMaxHeight()
                    .background(textColor.copy(alpha = 0.28f)),
            )
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = onPrev, enabled = chapterIndex > 1, colors = buttonColors) {
                Text("上一章")
            }
            TextButton(onClick = onToc, colors = buttonColors) { Text("目录") }
            Text(
                text = listOfNotNull(
                    pageLabel,
                    if (chapterCount > 0) "$chapterIndex/$chapterCount" else null,
                    kindLabel(kind),
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = secondaryColor,
            )
            TextButton(
                onClick = onNext,
                enabled = chapterCount > 0 && chapterIndex < chapterCount,
                colors = buttonColors,
            ) {
                Text("下一章")
            }
        }
    }
}

@Composable
fun LanguageModeMenu(
    mode: String,
    hasTranslation: Boolean,
    textColor: Color,
    onSelect: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    val label = when (mode) {
        "raw" -> "原文"
        "bilingual" -> "双语"
        else -> "译文"
    }
    Box {
        TextButton(
            onClick = { expanded = true },
            colors = androidx.compose.material3.ButtonDefaults.textButtonColors(contentColor = textColor),
        ) {
            Text("语言：$label")
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            listOf("translated" to "译文", "raw" to "原文", "bilingual" to "双语").forEach { (id, name) ->
                DropdownMenuItem(
                    text = { Text(name) },
                    enabled = id != "bilingual" || hasTranslation,
                    onClick = {
                        expanded = false
                        onSelect(id)
                    },
                )
            }
        }
    }
}

@Composable
private fun TranslationMenu(
    enabled: Boolean,
    hasTranslation: Boolean,
    textColor: Color,
    fontSizeSp: Float,
    onFontSizeChange: (Float) -> Unit,
    onThemeChange: () -> Unit,
    onRetranslate: () -> Unit,
    onPolish: () -> Unit,
    onOpenMemory: (() -> Unit)?,
    onOpenWorldline: () -> Unit,
    onOpenQuery: () -> Unit,
    queryMode: Boolean,
    onToggleQueryMode: () -> Unit,
    onShowInfo: () -> Unit,
    onShowGlossary: () -> Unit,
    onShowParagraph: () -> Unit,
    onToggleImmersive: () -> Unit,
    charCount: Int = 0,
    costLabel: String? = null,
) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        TextButton(
            onClick = { expanded = true },
            colors = androidx.compose.material3.ButtonDefaults.textButtonColors(
                contentColor = textColor,
                disabledContentColor = textColor.copy(alpha = 0.38f),
            ),
        ) {
            Text("更多")
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            val items = readerMenuItems(
                fontSizeSp = fontSizeSp,
                hasTranslation = hasTranslation,
                translationEnabled = enabled,
                hasStoryMemory = onOpenMemory != null,
                queryMode = queryMode,
                charCount = charCount,
                costLabel = costLabel,
            )
            var renderedGroup: ReaderMenuGroup? = null
            items.forEach { item ->
                if (item.group != renderedGroup) {
                    if (renderedGroup != null) HorizontalDivider()
                    Text(
                        text = item.group.label,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 2.dp),
                    )
                    renderedGroup = item.group
                }
                DropdownMenuItem(
                    text = { Text(item.label) },
                    enabled = item.enabled,
                    onClick = {
                        expanded = false
                        when (item.action) {
                            ReaderMenuAction.FONT_DECREASE -> onFontSizeChange(fontSizeSp - 1f)
                            ReaderMenuAction.FONT_INCREASE -> onFontSizeChange(fontSizeSp + 1f)
                            ReaderMenuAction.TOGGLE_THEME -> onThemeChange()
                            ReaderMenuAction.IMMERSIVE -> onToggleImmersive()
                            ReaderMenuAction.TRANSLATE -> onRetranslate()
                            ReaderMenuAction.POLISH -> onPolish()
                            ReaderMenuAction.CHAPTER_INFO -> onShowInfo()
                            ReaderMenuAction.STORY_MEMORY -> onOpenMemory?.invoke()
                            ReaderMenuAction.NEARBY_ENTITIES -> onOpenQuery()
                            ReaderMenuAction.QUERY_MODE -> onToggleQueryMode()
                            ReaderMenuAction.GLOSSARY -> onShowGlossary()
                            ReaderMenuAction.PARAGRAPH -> onShowParagraph()
                            ReaderMenuAction.WORLDLINE -> onOpenWorldline()
                        }
                    },
                )
            }
        }
    }
}

private fun kindLabel(kind: String): String = when (kind) {
    "complete" -> "已译"
    "translated" -> "有译文"
    "partial" -> "未译全"
    "raw" -> "生肉"
    "missing" -> "缺正文"
    else -> kind
}
