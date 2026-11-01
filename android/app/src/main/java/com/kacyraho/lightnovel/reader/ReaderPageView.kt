package com.kacyraho.lightnovel.reader

import android.content.Context
import android.graphics.Canvas
import android.text.StaticLayout
import android.view.View

class ReaderPageView(context: Context) : View(context) {
    private var pageLayout: StaticLayout? = null
    private var page: PageSlice? = null

    fun bind(layout: StaticLayout, slice: PageSlice) {
        pageLayout = layout
        page = slice
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val layout = pageLayout ?: return
        val slice = page ?: return
        canvas.save()
        canvas.clipRect(0, 0, width, height)
        canvas.translate(0f, -slice.top.toFloat())
        layout.draw(canvas)
        canvas.restore()
    }
}
