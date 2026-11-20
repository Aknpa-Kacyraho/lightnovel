package com.kacyraho.lightnovel.feature.reader

import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import java.nio.file.Files
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class BookSearchTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun emptyQueryReturnsNothing() {
        assertTrue(findHits("abc", " ").isEmpty())
    }

    @Test
    fun findsCaseInsensitiveMatchWithContext() {
        val text = "第一段没有关键词。\n\n雨声很大，那句话我到现在还记得。\n\n第三段。"

        val hits = findHits(text, "那句话")

        assertEquals(1, hits.size)
        val hit = hits.single()
        assertEquals(1, hit.paragraphId)
        assertEquals("雨声很大，", hit.before)
        assertEquals("那句话", hit.match)
        assertTrue(hit.after.startsWith("我到现在还记得"))
    }

    @Test
    fun capsHitsPerChapter() {
        val text = "keyword one\n\nkeyword two\n\nkeyword three"

        assertEquals(2, findHits(text, "keyword", max = 2).size)
        assertEquals(3, findHits(text, "keyword", max = 3).size)
    }

    @Test
    fun truncatesLongContextWithEllipsis() {
        val text = "x".repeat(100) + "needle" + "y".repeat(100)

        val hit = findHits(text, "needle").single()

        assertTrue(hit.before.startsWith("…"))
        assertTrue(hit.after.endsWith("…"))
    }

    @Test
    fun ignoresSecondMatchInSameParagraph() {
        val text = "foo foo foo"

        assertEquals(1, findHits(text, "foo").size)
    }

    @Test
    fun serviceSearchesChaptersAndPrefersTranslated() = runTest {
        val root = tmp.newFolder("data").toPath()
        Files.createDirectories(root.resolve("novels").resolve("b1").resolve("raw"))
        Files.createDirectories(root.resolve("novels").resolve("b1").resolve("chapters"))
        val store = com.kacyraho.lightnovel.core.storage.FileContentStore(root)
        store.writeRawAtomic("b1", 1, "原文关键词")
        store.writeZhAtomic("b1", 1, "译文关键词在这里")
        store.writeRawAtomic("b1", 2, "另一章")
        val book = BookEntity(
            id = "b1",
            storageDir = "b1",
            slug = "b1",
            source = "local",
            sourceId = "b1",
            title = "Book",
            titleZh = "书",
            author = null,
            tagsJson = null,
            genre = null,
            episodes = 2,
            local = true,
            createdAt = null,
            legacyJson = null,
        )
        val chapters = listOf(
            ChapterEntity("b1", 1, "c1", null, null, null, "complete", 0, 0, null, null),
            ChapterEntity("b1", 2, "c2", null, null, null, "raw", 0, 0, null, null),
        )

        val hits = BookSearchService(store).search(book, chapters, "关键词", preferTranslated = true)

        assertEquals(1, hits.size)
        assertEquals(1, hits.single().chapterIndex)
        assertEquals("关键词", hits.single().match)
        assertTrue(hits.single().before.contains("译文"))
    }
}
