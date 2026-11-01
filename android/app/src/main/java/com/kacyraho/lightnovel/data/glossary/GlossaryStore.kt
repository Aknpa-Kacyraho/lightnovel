package com.kacyraho.lightnovel.data.glossary

import com.kacyraho.lightnovel.data.translation.Hashes
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable
data class GlossaryEntry(
    val id: String,
    val source: String,
    val target: String,
    val aliases: List<String> = emptyList(),
)

@Serializable
data class GlossaryFile(
    val schemaVersion: Int = 1,
    val revision: String = "",
    val entries: List<GlossaryEntry> = emptyList(),
)

class GlossaryStore(
    private val root: Path,
) {
    private val file = root.resolve("glossary.json")
    private val json = Json {
        ignoreUnknownKeys = true
        prettyPrint = true
    }

    @Synchronized
    fun load(): GlossaryFile {
        if (!Files.isRegularFile(file)) return GlossaryFile()
        return runCatching {
            json.decodeFromString(
                GlossaryFile.serializer(),
                Files.readAllBytes(file).toString(Charsets.UTF_8),
            )
        }.getOrElse { GlossaryFile() }
    }

    @Synchronized
    fun save(entries: List<GlossaryEntry>): GlossaryFile {
        val clean = entries
            .filter { it.source.isNotBlank() && it.target.isNotBlank() }
            .distinctBy { it.source.trim() }
            .map {
                it.copy(
                    id = it.id.ifBlank { it.source.trim() },
                    source = it.source.trim(),
                    target = it.target.trim(),
                    aliases = it.aliases.map(String::trim).filter(String::isNotBlank),
                )
            }
        val body = GlossaryFile(schemaVersion = 1, entries = clean)
        val revision = Hashes.sha256(
            body.entries.joinToString("\n") { "${it.source}\t${it.target}\t${it.aliases.joinToString(",")}" },
        )
        val value = body.copy(revision = revision)
        Files.createDirectories(root)
        val tmp = file.resolveSibling("${file.fileName}.tmp-${System.nanoTime()}")
        try {
            Files.write(
                tmp,
                json.encodeToString(GlossaryFile.serializer(), value).toByteArray(Charsets.UTF_8),
            )
            try {
                Files.move(
                    tmp,
                    file,
                    StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.ATOMIC_MOVE,
                )
            } catch (_: AtomicMoveNotSupportedException) {
                Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING)
            }
        } finally {
            Files.deleteIfExists(tmp)
        }
        return value
    }

    fun hits(entries: List<GlossaryEntry>, text: String): List<GlossaryEntry> =
        entries.filter { entry ->
            entry.source in text || entry.aliases.any { it in text }
        }
}
