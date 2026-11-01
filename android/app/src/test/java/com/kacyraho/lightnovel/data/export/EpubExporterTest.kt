package com.kacyraho.lightnovel.data.export

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.util.zip.ZipFile
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class EpubExporterTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun exportsReadableEpubStructure() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val dao = db.libraryDao()
            val book = BookEntity(
                id = "kakuyomu-1",
                storageDir = "kakuyomu-1",
                slug = "kakuyomu-1",
                source = "kakuyomu",
                sourceId = "1",
                title = "Title",
                titleZh = "标题",
                author = "Author",
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
                    ChapterEntity(
                        bookId = book.id,
                        idx = 1,
                        title = "第一章",
                        titleZh = null,
                        rawPath = "raw/0001.txt",
                        zhPath = "chapters/0001.txt",
                        status = "complete",
                        tokenIn = 0,
                        tokenOut = 0,
                        model = null,
                        updatedAt = null,
                    ),
                ),
            )
            val store = FileContentStore(tmp.newFolder("data").toPath())
            store.writeZhAtomic(book.storageDir, 1, "这是正文。")

            val output = ByteArrayOutputStream()
            EpubExporter(dao, store).export(book, output)

            val zipPath = tmp.newFile("book.epub").toPath()
            Files.write(zipPath, output.toByteArray())
            ZipFile(zipPath.toFile()).use { zip ->
                assertTrue(zip.getEntry("mimetype") != null)
                assertTrue(zip.getEntry("META-INF/container.xml") != null)
                assertTrue(zip.getEntry("OEBPS/content.opf") != null)
                assertTrue(zip.getEntry("OEBPS/chapter-1.xhtml") != null)
                val chapter = zip.getInputStream(zip.getEntry("OEBPS/chapter-1.xhtml"))
                    .readBytes().toString(Charsets.UTF_8)
                assertTrue(chapter.contains("这是正文。"))
                assertEquals(
                    ZipEntryMethod.STORED,
                    zip.getEntry("mimetype")?.method,
                )
            }
        } finally {
            db.close()
        }
    }

    private object ZipEntryMethod {
        const val STORED = java.util.zip.ZipEntry.STORED
    }
}
