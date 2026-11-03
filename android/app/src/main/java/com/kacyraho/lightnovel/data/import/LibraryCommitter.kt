package com.kacyraho.lightnovel.data.import

import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

data class CommitResult(
    val moved: Int,
    val unchanged: Int,
    val backups: List<String>,
    val archived: List<String>,
)

class LibraryCommitter {
    fun commit(
        stagingRoot: Path,
        dataRoot: Path,
        backupId: String,
        report: MigrationReport,
    ): CommitResult {
        val novelsRoot = dataRoot.resolve("novels")
        val legacyRoot = dataRoot.resolve("legacy").resolve(safeSegment(backupId))
        Files.createDirectories(novelsRoot)
        Files.createDirectories(legacyRoot)

        val backups = mutableListOf<String>()
        val moves = mutableListOf<MoveRecord>()
        var unchanged = 0

        try {
            for (book in report.books) {
                val source = stagingRoot.resolve("novels").resolve(book.storageDir)
                if (!Files.isDirectory(source)) {
                    error("staging 缺少书目录：${book.storageDir}")
                }
                normalizePythonChapterFiles(source)
                val dest = novelsRoot.resolve(book.storageDir)
                if (Files.exists(dest)) {
                    if (sameTree(source, dest)) {
                        unchanged++
                        continue
                    }
                    val backup = uniqueSibling(dest)
                    moveDirectory(dest, backup)
                    backups += dataRoot.relativize(backup).toString().replace('\\', '/')
                    moves += MoveRecord(source, dest, backup)
                } else {
                    moves += MoveRecord(source, dest, null)
                }
                moveDirectory(source, dest)
            }
        } catch (e: Exception) {
            rollback(moves)
            throw e
        }

        val archived = mutableListOf<String>()
        archiveIfPresent(stagingRoot.resolve("data"), legacyRoot.resolve("data"), archived, legacyRoot)
        archiveIfPresent(stagingRoot.resolve("lnfinder"), legacyRoot.resolve("lnfinder"), archived, legacyRoot)
        deleteEmptyDirectories(stagingRoot)

        return CommitResult(
            moved = moves.size,
            unchanged = unchanged,
            backups = backups,
            archived = archived,
        )
    }

    private data class MoveRecord(
        val source: Path,
        val dest: Path,
        val backup: Path?,
    )

    private fun rollback(moves: List<MoveRecord>) {
        for (move in moves.asReversed()) {
            runCatching {
                if (Files.exists(move.dest)) moveDirectory(move.dest, move.source)
                move.backup?.let { backup ->
                    if (Files.exists(backup)) moveDirectory(backup, move.dest)
                }
            }
        }
    }

    private fun archiveIfPresent(source: Path, dest: Path, out: MutableList<String>, root: Path) {
        if (!Files.exists(source)) return
        if (Files.exists(dest)) {
            val backup = uniqueSibling(dest)
            runCatching { moveDirectory(dest, backup) }
        }
        Files.createDirectories(dest.parent)
        moveDirectory(source, dest)
        out += root.relativize(dest).toString().replace('\\', '/')
    }

    private fun moveDirectory(from: Path, to: Path) {
        Files.createDirectories(to.parent)
        try {
            Files.move(from, to, StandardCopyOption.ATOMIC_MOVE)
        } catch (_: AtomicMoveNotSupportedException) {
            Files.move(from, to)
        }
    }

    private fun uniqueSibling(path: Path): Path {
        val stamp = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")
            .format(LocalDateTime.now())
        var candidate = path.resolveSibling("${path.fileName}.bak-$stamp")
        var n = 2
        while (Files.exists(candidate)) {
            candidate = path.resolveSibling("${path.fileName}.bak-$stamp-$n")
            n++
        }
        return candidate
    }

    private fun normalizePythonChapterFiles(bookDir: Path) {
        val pattern = Regex("""^(\d{4})(\.txt|\.meta\.json)$""")
        for (sub in listOf("raw", "chapters")) {
            val dir = bookDir.resolve(sub)
            if (!Files.isDirectory(dir)) continue
            val files = Files.list(dir).use { stream ->
                stream.filter(Files::isRegularFile)
                    .collect(java.util.stream.Collectors.toList())
            }
            val numbered = files.mapNotNull { path ->
                val match = pattern.matchEntire(path.fileName.toString()) ?: return@mapNotNull null
                Triple(path, match.groupValues[1].toInt(), match.groupValues[2])
            }
            if (numbered.none { it.second == 0 }) continue
            numbered.sortedByDescending { it.second }.forEach { (path, index, suffix) ->
                val target = dir.resolve((index + 1).toString().padStart(4, '0') + suffix)
                Files.move(path, target, StandardCopyOption.REPLACE_EXISTING)
            }
        }
    }

    private fun sameTree(a: Path, b: Path): Boolean {
        if (!Files.isDirectory(a) || !Files.isDirectory(b)) return false
        val left = filesOf(a)
        val right = filesOf(b)
        if (left.keys != right.keys) return false
        for ((rel, pathA) in left) {
            val pathB = right.getValue(rel)
            if (Files.size(pathA) != Files.size(pathB)) return false
            if (sha256(pathA) != sha256(pathB)) return false
        }
        return true
    }

    private fun filesOf(root: Path): Map<String, Path> {
        val out = linkedMapOf<String, Path>()
        Files.walk(root).use { stream ->
            stream.filter { Files.isRegularFile(it) }.forEach { path ->
                out[root.relativize(path).toString().replace('\\', '/')] = path
            }
        }
        return out
    }

    private fun sha256(path: Path): String {
        val digest = MessageDigest.getInstance("SHA-256")
        Files.newInputStream(path).use { input ->
            val buffer = ByteArray(16 * 1024)
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
                digest.update(buffer, 0, n)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun safeSegment(value: String): String =
        value.ifBlank { "backup" }.replace(Regex("[^A-Za-z0-9._-]"), "_")

    private fun deleteEmptyDirectories(root: Path) {
        if (!Files.exists(root)) return
        Files.walk(root).use { stream ->
            stream.sorted(Comparator.reverseOrder())
                .filter { Files.isDirectory(it) && it != root }
                .forEach { dir ->
                    runCatching {
                        Files.newDirectoryStream(dir).use { entries ->
                            if (!entries.iterator().hasNext()) Files.deleteIfExists(dir)
                        }
                    }
                }
        }
    }
}
