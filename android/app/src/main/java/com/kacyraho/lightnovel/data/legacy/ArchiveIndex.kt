package com.kacyraho.lightnovel.data.legacy

import com.kacyraho.lightnovel.data.backup.BackupManifest

data class ArchiveChapterEntry(
    val idx: Int,
    val rawPath: String? = null,
    val zhPath: String? = null,
    val sidecarPath: String? = null,
)

data class ArchiveBookIndex(
    val storageDir: String,
    val metaPath: String? = null,
    val chapters: Map<Int, ArchiveChapterEntry> = emptyMap(),
)

data class ArchiveIndex(
    val books: Map<String, ArchiveBookIndex>,
) {
    companion object {
        fun from(manifest: BackupManifest): ArchiveIndex {
            val books = linkedMapOf<String, MutableBook>()

            for (entry in manifest.entries) {
                val parts = entry.path.split('/')
                if (parts.size < 3 || parts[0] != "novels") continue
                val dir = parts[1]
                if (dir.isBlank()) continue
                val book = books.getOrPut(dir) { MutableBook(dir) }

                if (parts.size == 3 && parts[2] == "meta.json") {
                    book.metaPath = entry.path
                    continue
                }
                if (parts.size != 4) continue
                val isRaw = parts[2] == "raw" && parts[3].endsWith(".txt")
                val isZh = parts[2] == "chapters" && parts[3].endsWith(".txt")
                val isSidecar = parts[2] == "chapters" && parts[3].endsWith(".meta.json")
                if (!isRaw && !isZh && !isSidecar) continue
                val idx = parts[3].substringBefore('.').toIntOrNull() ?: continue
                if (idx < 0) continue
                val chapter = book.chapters.getOrPut(idx) { ArchiveChapterEntry(idx) }
                book.chapters[idx] = when {
                    isRaw -> chapter.copy(rawPath = entry.path)
                    isZh -> chapter.copy(zhPath = entry.path)
                    else -> chapter.copy(sidecarPath = entry.path)
                }
            }

            return ArchiveIndex(
                books = books.mapValues { (_, value) ->
                    ArchiveBookIndex(
                        storageDir = value.storageDir,
                        metaPath = value.metaPath,
                        chapters = normalizeChapters(value.chapters),
                    )
                },
            )
        }
    }

    private data class MutableBook(
        val storageDir: String,
        var metaPath: String? = null,
        val chapters: MutableMap<Int, ArchiveChapterEntry> = linkedMapOf(),
    )
}

private fun normalizeChapters(
    chapters: Map<Int, ArchiveChapterEntry>,
): java.util.SortedMap<Int, ArchiveChapterEntry> {
    val shifted = if (chapters.containsKey(0)) {
        chapters.entries.associate { (idx, entry) ->
            (idx + 1) to entry.copy(idx = idx + 1)
        }
    } else {
        chapters
    }
    return java.util.TreeMap(shifted)
}
