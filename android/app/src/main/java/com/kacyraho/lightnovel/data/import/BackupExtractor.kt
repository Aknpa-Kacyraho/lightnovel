package com.kacyraho.lightnovel.data.import

import com.kacyraho.lightnovel.data.backup.BackupVerifyResult
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.util.zip.ZipFile

data class ExtractResult(
    val stagingRoot: Path,
    val files: Int,
    val bytes: Long,
)

class BackupExtractor {
    fun extract(
        zipPath: Path,
        stagingRoot: Path,
        verify: BackupVerifyResult,
    ): ExtractResult {
        val manifest = verify.requireOk()
        Files.createDirectories(stagingRoot)
        var files = 0
        var bytes = 0L

        ZipFile(zipPath.toFile()).use { zip ->
            for (entry in manifest.entries) {
                val dest = stagingRoot.resolve(entry.path).normalize()
                if (!dest.startsWith(stagingRoot)) {
                    error("拒绝越界的备份路径：${entry.path}")
                }
                Files.createDirectories(dest.parent)
                val tmp = dest.resolveSibling("${dest.fileName}.part")
                var written = 0L

                zip.getInputStream(
                    zip.getEntry(entry.path) ?: error("zip 缺少条目：${entry.path}"),
                ).use { input ->
                    Files.newOutputStream(tmp).use { output ->
                        val buffer = ByteArray(16 * 1024)
                        while (true) {
                            val n = input.read(buffer)
                            if (n < 0) break
                            written += n
                            if (written > entry.size) {
                                Files.deleteIfExists(tmp)
                                error("条目实际大小超过 manifest：${entry.path}")
                            }
                            output.write(buffer, 0, n)
                        }
                    }
                }

                if (written != entry.size) {
                    Files.deleteIfExists(tmp)
                    error("条目实际大小与 manifest 不一致：${entry.path}")
                }
                moveReplace(tmp, dest)
                files++
                bytes += written
            }
        }
        return ExtractResult(stagingRoot, files, bytes)
    }

    private fun moveReplace(from: Path, to: Path) {
        try {
            Files.move(
                from,
                to,
                StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING,
            )
        } catch (_: AtomicMoveNotSupportedException) {
            Files.move(from, to, StandardCopyOption.REPLACE_EXISTING)
        }
    }
}
