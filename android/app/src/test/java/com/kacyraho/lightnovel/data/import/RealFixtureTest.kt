package com.kacyraho.lightnovel.data.import

import java.nio.file.Files
import java.nio.file.Path
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class RealFixtureTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun importsRealBackupWhenProvided() {
        val raw = System.getenv("LN_TEST_FIXTURE_ZIP")
        assumeTrue("LN_TEST_FIXTURE_ZIP 未设置", !raw.isNullOrBlank())
        val zip = Path.of(raw!!)
        assumeTrue("fixture 不存在", Files.isRegularFile(zip))

        val plan = BackupImportService().plan(zip)
        assertTrue(plan.verify.error, plan.verify.ok)
        assertTrue(plan.report.books.isNotEmpty())
        assertTrue(plan.chapters.isNotEmpty())
        assertTrue(plan.readStates.isNotEmpty())

        val staging = tmp.newFolder("real-staging").toPath()
        BackupExtractor().extract(zip, staging, plan.verify)
        val dataRoot = tmp.newFolder("real-data").toPath()
        val committed = LibraryCommitter().commit(
            staging,
            dataRoot,
            plan.report.backupId,
            plan.report,
        )

        assertEquals(
            plan.report.books.size,
            committed.moved + committed.unchanged,
        )
        assertTrue(plan.report.orphanDirs.isEmpty())
        plan.report.books.forEach { book ->
            assertTrue(
                "缺少书目录：${book.storageDir}",
                Files.isDirectory(dataRoot.resolve("novels").resolve(book.storageDir)),
            )
        }
        println(
            "real fixture: books=${plan.report.books.size} " +
                "chapters=${plan.chapters.size} " +
                "readStates=${plan.readStates.size} " +
                "classes=${plan.report.dirClasses} " +
                "orphans=${plan.report.orphanDirs.size} " +
                "missing=${plan.report.missingDirs.size} " +
                "conflicts=${plan.report.conflicts.size}",
        )
    }
}
