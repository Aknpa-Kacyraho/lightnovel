package com.kacyraho.lightnovel.feature.reader

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TranslationFreshnessTest {
    @Test
    fun matchingGlossaryHashIsFresh() {
        assertFalse(glossaryOutdated("g1", "r1", "g1", "r2"))
    }

    @Test
    fun differentGlossaryHashIsOutdated() {
        assertTrue(glossaryOutdated("g1", "r1", "g2", "r1"))
    }

    @Test
    fun blankCurrentGlossaryIsFresh() {
        assertFalse(glossaryOutdated("g1", "r1", "", "r1"))
    }

    @Test
    fun legacyMatchingRevisionIsFresh() {
        assertFalse(glossaryOutdated(null, "r1", "g1", "r1"))
    }

    @Test
    fun legacyDifferentRevisionIsOutdated() {
        assertTrue(glossaryOutdated(null, "r1", "g1", "r2"))
    }
}
