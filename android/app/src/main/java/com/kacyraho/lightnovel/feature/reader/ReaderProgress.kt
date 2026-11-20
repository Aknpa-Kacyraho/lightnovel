package com.kacyraho.lightnovel.feature.reader

import kotlin.math.roundToInt

/**
 * 本章阅读进度：翻页模式按页，滚动模式按段；无内容时返回 0。
 */
internal fun readerChapterProgress(
    scrollMode: Boolean,
    pageIndex: Int,
    pageCount: Int,
    scrollParagraph: Int,
    blockCount: Int,
): Float {
    val index = if (scrollMode) scrollParagraph else pageIndex
    val count = if (scrollMode) blockCount else pageCount
    if (count <= 0) return 0f
    return ((index + 1).toFloat() / count).coerceIn(0f, 1f)
}

/**
 * 书架进度：话数未知时返回 0，不猜测。
 */
internal fun shelfProgress(progressIdx: Int, episodes: Int): Float {
    if (episodes <= 0 || progressIdx <= 0) return 0f
    return (progressIdx.toFloat() / episodes).coerceIn(0f, 1f)
}

/** 拖动进度 → 页码（0-based）。0 页返回 0，1 页始终 0。 */
internal fun progressToPage(progress: Float, pageCount: Int): Int {
    if (pageCount <= 0) return 0
    if (pageCount == 1) return 0
    return (progress.coerceIn(0f, 1f) * (pageCount - 1))
        .roundToInt()
        .coerceIn(0, pageCount - 1)
}

/** 页码（0-based）→ 拖动进度。 */
internal fun pageToProgress(pageIndex: Int, pageCount: Int): Float {
    if (pageCount <= 1) return 0f
    return (pageIndex.toFloat() / (pageCount - 1)).coerceIn(0f, 1f)
}
