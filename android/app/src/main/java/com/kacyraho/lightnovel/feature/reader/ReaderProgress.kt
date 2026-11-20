package com.kacyraho.lightnovel.feature.reader

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
