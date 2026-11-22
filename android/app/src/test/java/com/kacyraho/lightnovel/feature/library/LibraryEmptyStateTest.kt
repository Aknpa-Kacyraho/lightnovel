package com.kacyraho.lightnovel.feature.library

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LibraryEmptyStateTest {
    @Test
    fun completelyEmptyShelfOffersDiscoverFirst() {
        val copy = emptyShelfCopy("", favoritesOnly = false, removedOnly = false, shelf = null)

        assertEquals("还没有书", copy.title)
        assertEquals(EmptyShelfAction.OPEN_DISCOVER, copy.primary)
        assertEquals(
            listOf(EmptyShelfAction.IMPORT_BACKUP, EmptyShelfAction.IMPORT_DOCUMENT),
            copy.secondary,
        )
        assertTrue(copy.message.contains("第一次用"))
        assertTrue(copy.message.contains("旧备份"))
    }

    @Test
    fun searchWithoutResultOffersClearFilters() {
        val copy = emptyShelfCopy("星", favoritesOnly = false, removedOnly = false, shelf = null)

        assertEquals("没有匹配的书", copy.title)
        assertEquals(EmptyShelfAction.CLEAR_FILTERS, copy.primary)
        assertTrue(copy.secondary.isEmpty())
    }

    @Test
    fun favoritesWithoutResultOffersClearFilters() {
        val copy = emptyShelfCopy("", favoritesOnly = true, removedOnly = false, shelf = null)

        assertEquals(EmptyShelfAction.CLEAR_FILTERS, copy.primary)
    }

    @Test
    fun shelfFilterWithoutResultOffersClearFilters() {
        val copy = emptyShelfCopy("", favoritesOnly = false, removedOnly = false, shelf = "reading")

        assertEquals(EmptyShelfAction.CLEAR_FILTERS, copy.primary)
    }

    @Test
    fun removedOnlyWithSearchExplainsFilterMismatch() {
        val copy = emptyShelfCopy("星", favoritesOnly = false, removedOnly = true, shelf = null)

        assertEquals("没有匹配的已移出书籍", copy.title)
        assertEquals(EmptyShelfAction.CLEAR_FILTERS, copy.primary)
    }

    @Test
    fun removedOnlyExplainsNothingWasLost() {
        val copy = emptyShelfCopy("", favoritesOnly = false, removedOnly = true, shelf = null)

        assertEquals("没有已移出的书", copy.title)
        assertEquals(EmptyShelfAction.CLEAR_FILTERS, copy.primary)
        assertTrue(copy.message.contains("阅读进度"))
    }
}
