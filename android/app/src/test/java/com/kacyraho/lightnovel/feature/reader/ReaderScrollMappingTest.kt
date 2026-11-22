package com.kacyraho.lightnovel.feature.reader

import com.kacyraho.lightnovel.reader.engine.ReaderBlock
import org.junit.Assert.assertEquals
import org.junit.Test

class ReaderScrollMappingTest {
    private fun paragraph(source: String, translated: String? = null) =
        ReaderParagraph(id = 0, source = source, translated = translated)

    @Test
    fun singleParagraphStartsAtLineZero() {
        val paragraphs = listOf(paragraph("一段\n两行"))

        assertEquals(0, paragraphIndexForLine(paragraphs, "raw", 0))
        assertEquals(0, paragraphIndexForLine(paragraphs, "raw", 1))
        assertEquals(0, lineForParagraph(paragraphs, "raw", 0))
    }

    @Test
    fun mapsLinesAcrossParagraphs() {
        // p0: 2 行 + 空行 = 3；p1 从第 3 行开始，2 行。
        val paragraphs = listOf(paragraph("a\nb"), paragraph("c\nd"))

        assertEquals(0, paragraphIndexForLine(paragraphs, "raw", 1))
        assertEquals(1, paragraphIndexForLine(paragraphs, "raw", 3))
        assertEquals(1, paragraphIndexForLine(paragraphs, "raw", 4))
        assertEquals(3, lineForParagraph(paragraphs, "raw", 1))
    }

    @Test
    fun bilingualCountsBothSides() {
        // bilingual: source 1 行 + translated 1 行 = 2 行；p1 从第 3 行开始。
        val paragraphs = listOf(
            paragraph("原文", "译文"),
            paragraph("二段原文", "二段译文"),
        )

        assertEquals(0, paragraphIndexForLine(paragraphs, "bilingual", 1))
        assertEquals(1, paragraphIndexForLine(paragraphs, "bilingual", 3))
        assertEquals(3, lineForParagraph(paragraphs, "bilingual", 1))
    }

    @Test
    fun scrollBlocksKeepMappingForSingleNewlineText() {
        val paragraphs = listOf(
            paragraph("a"),
            paragraph("b"),
            paragraph("c"),
        )
        val blocks = readerScrollBlocks(
            blocks = paragraphs.mapIndexed { index, value ->
                ReaderBlock(index, value.source)
            },
            fallbackText = "a\nb\nc",
        )

        assertEquals(listOf("a", "", "b", "", "c"), blocks)
        assertEquals(0, lineForParagraph(paragraphs, "raw", 0))
        assertEquals(2, lineForParagraph(paragraphs, "raw", 1))
        assertEquals(4, lineForParagraph(paragraphs, "raw", 2))
        assertEquals(1, paragraphIndexForLine(paragraphs, "raw", 2))
        assertEquals(2, paragraphIndexForLine(paragraphs, "raw", 4))
    }

    @Test
    fun emptyParagraphsReturnZero() {
        assertEquals(0, paragraphIndexForLine(emptyList(), "raw", 10))
        assertEquals(0, lineForParagraph(emptyList(), "raw", 5))
    }

    @Test
    fun outOfRangeValuesAreClamped() {
        val paragraphs = listOf(paragraph("a"), paragraph("b"))

        assertEquals(0, paragraphIndexForLine(paragraphs, "raw", -3))
        assertEquals(1, paragraphIndexForLine(paragraphs, "raw", 99))
        assertEquals(0, lineForParagraph(paragraphs, "raw", -1))
        assertEquals(2, lineForParagraph(paragraphs, "raw", 99))
    }

    @Test
    fun paragraphToLineToParagraphRoundTrips() {
        val paragraphs = listOf(
            paragraph("a\nb\nc"),
            paragraph("d"),
            paragraph("e\nf"),
        )

        for (index in paragraphs.indices) {
            val line = lineForParagraph(paragraphs, "raw", index)
            assertEquals(index, paragraphIndexForLine(paragraphs, "raw", line))
        }
    }
}
