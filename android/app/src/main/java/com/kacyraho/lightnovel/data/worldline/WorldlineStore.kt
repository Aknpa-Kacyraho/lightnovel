package com.kacyraho.lightnovel.data.worldline

import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.translation.Hashes
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.time.Instant
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

class WorldlineStore(
    private val contentStore: ContentStore,
) {
    private val json = Json {
        ignoreUnknownKeys = true
        prettyPrint = true
        explicitNulls = false
    }

    @Synchronized
    fun list(storageDir: String): List<WorldlineFile> {
        val root = root(storageDir)
        if (!Files.isDirectory(root)) return emptyList()
        val dirs = Files.newDirectoryStream(root).use { it.toList() }
        return dirs.filter { Files.isDirectory(it) }
            .map { it.resolve("worldline.json") }
            .filter { Files.isRegularFile(it) }
            .mapNotNull { path ->
                runCatching {
                    json.decodeFromString(
                        WorldlineFile.serializer(),
                        Files.readAllBytes(path).toString(Charsets.UTF_8),
                    )
                }.getOrNull()
            }
            .sortedByDescending { it.updatedAt }
    }

    @Synchronized
    fun load(storageDir: String, id: String): WorldlineFile? {
        val path = path(storageDir, id)
        if (!Files.isRegularFile(path)) return null
        return runCatching {
            json.decodeFromString(
                WorldlineFile.serializer(),
                Files.readAllBytes(path).toString(Charsets.UTF_8),
            )
        }.getOrNull()
    }

    @Synchronized
    fun save(storageDir: String, worldline: WorldlineFile): WorldlineFile {
        val value = worldline.copy(
            branchCursor = worldline.chapters.size,
            updatedAt = Instant.now().toString(),
        )
        val path = path(storageDir, value.id)
        Files.createDirectories(path.parent)
        val tmp = path.resolveSibling("${path.fileName}.tmp-${System.nanoTime()}")
        try {
            Files.write(
                tmp,
                json.encodeToString(WorldlineFile.serializer(), value)
                    .toByteArray(Charsets.UTF_8),
            )
            try {
                Files.move(
                    tmp,
                    path,
                    StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.ATOMIC_MOVE,
                )
            } catch (_: AtomicMoveNotSupportedException) {
                Files.move(tmp, path, StandardCopyOption.REPLACE_EXISTING)
            }
        } finally {
            Files.deleteIfExists(tmp)
        }
        return value
    }

    @Synchronized
    fun delete(storageDir: String, id: String): Boolean {
        if (id.isBlank() || id.contains('/') || id.contains('\\')) return false
        val dir = root(storageDir).resolve(id)
        if (!Files.isDirectory(dir)) return false
        Files.walk(dir).use { stream ->
            stream.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
        }
        return true
    }

    fun newId(bookId: String, forkChapter: Int, forkParagraph: Int): String =
        "wl-" + Hashes.sha256(
            "$bookId|$forkChapter|$forkParagraph|${System.nanoTime()}",
        ).take(12)

    private fun root(storageDir: String) =
        contentStore.paths(storageDir).bookDir.resolve("worldlines")

    private fun path(storageDir: String, id: String) =
        root(storageDir).resolve(id).resolve("worldline.json")
}
