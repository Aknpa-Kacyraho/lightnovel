package com.kacyraho.lightnovel.reader.engine

import android.text.TextPaint
import com.kacyraho.lightnovel.core.model.ReaderAnchor
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
    ): ReaderLayout {
        val layout = StaticLayoutPaginator.build(
            text = chapter.text,
            widthPx = viewport.widthPx,
            paint = paint,
            lineSpacingMultiplier = style.lineHeight,
        )
        val result = StaticLayoutPaginator.paginate(layout, viewport.heightPx)
        val ranges = blockRanges(chapter.blocks)
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

    private fun blockRanges(blocks: List<ReaderBlock>): List<BlockRange> {
        val out = mutableListOf<BlockRange>()
        var cursor = 0
        for (block in blocks) {
            out += BlockRange(block.id, cursor, cursor + block.text.length)
            cursor += block.text.length + 2 // "\n\n"
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
