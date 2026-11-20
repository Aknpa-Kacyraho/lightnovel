package com.kacyraho.lightnovel.feature.reader

import org.junit.Assert.assertEquals
import org.junit.Test

class CostEstimatorTest {
    @Test
    fun zeroCharsOrZeroPriceReturnsZero() {
        assertEquals(CostRange(0.0, 0.0), estimateTranslationCost(0, 1.0, 2.0))
        assertEquals(CostRange(0.0, 0.0), estimateTranslationCost(1000, 0.0, 2.0))
        assertEquals(CostRange(0.0, 0.0), estimateTranslationCost(1000, 1.0, 0.0))
    }

    @Test
    fun thousandCharsStaysInSmallRange() {
        val range = estimateTranslationCost(1000, 1.0, 2.0)

        assertEquals(0.0024, range.minCny, 0.0001)
        assertEquals(0.0035, range.maxCny, 0.0001)
        assertEquals("< ¥0.01", formatCostRange(range))
    }

    @Test
    fun tenThousandCharsShowsTwoDecimals() {
        val range = estimateTranslationCost(10_000, 1.0, 2.0)

        assertEquals("¥0.02–0.03", formatCostRange(range))
    }

    @Test
    fun rangeNeverInverts() {
        val range = estimateTranslationCost(500, 0.01, 0.01)

        assertEquals(true, range.maxCny >= range.minCny)
    }

    @Test
    fun equalBoundsPrintSingleValue() {
        assertEquals("¥1.00", formatCostRange(CostRange(1.0, 1.0)))
    }
}
