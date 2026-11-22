package com.kacyraho.lightnovel.feature.reader

import com.kacyraho.lightnovel.reader.engine.ReaderBlock

/**
 * 滚动阅读的「行号」与段落模型的「段号」映射。
 *
 * - 行号：`chapterBlocks` 的下标（章节文本按换行切分），只用于列表滚动；
 * - 段号：`paragraphs` 的下标（Paragraphs.split），用于分页锚点、书签、进度与知识库。
 *
 * 持久化只存段号；滚动模式显示前换算成起始行号。
 */
/**
 * Builds the scroll list from the same paragraph blocks used by Paragraphs.split,
 * inserting exactly one empty item between paragraphs. The empty item keeps the
 * line<->paragraph mapping honest for single-newline source text; the UI renders
 * it with zero height.
 */
internal fun readerScrollBlocks(
    blocks: List<ReaderBlock>,
    fallbackText: String,
): List<String> {
    if (blocks.isEmpty()) return listOf(fallbackText)
    return blocks.flatMapIndexed { index, block ->
        val lines = block.text.split("\n")
        if (index == 0) lines else listOf("") + lines
    }.map { it.trimEnd() }
}

internal fun paragraphDisplayText(paragraph: ReaderParagraph, displayMode: String): String =
    when (displayMode) {
        "raw" -> paragraph.source
        "bilingual" -> listOfNotNull(
            paragraph.source.takeIf(String::isNotBlank),
            paragraph.translated?.takeIf(String::isNotBlank),
        ).joinToString("\n")
        else -> paragraph.translated ?: paragraph.source
    }

internal fun paragraphIndexForLine(
    paragraphs: List<ReaderParagraph>,
    displayMode: String,
    line: Int,
): Int {
    if (paragraphs.isEmpty()) return 0
    val safeLine = line.coerceAtLeast(0)
    var cursor = 0
    paragraphs.forEachIndexed { index, paragraph ->
        val lines = paragraphDisplayText(paragraph, displayMode)
            .split("\n")
            .size
            .coerceAtLeast(1)
        if (safeLine < cursor + lines) return index
        cursor += lines
        if (index < paragraphs.lastIndex) cursor += 1
    }
    return paragraphs.lastIndex
}

internal fun lineForParagraph(
    paragraphs: List<ReaderParagraph>,
    displayMode: String,
    paragraphIndex: Int,
): Int {
    if (paragraphs.isEmpty()) return 0
    val target = paragraphIndex.coerceIn(0, paragraphs.lastIndex)
    var cursor = 0
    for (index in 0 until target) {
        cursor += paragraphDisplayText(paragraphs[index], displayMode)
            .split("\n")
            .size
            .coerceAtLeast(1)
        if (index < paragraphs.lastIndex) cursor += 1
    }
    return cursor
}
