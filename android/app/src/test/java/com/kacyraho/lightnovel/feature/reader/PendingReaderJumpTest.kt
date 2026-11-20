package com.kacyraho.lightnovel.feature.reader

import com.kacyraho.lightnovel.core.model.ReaderAnchor
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PendingReaderJumpTest {
    @Test
    fun takeReturnsAnchorOnce() {
        val pending = PendingReaderJump()
        val anchor = ReaderAnchor(chapterIndex = 3, paragraphId = 7, charOffset = 0)

        pending.put("book", anchor)

        assertEquals(anchor, pending.take("book"))
        assertNull(pending.take("book"))
    }

    @Test
    fun laterPutOverwritesEarlier() {
        val pending = PendingReaderJump()
        pending.put("book", ReaderAnchor(1, 1, 0))
        pending.put("book", ReaderAnchor(5, 9, 0))

        assertEquals(ReaderAnchor(5, 9, 0), pending.take("book"))
    }

    @Test
    fun clearRemovesAnchor() {
        val pending = PendingReaderJump()
        pending.put("book", ReaderAnchor(2, 4, 0))

        pending.clear("book")

        assertNull(pending.take("book"))
    }

    @Test
    fun differentBooksAreIsolated() {
        val pending = PendingReaderJump()
        pending.put("a", ReaderAnchor(1, 1, 0))
        pending.put("b", ReaderAnchor(2, 2, 0))

        assertEquals(ReaderAnchor(2, 2, 0), pending.take("b"))
        assertEquals(ReaderAnchor(1, 1, 0), pending.take("a"))
    }
}
