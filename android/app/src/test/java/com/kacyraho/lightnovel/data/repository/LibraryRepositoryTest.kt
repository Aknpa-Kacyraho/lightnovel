package com.kacyraho.lightnovel.data.repository

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.model.ReaderAnchor
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class LibraryRepositoryTest {
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
