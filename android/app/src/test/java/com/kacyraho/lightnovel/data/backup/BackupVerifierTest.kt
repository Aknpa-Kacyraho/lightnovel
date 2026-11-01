package com.kacyraho.lightnovel.data.backup

import com.kacyraho.lightnovel.fixture.ZipFixture
import java.nio.file.Path
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class BackupVerifierTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun file(name: String): Path = tmp.newFile(name).toPath()

    @Test
    fun acceptsValidBackup() {
        val path = file("ok.zip")
        val fx = ZipFixture()
            .add("novels/kakuyomu-1/meta.json", "{\"title\":\"A\"}")
            .add("data/library.json", "{\"schema_version\":1,\"items\":{},\"candidates\":{},\"aliases\":{}}")
        fx.write(path)

        val result = BackupVerifier().verify(path)

        assertTrue(result.error, result.ok)
        assertEquals(2, result.entryCount)
    }

    @Test
    fun rejectsBadHash() {
        val path = file("bad-hash.zip")
        val fx = ZipFixture().add("data/library.json", "{}")
        val good = fx.manifest()
        val bad = good.copy(
            entries = good.entries.map { it.copy(sha256 = "0".repeat(64)) },
        )
        fx.write(path, bad)

        val result = BackupVerifier().verify(path)

        assertFalse(result.ok)
        assertTrue(result.error, result.error.contains("sha256"))
    }

    @Test
    fun rejectsBytesMismatch() {
        val path = file("bytes.zip")
        val fx = ZipFixture().add("data/library.json", "{}")
        val good = fx.manifest()
        fx.write(path, good.copy(bytes = good.bytes + 1))

        val result = BackupVerifier().verify(path)

        assertFalse(result.ok)
        assertTrue(result.error, result.error.contains("manifest.bytes"))
    }

    @Test
    fun rejectsFutureFormat() {
        val path = file("future.zip")
        val fx = ZipFixture().add("data/library.json", "{}")
        fx.write(path, fx.manifest(format = 2))

        val result = BackupVerifier().verify(path)

        assertFalse(result.ok)
        assertTrue(result.error, result.error.contains("格式"))
    }

    @Test
    fun rejectsTraversal() {
        val path = file("traversal.zip")
        val fx = ZipFixture().add("../evil.txt", "x")
        fx.write(path)

        val result = BackupVerifier().verify(path)

        assertFalse(result.ok)
        assertTrue(result.error, result.error.contains("路径"))
    }

    @Test
    fun rejectsUnexpectedEntry() {
        val path = file("extra.zip")
        val fx = ZipFixture().add("data/library.json", "{}")
        fx.write(path, extraEntries = mapOf("data/extra.txt" to "x".toByteArray()))

        val result = BackupVerifier().verify(path)

        assertFalse(result.ok)
        assertTrue(result.error, result.error.contains("不一致"))
    }

    @Test
    fun rejectsMissingManifest() {
        val path = file("no-manifest.zip")
        ZipFixture().add("data/library.json", "{}").write(path, omitManifest = true)

        val result = BackupVerifier().verify(path)

        assertFalse(result.ok)
        assertTrue(result.error, result.error.contains("manifest"))
    }

    @Test
    fun rejectsOversizeEntry() {
        val path = file("bomb.zip")
        ZipFixture()
            .addBytes("novels/bomb/data.bin", ByteArray(2 * 1024 * 1024))
            .write(path)

        val result = BackupVerifier(
            BackupLimits(maxSingleFile = 1024L * 1024L),
        ).verify(path)

        assertFalse(result.ok)
        assertTrue(result.error, result.error.contains("单文件"))
    }
}
