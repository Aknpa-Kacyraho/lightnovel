package com.kacyraho.lightnovel.feature.reader

import com.kacyraho.lightnovel.core.model.ReaderAnchor

/**
 * 跨章跳转的一次性锚点：书签/搜索结果在导航前写入，目标章加载完成后取走。
 * 只存在内存，进程结束即失效。
 */
class PendingReaderJump {
    private val anchors = mutableMapOf<String, ReaderAnchor>()

    fun put(bookId: String, anchor: ReaderAnchor) {
        anchors[bookId] = anchor
    }

    fun take(bookId: String): ReaderAnchor? = anchors.remove(bookId)

    fun clear(bookId: String) {
        anchors.remove(bookId)
    }
}
