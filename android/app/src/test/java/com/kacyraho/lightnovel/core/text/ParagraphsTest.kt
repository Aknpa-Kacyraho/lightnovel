package com.kacyraho.lightnovel.core.text

import org.junit.Assert.assertEquals
import org.junit.Test

class ParagraphsTest {
    @Test
    fun splitsSingleNewlineParagraphs() {
        assertEquals(
            listOf("第一行", "第二行", "第三行"),
            Paragraphs.split("第一行\n第二行\n第三行"),
        )
    }

    @Test
    fun prefersBlankLineParagraphs() {
        assertEquals(
            listOf("第一段\n第一段续", "第二段"),
            Paragraphs.split("第一段\n第一段续\n\n第二段"),
        )
    }

    @Test
    fun normalizesWindowsNewlines() {
        assertEquals(
            listOf("第一段", "第二段"),
            Paragraphs.split("第一段\r\n第二段\r\n"),
        )
    }

    @Test
    fun findsStartOfDuplicateParagraph() {
        val text = "开头\n\n重复段落\n\n重复段落\n\n结尾"
        assertEquals(text.indexOf("重复段落", text.indexOf("重复段落") + 1), Paragraphs.startOffset(text, 2))
        assertEquals(text.indexOf("结尾"), Paragraphs.startOffset(text, 3))
    }
}
