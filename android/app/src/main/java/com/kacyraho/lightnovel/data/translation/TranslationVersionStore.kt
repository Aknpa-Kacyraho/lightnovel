package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.storage.ChapterSidecar
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.core.storage.SidecarJson
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.time.Instant

data class TranslationVersion(
    val text: String,
    val sidecar: ChapterSidecar,
)

class TranslationVersionStore(
    private val contentStore: ContentStore,
) {
    fun save(
        storageDir: String,
        chapterIndex: Int,
        text: String,
        sidecar: ChapterSidecar,
    ) {
        if (text.isBlank()) return
        val dir = contentStore.paths(storageDir).cacheDir()
            .resolve("versions")
            .resolve(chapterIndex.toString())
        Files.createDirectories(dir)
        val stamp = Instant.now().toEpochMilli().toString()
        write(dir.resolve("$stamp.txt"), text.toByteArray(Charsets.UTF_8))
        write(
            dir.resolve("$stamp.meta.json"),
            SidecarJson.encodeToString(ChapterSidecar.serializer(), sidecar).toByteArray(Charsets.UTF_8),
        )
    }

    fun latest(storageDir: String, chapterIndex: Int): TranslationVersion? {
        val dir = contentStore.paths(storageDir).cacheDir()
            .resolve("versions")
            .resolve(chapterIndex.toString())
        if (!Files.isDirectory(dir)) return null
        val textFile = Files.list(dir).use { stream ->
            stream.filter { it.fileName.toString().endsWith(".txt") }
                .max(compareBy { it.fileName.toString() })
                .orElse(null)
        } ?: return null
        val text = runCatching {
            Files.readAllBytes(textFile).toString(Charsets.UTF_8)
        }.getOrNull() ?: return null
        val metaFile = textFile.resolveSibling(
            textFile.fileName.toString().removeSuffix(".txt") + ".meta.json",
        )
        val sidecar = runCatching {
            SidecarJson.decodeFromString(
                ChapterSidecar.serializer(),
                Files.readAllBytes(metaFile).toString(Charsets.UTF_8),
            )
        }.getOrNull() ?: return null
        return TranslationVersion(text, sidecar)
    }

    fun diffParagraphs(oldText: String, newText: String): Int {
        val oldParagraphs = oldText.replace("\r\n", "\n").split("\n\n")
        val newParagraphs = newText.replace("\r\n", "\n").split("\n\n")
        val size = maxOf(oldParagraphs.size, newParagraphs.size)
        return (0 until size).count { index ->
            oldParagraphs.getOrNull(index) != newParagraphs.getOrNull(index)
        }
    }

    private fun write(path: java.nio.file.Path, bytes: ByteArray) {
        val tmp = path.resolveSibling("${path.fileName}.tmp-${System.nanoTime()}")
        try {
            Files.write(tmp, bytes)
            try {
                Files.move(tmp, path, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
            } catch (_: AtomicMoveNotSupportedException) {
                Files.move(tmp, path, StandardCopyOption.REPLACE_EXISTING)
            }
        } finally {
            Files.deleteIfExists(tmp)
        }
    }
}
