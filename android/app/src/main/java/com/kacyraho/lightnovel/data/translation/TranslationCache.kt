package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.storage.ContentStore
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable
data class CachedParagraph(
    val index: Int,
    val sourceHash: String,
    val text: String,
)

@Serializable
data class CachedBlock(
    val index: Int,
    val sourceHash: String,
    val text: String,
)

@Serializable
data class ChapterCache(
    val sourceSha256: String,
    val configHash: String,
    val paragraphs: List<CachedParagraph> = emptyList(),
    val blocks: List<CachedBlock> = emptyList(),
    val model: String = "",
    val tokensIn: Int = 0,
    val tokensOut: Int = 0,
)

interface TranslationStore {
    fun load(
        storageDir: String,
        idx: Int,
        sourceSha256: String,
        configHash: String,
    ): ChapterCache?

    fun save(
        storageDir: String,
        idx: Int,
        cache: ChapterCache,
    )
}

object Hashes {
    fun sha256(text: String): String =
        MessageDigest.getInstance("SHA-256")
            .digest(text.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
}

class FileTranslationStore(
    private val contentStore: ContentStore,
) : TranslationStore {
    private val json = Json {
        ignoreUnknownKeys = true
        prettyPrint = true
    }

    override fun load(
        storageDir: String,
        idx: Int,
        sourceSha256: String,
        configHash: String,
    ): ChapterCache? {
        val path = path(storageDir, idx, sourceSha256, configHash)
        if (!Files.isRegularFile(path)) return null
        return runCatching {
            json.decodeFromString(ChapterCache.serializer(), Files.readAllBytes(path).toString(Charsets.UTF_8))
        }.getOrNull()
    }

    override fun save(storageDir: String, idx: Int, cache: ChapterCache) {
        val path = path(storageDir, idx, cache.sourceSha256, cache.configHash)
        Files.createDirectories(path.parent)
        val tmp = path.resolveSibling("${path.fileName}.tmp-${System.nanoTime()}")
        try {
            Files.write(tmp, json.encodeToString(ChapterCache.serializer(), cache).toByteArray())
            try {
                Files.move(
                    tmp,
                    path,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING,
                )
            } catch (_: AtomicMoveNotSupportedException) {
                Files.move(tmp, path, StandardCopyOption.REPLACE_EXISTING)
            }
        } finally {
            Files.deleteIfExists(tmp)
        }
    }

    private fun path(
        storageDir: String,
        idx: Int,
        sourceSha256: String,
        configHash: String,
    ) = contentStore.paths(storageDir).cacheDir()
        .resolve("translation")
        .resolve(idx.toString())
        .resolve("$sourceSha256-$configHash.json")
}
