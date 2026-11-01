package com.kacyraho.lightnovel.feature.reader

import org.junit.Assert.assertEquals
import org.junit.Test

class StaleBannerReasonTest {
    @Test
    fun mapsAllSingleAndMergedReasons() {
        assertEquals(
            StaleBannerReason.SOURCE,
            staleBannerReason(setOf(StaleReason.SOURCE)),
        )
        assertEquals(
            StaleBannerReason.GLOSSARY,
            staleBannerReason(setOf(StaleReason.GLOSSARY)),
        )
        assertEquals(
            StaleBannerReason.MODEL_PROMPT,
            staleBannerReason(setOf(StaleReason.MODEL_PROMPT)),
        )
        assertEquals(
            StaleBannerReason.MERGED_SOURCE_GLOSSARY,
            staleBannerReason(setOf(StaleReason.SOURCE, StaleReason.GLOSSARY)),
        )
        assertEquals(
            StaleBannerReason.MERGED_SOURCE_MODEL,
            staleBannerReason(setOf(StaleReason.SOURCE, StaleReason.MODEL_PROMPT)),
        )
        assertEquals(
            StaleBannerReason.MERGED_GLOSSARY_MODEL,
            staleBannerReason(setOf(StaleReason.GLOSSARY, StaleReason.MODEL_PROMPT)),
        )
        assertEquals(
            StaleBannerReason.MERGED_ALL,
            staleBannerReason(
                setOf(
                    StaleReason.SOURCE,
                    StaleReason.GLOSSARY,
                    StaleReason.MODEL_PROMPT,
                ),
            ),
        )
        assertEquals(
            StaleBannerReason.ORIGINAL_REFRESH,
            staleBannerReason(
                setOf(StaleReason.SOURCE, StaleReason.ORIGINAL_REFRESH),
            ),
        )
    }
}
