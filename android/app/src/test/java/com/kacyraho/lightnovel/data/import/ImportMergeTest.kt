package com.kacyraho.lightnovel.data.import

import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ImportMergeTest {
    @Test
    fun newBookUsesChapterCountAndHasNoImportHash() {
        val planned = plannedBook(episodes = 5)

        val merged = mergeBook(existing = null, planned = planned, chapterCount = 12)

        assertEquals(12, merged.episodes)
        assertEquals("Book", merged.title)
        assertNull(merged.importHash)
    }

    @Test
    fun existingBookKeepsTranslatedTitleTagsAndImportHash() {
        val existing = bookEntity(
            titleZh = "中文书名",
            author = null,
            tagsJson = """["奇幻"]""",
            importHash = "hash-1",
            episodes = 8,
        )
        val planned = plannedBook(
            title = "さよならアイリス",
            titleZh = null,
            author = "作者",
            episodes = 3,
            tags = listOf("百合"),
        )

        val merged = mergeBook(existing, planned, chapterCount = 2)

        assertEquals("中文书名", merged.titleZh)
        assertEquals("作者", merged.author)
        assertEquals("""["奇幻"]""", merged.tagsJson)
        assertEquals("hash-1", merged.importHash)
        assertEquals(8, merged.episodes)
    }

    @Test
    fun existingBookFillsMissingTitleZhFromBackup() {
        val existing = bookEntity(
            titleZh = null,
            author = null,
            tagsJson = null,
            importHash = null,
            episodes = 0,
        )
        val planned = plannedBook(titleZh = "备份译名", author = "作者")

        val merged = mergeBook(existing, planned, chapterCount = 0)

        assertEquals("备份译名", merged.titleZh)
        assertEquals("作者", merged.author)
    }

    @Test
    fun newerExistingStateKeepsProgressAndUnionsFavorite() {
        val existing = stateEntity(
            progress = 50,
            favorite = false,
            hidden = true,
            updatedAt = "2026-02-01T00:00:00Z",
        )
        val planned = stateEntity(
            progress = 10,
            favorite = true,
            hidden = false,
            updatedAt = "2025-01-01T00:00:00Z",
        )

        val merged = mergeReadState(existing, planned)

        assertEquals(50, merged.progressIdx)
        assertTrue(merged.favorite)
        assertTrue(merged.hidden)
    }

    @Test
    fun newerPlannedStateWinsProgress() {
        val existing = stateEntity(
            progress = 10,
            favorite = false,
            hidden = false,
            updatedAt = "2025-01-01T00:00:00Z",
        )
        val planned = stateEntity(
            progress = 80,
            favorite = false,
            hidden = false,
            updatedAt = "2026-02-01T00:00:00Z",
        )

        val merged = mergeReadState(existing, planned)

        assertEquals(80, merged.progressIdx)
    }

    @Test
    fun missingChaptersSkipsExistingKeysAndDuplicates() {
        val planned = listOf(
            plannedChapter("book", 1),
            plannedChapter("book", 2),
            plannedChapter("book", 2),
            plannedChapter("book", 3),
        )

        val missing = missingChapters(planned, setOf("book" to 1, "book" to 3))

        assertEquals(listOf(plannedChapter("book", 2)), missing)
    }

    private fun plannedBook(
        title: String = "Book",
        titleZh: String? = null,
        author: String? = null,
        episodes: Int = 0,
        tags: List<String> = emptyList(),
    ) = PlannedBook(
        id = "book",
        storageDir = "book",
        slug = "book",
        source = "kakuyomu",
        sourceId = "book",
        title = title,
        titleZh = titleZh,
        author = author,
        episodes = episodes,
        shelf = "reading",
        favorite = false,
        hidden = false,
        addedAt = "2025-01-01T00:00:00Z",
        legacyJson = null,
        tags = tags,
    )

    private fun bookEntity(
        titleZh: String?,
        author: String?,
        tagsJson: String?,
        importHash: String?,
        episodes: Int,
    ) = BookEntity(
        id = "book",
        storageDir = "book",
        slug = "book",
        source = "kakuyomu",
        sourceId = "book",
        title = "Book",
        titleZh = titleZh,
        author = author,
        tagsJson = tagsJson,
        genre = null,
        episodes = episodes,
        local = false,
        createdAt = "2025-01-01T00:00:00Z",
        legacyJson = null,
        importHash = importHash,
    )

    private fun stateEntity(
        progress: Int,
        favorite: Boolean,
        hidden: Boolean,
        updatedAt: String,
    ) = ReadStateEntity(
        bookId = "book",
        shelf = "reading",
        favorite = favorite,
        hidden = hidden,
        progressIdx = progress,
        openedAt = null,
        finishedAt = null,
        updatedAt = updatedAt,
    )

    private fun plannedChapter(bookId: String, idx: Int) = PlannedChapter(
        bookId = bookId,
        idx = idx,
        rawPath = "raw/$idx.txt",
        zhPath = null,
        status = "raw",
    )
}
