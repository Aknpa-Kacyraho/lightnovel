package com.kacyraho.lightnovel.data.import

import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class LibraryCommitterTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun shiftsPythonZeroBasedChapterFilesInStaging() {
        val staging = tmp.newFolder("staging-zero").toPath()
        val source = staging.resolve("novels/book")
        Files.createDirectories(source.resolve("raw"))
        Files.createDirectories(source.resolve("chapters"))
        Files.write(source.resolve("raw/0000.txt"), "first".toByteArray(Charsets.UTF_8))
        Files.write(source.resolve("raw/0001.txt"), "second".toByteArray(Charsets.UTF_8))
        Files.write(source.resolve("chapters/0000.meta.json"), "{}".toByteArray(Charsets.UTF_8))

        val dataRoot = tmp.newFolder("data-zero").toPath()
        val book = PlannedBook(
            id = "book",
            storageDir = "book",
            slug = "book",
            source = "kakuyomu",
            sourceId = "book",
            title = "Book",
            shelf = null,
            favorite = false,
            hidden = false,
            addedAt = null,
            legacyJson = null,
        )
        val report = MigrationReport(
            backupId = "backup-zero",
            dirClasses = emptyMap(),
            books = listOf(book),
            orphanDirs = emptyList(),
            missingDirs = emptyList(),
            conflicts = emptyList(),
        )

        LibraryCommitter().commit(staging, dataRoot, report.backupId, report)

        val dest = dataRoot.resolve("novels/book")
        assertTrue(Files.exists(dest.resolve("raw/0001.txt")))
        assertTrue(Files.exists(dest.resolve("raw/0002.txt")))
        assertTrue(Files.exists(dest.resolve("chapters/0001.meta.json")))
        assertFalse(Files.exists(dest.resolve("raw/0000.txt")))
    }

    @Test
    fun failedCommitRollsBackAlreadyMovedBooks() {
        val staging = tmp.newFolder("staging").toPath()
        val source = staging.resolve("novels/ok")
        Files.createDirectories(source)
        Files.write(source.resolve("a.txt"), "x".toByteArray(Charsets.UTF_8))

        val dataRoot = tmp.newFolder("data").toPath()
        val ok = PlannedBook(
            id = "ok",
            storageDir = "ok",
            slug = "ok",
            source = "kakuyomu",
            sourceId = "ok",
            title = "OK",
            shelf = null,
            favorite = false,
            hidden = false,
            addedAt = null,
            legacyJson = null,
        )
        val missing = ok.copy(id = "missing", storageDir = "missing", slug = "missing")
        val report = MigrationReport(
            backupId = "backup-rollback",
            dirClasses = emptyMap(),
            books = listOf(ok, missing),
            orphanDirs = emptyList(),
            missingDirs = emptyList(),
            conflicts = emptyList(),
        )

        assertThrows(Exception::class.java) {
            LibraryCommitter().commit(staging, dataRoot, report.backupId, report)
        }

        assertFalse(Files.exists(dataRoot.resolve("novels/ok")))
        assertTrue(Files.isDirectory(source))
    }

    @Test
    fun mergingKeepsExistingFilesAndAddsMissingOnes() {
        val staging = tmp.newFolder("staging-merge").toPath()
        val source = staging.resolve("novels/book")
        Files.createDirectories(source.resolve("raw"))
        Files.write(source.resolve("raw/0001.txt"), "backup-1".toByteArray(Charsets.UTF_8))
        Files.write(source.resolve("raw/0002.txt"), "backup-2".toByteArray(Charsets.UTF_8))

        val dataRoot = tmp.newFolder("data-merge").toPath()
        val dest = dataRoot.resolve("novels/book")
        Files.createDirectories(dest.resolve("raw"))
        Files.createDirectories(dest.resolve("zh"))
        Files.write(dest.resolve("raw/0001.txt"), "local-1".toByteArray(Charsets.UTF_8))
        Files.write(dest.resolve("zh/0001.txt"), "translated-1".toByteArray(Charsets.UTF_8))

        val book = PlannedBook(
            id = "book",
            storageDir = "book",
            slug = "book",
            source = "kakuyomu",
            sourceId = "book",
            title = "Book",
            shelf = null,
            favorite = false,
            hidden = false,
            addedAt = null,
            legacyJson = null,
        )
        val report = MigrationReport(
            backupId = "backup-merge",
            dirClasses = emptyMap(),
            books = listOf(book),
            orphanDirs = emptyList(),
            missingDirs = emptyList(),
            conflicts = emptyList(),
        )

        val result = LibraryCommitter().commit(staging, dataRoot, report.backupId, report)

        assertEquals("local-1", String(Files.readAllBytes(dest.resolve("raw/0001.txt")), Charsets.UTF_8))
        assertEquals(
            "translated-1",
            String(Files.readAllBytes(dest.resolve("zh/0001.txt")), Charsets.UTF_8),
        )
        assertEquals("backup-2", String(Files.readAllBytes(dest.resolve("raw/0002.txt")), Charsets.UTF_8))
        assertEquals(1, result.merged)
    }
}
