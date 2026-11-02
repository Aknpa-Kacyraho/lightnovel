package com.kacyraho.lightnovel.data.translation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TranslationValidatorsTest {
    @Test
    fun detectsTranslatableTextButSkipsDecorations() {
        assertTrue(TranslationValidators.hasTranslatable("これは日本語です"))
        assertTrue(TranslationValidators.hasTranslatable("这是中文"))
        assertTrue(TranslationValidators.hasTranslatable("hello beautiful world"))
        assertFalse(TranslationValidators.hasTranslatable("――――――"))
        assertFalse(TranslationValidators.hasTranslatable("12345"))
        assertFalse(TranslationValidators.hasTranslatable("https://example.com/a/b"))
        assertFalse(TranslationValidators.hasTranslatable(""))
    }

    @Test
    fun countsDialogueAndDetectsMissingLines() {
        assertEquals(2, TranslationValidators.dialogueCount("「a」「b」"))
        assertTrue(TranslationValidators.missingDialogue("「a」「b」", "「a」"))
        assertFalse(TranslationValidators.missingDialogue("「a」", "「a」"))
    }

    @Test
    fun alignsQuoteGlyphsOnlyWhenStructureMatches() {
        assertEquals(
            "「你好」",
            TranslationValidators.alignQuotes("“你好”", "「こんにちは」"),
        )
        assertEquals(
            "『你好』",
            TranslationValidators.alignQuotes("“你好”", "『こんにちは』"),
        )
        assertEquals(
            "「a「b」」",
            TranslationValidators.alignQuotes("「a『b』」", "「a「b」」"),
        )
        assertEquals("“没有原文引号”", TranslationValidators.alignQuotes("“没有原文引号”", "没有引号"))
        assertEquals("「a」", TranslationValidators.alignQuotes("「a」", "「a」「b」"))
    }

    @Test
    fun detectsChineseWithKanaThresholds() {
        assertTrue(TranslationValidators.detectChinese("这是简体中文的译文。"))
        assertFalse(TranslationValidators.detectChinese("これは日本語の文章です。"))
        assertTrue(TranslationValidators.detectChinese("这是中文，只有少量か。"))
        assertTrue(TranslationValidators.isEcho("这是中文", "这是中文"))
        assertFalse(TranslationValidators.isEcho("这是中文", "これは日本語"))
    }

    @Test
    fun splitsParagraphsAndParsesNumberedReply() {
        val paragraphs = TranslationValidators.splitParagraphs("a\nb\n\nc")
        assertEquals(listOf("a\nb", "", "c"), paragraphs)
        assertEquals(
            listOf("a", "b", "c"),
            TranslationValidators.splitParagraphs("a\nb\nc"),
        )

        val parsed = TranslationValidators.parseNumbered(
            "1. 你好\n2. 世界\n3) 继续",
        )
        assertEquals("你好", parsed[1])
        assertEquals("世界", parsed[2])
        assertEquals("继续", parsed[3])
    }

    @Test
    fun chunksAtParagraphBoundaries() {
        val chunks = TranslationValidators.chunkIndexed(
            paragraphs = listOf(
                TranslationValidators.IndexedParagraph(0, "a".repeat(4000)),
                TranslationValidators.IndexedParagraph(1, "b".repeat(3000)),
                TranslationValidators.IndexedParagraph(2, "c".repeat(1000)),
            ),
            maxChars = 6000,
        )
        assertEquals(2, chunks.size)
        assertEquals(listOf(0), chunks[0].map { it.index })
        assertEquals(listOf(1, 2), chunks[1].map { it.index })
    }
}
