package com.kacyraho.lightnovel.data.catalog

import org.junit.Assert.assertEquals
import org.junit.Test

class TagLocalizerTest {
    @Test
    fun translatesCommonLightNovelTags() {
        assertEquals("反派千金", TagLocalizer.translate("悪役令嬢"))
        assertEquals("转生", TagLocalizer.translate("転生"))
        assertEquals("打脸", TagLocalizer.translate("ざまぁ"))
        assertEquals("AI正文使用", TagLocalizer.translate("AI本文利用"))
    }

    @Test
    fun leavesUnknownTagsUntranslated() {
        assertEquals(null, TagLocalizer.translate("未知タグ"))
    }
}
