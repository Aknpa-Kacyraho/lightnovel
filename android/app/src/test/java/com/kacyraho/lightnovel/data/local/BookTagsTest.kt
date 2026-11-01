package com.kacyraho.lightnovel.data.local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class BookTagsTest {
    @Test
    fun encodesAndDecodesTags() {
        val raw = BookTags.encode(listOf(" 転生 ", "百合", "百合", ""))
        assertEquals(listOf("転生", "百合"), BookTags.decode(raw))
    }

    @Test
    fun acceptsLegacyDelimitedTags() {
        assertEquals(listOf("A", "B", "C"), BookTags.decode("A|B|C"))
        assertEquals(listOf("A", "B"), BookTags.decode("A、B"))
    }

    @Test
    fun emptyTagsStayNull() {
        assertNull(BookTags.encode(emptyList()))
        assertEquals(emptyList<String>(), BookTags.decode(null))
    }
}
