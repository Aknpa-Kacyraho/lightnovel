package com.kacyraho.lightnovel.ui.components

import org.junit.Assert.assertEquals
import org.junit.Test

class BookCoverLabelTest {
    @Test
    fun skipsLeadingBracketsAndPunctuation() {
        assertEquals("所以你的", BookCoverLabel.of("【所以你的封面就显示的是【了", 4))
        assertEquals(
            "所以你的封面就显示的",
            BookCoverLabel.of("【所以你的封面就显示的是【了", 10),
        )
        assertEquals("转生后我成了魔女", BookCoverLabel.of("「转生后」我成了魔女", 10))
        assertEquals("再见了", BookCoverLabel.of("再见了，鸢尾魔女", 4))
        assertEquals("再见了，鸢尾魔女", BookCoverLabel.of("再见了，鸢尾魔女", 20))
        assertEquals("Re:Zero", BookCoverLabel.of("Re:Zero", 12))
    }

    @Test
    fun largerCoverShowsMoreCharacters() {
        assertEquals(8, BookCoverSize.COMPACT.maxChars)
        assertEquals(14, BookCoverSize.SMALL.maxChars)
        assertEquals(30, BookCoverSize.LARGE.maxChars)
    }

    @Test
    fun fallsBackForBlankOrOnlyPunctuation() {
        assertEquals("书", BookCoverLabel.of(""))
        assertEquals("书", BookCoverLabel.of("【「"))
    }

    @Test
    fun keepsSingleCharacterTitles() {
        assertEquals("家", BookCoverLabel.of("家"))
    }
}
