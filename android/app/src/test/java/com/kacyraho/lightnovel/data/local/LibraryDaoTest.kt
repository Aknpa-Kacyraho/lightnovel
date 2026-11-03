package com.kacyraho.lightnovel.data.local

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.data.import.BackupImportService
import com.kacyraho.lightnovel.fixture.SyntheticBackup
import java.nio.file.Files
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class LibraryDaoTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun database(): LightnovelDatabase {
        val context = ApplicationProvider.getApplicationContext<Context>()
        return Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
    }

    @Test
    fun upsertDoesNotDeleteExistingRows() = runTest {
        val db = database()
        try {
            val dao = db.libraryDao()
            dao.upsertBooks(listOf(book("kakuyomu-1", "one", "One")))
            dao.upsertBooks(listOf(book("kakuyomu-2", "two", "Two")))
            assertEquals(2, dao.bookCount())

            dao.upsertBooks(listOf(book("kakuyomu-1", "one", "One Updated")))
            assertEquals(2, dao.bookCount())
            assertEquals("One Updated", dao.books().first { it.id == "kakuyomu-1" }.title)
        } finally {
            db.close()
        }
    }

    @Test
    fun onlineKeysExcludeLocalBooks() = runTest {
        val db = database()
        try {
            val dao = db.libraryDao()
            dao.upsertBooks(
                listOf(
                    book("kakuyomu-online", "online", "Online"),
                    book("kakuyomu-hidden", "hidden", "Hidden"),
                    book("local-1", "local", "Local").copy(
                        source = "local",
                        sourceId = "1",
                        local = true,
                    ),
                ),
            )
            dao.upsertReadStates(
                listOf(
                    ReadStateEntity(
                        bookId = "kakuyomu-hidden",
                        shelf = "reading",
                        favorite = false,
                        hidden = true,
                        progressIdx = 3,
                        openedAt = null,
                        finishedAt = null,
                    ),
                ),
            )

            assertEquals(setOf("kakuyomu/online"), dao.onlineKeys().toSet())
        } finally {
            db.close()
        }
    }

    @Test
    fun appliesImportPlanWithoutDeletingAndIsIdempotent() = runTest {
        val path = tmp.newFile("import.zip").toPath()
        SyntheticBackup.nineteenBooks(path)
        val service = BackupImportService()
        val plan = service.plan(path)

        val db = database()
        try {
            val dao = db.libraryDao()
            val first = service.apply(plan, dao)
            assertEquals(19, first.books)
            assertEquals(19, first.chapters)
            assertEquals(19, dao.bookCount())
            assertEquals(19, dao.chapterCount())
            assertEquals("translated", dao.chapters("kakuyomu-1").single().status)
            assertEquals(4, dao.aliases().size)

            val second = service.apply(plan, dao)
            assertEquals(19, second.books)
            assertEquals(19, dao.bookCount())
            assertEquals(4, dao.aliases().size)

            val state = dao.readState("kakuyomu-1")
            assertNotNull(state)
            assertEquals("reading", state?.shelf)
            assertEquals(true, state?.favorite)

            val finished = dao.readState("kakuyomu-2")
            assertNotNull(finished)
            assertEquals("finished", finished?.shelf)
            assertEquals(5, finished?.progressIdx)

            val short = dao.books().first { it.id == "kakuyomu-3" }
            assertEquals("short-3", short.storageDir)
            assertEquals("short-3", short.slug)
        } finally {
            db.close()
        }
    }

    private fun book(id: String, slug: String, title: String): BookEntity = BookEntity(
        id = id,
        storageDir = id,
        slug = slug,
        source = "kakuyomu",
        sourceId = id.removePrefix("kakuyomu-"),
        title = title,
        titleZh = null,
        author = null,
        tagsJson = null,
        genre = null,
        episodes = 0,
        local = false,
        createdAt = null,
        legacyJson = null,
    )
}
