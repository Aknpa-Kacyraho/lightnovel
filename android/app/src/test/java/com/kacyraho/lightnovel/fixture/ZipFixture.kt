package com.kacyraho.lightnovel.fixture

import com.kacyraho.lightnovel.data.backup.BackupEntry
import com.kacyraho.lightnovel.data.backup.BackupManifest
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

class ZipFixture {
    val entries = linkedMapOf<String, ByteArray>()

    fun add(path: String, content: String): ZipFixture {
        entries[path] = content.toByteArray(Charsets.UTF_8)
        return this
    }

    fun addBytes(path: String, content: ByteArray): ZipFixture {
        entries[path] = content
        return this
    }

    fun manifest(format: Int = 1): BackupManifest {
        val listed = entries.map { (path, bytes) ->
            BackupEntry(path = path, size = bytes.size.toLong(), sha256 = sha256(bytes))
        }
        val dirs = entries.keys
            .mapNotNull { path ->
                val parts = path.split('/')
                if (parts.size < 2) null else parts.dropLast(1).joinToString("/")
            }
            .distinct()
            .sorted()
        return BackupManifest(
            kind = "lntrans-backup",
            format = format,
            backupId = "backup-test",
            createdAt = "2026-10-27T00:00:00",
            counts = entries.keys.groupingBy { it.substringBefore('/') }.eachCount(),
            files = listed.size,
            bytes = listed.sumOf { it.size },
            dirs = dirs,
            entries = listed,
        )
    }

    fun write(
        path: Path,
        manifest: BackupManifest? = null,
        omitManifest: Boolean = false,
        extraEntries: Map<String, ByteArray> = emptyMap(),
    ) {
        val actual = manifest ?: manifest()
        Files.newOutputStream(path).use { out ->
            ZipOutputStream(out).use { zip ->
                if (!omitManifest) {
                    put(zip, "manifest.json", Json.encodeToString(actual).toByteArray(Charsets.UTF_8))
                }
                for ((name, bytes) in entries) put(zip, name, bytes)
                for ((name, bytes) in extraEntries) put(zip, name, bytes)
            }
        }
    }

    private fun put(zip: ZipOutputStream, name: String, bytes: ByteArray) {
        val entry = ZipEntry(name)
        entry.time = 0L
        zip.putNextEntry(entry)
        zip.write(bytes)
        zip.closeEntry()
    }

    fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256")
            .digest(bytes)
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
}
