package com.kacyraho.lightnovel.data.export

import com.kacyraho.lightnovel.data.backup.BackupEntry
import com.kacyraho.lightnovel.data.backup.BackupManifest
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.BookTags
import com.kacyraho.lightnovel.data.local.LibraryDao
import java.io.OutputStream
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.time.Instant
import java.time.format.DateTimeFormatter
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject

class BackupExporter(
    private val dataRoot: Path,
    private val dao: LibraryDao,
) {
    private val json = Json { prettyPrint = false }

    suspend fun export(output: OutputStream): BackupManifest = withContext(Dispatchers.IO) {
        val entries = mutableListOf<BackupEntry>()
        val dirs = linkedSetOf<String>()
        val counts = linkedMapOf<String, Int>()
        var totalBytes = 0L

        ZipOutputStream(output).use { zip ->
            fun put(path: String, bytes: ByteArray) {
                val entry = ZipEntry(path)
                entry.time = 0L
                zip.putNextEntry(entry)
                zip.write(bytes)
                zip.closeEntry()
                entries += BackupEntry(path, bytes.size.toLong(), sha256(bytes))
                totalBytes += bytes.size
                val root = path.substringBefore('/')
                counts[root] = (counts[root] ?: 0) + 1
                var dir = path.substringBeforeLast('/', "")
                while (dir.isNotEmpty()) {
                    dirs += dir
                    dir = dir.substringBeforeLast('/', "")
                }
            }

            val novelFiles = filesUnder(dataRoot.resolve("novels"))
            for (file in novelFiles) {
                val rel = dataRoot.relativize(file).toString().replace('\\', '/')
                put(rel, Files.readAllBytes(file))
            }

            val books = dao.books()
            put("data/library.json", libraryJson(books))
            put("data/slug-aliases.json", aliasesJson())
            for (book in books) {
                put("data/books/${book.id}.json", bookStateJson(book))
            }

            val finder = dataRoot.resolve("lnfinder")
            if (Files.isDirectory(finder)) {
                for (file in filesUnder(finder)) {
                    val rel = dataRoot.relativize(file).toString().replace('\\', '/')
                    put(rel, Files.readAllBytes(file))
                }
            }

            val now = Instant.now()
            val manifest = BackupManifest(
                kind = "lntrans-backup",
                format = 1,
                backupId = "backup-" + DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")
                    .format(java.time.LocalDateTime.now()) + "-" + randomSuffix(),
                createdAt = now.toString(),
                counts = counts,
                files = entries.size,
                bytes = totalBytes,
                includeRaw = true,
                includeCache = false,
                dirs = dirs.sorted(),
                entries = entries.toList(),
            )
            val manifestEntry = ZipEntry("manifest.json")
            manifestEntry.time = 0L
            zip.putNextEntry(manifestEntry)
            zip.write(json.encodeToString(BackupManifest.serializer(), manifest).toByteArray())
            zip.closeEntry()
            manifest
        }
    }

    private fun filesUnder(root: Path): List<Path> {
        if (!Files.isDirectory(root)) return emptyList()
        return Files.walk(root).use { stream ->
            stream.filter { Files.isRegularFile(it) }
                .filter { file ->
                    val name = file.fileName.toString()
                    val rel = root.relativize(file).toString().replace('\\', '/')
                    !rel.contains("/cache/") &&
                        !name.contains(".tmp-") &&
                        !name.contains(".bak-") &&
                        !name.endsWith(".part") &&
                        !name.endsWith(".restore-tmp")
                }
                .sorted()
                .collect(java.util.stream.Collectors.toList())
        }
    }

    private suspend fun libraryJson(books: List<BookEntity>): ByteArray {
        val aliases = dao.aliases().associate { it.oldSlug to it.finalSlug }
        val jsonObject = buildJsonObject {
            put("schema_version", kotlinx.serialization.json.JsonPrimitive(1))
            put("items", kotlinx.serialization.json.buildJsonObject {
                for (book in books) {
                    put(
                        book.id,
                        buildJsonObject {
                            put("id", kotlinx.serialization.json.JsonPrimitive(book.id))
                            book.slug?.let { put("slug", kotlinx.serialization.json.JsonPrimitive(it)) }
                            put("source", kotlinx.serialization.json.JsonPrimitive(book.source))
                            put("source_id", kotlinx.serialization.json.JsonPrimitive(book.sourceId))
                            put("title", kotlinx.serialization.json.JsonPrimitive(book.title))
                            book.titleZh?.let { put("title_zh", kotlinx.serialization.json.JsonPrimitive(it)) }
                            book.author?.let { put("author", kotlinx.serialization.json.JsonPrimitive(it)) }
                            val tags = BookTags.decode(book.tagsJson)
                            if (tags.isNotEmpty()) {
                                put(
                                    "tags",
                                    kotlinx.serialization.json.buildJsonArray {
                                        tags.forEach { add(kotlinx.serialization.json.JsonPrimitive(it)) }
                                    },
                                )
                            }
                        },
                    )
                }
            })
            put("candidates", kotlinx.serialization.json.buildJsonObject {})
            put(
                "aliases",
                kotlinx.serialization.json.buildJsonObject {
                    for ((old, final) in aliases) {
                        put(old, kotlinx.serialization.json.JsonPrimitive(final))
                    }
                },
            )
        }
        return jsonObject.toString().toByteArray(Charsets.UTF_8)
    }

    private suspend fun aliasesJson(): ByteArray {
        val obj = buildJsonObject {
            for (alias in dao.aliases()) {
                put(alias.oldSlug, kotlinx.serialization.json.JsonPrimitive(alias.finalSlug))
            }
        }
        return obj.toString().toByteArray(Charsets.UTF_8)
    }

    private suspend fun bookStateJson(book: BookEntity): ByteArray {
        val state = runCatching { dao.readState(book.id) }.getOrNull()
        val obj = buildJsonObject {
            state?.shelf?.let { put("tracking", kotlinx.serialization.json.JsonPrimitive(it)) }
            put("favorites", kotlinx.serialization.json.JsonPrimitive(state?.favorite ?: false))
            put("hidden", kotlinx.serialization.json.JsonPrimitive(state?.hidden ?: false))
            put(
                "progress",
                buildJsonObject {
                    put(
                        "chapter",
                        kotlinx.serialization.json.JsonPrimitive(state?.progressIdx ?: 0),
                    )
                    put(
                        "block",
                        kotlinx.serialization.json.JsonPrimitive(state?.progressBlock ?: 0),
                    )
                    put(
                        "char",
                        kotlinx.serialization.json.JsonPrimitive(state?.progressChar ?: 0),
                    )
                },
            )
            state?.openedAt?.let { put("opened", kotlinx.serialization.json.JsonPrimitive(it)) }
            state?.finishedAt?.let { put("finished", kotlinx.serialization.json.JsonPrimitive(it)) }
            state?.updatedAt?.let { put("updated_at", kotlinx.serialization.json.JsonPrimitive(it)) }
        }
        return obj.toString().toByteArray(Charsets.UTF_8)
    }

    private fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256")
            .digest(bytes)
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }

    private fun randomSuffix(): String =
        java.util.UUID.randomUUID().toString().replace("-", "").take(8)

}

