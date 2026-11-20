package com.kacyraho.lightnovel.feature.memory

import com.kacyraho.lightnovel.data.glossary.GlossaryEntry
import org.junit.Assert.assertEquals
import org.junit.Test

class GlossaryFilterTest {
    private val entries = listOf(
        GlossaryEntry("1", "アリス", "爱丽丝", listOf("アリシア")),
        GlossaryEntry("2", "王都", "王都", emptyList()),
        GlossaryEntry("3", "ギルド", "公会", emptyList()),
    )

    @Test
    fun blankQueryReturnsAll() {
        assertEquals(entries, filterGlossary(entries, ""))
        assertEquals(entries, filterGlossary(entries, "   "))
    }

    @Test
    fun matchesSource() {
        assertEquals(listOf("爱丽丝"), filterGlossary(entries, "アリス").map { it.target })
    }

    @Test
    fun matchesTarget() {
        assertEquals(listOf("爱丽丝"), filterGlossary(entries, "爱丽").map { it.target })
    }

    @Test
    fun matchesAlias() {
        assertEquals(listOf("爱丽丝"), filterGlossary(entries, "アリシア").map { it.target })
    }

    @Test
    fun isCaseInsensitive() {
        val latin = listOf(GlossaryEntry("x", "Alice", "爱丽丝"))
        assertEquals(1, filterGlossary(latin, "alice").size)
    }

    @Test
    fun noMatchReturnsEmpty() {
        assertEquals(emptyList<GlossaryEntry>(), filterGlossary(entries, "不存在"))
    }
}
