package com.kacyraho.lightnovel.reader

import android.text.TextPaint
import android.text.style.ClickableSpan
import android.view.View

class EntityClickSpan(
    val entityId: String,
) : ClickableSpan() {
    override fun onClick(widget: View) = Unit

    override fun updateDrawState(ds: TextPaint) {
        ds.isUnderlineText = true
    }
}
