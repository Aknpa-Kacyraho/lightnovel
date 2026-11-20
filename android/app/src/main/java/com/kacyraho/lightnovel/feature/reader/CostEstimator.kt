package com.kacyraho.lightnovel.feature.reader

import java.util.Locale
import kotlin.math.max

data class CostRange(val minCny: Double, val maxCny: Double)

/**
 * 翻译前费用区间估算。token 比例是经验值，只用于量级判断；
 * 实际费用以 sidecar 记录的 tokens 为准。
 */
internal fun estimateTranslationCost(
    charCount: Int,
    priceInCnyPerMillion: Double,
    priceOutCnyPerMillion: Double,
): CostRange {
    if (charCount <= 0 || priceInCnyPerMillion <= 0.0 || priceOutCnyPerMillion <= 0.0) {
        return CostRange(0.0, 0.0)
    }
    val minTokensIn = charCount * 0.6
    val maxTokensIn = charCount * 0.9
    val minTokensOut = charCount * 0.9
    val maxTokensOut = charCount * 1.3
    val min = minTokensIn / 1_000_000.0 * priceInCnyPerMillion +
        minTokensOut / 1_000_000.0 * priceOutCnyPerMillion
    val max = maxTokensIn / 1_000_000.0 * priceInCnyPerMillion +
        maxTokensOut / 1_000_000.0 * priceOutCnyPerMillion
    // 保留一点余量，避免显示为 0.00；上限始终不低于下限。
    val lower = min.coerceAtLeast(0.0)
    val upper = max(max, lower)
    return CostRange(lower, upper)
}

internal fun formatCostRange(range: CostRange): String {
    if (range.maxCny < 0.01) return "< ¥0.01"
    val low = String.format(Locale.US, "%.2f", range.minCny)
    val high = String.format(Locale.US, "%.2f", range.maxCny)
    return if (low == high) "¥$low" else "¥$low–$high"
}
