package com.kacyraho.lightnovel.data.import

import com.kacyraho.lightnovel.fixture.SyntheticBackup
import java.nio.file.Path
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ImportPlannerTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun file(name: String): Path = tmp.newFile(name).toPath()

    @Test
    fun plansNineteenBooksWithLegacyAndOrphanCases() {
        val path = file("nineteen.zip")
        SyntheticBackup.nineteenBooks(path)

        val plan = BackupImportService().plan(path)

        assertTrue(plan.verify.error, plan.verify.ok)
        assertEquals(19, plan.report.books.size)
        assertEquals(19, plan.chapters.size)
        assertEquals(2, plan.readStates.size)
        assertEquals(listOf("orphan-4-日本語"), plan.report.orphanDirs)
        assertEquals(listOf("kakuyomu-20"), plan.report.missingDirs)
        assertEquals(17, plan.report.dirClasses["v5_conform"])
        assertEquals(1, plan.report.dirClasses["legacy_short"])
        assertEquals(1, plan.report.dirClasses["legacy_other"])

        val short = plan.report.books.first { it.storageDir == "short-3" }
        assertEquals("kakuyomu-3", short.id)
        assertTrue(short.flags.contains("id_dir_mismatch"))
        assertTrue(short.flags.contains("id_format_legacy"))

        val orphan = plan.report.books.first { it.storageDir == "orphan-4-日本語" }
        assertEquals("orphan-4-日本語", orphan.id)
        assertTrue(orphan.flags.contains("orphan_dir"))
    }

    @Test
    fun resolvesSlugConflictsWithoutStealingTheWinner() {
        val path = file("conflict.zip")
        SyntheticBackup.conflictedSlugs(path)

        val plan = BackupImportService().plan(path)
        val books = plan.report.books.associateBy { it.id }

        assertEquals(setOf("same", "same-2"), books.values.map { it.slug }.toSet())
        assertEquals(1, plan.report.conflicts.size)
        assertEquals("same-2", plan.report.conflicts.single().chosenSlug)
        assertTrue(plan.catalog.aliases.isEmpty())
    }
}
