package com.kacyraho.lightnovel.reader

import android.content.Context
import android.graphics.Canvas
import android.text.Spanned
import android.text.StaticLayout
import android.view.MotionEvent
import android.view.View

class ReaderPageView(context: Context) : View(context) {
    private var pageLayout: StaticLayout? = null
    private var page: PageSlice? = null

    var onEntityClick: ((String) -> Unit)? = null

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

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked != MotionEvent.ACTION_UP) {
            return super.onTouchEvent(event)
        }
        val layout = pageLayout ?: return super.onTouchEvent(event)
        val slice = page ?: return super.onTouchEvent(event)
        val spanned = layout.text as? Spanned ?: return super.onTouchEvent(event)
        val y = (event.y + slice.top).toInt().coerceIn(0, layout.height)
        val line = layout.getLineForVertical(y)
        val x = event.x.coerceIn(0f, width.toFloat())
        val offset = layout.getOffsetForHorizontal(line, x)
        val span = spanned.getSpans(offset, offset, EntityClickSpan::class.java)
            .firstOrNull() ?: return super.onTouchEvent(event)
        performClick()
        onEntityClick?.invoke(span.entityId)
        return true
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }
}
