package com.kacyraho.lightnovel.data.knowledge

import com.kacyraho.lightnovel.core.storage.ContentStore
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.time.Instant
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

class KnowledgeStore(
    private val contentStore: ContentStore,
) {
    private val json = Json {
        ignoreUnknownKeys = true
        prettyPrint = true
        explicitNulls = false
    }

    @Synchronized
    fun load(storageDir: String, workId: String, title: String = ""): KnowledgeFile {
        val path = path(storageDir)
        if (!Files.isRegularFile(path)) {
            return KnowledgeFile(workId = workId, title = title)
        }
        val loaded = runCatching {
            json.decodeFromString(
                KnowledgeFile.serializer(),
                Files.readAllBytes(path).toString(Charsets.UTF_8),
            )
        }.getOrElse { KnowledgeFile(workId = workId, title = title) }
        return loaded.copy(
            workId = loaded.workId.ifBlank { workId },
            title = loaded.title.ifBlank { title },
        )
    }

    @Synchronized
    fun save(storageDir: String, knowledge: KnowledgeFile): KnowledgeFile {
        val chapters = knowledge.extractedChapters.distinct().sorted()
        val contiguous = contiguousThrough(chapters)
        val value = knowledge.copy(
            extractedChapters = chapters,
            canonExtractedThrough = contiguous,
            updatedAt = Instant.now().toString(),
        )
        val path = path(storageDir)
        Files.createDirectories(path.parent)
        val tmp = path.resolveSibling("${path.fileName}.tmp-${System.nanoTime()}")
        try {
            Files.write(
                tmp,
                json.encodeToString(KnowledgeFile.serializer(), value)
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

    fun contiguousThrough(chapters: List<Int>): Int {
        val set = chapters.toSet()
        var value = 0
        while (set.contains(value + 1)) value++
        return value
    }

    private fun path(storageDir: String) =
        contentStore.paths(storageDir).bookDir.resolve("knowledge.json")
}
