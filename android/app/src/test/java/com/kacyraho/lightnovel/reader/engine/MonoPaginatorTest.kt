package com.kacyraho.lightnovel.reader.engine

import android.graphics.Typeface
import android.text.TextPaint
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class MonoPaginatorTest {
    private fun paint(sizePx: Float): TextPaint = TextPaint().apply {
        textSize = sizePx
        typeface = Typeface.SERIF
        isAntiAlias = true
    }

    private fun chapter(): ReaderChapter {
        val text = (1..40).joinToString("\n\n") { i ->
            "第${i}段：これはページ分割のテストです。中文和日文混排，用来确认分页锚点。" +
                "「会話の行も入れてみます」と彼女は言った。"
        }
        return ReaderChapter(
            bookId = "b1",
            idx = 1,
            title = "第一章",
            blocks = text.split("\n\n").mapIndexed { index, value -> ReaderBlock(index, value) },
            text = text,
            textKind = "raw",
        )
    }

    @Test
    fun pagesCarryMonotonicParagraphAnchors() {
        val result = MonoPaginator().paginate(
            chapter = chapter(),
            viewport = Viewport(720, 1200),
            paint = paint(48f),
            style = MonoStyle(fontSizeSp = 18f, lineHeight = 1.7f),
        )

        assertTrue(result.pages.size > 1)
        assertEquals(0, result.pages.first().startAnchor.paragraphId)
        assertEquals(0, result.pages.first().startAnchor.charOffset)

        for (i in 0 until result.pages.size - 1) {
            val current = result.pages[i]
            val next = result.pages[i + 1]
            assertTrue(compare(current.startAnchor, current.endAnchor) <= 0)
            assertTrue(compare(current.endAnchor, next.startAnchor) <= 0)
        }
    }

    @Test
    fun singleNewlineParagraphsAdvancePageAnchors() {
        val text = (1..80).joinToString("\n") { i ->
            "第${i}段：这是一行用来验证单换行分段的正文。"
        }
        val chapter = ReaderChapter(
            bookId = "b1",
            idx = 1,
            title = "第一话",
            blocks = text.split("\n").mapIndexed { index, value -> ReaderBlock(index, value) },
            text = text,
            textKind = "raw",
        )
        val result = MonoPaginator().paginate(
            chapter = chapter,
            viewport = Viewport(720, 600),
            paint = paint(48f),
            style = MonoStyle(fontSizeSp = 18f, lineHeight = 1.7f),
        )

        assertTrue(result.pages.size > 1)
        assertTrue(result.pages.any { it.startAnchor.paragraphId > 0 })
        assertTrue(result.pages.last().endAnchor.paragraphId > 0)
    }

    @Test
    fun shorterViewportDoesNotReducePageCount() {
        val tall = MonoPaginator().paginate(
            chapter = chapter(),
            viewport = Viewport(720, 1600),
            paint = paint(48f),
            style = MonoStyle(fontSizeSp = 18f, lineHeight = 1.7f),
        )
        val short = MonoPaginator().paginate(
            chapter = chapter(),
            viewport = Viewport(720, 600),
            paint = paint(48f),
            style = MonoStyle(fontSizeSp = 18f, lineHeight = 1.7f),
        )
        assertTrue(short.pages.size >= tall.pages.size)
    }

    private fun compare(a: com.kacyraho.lightnovel.core.model.ReaderAnchor,
                        b: com.kacyraho.lightnovel.core.model.ReaderAnchor): Int {
        val chapter = a.chapterIndex.compareTo(b.chapterIndex)
        if (chapter != 0) return chapter
        val paragraph = a.paragraphId.compareTo(b.paragraphId)
        if (paragraph != 0) return paragraph
        return a.charOffset.compareTo(b.charOffset)
    }
}
