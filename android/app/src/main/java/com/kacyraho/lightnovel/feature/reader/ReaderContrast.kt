package com.kacyraho.lightnovel.feature.reader

import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/**
 * WCAG 2.x 相对亮度与对比度，用于守护阅读器配色。
 * 输入为 0xRRGGBB 或 0xAARRGGBB 的 ARGB 值。
 */
internal fun contrastRatio(foreground: Long, background: Long): Double {
    val a = relativeLuminance(foreground)
    val b = relativeLuminance(background)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)
}

internal fun relativeLuminance(color: Long): Double {
    val r = channel((color shr 16) and 0xFF)
    val g = channel((color shr 8) and 0xFF)
    val b = channel(color and 0xFF)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

private fun channel(value: Long): Double {
    val c = value / 255.0
    return if (c <= 0.03928) c / 12.92 else ((c + 0.055) / 1.055).pow(2.4)
}
