package com.kacyraho.lightnovel.reader

import android.content.Context
import android.graphics.Canvas
import android.text.Spanned
import android.text.StaticLayout
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import kotlin.math.abs

class ReaderPageView(context: Context) : View(context) {
    private var sourceLayout: StaticLayout? = null
    private var sourceSlice: PageSlice? = null
    private var pageLayout: StaticLayout? = null
    private val touchSlop = ViewConfiguration.get(context).scaledTouchSlop
    private var downX = 0f
    private var downY = 0f
    private var moved = false

    var onEntityClick: ((String) -> Unit)? = null

    fun bind(layout: StaticLayout, slice: PageSlice) {
        if (sourceLayout === layout && sourceSlice == slice) return
        sourceLayout = layout
        sourceSlice = slice
        pageLayout = buildPageLayout(layout, slice)
        invalidate()
    }

    private fun buildPageLayout(layout: StaticLayout, slice: PageSlice): StaticLayout {
        val text = layout.text
        val start = slice.start.coerceIn(0, text.length)
        val end = slice.end.coerceIn(start, text.length)
        if (start == end) return layout
        return StaticLayoutPaginator.build(
            text = text.subSequence(start, end),
            widthPx = layout.width,
            paint = layout.paint,
            lineSpacingMultiplier = layout.spacingMultiplier,
        )
    }

    override fun onDraw(canvas: Canvas) {
        val layout = pageLayout ?: return
        canvas.save()
        canvas.clipRect(0, 0, width, height)
        layout.draw(canvas)
        canvas.restore()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (onEntityClick == null) return super.onTouchEvent(event)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = event.x
                downY = event.y
                moved = false
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                if (abs(event.x - downX) > touchSlop || abs(event.y - downY) > touchSlop) {
                    moved = true
                    parent?.requestDisallowInterceptTouchEvent(false)
                    return false
                }
                return true
            }
            MotionEvent.ACTION_UP -> {
                if (!moved) handleTap(event)
                return true
            }
            MotionEvent.ACTION_CANCEL -> return true
        }
        return super.onTouchEvent(event)
    }

    private fun handleTap(event: MotionEvent) {
        val layout = pageLayout ?: return
        val spanned = layout.text as? Spanned ?: return
        val y = event.y.toInt().coerceIn(0, layout.height)
        val line = layout.getLineForVertical(y)
        val x = event.x.coerceIn(0f, width.toFloat())
        val offset = layout.getOffsetForHorizontal(line, x)
        val span = spanned.getSpans(offset, offset, EntityClickSpan::class.java)
            .firstOrNull() ?: return
        performClick()
        onEntityClick?.invoke(span.entityId)
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }
}
