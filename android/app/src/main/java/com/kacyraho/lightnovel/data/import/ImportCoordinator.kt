package com.kacyraho.lightnovel.data.import

import androidx.room.withTransaction
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import java.nio.file.Files
import java.nio.file.Path
import java.util.Comparator
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

data class ImportResult(
    val plan: ImportPlan,
    val commit: CommitResult,
    val applied: ImportApplyResult,
)

class ImportCoordinator(
    private val database: LightnovelDatabase,
    private val contentStore: ContentStore,
    private val service: BackupImportService = BackupImportService(),
    private val extractor: BackupExtractor = BackupExtractor(),
    private val committer: LibraryCommitter = LibraryCommitter(),
) {
    suspend fun import(
        path: Path,
        onProgress: (String) -> Unit = {},
    ): ImportResult = withContext(Dispatchers.IO) {
        onProgress("校验备份")
        val original = service.plan(path)
        val backups = database.libraryDao().books()
        val idMap = buildMap {
            for (book in original.report.books) {
                val match = backups.firstOrNull { it.id == book.id }
                    ?: book.importHash?.let { hash ->
                        backups.firstOrNull { it.importHash == hash }
                    }
                    ?: backups.firstOrNull {
                        it.source == book.source && it.sourceId == book.sourceId
                    }
                    ?: backups.firstOrNull { it.slug == book.slug }
                if (match != null && match.id != book.id) {
                    put(book.id, match.id)
                }
            }
        }
        val plan = original.remapBookIds(idMap)
        val staging = Files.createTempDirectory(contentStore.root, "staging-")
        try {
            onProgress("解压到 staging")
            extractor.extract(path, staging, plan.verify)

            onProgress("提交文件")
            val plannedDirs = plan.report.books.associate { it.id to it.storageDir }
            val overrides = backups
                .mapNotNull { book ->
                    val planned = plannedDirs[book.id] ?: return@mapNotNull null
                    if (planned.isBlank() ||
                        book.storageDir.isBlank() ||
                        planned == book.storageDir
                    ) {
                        null
                    } else {
                        book.id to book.storageDir
                    }
                }
                .toMap()
            val commit = committer.commit(
                stagingRoot = staging,
                dataRoot = contentStore.root,
                backupId = plan.report.backupId,
                report = plan.report,
                storageDirOverrides = overrides,
            )

            onProgress("写入数据库")
            val applied = database.withTransaction {
                service.apply(plan, database.libraryDao())
            }
            ImportResult(plan, commit, applied)
        } finally {
            onProgress("清理 staging")
            deleteRecursively(staging)
        }
    }

    private fun deleteRecursively(path: Path) {
        if (!Files.exists(path)) return
        Files.walk(path).use { stream ->
            stream.sorted(Comparator.reverseOrder()).forEach { current ->
                runCatching { Files.deleteIfExists(current) }
            }
        }
    }
}
