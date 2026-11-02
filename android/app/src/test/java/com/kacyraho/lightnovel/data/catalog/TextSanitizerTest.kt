package com.kacyraho.lightnovel.data.catalog

import org.junit.Assert.assertEquals
import org.junit.Test

class TextSanitizerTest {
    @Test
    fun decodesNumericHtmlEntities() {
        assertEquals("第一行\n第二行", TextSanitizer.decode("第一行&#10;第二行"))
        assertEquals("A&B", TextSanitizer.decode("A&amp;B"))
        assertEquals("★", TextSanitizer.decode("&#9733;"))
    }
}
