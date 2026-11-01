package com.kacyraho.lightnovel.data.export

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.data.backup.BackupVerifier
import com.kacyraho.lightnovel.data.local.AliasEntity
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.nio.file.Path
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
class BackupExporterTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun exportsVerifiableBackupWithCatalogAndState() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val dao = db.libraryDao()
            dao.upsertBooks(
                listOf(
                    BookEntity(
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
                        createdAt = "2026-10-01",
                        legacyJson = null,
                    ),
                ),
            )
            dao.upsertReadStates(
                listOf(
                    ReadStateEntity(
                        bookId = "kakuyomu-1",
                        shelf = "reading",
                        favorite = true,
                        hidden = false,
                        progressIdx = 3,
                        progressBlock = 2,
                        progressChar = 5,
                        openedAt = "2026-10-02",
                        finishedAt = null,
                    ),
                ),
            )
            dao.upsertAliases(listOf(AliasEntity("old-slug", "kakuyomu-1")))

            val dataRoot = tmp.newFolder("data-root").toPath()
            val novelFile = dataRoot.resolve("novels/kakuyomu-1/chapters/0001.txt")
            Files.createDirectories(novelFile.parent)
            Files.write(novelFile, "中文译文".toByteArray(Charsets.UTF_8))
            val cacheFile = dataRoot.resolve("novels/kakuyomu-1/cache/0000.json")
            Files.createDirectories(cacheFile.parent)
            Files.write(cacheFile, "{\"chunk\":\"secret\"}".toByteArray(Charsets.UTF_8))

            val bytes = ByteArrayOutputStream()
            val manifest = BackupExporter(dataRoot, dao).export(bytes)

            assertEquals(1, manifest.format)
            assertEquals(3, manifest.entries.count { it.path.startsWith("data/") })
            assertTrue(manifest.entries.any { it.path == "novels/kakuyomu-1/chapters/0001.txt" })
            assertTrue(manifest.entries.none { it.path.contains("/cache/") })
            assertTrue(manifest.entries.any { it.path == "data/books/kakuyomu-1.json" })

            val zip = write(bytes.toByteArray())
            val verify = BackupVerifier().verify(zip)
            assertTrue(verify.error, verify.ok)
            ZipFile(zip.toFile()).use { file ->
                assertTrue(file.getEntry("data/library.json") != null)
                assertTrue(file.getEntry("data/slug-aliases.json") != null)
                val state = file.getInputStream(file.getEntry("data/books/kakuyomu-1.json"))
                    .bufferedReader()
                    .readText()
                assertTrue(state.contains("\"block\":2"))
                assertTrue(state.contains("\"char\":5"))
            }
        } finally {
            db.close()
        }
    }

    private fun write(bytes: ByteArray): Path {
        val path = tmp.newFile("export.zip").toPath()
        Files.write(path, bytes)
        return path
    }
}
