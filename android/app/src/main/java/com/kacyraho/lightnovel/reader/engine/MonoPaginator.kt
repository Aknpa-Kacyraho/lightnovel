package com.kacyraho.lightnovel.reader.engine

import android.text.SpannableString
import android.text.Spanned
import android.text.TextPaint
import com.kacyraho.lightnovel.core.model.ReaderAnchor
import com.kacyraho.lightnovel.data.knowledge.EntityHighlighter
import com.kacyraho.lightnovel.reader.EntityClickSpan
import com.kacyraho.lightnovel.reader.StaticLayoutPaginator

data class MonoStyle(
    val fontSizeSp: Float,
    val lineHeight: Float,
)

class MonoPaginator {
    fun paginate(
        chapter: ReaderChapter,
        viewport: Viewport,
        paint: TextPaint,
        style: MonoStyle,
        highlights: Map<String, String> = emptyMap(),
    ): ReaderLayout {
        val text = if (highlights.isEmpty()) {
            chapter.text
        } else {
            val spans = EntityHighlighter.find(chapter.text, highlights)
            if (spans.isEmpty()) {
                chapter.text
            } else {
                SpannableString(chapter.text).apply {
                    spans.forEach { match ->
                        setSpan(
                            EntityClickSpan(match.entityId),
                            match.start,
                            match.end,
                            Spanned.SPAN_EXCLUSIVE_EXCLUSIVE,
                        )
                    }
                }
            }
        }
        val layout = StaticLayoutPaginator.build(
            text = text,
            widthPx = viewport.widthPx,
            paint = paint,
            lineSpacingMultiplier = style.lineHeight,
        )
        val result = StaticLayoutPaginator.paginate(layout, viewport.heightPx)
        val ranges = blockRanges(chapter.blocks, chapter.text)
        val pages = result.pages.mapIndexed { index, slice ->
            ReaderPage(
                index = index,
                slice = slice,
                startAnchor = anchorAt(chapter.idx, ranges, slice.start),
                endAnchor = anchorAt(chapter.idx, ranges, slice.end),
            )
        }
        return ReaderLayout(layout, pages, viewport)
    }

    private data class BlockRange(
        val id: Int,
        val start: Int,
        val end: Int,
    )

    private fun blockRanges(blocks: List<ReaderBlock>, text: String): List<BlockRange> {
        val out = mutableListOf<BlockRange>()
        var cursor = 0
        for (block in blocks) {
            if (block.text.isEmpty()) continue
            val found = text.indexOf(block.text, cursor)
            val start = if (found >= 0) found else cursor
            val end = (start + block.text.length).coerceAtMost(text.length)
            out += BlockRange(block.id, start, end)
            cursor = end
        }
        return out
    }

    private fun anchorAt(
        chapterIndex: Int,
        ranges: List<BlockRange>,
        offset: Int,
    ): ReaderAnchor {
        if (ranges.isEmpty()) return ReaderAnchor(chapterIndex, 0, 0)
        val range = ranges.firstOrNull { offset <= it.end } ?: ranges.last()
        return ReaderAnchor(
            chapterIndex = chapterIndex,
            paragraphId = range.id,
            charOffset = (offset - range.start).coerceIn(0, range.end - range.start),
        )
    }
}
