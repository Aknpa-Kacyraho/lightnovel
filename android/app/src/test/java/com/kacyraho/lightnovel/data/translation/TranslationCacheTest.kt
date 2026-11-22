package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.storage.FileContentStore
import java.nio.file.Files
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class TranslationCacheTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun invalidateRemovesOnlyTheTargetChapterCache() {
        val store = FileContentStore(tmp.newFolder("data").toPath())
        val cache = FileTranslationStore(store)
        val translation = store.paths("book").cacheDir().resolve("translation")
        val first = translation.resolve("1")
        val second = translation.resolve("2")
        Files.createDirectories(first)
        Files.createDirectories(second)
        Files.write(first.resolve("a.json"), "{}".toByteArray())
        Files.write(second.resolve("b.json"), "{}".toByteArray())

        cache.invalidate("book", 1)

        assertFalse(Files.exists(first))
        assertTrue(Files.exists(second))
    }
}
