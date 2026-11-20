package com.kacyraho.lightnovel.feature.reader

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReaderMenuTest {
    private fun items(
        fontSizeSp: Float = 18f,
        hasTranslation: Boolean = false,
        translationEnabled: Boolean = true,
        hasStoryMemory: Boolean = false,
        queryMode: Boolean = false,
    ) = readerMenuItems(fontSizeSp, hasTranslation, translationEnabled, hasStoryMemory, queryMode)

    @Test
    fun keepsEveryActionAndGroupOrder() {
        val menu = items(hasTranslation = true, hasStoryMemory = true)

        assertEquals(
            ReaderMenuGroup.entries.toList(),
            menu.map { it.group }.distinct(),
        )
        assertEquals(
            setOf(
                ReaderMenuAction.FONT_DECREASE,
                ReaderMenuAction.FONT_INCREASE,
                ReaderMenuAction.TOGGLE_THEME,
                ReaderMenuAction.IMMERSIVE,
                ReaderMenuAction.TRANSLATE,
                ReaderMenuAction.POLISH,
                ReaderMenuAction.CHAPTER_INFO,
                ReaderMenuAction.STORY_MEMORY,
                ReaderMenuAction.NEARBY_ENTITIES,
                ReaderMenuAction.QUERY_MODE,
                ReaderMenuAction.GLOSSARY,
                ReaderMenuAction.PARAGRAPH,
                ReaderMenuAction.ADD_BOOKMARK,
                ReaderMenuAction.OPEN_BOOKMARKS,
                ReaderMenuAction.WORLDLINE,
            ),
            menu.map { it.action }.toSet(),
        )
        assertEquals(15, menu.size)
    }

    @Test
    fun hidesStoryMemoryWhenUnavailable() {
        val menu = items(hasStoryMemory = false)

        assertTrue(menu.none { it.action == ReaderMenuAction.STORY_MEMORY })
        assertEquals(14, menu.size)
    }

    @Test
    fun bookmarkLabelReflectsCurrentParagraph() {
        assertEquals(
            "添加书签",
            items().first { it.action == ReaderMenuAction.ADD_BOOKMARK }.label,
        )
        assertEquals(
            "已添加书签",
            readerMenuItems(
                fontSizeSp = 18f,
                hasTranslation = false,
                translationEnabled = true,
                hasStoryMemory = false,
                queryMode = false,
                hasBookmarkHere = true,
            ).first { it.action == ReaderMenuAction.ADD_BOOKMARK }.label,
        )
    }

    @Test
    fun translationActionsFollowAvailability() {
        val untranslated = items(hasTranslation = false, translationEnabled = true)
        assertEquals("翻译本章", untranslated.first { it.action == ReaderMenuAction.TRANSLATE }.label)
        assertTrue(untranslated.first { it.action == ReaderMenuAction.POLISH }.enabled.not())

        val translated = items(hasTranslation = true, translationEnabled = true)
        assertEquals("重译本章", translated.first { it.action == ReaderMenuAction.TRANSLATE }.label)
        assertTrue(translated.first { it.action == ReaderMenuAction.POLISH }.enabled)

        val disabled = items(hasTranslation = true, translationEnabled = false)
        assertTrue(disabled.first { it.action == ReaderMenuAction.TRANSLATE }.enabled.not())
        assertTrue(disabled.first { it.action == ReaderMenuAction.POLISH }.enabled.not())
    }

    @Test
    fun queryModeLabelReflectsState() {
        assertEquals(
            "查询模式：开",
            items(queryMode = true).first { it.action == ReaderMenuAction.QUERY_MODE }.label,
        )
        assertEquals(
            "查询模式：关",
            items(queryMode = false).first { it.action == ReaderMenuAction.QUERY_MODE }.label,
        )
    }

    @Test
    fun fontLabelShowsCurrentSize() {
        val menu = items(fontSizeSp = 21f)

        assertEquals(
            "字号 21 · 减小",
            menu.first { it.action == ReaderMenuAction.FONT_DECREASE }.label,
        )
        assertEquals(
            "字号 21 · 增大",
            menu.first { it.action == ReaderMenuAction.FONT_INCREASE }.label,
        )
    }

    @Test
    fun charCountIsFormattedOnlyWhenKnown() {
        assertNull(formatCharCount(0))
        assertEquals("约 800 字", formatCharCount(800))
        assertEquals("约 1.2 千字", formatCharCount(1200))
    }

    @Test
    fun translateLabelCarriesCharCount() {
        val menu = readerMenuItems(
            fontSizeSp = 18f,
            hasTranslation = false,
            translationEnabled = true,
            hasStoryMemory = false,
            queryMode = false,
            charCount = 1200,
        )

        assertEquals(
            "翻译本章（约 1.2 千字）",
            menu.first { it.action == ReaderMenuAction.TRANSLATE }.label,
        )
    }
}
