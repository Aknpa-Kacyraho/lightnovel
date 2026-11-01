package com.kacyraho.lightnovel.reader

import android.annotation.SuppressLint
import android.graphics.text.LineBreakConfig
import android.os.Build
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint

data class PageSlice(
    val start: Int,
    val end: Int,
    val top: Int,
    val bottom: Int,
)

data class PaginationResult(
    val pages: List<PageSlice>,
    val lineCount: Int,
)

object StaticLayoutPaginator {
    @SuppressLint("WrongConstant")
    fun paginate(
        text: CharSequence,
        widthPx: Int,
        heightPx: Int,
        paint: TextPaint,
        lineSpacingMultiplier: Float = 1.4f,
    ): PaginationResult {
        require(widthPx > 0) { "widthPx 必须 > 0" }
        require(heightPx > 0) { "heightPx 必须 > 0" }

        if (text.isEmpty()) {
            return PaginationResult(listOf(PageSlice(0, 0, 0, 0)), 0)
        }

        return paginate(build(text, widthPx, paint, lineSpacingMultiplier), heightPx)
    }

    @SuppressLint("WrongConstant")
    fun build(
        text: CharSequence,
        widthPx: Int,
        paint: TextPaint,
        lineSpacingMultiplier: Float = 1.4f,
    ): StaticLayout {
        require(widthPx > 0) { "widthPx 必须 > 0" }
        val builder = StaticLayout.Builder
            .obtain(text, 0, text.length, paint, widthPx)
            .setAlignment(Layout.Alignment.ALIGN_NORMAL)
            .setLineSpacing(0f, lineSpacingMultiplier)
            .setIncludePad(false)
            .setBreakStrategy(Layout.BREAK_STRATEGY_SIMPLE)
            .setHyphenationFrequency(Layout.HYPHENATION_FREQUENCY_NONE)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            builder.setLineBreakConfig(
                LineBreakConfig.Builder()
                    .setLineBreakStyle(LineBreakConfig.LINE_BREAK_STYLE_STRICT)
                    .setLineBreakWordStyle(LineBreakConfig.LINE_BREAK_WORD_STYLE_PHRASE)
                    .build(),
            )
        }
        return builder.build()
    }

    fun paginate(layout: StaticLayout, heightPx: Int): PaginationResult {
        require(heightPx > 0) { "heightPx 必须 > 0" }
        val textLength = layout.text.length
        if (textLength == 0 || layout.lineCount == 0) {
            return PaginationResult(listOf(PageSlice(0, textLength, 0, 0)), layout.lineCount)
        }

        val pages = mutableListOf<PageSlice>()
        var pageStartLine = 0
        for (line in 0 until layout.lineCount) {
            val pageTop = layout.getLineTop(pageStartLine)
            val lineBottom = layout.getLineBottom(line)
            if (line > pageStartLine && lineBottom - pageTop > heightPx) {
                pages += PageSlice(
                    start = layout.getLineStart(pageStartLine),
                    end = layout.getLineStart(line),
                    top = pageTop,
                    bottom = layout.getLineBottom(line - 1),
                )
                pageStartLine = line
            }
        }
        pages += PageSlice(
            start = layout.getLineStart(pageStartLine),
            end = textLength,
            top = layout.getLineTop(pageStartLine),
            bottom = layout.height,
        )
        return PaginationResult(pages, layout.lineCount)
    }
}
