package com.kacyraho.lightnovel.core.storage

import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ContentStoreTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun store(): FileContentStore =
        FileContentStore(tmp.newFolder("data").toPath())

    @Test
    fun writesAndReadsRawAndTranslation() {
        val store = store()
        store.writeRawAtomic("kakuyomu-1", 1, "raw text")
        store.writeZhAtomic("kakuyomu-1", 1, "中文译文")

        assertEquals("raw text", store.readRaw("kakuyomu-1", 1))
        assertEquals("中文译文", store.readZh("kakuyomu-1", 1))
        assertNull(store.readRaw("kakuyomu-1", 2))
    }

    @Test
    fun sidecarRoundTripAndMissingFile() {
        val store = store()
        val sidecar = ChapterSidecar(
            status = "partial",
            sourceSha256 = "a".repeat(64),
            contentSha256 = "b".repeat(64),
            translationConfigHash = "c".repeat(64),
            modelProvider = "deepseek",
            modelId = "deepseek-flash",
            promptVersion = "v1",
            translatedAt = "2026-10-28T00:00:00Z",
            tokens = ChapterTokens(input = 10, output = 20),
            cost = ChapterCost(amount = 0.01),
            incompleteParagraphs = listOf(2),
            incompleteReason = "provider_incomplete",
        )

        store.writeSidecar("kakuyomu-1", 1, sidecar)

        assertEquals(sidecar, store.readSidecar("kakuyomu-1", 1))
        assertNull(store.readSidecar("kakuyomu-1", 2))
    }

    @Test
    fun atomicWriteLeavesNoTempFile() {
        val store = store()
        store.writeZhAtomic("kakuyomu-1", 1, "text")

        val chapterDir = store.paths("kakuyomu-1").bookDir.resolve("chapters")
        val leftovers = Files.list(chapterDir).use { stream ->
            stream.filter { it.fileName.toString().contains(".tmp-") }.count()
        }
        assertEquals(0, leftovers.toInt())
        assertTrue(Files.isRegularFile(store.paths("kakuyomu-1").zh(1)))
    }

    @Test
    fun chapterPathUsesFourDigitPadding() {
        val store = store()
        assertEquals(
            "0001.txt",
            store.paths("kakuyomu-1").zh(1).fileName.toString(),
        )
        assertEquals(
            "0042.txt",
            store.paths("kakuyomu-1").zh(42).fileName.toString(),
        )
    }
}
