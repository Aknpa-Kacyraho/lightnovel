package com.kacyraho.lightnovel.feature.reader

/** 平板上正文不铺满整行：超过这个宽度就居中留白。 */
internal const val READER_MAX_CONTENT_DP = 680

/**
 * 正文可用宽度：先限制屏幕内容宽度，再扣掉左右页边距。
 * 最小值 1dp，避免极端设置导致负宽度。
 */
internal fun readerContentWidthDp(screenWidthDp: Float, marginDp: Float): Float =
    (minOf(screenWidthDp, READER_MAX_CONTENT_DP.toFloat()) - marginDp * 2f).coerceAtLeast(1f)
