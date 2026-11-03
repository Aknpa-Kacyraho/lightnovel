package com.kacyraho.lightnovel.data.repository

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.model.ReaderAnchor
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import java.nio.file.Files
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class LibraryRepositoryTest {
    @get:Rule
    val tmp = TemporaryFolder()
    private fun database(): LightnovelDatabase {
        val context = ApplicationProvider.getApplicationContext<Context>()
        return Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
    }

    @Test
    fun observesVisibleBooksAndFiltersShelfAndQuery() = runTest {
        val db = database()
        try {
            val dao = db.libraryDao()
            dao.upsertBooks(
                listOf(
                    book("b1", "1", "Alpha", "作者甲"),
                    book("b2", "2", "Beta", "作者乙"),
                ),
            )
            dao.upsertReadStates(
                listOf(
                    state("b1", "reading", hidden = false),
                    state("b2", "reading", hidden = true),
                ),
            )

            val repo = RoomLibraryRepository(db)
            val visible = repo.observeBooks().first()
            assertEquals(listOf("b1"), visible.map { it.id })

            val reading = repo.observeBooks(ShelfFilter(shelf = "reading")).first()
            assertEquals(listOf("b1"), reading.map { it.id })

            val library = repo.observeLibrary().first()
            assertEquals(listOf("b1"), library.map { it.book.id })
            assertEquals("reading", library.single().state?.shelf)

            val query = repo.observeBooks(ShelfFilter(query = "作者甲")).first()
            assertEquals(listOf("b1"), query.map { it.id })
        } finally {
            db.close()
        }
    }

    @Test
    fun updateProgressCreatesThenUpdatesAnchor() = runTest {
        val db = database()
        try {
            val repo = RoomLibraryRepository(db)
            repo.updateProgress("b1", ReaderAnchor(chapterIndex = 3, paragraphId = 7, charOffset = 12))
            val created = repo.readState("b1")
            assertNotNull(created)
            assertEquals(3, created?.progressIdx)
            assertEquals(7, created?.progressBlock)
            assertEquals(12, created?.progressChar)
            assertNotNull(created?.updatedAt)

            repo.updateProgress("b1", ReaderAnchor(chapterIndex = 4, paragraphId = 2, charOffset = 5))
            val updated = repo.readState("b1")
            assertEquals(4, updated?.progressIdx)
            assertEquals(2, updated?.progressBlock)
            assertEquals(5, updated?.progressChar)
        } finally {
            db.close()
        }
    }

    @Test
    fun removeBookHidesItAndRestoreKeepsProgressAndFiles() = runTest {
        val db = database()
        val store = FileContentStore(tmp.newFolder("data").toPath())
        try {
            val dao = db.libraryDao()
            val entity = book("b1", "1", "Alpha", "作者")
            dao.upsertBooks(listOf(entity))
            dao.upsertReadStates(
                listOf(
                    state("b1", "reading", hidden = false).copy(
                        progressIdx = 7,
                        progressBlock = 3,
                    ),
                ),
            )
            dao.upsertChapters(
                listOf(
                    ChapterEntity(
                        bookId = "b1",
                        idx = 1,
                        title = "第一章",
                        titleZh = "第一章",
                        rawPath = null,
                        zhPath = null,
                        status = "complete",
                        tokenIn = 0,
                        tokenOut = 0,
                        model = null,
                        updatedAt = null,
                    ),
                ),
            )
            store.writeZhAtomic("b1", 1, "译文")

            val repo = RoomLibraryRepository(db)
            repo.removeBook("b1")

            assertNotNull(dao.book("b1"))
            assertEquals(true, dao.readState("b1")?.hidden)
            assertEquals(1, dao.chapters("b1").size)
            assertTrue(Files.exists(store.paths("b1").bookDir))
            assertTrue(repo.observeLibrary().first().isEmpty())
            assertEquals(
                listOf("b1"),
                repo.observeLibrary(ShelfFilter(removedOnly = true)).first().map { it.book.id },
            )

            repo.restoreBook("b1")

            val restored = dao.readState("b1")
            assertEquals(false, restored?.hidden)
            assertEquals(7, restored?.progressIdx)
            assertEquals(3, restored?.progressBlock)
            assertEquals(listOf("b1"), repo.observeLibrary().first().map { it.book.id })
        } finally {
            db.close()
        }
    }

    private fun book(id: String, sourceId: String, title: String, author: String): BookEntity =
        BookEntity(
            id = id,
            storageDir = id,
            slug = id,
            source = "kakuyomu",
            sourceId = sourceId,
            title = title,
            titleZh = null,
            author = author,
            tagsJson = null,
            genre = null,
            episodes = 0,
            local = false,
            createdAt = null,
            legacyJson = null,
        )

    private fun state(bookId: String, shelf: String, hidden: Boolean): ReadStateEntity =
        ReadStateEntity(
            bookId = bookId,
            shelf = shelf,
            favorite = false,
            hidden = hidden,
            progressIdx = 0,
            openedAt = null,
            finishedAt = null,
        )
}
