package com.kacyraho.lightnovel.reader.engine

import android.text.StaticLayout
import com.kacyraho.lightnovel.core.model.ReaderAnchor
import com.kacyraho.lightnovel.reader.PageSlice

data class ReaderBlock(
    val id: Int,
    val text: String,
)

data class ReaderChapter(
    val bookId: String,
    val idx: Int,
    val title: String,
    val blocks: List<ReaderBlock>,
    val text: String,
    val textKind: String,
)

data class Viewport(
    val widthPx: Int,
    val heightPx: Int,
)

data class ReaderPage(
    val index: Int,
    val slice: PageSlice,
    val startAnchor: ReaderAnchor,
    val endAnchor: ReaderAnchor,
)

data class ReaderLayout(
    val layout: StaticLayout,
    val pages: List<ReaderPage>,
    val viewport: Viewport,
)
