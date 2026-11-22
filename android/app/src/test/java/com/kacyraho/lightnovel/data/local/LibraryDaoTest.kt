package com.kacyraho.lightnovel.data.local

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.data.import.BackupImportService
import com.kacyraho.lightnovel.fixture.SyntheticBackup
import java.nio.file.Files
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
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
            assertEquals(20, first.books)
            assertEquals(19, first.chapters)
            assertEquals(20, dao.bookCount())
            assertEquals(19, dao.chapterCount())
            assertEquals("translated", dao.chapters("kakuyomu-1").single().status)
            assertEquals(4, dao.aliases().size)

            val second = service.apply(plan, dao)
            assertEquals(20, second.books)
            assertEquals(20, dao.bookCount())
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

    @Test
    fun findsBookByImportHashAndRejectsDuplicates() = runTest {
        val db = database()
        try {
            val dao = db.libraryDao()
            val first = book("local-1", "local-1", "Local").copy(
                source = "local",
                sourceId = "local-1",
                local = true,
                importHash = "abc",
            )
            dao.upsertBooks(listOf(first))

            assertEquals("local-1", dao.bookByImportHash("abc")?.id)
            assertNull(dao.bookByImportHash("missing"))

            val duplicate = book("local-2", "local-2", "Local 2").copy(
                source = "local",
                sourceId = "local-2",
                local = true,
                importHash = "abc",
            )
            dao.upsertBooks(listOf(duplicate))

            // 唯一索引让重复 hash 的插入被忽略，不会新增第二本。
            assertEquals(1, dao.bookCount())
            assertEquals("local-1", dao.bookByImportHash("abc")?.id)
        } finally {
            db.close()
        }
    }

    @Test
    fun deleteBookRemovesChaptersAndReadState() = runTest {
        val db = database()
        try {
            val dao = db.libraryDao()
            dao.upsertBooks(listOf(book("local-1", "l1", "Local")))
            dao.upsertChapters(
                listOf(
                    ChapterEntity(
                        bookId = "local-1",
                        idx = 1,
                        title = "c1",
                        titleZh = null,
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
            dao.upsertReadStates(
                listOf(
                    ReadStateEntity(
                        bookId = "local-1",
                        shelf = "reading",
                        favorite = false,
                        hidden = false,
                        progressIdx = 1,
                        openedAt = null,
                        finishedAt = null,
                        updatedAt = null,
                    ),
                ),
            )

            dao.deleteChapters("local-1")
            dao.deleteReadState("local-1")
            dao.deleteBook("local-1")

            assertEquals(0, dao.bookCount())
            assertEquals(0, dao.chapterCount())
            assertNull(dao.readState("local-1"))
        } finally {
            db.close()
        }
    }

    @Test
    fun bookmarkUpsertDeduplicatesAndDeletes() = runTest {
        val db = database()
        try {
            val dao = db.libraryDao()
            dao.upsertBooks(listOf(book("local-1", "l1", "Local")))
            val bookmark = BookmarkEntity(
                bookId = "local-1",
                chapterIdx = 1,
                paragraphId = 2,
                charOffset = 0,
                preview = "preview",
                createdAt = "2026-11-20T00:00:00Z",
            )

            dao.upsertBookmark(bookmark)
            dao.upsertBookmark(bookmark.copy(preview = "updated"))

            val all = dao.observeBookmarks("local-1").first()
            assertEquals(1, all.size)
            assertEquals("updated", dao.bookmark("local-1", 1, 2)?.preview)

            dao.deleteBookmark("local-1", 1, 2)
            assertEquals(0, dao.observeBookmarks("local-1").first().size)
        } finally {
            db.close()
        }
    }

    @Test
    fun failureReasonIsStoredAndClearedOnRetry() = runTest {
        val db = database()
        try {
            val dao = db.libraryDao()
            val book = book("kakuyomu-7", "7", "Seven")
            dao.upsertBooks(listOf(book))
            dao.upsertChapters(
                listOf(
                    ChapterEntity(
                        bookId = book.id,
                        idx = 1,
                        title = "第一章",
                        titleZh = null,
                        rawPath = null,
                        zhPath = null,
                        status = "raw",
                        tokenIn = 0,
                        tokenOut = 0,
                        model = null,
                        updatedAt = null,
                    ),
                ),
            )

            dao.markChapterFailure(
                bookId = book.id,
                idx = 1,
                status = "failed",
                model = "deepseek-flash",
                tokenIn = 0,
                tokenOut = 0,
                updatedAt = "2026-11-22T00:00:00Z",
                lastError = "网络超时",
            )

            val task = dao.observeActiveTasks().first().single()
            assertEquals("failed", task.status)
            assertEquals("网络超时", task.lastError)

            dao.updateChapterTranslation(
                bookId = book.id,
                idx = 1,
                status = "translating",
                model = "deepseek-flash",
                tokenIn = 0,
                tokenOut = 0,
                updatedAt = "2026-11-22T00:01:00Z",
            )

            assertNull(dao.chapters(book.id).single().lastError)
        } finally {
            db.close()
        }
    }

    private fun book(id: String, slug: String, title: String): BookEntity = BookEntity(        id = id,
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
