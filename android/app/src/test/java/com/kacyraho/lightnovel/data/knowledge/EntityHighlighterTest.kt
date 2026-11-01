package com.kacyraho.lightnovel.data.knowledge

import org.junit.Assert.assertEquals
import org.junit.Test

class EntityHighlighterTest {
    @Test
    fun prefersLongestMatchAndDoesNotOverlap() {
        val matches = EntityHighlighter.find(
            "爱丽丝和爱丽丝娅站在一起。",
            mapOf("爱丽丝" to "a", "爱丽丝娅" to "b"),
        )
        assertEquals(2, matches.size)
        assertEquals("a", matches[0].entityId)
        assertEquals("b", matches[1].entityId)
        assertEquals("爱丽丝娅", "爱丽丝和爱丽丝娅站在一起。".substring(matches[1].start, matches[1].end))
    }

    @Test
    fun ignoresBlankNamesAndNoMatch() {
        assertEquals(
            0,
            EntityHighlighter.find("文本", mapOf("" to "a", "不存在" to "b")).size,
        )
    }
}
