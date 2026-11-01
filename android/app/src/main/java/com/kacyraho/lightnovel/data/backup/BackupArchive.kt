package com.kacyraho.lightnovel.data.backup

import java.util.zip.ZipEntry
import java.util.zip.ZipFile

object BackupArchive {
    const val MANIFEST = "manifest.json"

    fun entries(zip: ZipFile): LinkedHashMap<String, ZipEntry> {
        val out = LinkedHashMap<String, ZipEntry>()
        val en = zip.entries()
        while (en.hasMoreElements()) {
            val entry = en.nextElement()
            if (!entry.isDirectory) out[entry.name] = entry
        }
        return out
    }

    fun readBytes(zip: ZipFile, entry: ZipEntry, maxBytes: Int): ByteArray? {
        if (maxBytes <= 0) return null
        zip.getInputStream(entry).use { input ->
            val out = java.io.ByteArrayOutputStream(minOf(maxBytes, 64 * 1024))
            val buffer = ByteArray(16 * 1024)
            var total = 0
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
                total += n
                if (total > maxBytes) return null
                out.write(buffer, 0, n)
            }
            return out.toByteArray()
        }
    }

    fun readText(zip: ZipFile, path: String, maxBytes: Int = 8 * 1024 * 1024): String? {
        val entry = zip.getEntry(path) ?: return null
        return readBytes(zip, entry, maxBytes)?.toString(Charsets.UTF_8)
    }
}
