package com.kacyraho.lightnovel.core.storage

import java.nio.file.Files
import java.nio.file.Path
import java.util.Comparator
import java.util.stream.Collectors

data class CacheUsage(
    val bytes: Long,
    val files: Int,
)

class CacheManager(
    private val contentStore: ContentStore,
) {
    fun usage(): CacheUsage {
        var bytes = 0L
        var files = 0
        for (dir in cacheDirs()) {
            if (!Files.isDirectory(dir)) continue
            Files.walk(dir).use { stream ->
                stream.forEach { path ->
                    if (Files.isRegularFile(path)) {
                        files++
                        bytes += runCatching { Files.size(path) }.getOrDefault(0L)
                    }
                }
            }
        }
        return CacheUsage(bytes, files)
    }

    fun clear(): CacheUsage {
        val before = usage()
        for (dir in cacheDirs()) {
            if (!Files.isDirectory(dir)) continue
            Files.walk(dir).use { stream ->
                stream.sorted(Comparator.reverseOrder()).forEach { path ->
                    if (path != dir) runCatching { Files.deleteIfExists(path) }
                }
            }
        }
        return before
    }

    private fun cacheDirs(): List<Path> {
        val novels = contentStore.root.resolve("novels")
        if (!Files.isDirectory(novels)) return emptyList()
        return Files.list(novels).use { stream ->
            stream.filter { Files.isDirectory(it) }
                .map { it.resolve("cache") }
                .collect(Collectors.toList())
        }
    }
}
