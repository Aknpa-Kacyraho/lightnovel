package com.kacyraho.lightnovel.data.story

import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.glossary.GlossaryEntry
import com.kacyraho.lightnovel.data.glossary.GlossaryFile
import com.kacyraho.lightnovel.data.translation.Hashes
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

class StoryMemoryStore(
    private val contentStore: ContentStore,
) {
    private val json = Json {
        ignoreUnknownKeys = true
        prettyPrint = true
        explicitNulls = false
    }

    @Synchronized
    fun load(storageDir: String, workId: String, title: String = ""): StoryMemory {
        val path = path(storageDir)
        if (!Files.isRegularFile(path)) {
            return StoryMemory(workId = workId, title = title)
        }
        val loaded = runCatching {
            json.decodeFromString(
                StoryMemory.serializer(),
                Files.readAllBytes(path).toString(Charsets.UTF_8),
            )
        }.getOrElse { StoryMemory(workId = workId, title = title) }
        return loaded.copy(
            workId = loaded.workId.ifBlank { workId },
            title = loaded.title.ifBlank { title },
        )
    }

    @Synchronized
    fun save(storageDir: String, memory: StoryMemory): StoryMemory {
        val clean = memory.copy(
            glossary = cleanGlossary(memory.glossary),
            characters = memory.characters
                .filter { it.source.isNotBlank() || it.target.isNotBlank() }
                .distinctBy { it.source.ifBlank { it.target }.trim() }
                .map {
                    it.copy(
                        id = it.id.ifBlank { it.source.ifBlank { it.target }.trim() },
                        source = it.source.trim(),
                        target = it.target.trim(),
                        aliases = it.aliases.map(String::trim)
                            .filter(String::isNotBlank)
                            .distinct(),
                    )
                },
            summaries = memory.summaries.filterValues { it.text.isNotBlank() },
            lessons = memory.lessons.map(String::trim)
                .filter(String::isNotBlank)
                .distinct()
                .takeLast(30),
        )
        val revision = revision(clean)
        val value = clean.copy(revision = revision)
        val path = path(storageDir)
        Files.createDirectories(path.parent)
        val tmp = path.resolveSibling("${path.fileName}.tmp-${System.nanoTime()}")
        try {
            Files.write(
                tmp,
                json.encodeToString(StoryMemory.serializer(), value).toByteArray(Charsets.UTF_8),
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

    fun importLegacy(storageDir: String, workId: String, title: String, legacy: GlossaryFile): StoryMemory {
        val current = load(storageDir, workId, title)
        val merged = cleanGlossary(current.glossary + legacy.entries)
        return save(storageDir, current.copy(glossary = merged))
    }

    fun revision(memory: StoryMemory): String {
        val glossary = cleanGlossary(memory.glossary).joinToString("\n") {
            "${it.source}\t${it.target}\t${it.aliases.joinToString(",")}"
        }
        val extra = buildList {
            memory.characters.forEach { card ->
                add(
                    "C:${card.source}\t${card.target}\t${card.aliases.joinToString(",")}\t" +
                        "${card.description}\t${card.voice}\t${card.address}\t" +
                        "${card.lexicon}\t${card.syntax}\t${card.volume}\t${card.notes}",
                )
            }
            val style = memory.style
            listOf(
                style.general,
                style.narrator,
                style.honorifics,
                style.notes,
                style.guide,
                style.medium,
            ).filter(String::isNotBlank).forEach { add("S:$it") }
            memory.lessons.filter(String::isNotBlank).forEach { add("L:$it") }
        }
        if (glossary.isBlank() && extra.isEmpty()) return ""
        if (extra.isEmpty()) return Hashes.sha256(glossary)
        return Hashes.sha256(glossary + "\n" + extra.joinToString("\n"))
    }

    private fun cleanGlossary(entries: List<GlossaryEntry>): List<GlossaryEntry> =
        entries.filter { it.source.isNotBlank() && it.target.isNotBlank() }
            .distinctBy { it.source.trim() }
            .map {
                it.copy(
                    id = it.id.ifBlank { it.source.trim() },
                    source = it.source.trim(),
                    target = it.target.trim(),
                    aliases = it.aliases.map(String::trim)
                        .filter(String::isNotBlank)
                        .distinct(),
                )
            }

    private fun path(storageDir: String) =
        contentStore.paths(storageDir).bookDir.resolve("story.json")
}
