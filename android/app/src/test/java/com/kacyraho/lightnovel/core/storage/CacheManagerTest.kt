package com.kacyraho.lightnovel.core.storage

import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class CacheManagerTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun countsAndClearsOnlyCacheFiles() {
        val store = FileContentStore(tmp.newFolder("data").toPath())
        val cache = store.paths("book").cacheDir().resolve("translation")
        Files.createDirectories(cache)
        Files.write(cache.resolve("chunk.json"), "x".repeat(128).toByteArray())
        Files.createDirectories(store.paths("book").raw(1).parent)
        Files.write(store.paths("book").raw(1), "raw".toByteArray())

        val manager = CacheManager(store)
        assertEquals(1, manager.usage().files)
        assertTrue(manager.usage().bytes > 0)

        manager.clear()

        assertEquals(0, manager.usage().files)
        assertTrue(Files.isRegularFile(store.paths("book").raw(1)))
    }
}
