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
        val plan = service.plan(path)
        val staging = Files.createTempDirectory(contentStore.root, "staging-")
        try {
            onProgress("解压到 staging")
            extractor.extract(path, staging, plan.verify)

            onProgress("提交文件")
            val commit = committer.commit(
                stagingRoot = staging,
                dataRoot = contentStore.root,
                backupId = plan.report.backupId,
                report = plan.report,
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
