package com.kacyraho.lightnovel.data.source

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class DirectLibraryServiceSyncTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun appendsSourceChaptersWithoutTouchingLocalData() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val dao = db.libraryDao()
            val book = BookEntity(
                id = "fake-1",
                storageDir = "fake-1",
                slug = "fake-1",
                source = "fake",
                sourceId = "1",
                title = "Book",
                titleZh = null,
                author = null,
                tagsJson = null,
                genre = null,
                episodes = 2,
                local = false,
                createdAt = null,
                legacyJson = null,
            )
            dao.upsertBooks(listOf(book))
            dao.upsertChapters(
                listOf(
                    chapter(book.id, 1, "complete", "raw/0001.txt", "zh/0001.txt"),
                    chapter(book.id, 2, "partial", "raw/0002.txt", null),
                ),
            )
            val store = FileContentStore(tmp.newFolder("data").toPath())
            val source = FakeSource(
                listOf(
                    SourceChapterRef("1", "第一章"),
                    SourceChapterRef("2", "第二章"),
                    SourceChapterRef("3", "第三章"),
                    SourceChapterRef("4", "第四章"),
                ),
            )
            val service = DirectLibraryService(listOf(source), dao, db, store)

            val result = service.syncCatalog(book)

            assertEquals(2, result.added)
            assertEquals(4, result.total)
            assertEquals(listOf(3, 4), result.newIndices)
            val rows = dao.chapters(book.id)
            assertEquals(listOf(1, 2, 3, 4), rows.map { it.idx })
            assertEquals("complete", rows[0].status)
            assertEquals("raw/0001.txt", rows[0].rawPath)
            assertEquals("zh/0001.txt", rows[0].zhPath)
            assertEquals("partial", rows[1].status)
            assertEquals("online", rows[2].status)
            assertNull(rows[2].rawPath)
            assertEquals(4, dao.book(book.id)?.episodes)

            val again = service.syncCatalog(book)
            assertEquals(0, again.added)
            assertEquals(4, dao.chapters(book.id).size)
        } finally {
            db.close()
        }
    }

    @Test
    fun fillsBlankExistingTitlesButKeepsNonBlankOnes() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val dao = db.libraryDao()
            val book = BookEntity(
                id = "fake-2",
                storageDir = "fake-2",
                slug = "fake-2",
                source = "fake",
                sourceId = "2",
                title = "Book",
                titleZh = null,
                author = null,
                tagsJson = null,
                genre = null,
                episodes = 1,
                local = false,
                createdAt = null,
                legacyJson = null,
            )
            dao.upsertBooks(listOf(book))
            dao.upsertChapters(
                listOf(
                    chapter(book.id, 1, "raw", null, null).copy(title = null),
                ),
            )
            val source = FakeSource(listOf(SourceChapterRef("1", "源站标题")))
            val service = DirectLibraryService(listOf(source), dao, db, FileContentStore(tmp.newFolder("d2").toPath()))

            service.syncCatalog(book)

            assertEquals("源站标题", dao.chapters(book.id).single().title)
        } finally {
            db.close()
        }
    }

    private fun chapter(
        bookId: String,
        idx: Int,
        status: String,
        rawPath: String?,
        zhPath: String?,
    ) = ChapterEntity(
        bookId = bookId,
        idx = idx,
        title = "第 $idx 话",
        titleZh = null,
        rawPath = rawPath,
        zhPath = zhPath,
        status = status,
        tokenIn = 0,
        tokenOut = 0,
        model = null,
        updatedAt = null,
    )

    private class FakeSource(
        private val chapters: List<SourceChapterRef>,
    ) : WebSource {
        override val id: String = "fake"
        override val label: String = "Fake"

        override suspend fun search(query: String, page: Int): List<SourceBook> = emptyList()

        override suspend fun detail(bookId: String): SourceDetail = SourceDetail(
            book = SourceBook(provider = id, id = bookId, title = "Book"),
            chapters = chapters,
        )

        override suspend fun chapter(bookId: String, chapterId: String): String = "text"
    }
}
