package com.kacyraho.lightnovel.data.import

import java.nio.file.Files
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
}
