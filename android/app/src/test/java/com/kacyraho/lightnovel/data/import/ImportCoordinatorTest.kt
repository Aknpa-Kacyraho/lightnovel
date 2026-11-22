package com.kacyraho.lightnovel.data.import

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.fixture.SyntheticBackup
import com.kacyraho.lightnovel.fixture.ZipFixture
import java.nio.file.Files
import java.time.Instant
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class ImportCoordinatorTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun importsBackupWithTransactionAndCleansStaging() = runTest {
        val zip = tmp.newFile("nineteen.zip").toPath()
        SyntheticBackup.nineteenBooks(zip)

        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val store = FileContentStore(tmp.newFolder("data").toPath())
            val coordinator = ImportCoordinator(db, store)

            val result = coordinator.import(zip)

            assertEquals(20, result.applied.books)
            assertEquals(19, result.applied.chapters)
            assertEquals(20, result.applied.readStates)
            assertEquals(20, db.libraryDao().bookCount())
            assertEquals(19, db.libraryDao().chapterCount())
            assertTrue(
                Files.isRegularFile(
                    store.paths("kakuyomu-1").zh(1),
                ),
            )
            assertTrue(
                Files.isRegularFile(
                    store.root.resolve("legacy/backup-test/data/library.json"),
                ),
            )
            assertFalse(
                Files.list(store.root).use { stream ->
                    stream.anyMatch { it.fileName.toString().startsWith("staging-") }
                },
            )

            db.libraryDao().updateBookTitle("kakuyomu-1", "新译名")
            db.libraryDao().updateChapterTitle("kakuyomu-1", 1, "新章节名")
            db.libraryDao().updateProgress("kakuyomu-1", 5, 10, 0, "2099-01-01T00:00:00Z")

            val again = coordinator.import(zip)
            assertEquals(20, again.applied.books)
            assertEquals(0, again.applied.chapters)
            assertEquals(20, db.libraryDao().bookCount())
            assertEquals("新译名", db.libraryDao().book("kakuyomu-1")?.titleZh)
            assertEquals(
                "新章节名",
                db.libraryDao().chapters("kakuyomu-1").first { it.idx == 1 }.titleZh,
            )
            assertEquals(5, db.libraryDao().readState("kakuyomu-1")?.progressIdx)
            assertEquals(10, db.libraryDao().readState("kakuyomu-1")?.progressBlock)
        } finally {
            db.close()
        }
    }

    @Test
    fun mergesBackupIntoExistingBookWithSameImportHash() = runTest {
        val zip = tmp.newFile("hash-merge.zip").toPath()
        val fixture = ZipFixture()
        fixture.add(
            "data/library.json",
            "{\"schema_version\":1,\"items\":{\"local-aaa\":{" +
                "\"id\":\"local-aaa\",\"slug\":\"local-aaa\"," +
                "\"source\":\"local\",\"source_id\":\"local-aaa\"," +
                "\"title\":\"Backup\",\"shelf\":\"reading\"," +
                "\"favorite\":false,\"hidden\":false," +
                "\"import_hash\":\"same-hash\"}}," +
                "\"candidates\":{},\"aliases\":{}}",
        )
        fixture.add("data/slug-aliases.json", "{}")
        fixture.add(
            "data/books/local-aaa.json",
            "{\"tracking\":\"reading\",\"favorites\":true," +
                "\"progress\":{\"chapter\":5,\"block\":10,\"char\":0}," +
                "\"updated_at\":\"2026-10-03T00:00:00Z\"}",
        )
        fixture.add(
            "data/chapters.json",
            "[{\"bookId\":\"local-aaa\",\"idx\":1," +
                "\"title\":\"备份章\",\"status\":\"raw\"}]",
        )
        fixture.add(
            "data/bookmarks.json",
            "[{\"bookId\":\"local-aaa\",\"chapterIdx\":1,\"paragraphId\":0," +
                "\"preview\":\"备份书签\",\"createdAt\":\"2026-10-03T00:00:00Z\"}]",
        )
        val manifest = fixture.manifest()
        fixture.write(zip, manifest)

        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            db.libraryDao().upsertBooks(
                listOf(
                    BookEntity(
                        id = "local-bbb",
                        storageDir = "local-bbb",
                        slug = "local-bbb",
                        source = "local",
                        sourceId = "local-bbb",
                        title = "Local",
                        titleZh = "本地",
                        author = null,
                        tagsJson = null,
                        genre = null,
                        episodes = 1,
                        local = true,
                        createdAt = "2026-10-01T00:00:00Z",
                        legacyJson = null,
                        importHash = "same-hash",
                    ),
                ),
            )
            val store = FileContentStore(tmp.newFolder("hash-merge-data").toPath())
            val coordinator = ImportCoordinator(db, store)

            coordinator.import(zip)

            assertEquals(1, db.libraryDao().bookCount())
            assertTrue(db.libraryDao().book("local-bbb") != null)
            assertTrue(db.libraryDao().book("local-aaa") == null)
            assertEquals(1, db.libraryDao().chapters("local-bbb").size)
            assertEquals(5, db.libraryDao().readState("local-bbb")?.progressIdx)
            assertEquals(10, db.libraryDao().readState("local-bbb")?.progressBlock)
            assertEquals("local-bbb", db.libraryDao().allBookmarks().single().bookId)
        } finally {
            db.close()
        }
    }

    @Test
    fun oldBackupWithoutChapterMetadataRebuildsOnlineCatalog() = runTest {
        val zip = tmp.newFile("old-catalog.zip").toPath()
        val fixture = ZipFixture()
        fixture.add(
            "data/library.json",
            "{\"schema_version\":1,\"items\":{\"kakuyomu-20\":{" +
                "\"id\":\"kakuyomu-20\",\"slug\":\"kakuyomu-20\"," +
                "\"source\":\"kakuyomu\",\"source_id\":\"20\"," +
                "\"title\":\"在线书\",\"shelf\":\"reading\"," +
                "\"favorite\":false,\"hidden\":false,\"episodes\":5}}," +
                "\"candidates\":{},\"aliases\":{}}",
        )
        fixture.add("data/slug-aliases.json", "{}")
        val manifest = fixture.manifest()
        fixture.write(zip, manifest)

        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val store = FileContentStore(tmp.newFolder("old-catalog-data").toPath())
            val coordinator = ImportCoordinator(db, store)

            coordinator.import(zip)

            val chapters = db.libraryDao().chapters("kakuyomu-20")
            assertEquals(5, chapters.size)
            assertEquals((1..5).toList(), chapters.map { it.idx })
            assertTrue(chapters.all { it.status == "online" })
        } finally {
            db.close()
        }
    }

    @Test
    fun restoresChapterMetadataForOnlineOnlyBook() = runTest {
        val zip = tmp.newFile("chapter-meta.zip").toPath()
        val fixture = ZipFixture()
        fixture.add(
            "data/library.json",
            "{\"schema_version\":1,\"items\":{\"kakuyomu-20\":{" +
                "\"id\":\"kakuyomu-20\",\"slug\":\"kakuyomu-20\"," +
                "\"source\":\"kakuyomu\",\"source_id\":\"20\"," +
                "\"title\":\"在线书\",\"shelf\":\"reading\"," +
                "\"favorite\":false,\"hidden\":false}}," +
                "\"candidates\":{},\"aliases\":{}}",
        )
        fixture.add("data/slug-aliases.json", "{}")
        fixture.add(
            "data/chapters.json",
            "[{\"bookId\":\"kakuyomu-20\",\"idx\":1," +
                "\"title\":\"第一话\",\"titleZh\":\"第一话\",\"status\":\"raw\"}]",
        )
        val manifest = fixture.manifest()
        fixture.write(zip, manifest)

        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val store = FileContentStore(tmp.newFolder("chapter-meta-data").toPath())
            val coordinator = ImportCoordinator(db, store)

            val result = coordinator.import(zip)

            assertEquals(1, result.applied.books)
            assertEquals(1, result.applied.chapters)
            val chapters = db.libraryDao().chapters("kakuyomu-20")
            assertEquals(1, chapters.size)
            assertEquals("第一话", chapters.single().title)
            assertEquals("第一话", chapters.single().titleZh)
            assertEquals("raw", chapters.single().status)
        } finally {
            db.close()
        }
    }

    @Test
    fun importsBookmarksWithoutDuplicatingOnReimport() = runTest {
        val zip = tmp.newFile("bookmarks.zip").toPath()
        val fixture = ZipFixture()
        fixture.add("novels/kakuyomu-1/meta.json", "{\"title\":\"Bookmarks\"}")
        fixture.add("novels/kakuyomu-1/raw/0001.txt", "日本語の本文")
        fixture.add("novels/kakuyomu-1/chapters/0001.txt", "中文译文")
        fixture.add(
            "data/library.json",
            "{\"schema_version\":1,\"items\":{\"kakuyomu-1\":{" +
                "\"id\":\"kakuyomu-1\",\"slug\":\"kakuyomu-1\"," +
                "\"source\":\"kakuyomu\",\"source_id\":\"1\"," +
                "\"title\":\"Bookmarks\",\"shelf\":\"reading\"," +
                "\"favorite\":false,\"hidden\":false}}," +
                "\"candidates\":{},\"aliases\":{}}",
        )
        fixture.add("data/slug-aliases.json", "{}")
        fixture.add(
            "data/bookmarks.json",
            "[{\"bookId\":\"kakuyomu-1\",\"chapterIdx\":2,\"paragraphId\":3," +
                "\"charOffset\":4,\"preview\":\"测试书签\"," +
                "\"createdAt\":\"2026-10-03T00:00:00Z\"}]",
        )
        val manifest = fixture.manifest()
        fixture.write(zip, manifest)

        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val store = FileContentStore(tmp.newFolder("bookmarks-data").toPath())
            val coordinator = ImportCoordinator(db, store)

            coordinator.import(zip)
            val first = db.libraryDao().allBookmarks()
            assertEquals(1, first.size)
            assertEquals(2, first.single().chapterIdx)
            assertEquals(3, first.single().paragraphId)
            assertEquals("测试书签", first.single().preview)

            coordinator.import(zip)
            assertEquals(1, db.libraryDao().allBookmarks().size)
        } finally {
            db.close()
        }
    }

    @Test
    fun importWithoutStateFileKeepsLocalProgress() = runTest {
        val zip = tmp.newFile("no-state.zip").toPath()
        val fixture = ZipFixture()
        fixture.add("novels/kakuyomu-1/meta.json", "{\"title\":\"No State\"}")
        fixture.add("novels/kakuyomu-1/raw/0001.txt", "日本語の本文")
        fixture.add("novels/kakuyomu-1/chapters/0001.txt", "中文译文")
        fixture.add(
            "data/library.json",
            "{\"schema_version\":1,\"items\":{\"kakuyomu-1\":{" +
                "\"id\":\"kakuyomu-1\",\"slug\":\"kakuyomu-1\"," +
                "\"source\":\"kakuyomu\",\"source_id\":\"1\"," +
                "\"title\":\"No State\",\"shelf\":\"reading\"," +
                "\"favorite\":false,\"hidden\":false}}," +
                "\"candidates\":{},\"aliases\":{}}",
        )
        fixture.add("data/slug-aliases.json", "{}")
        val manifest = fixture.manifest()
        fixture.write(zip, manifest)

        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val store = FileContentStore(tmp.newFolder("no-state-data").toPath())
            val coordinator = ImportCoordinator(db, store)

            coordinator.import(zip)
            db.libraryDao().updateProgress(
                "kakuyomu-1",
                5,
                10,
                0,
                Instant.now().toString(),
            )
            Thread.sleep(30)
            coordinator.import(zip)

            val state = db.libraryDao().readState("kakuyomu-1")
            assertEquals(5, state?.progressIdx)
            assertEquals(10, state?.progressBlock)
        } finally {
            db.close()
        }
    }
}
