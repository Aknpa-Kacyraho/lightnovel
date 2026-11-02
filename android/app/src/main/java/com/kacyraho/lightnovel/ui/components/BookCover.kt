package com.kacyraho.lightnovel.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.kacyraho.lightnovel.ui.theme.lnColors

enum class BookCoverSize(
    val maxChars: Int,
    val maxLines: Int,
    val fontSize: TextUnit,
    val lineHeight: TextUnit,
    val padding: Dp,
    val shortFontSize: TextUnit,
    val shortLineHeight: TextUnit,
) {
    COMPACT(8, 3, 10.sp, 12.sp, 4.dp, 15.sp, 17.sp),
    TINY(10, 3, 11.sp, 13.sp, 4.dp, 16.sp, 18.sp),
    SMALL(14, 4, 12.sp, 14.sp, 5.dp, 18.sp, 21.sp),
    MEDIUM(20, 4, 14.sp, 17.sp, 6.dp, 22.sp, 26.sp),
    LARGE(30, 5, 18.sp, 22.sp, 8.dp, 30.sp, 36.sp),
}

internal object BookCoverLabel {
    private val ignoredMarks = setOf(
        '【', '】', '〔', '〕', '〖', '〗', '〘', '〙', '〚', '〛',
        '「', '」', '『', '』', '（', '）', '(', ')', '[', ']', '{', '}',
        '〈', '〉', '《', '》', '“', '”', '"', '\'', '#',
    )
    private val trailingMarks = setOf(
        '，', '。', '、', '！', '？', ',', '.', '!', '?', ':', '：', ';', '；', '…', '—',
    )

    fun of(title: String, maxChars: Int = 12): String {
        val trimmed = title.trim()
        val base = trimmed.filterNot { it in ignoredMarks }.trim()
        if (base.isBlank()) return "书"
        val codePoints = base.codePoints().toArray()
        return String(codePoints, 0, codePoints.size.coerceAtMost(maxChars))
            .trim()
            .trimEnd { it in trailingMarks }
            .ifBlank { "书" }
    }
}

@Composable
fun BookCover(
    title: String,
    modifier: Modifier = Modifier,
    size: BookCoverSize = BookCoverSize.SMALL,
) {
    val colors = lnColors()
    val label = remember(title, size) { BookCoverLabel.of(title, size.maxChars) }
    val brush = remember(colors.coverStart, colors.coverEnd) {
        Brush.linearGradient(listOf(colors.coverStart, colors.coverEnd))
    }
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(12.dp))
            .background(brush)
            .semantics { contentDescription = "《$title》封面" },
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(size.padding),
            contentAlignment = Alignment.Center,
        ) {
            val short = label.length <= 2
            Text(
                text = label,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
                style = MaterialTheme.typography.titleSmall.copy(
                    fontSize = if (short) size.shortFontSize else size.fontSize,
                    lineHeight = if (short) size.shortLineHeight else size.lineHeight,
                ),
                fontFamily = FontFamily.Serif,
                fontWeight = FontWeight.SemiBold,
                textAlign = TextAlign.Center,
                maxLines = size.maxLines,
                overflow = TextOverflow.Clip,
            )
        }
    }
}
