package com.kacyraho.lightnovel.data.import

import com.kacyraho.lightnovel.fixture.SyntheticBackup
import java.nio.file.Files
import java.nio.file.Path
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class BackupFilesTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun prepared(): Pair<Path, ImportPlan> {
        val zip = tmp.newFile("nineteen.zip").toPath()
        SyntheticBackup.nineteenBooks(zip)
        return zip to BackupImportService().plan(zip)
    }

    private fun extract(zip: Path, plan: ImportPlan, name: String): Path {
        val staging = tmp.newFolder(name).toPath()
        BackupExtractor().extract(zip, staging, plan.verify)
        return staging
    }

    @Test
    fun extractsAllManifestFiles() {
        val (zip, plan) = prepared()
        val staging = extract(zip, plan, "staging-extract")

        assertEquals(
            "中文译文 1",
            read(staging.resolve("novels/kakuyomu-1/chapters/0001.txt")),
        )
        assertTrue(Files.isRegularFile(staging.resolve("data/library.json")))
        assertTrue(Files.isRegularFile(staging.resolve("lnfinder/taste_profile.json")))
        assertTrue(Files.isRegularFile(staging.resolve("data/jobs/quarantine/bad.json")))
    }

    @Test
    fun commitsBooksAndArchivesLegacyData() {
        val (zip, plan) = prepared()
        val staging = extract(zip, plan, "staging-commit")
        val dataRoot = tmp.newFolder("data-root").toPath()

        val result = LibraryCommitter().commit(
            staging,
            dataRoot,
            plan.report.backupId,
            plan.report,
        )

        assertEquals(19, result.moved)
        assertTrue(Files.isRegularFile(dataRoot.resolve("novels/kakuyomu-1/chapters/0001.txt")))
        assertTrue(Files.isRegularFile(dataRoot.resolve("legacy/backup-test/data/library.json")))
        assertTrue(Files.isRegularFile(dataRoot.resolve("legacy/backup-test/lnfinder/taste_profile.json")))
        assertFalse(Files.exists(staging.resolve("novels/kakuyomu-1")))
    }

    @Test
    fun recommitIsIdempotentAndDoesNotCreateBak() {
        val (zip, plan) = prepared()
        val dataRoot = tmp.newFolder("data-root-idem").toPath()
        val first = extract(zip, plan, "staging-idem-1")
        LibraryCommitter().commit(first, dataRoot, plan.report.backupId, plan.report)

        val second = extract(zip, plan, "staging-idem-2")
        val result = LibraryCommitter().commit(second, dataRoot, plan.report.backupId, plan.report)

        assertEquals(0, result.moved)
        assertEquals(19, result.unchanged)
        assertFalse(hasBak(dataRoot.resolve("novels")))
    }

    @Test
    fun existingDifferentBookGetsBakAndIsReplaced() {
        val (zip, plan) = prepared()
        val dataRoot = tmp.newFolder("data-root-bak").toPath()
        val first = extract(zip, plan, "staging-bak-1")
        LibraryCommitter().commit(first, dataRoot, plan.report.backupId, plan.report)

        val chapter = dataRoot.resolve("novels/kakuyomu-1/chapters/0001.txt")
        write(chapter, "dirty-local-content")
        val second = extract(zip, plan, "staging-bak-2")
        val result = LibraryCommitter().commit(second, dataRoot, plan.report.backupId, plan.report)

        assertEquals(1, result.moved)
        assertEquals(18, result.unchanged)
        assertEquals(1, result.backups.size)
        assertEquals("中文译文 1", read(chapter))
        assertTrue(hasBak(dataRoot.resolve("novels")))
        val bakDir = bakDirs(dataRoot.resolve("novels")).single()
        assertEquals(
            "dirty-local-content",
            read(bakDir.resolve("chapters/0001.txt")),
        )
    }

    private fun hasBak(root: Path): Boolean = bakDirs(root).isNotEmpty()

    private fun bakDirs(root: Path): List<Path> {
        if (!Files.exists(root)) return emptyList()
        Files.walk(root).use { stream ->
            return stream
                .filter { Files.isDirectory(it) && it.fileName.toString().contains(".bak-") }
                .collect(java.util.stream.Collectors.toList())
        }
    }

    private fun read(path: Path): String =
        Files.readAllBytes(path).toString(Charsets.UTF_8)

    private fun write(path: Path, text: String) {
        Files.write(path, text.toByteArray(Charsets.UTF_8))
    }
}
