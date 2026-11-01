package com.kacyraho.lightnovel.reader

import android.graphics.Typeface
import android.text.TextPaint
import android.util.Log
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import androidx.test.ext.junit.runners.AndroidJUnit4

@RunWith(AndroidJUnit4::class)
class PaginatorDeviceTest {
    private fun paint(sizePx: Float): TextPaint = TextPaint().apply {
        textSize = sizePx
        typeface = Typeface.SERIF
        isAntiAlias = true
    }

    private fun sampleText(paragraphs: Int = 40): String =
        (1..paragraphs).joinToString("\n\n") { i ->
            "第${i}段：これはページ分割のテストです。中文和日文混排，用来确认分页覆盖完整、没有丢字。" +
                "「会話の行も入れてみます」と彼女は言った。"
        }

    @Test
    fun fontAndWidthChangePageCountOnRealMetrics() {
        val text = sampleText()
        val small = StaticLayoutPaginator.paginate(text, 720, 1200, paint(36f))
        val large = StaticLayoutPaginator.paginate(text, 720, 1200, paint(72f))
        assertTrue(
            "small=${small.pages.size} large=${large.pages.size}",
            large.pages.size > small.pages.size,
        )

        val wide = StaticLayoutPaginator.paginate(text, 900, 1200, paint(48f))
        val narrow = StaticLayoutPaginator.paginate(text, 360, 1200, paint(48f))
        assertTrue(
            "wide=${wide.pages.size} narrow=${narrow.pages.size}",
            narrow.pages.size > wide.pages.size,
        )
        Log.i(
            "PaginatorDevice",
            "small=${small.pages.size} large=${large.pages.size} " +
                "wide=${wide.pages.size} narrow=${narrow.pages.size}",
        )
    }
}
