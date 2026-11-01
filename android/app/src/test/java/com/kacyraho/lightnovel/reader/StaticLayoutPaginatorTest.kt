package com.kacyraho.lightnovel.reader

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
class StaticLayoutPaginatorTest {
    private fun paint(sizePx: Float): TextPaint = TextPaint().apply {
        textSize = sizePx
        typeface = Typeface.SERIF
        isAntiAlias = true
    }

    private fun sampleText(paragraphs: Int = 120): String =
        (1..paragraphs).joinToString("\n\n") { i ->
            "第${i}段：これはページ分割のテストです。中文和日文混排，用来确认分页覆盖完整、没有丢字。" +
                "「会話の行も入れてみます」と彼女は言った。"
        }

    @Test
    fun pagesCoverTheWholeTextWithoutGaps() {
        val text = sampleText()
        val result = StaticLayoutPaginator.paginate(
            text = text,
            widthPx = 720,
            heightPx = 1200,
            paint = paint(48f),
        )

        assertTrue(result.pages.size > 1)
        assertEquals(0, result.pages.first().start)
        assertEquals(text.length, result.pages.last().end)
        for (i in 0 until result.pages.size - 1) {
            assertEquals(result.pages[i].end, result.pages[i + 1].start)
            assertTrue(result.pages[i].end > result.pages[i].start)
        }
    }

    @Test
    fun smallerPageHeightProducesMorePages() {
        val text = sampleText(40)
        val tall = StaticLayoutPaginator.paginate(text, 720, 1600, paint(48f))
        val short = StaticLayoutPaginator.paginate(text, 720, 600, paint(48f))

        assertTrue(
            "tall=${tall.pages.size} short=${short.pages.size}",
            short.pages.size > tall.pages.size,
        )
    }

    @Test
    fun emptyTextStillHasOnePage() {
        val result = StaticLayoutPaginator.paginate("", 720, 1200, paint(48f))

        assertEquals(1, result.pages.size)
        assertEquals(0, result.pages.single().start)
        assertEquals(0, result.pages.single().end)
    }

    @Test
    fun tinyHeightStillTerminates() {
        val result = StaticLayoutPaginator.paginate(sampleText(4), 720, 20, paint(48f))
        assertTrue(result.pages.isNotEmpty())
        assertEquals(0, result.pages.first().start)
    }
}
