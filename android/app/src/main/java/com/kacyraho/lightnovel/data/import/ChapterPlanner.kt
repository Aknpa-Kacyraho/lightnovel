package com.kacyraho.lightnovel.data.import

import com.kacyraho.lightnovel.data.backup.BackupManifest
import com.kacyraho.lightnovel.data.legacy.ArchiveIndex

data class PlannedChapter(
    val bookId: String,
    val idx: Int,
    val rawPath: String?,
    val zhPath: String?,
    val status: String,
)

object ChapterPlanner {
    fun plan(
        manifest: BackupManifest,
        report: MigrationReport,
        sidecarStatuses: Map<String, String> = emptyMap(),
    ): List<PlannedChapter> {
        val dirToId = report.books.associate { it.storageDir to it.id }
        val index = ArchiveIndex.from(manifest)
        val out = mutableListOf<PlannedChapter>()

        for ((dir, bookIndex) in index.books) {
            val bookId = dirToId[dir] ?: continue
            for (chapter in bookIndex.chapters.values) {
                val sidecarStatus = chapter.sidecarPath?.let { sidecarStatuses[it] }
                out += PlannedChapter(
                    bookId = bookId,
                    idx = chapter.idx,
                    rawPath = chapter.rawPath,
                    zhPath = chapter.zhPath,
                    status = when (sidecarStatus) {
                        "complete" -> "complete"
                        "partial" -> "partial"
                        else -> when {
                            chapter.zhPath != null -> "translated"
                            chapter.rawPath != null -> "raw"
                            else -> "missing"
                        }
                    },
                )
            }
        }
        return out.sortedWith(compareBy({ it.bookId }, { it.idx }))
    }
}
