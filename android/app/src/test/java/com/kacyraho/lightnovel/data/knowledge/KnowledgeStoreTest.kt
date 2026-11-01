package com.kacyraho.lightnovel.data.knowledge

import com.kacyraho.lightnovel.core.storage.FileContentStore
import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class KnowledgeStoreTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun store(): KnowledgeStore =
        KnowledgeStore(FileContentStore(tmp.newFolder("data").toPath()))

    @Test
    fun savesAndLoadsPerBook() {
        val store = store()
        val saved = store.save(
            "book-a",
            KnowledgeFile(
                workId = "book-a",
                title = "A",
                extractedChapters = listOf(1, 2, 4),
            ),
        )
        assertEquals(2, saved.canonExtractedThrough)
        val loaded = store.load("book-a", "book-a")
        assertEquals("A", loaded.title)
        assertEquals(listOf(1, 2, 4), loaded.extractedChapters)
        assertEquals(2, loaded.canonExtractedThrough)
        assertTrue(
            Files.isRegularFile(
                tmp.root.toPath().resolve("data/novels/book-a/knowledge.json"),
            ),
        )
        assertEquals(0, store.load("book-b", "book-b").extractedChapters.size)
    }

    @Test
    fun contiguousPrefixStopsAtGap() {
        val store = store()
        val saved = store.save(
            "book",
            KnowledgeFile(workId = "book", extractedChapters = listOf(2, 3)),
        )
        assertEquals(0, saved.canonExtractedThrough)
    }
}
