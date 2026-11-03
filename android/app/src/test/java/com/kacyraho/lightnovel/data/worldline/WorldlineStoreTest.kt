package com.kacyraho.lightnovel.data.worldline

import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.knowledge.Fact
import com.kacyraho.lightnovel.data.knowledge.FactAnchor
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class WorldlineStoreTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun store(): WorldlineStore =
        WorldlineStore(FileContentStore(tmp.newFolder("data").toPath()))

    @Test
    fun savesListsLoadsAndDeletesBranches() {
        val store = store()
        val a = store.save(
            "book",
            WorldlineFile(
                id = "wl-a",
                bookId = "book",
                title = "A",
                forkChapter = 3,
                chapters = listOf(BranchChapter(1, "一", "正文", "梗概")),
            ),
        )
        store.save(
            "book",
            WorldlineFile(id = "wl-b", bookId = "book", title = "B", forkChapter = 5),
        )
        assertEquals(1, a.branchCursor)
        assertEquals(2, store.list("book").size)
        assertNotNull(store.load("book", "wl-a"))
        assertTrue(store.delete("book", "wl-a"))
        assertEquals(1, store.list("book").size)
        assertTrue(!store.delete("book", "missing"))
    }

    @Test
    fun removesKnowledgeForOneChapter() {
        val store = store()
        store.saveKnowledge(
            "book",
            BranchKnowledgeFile(
                worldlineId = "wl-a",
                facts = listOf(
                    Fact(id = "f1", text = "一", sourceAnchor = FactAnchor(1, 0, 0, "")),
                    Fact(id = "f2", text = "二", sourceAnchor = FactAnchor(2, 0, 0, "")),
                ),
                extractedChapters = listOf(1, 2),
            ),
        )
        store.removeKnowledgeChapter("book", "wl-a", 2)
        val knowledge = store.loadKnowledge("book", "wl-a")
        assertEquals(listOf(1), knowledge?.extractedChapters)
        assertEquals(listOf("f1"), knowledge?.facts?.map { it.id })
        assertEquals(1, knowledge?.branchExtractedThrough)
    }
}
