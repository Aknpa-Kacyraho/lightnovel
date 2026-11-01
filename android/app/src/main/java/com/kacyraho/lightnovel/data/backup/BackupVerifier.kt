package com.kacyraho.lightnovel.data.backup

import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.util.zip.ZipFile
import kotlin.math.max

data class BackupLimits(
    val maxTotalUncompressed: Long = 1L shl 30,
    val maxTotalMultiplier: Long = 50,
    val maxSingleFile: Long = 64L shl 20,
    val maxEntries: Int = 100_000,
    val maxCompressionRatio: Long = 200,
    val maxManifestBytes: Int = 8 * 1024 * 1024,
)

data class BackupVerifyResult(
    val ok: Boolean,
    val error: String = "",
    val manifest: BackupManifest? = null,
    val entryCount: Int = 0,
    val totalUncompressed: Long = 0,
) {
    fun requireOk(): BackupManifest {
        if (!ok || manifest == null) error("备份校验失败：$error")
        return manifest
    }
}

class BackupVerifier(
    private val limits: BackupLimits = BackupLimits(),
) {
    companion object {
        const val SUPPORTED_FORMAT = 1
    }

    fun verify(path: Path): BackupVerifyResult {
        if (!Files.isRegularFile(path)) {
            return BackupVerifyResult(false, "备份文件不存在")
        }
        val compressedSize = runCatching { Files.size(path) }.getOrElse {
            return BackupVerifyResult(false, "无法读取备份大小：${it.message}")
        }
        val maxTotal = max(
            limits.maxTotalUncompressed,
            safeMultiply(compressedSize, limits.maxTotalMultiplier),
        )

        return runCatching {
            ZipFile(path.toFile()).use { zip ->
                val zipEntries = BackupArchive.entries(zip)
                val manifestEntry = zipEntries[BackupArchive.MANIFEST]
                    ?: return@use BackupVerifyResult(false, "缺少 manifest.json")

                val manifestBytes = BackupArchive.readBytes(
                    zip,
                    manifestEntry,
                    limits.maxManifestBytes,
                ) ?: return@use BackupVerifyResult(false, "manifest.json 过大或读取失败")

                val manifest = try {
                    BackupJson.decodeFromString<BackupManifest>(
                        manifestBytes.toString(Charsets.UTF_8),
                    )
                } catch (e: Exception) {
                    return@use BackupVerifyResult(false, "manifest.json 无法解析：${e.message}")
                }

                if (manifest.format <= 0) {
                    return@use BackupVerifyResult(false, "manifest.format 非法：${manifest.format}")
                }
                if (manifest.format > SUPPORTED_FORMAT) {
                    return@use BackupVerifyResult(
                        false,
                        "备份格式 v${manifest.format} 高于支持的 v$SUPPORTED_FORMAT",
                    )
                }
                if (manifest.entries.size > limits.maxEntries) {
                    return@use BackupVerifyResult(false, "条目过多：${manifest.entries.size}")
                }
                if (manifest.files != manifest.entries.size) {
                    return@use BackupVerifyResult(
                        false,
                        "manifest.files=${manifest.files} 与 entries=${manifest.entries.size} 不一致",
                    )
                }

                val expected = manifest.entries.map { it.path }.toSet()
                if (expected.size != manifest.entries.size) {
                    return@use BackupVerifyResult(false, "manifest 条目重复")
                }
                val actual = zipEntries.keys - BackupArchive.MANIFEST
                if (actual != expected) {
                    val extra = actual - expected
                    val missing = expected - actual
                    return@use BackupVerifyResult(
                        false,
                        "zip 条目与 manifest 不一致（多 ${extra.size} / 缺 ${missing.size}）",
                    )
                }

                var total = 0L
                for (entry in manifest.entries) {
                    if (!isSafePath(entry.path)) {
                        return@use BackupVerifyResult(false, "不安全路径：${entry.path}")
                    }
                    if (!isAllowedRoot(entry.path)) {
                        return@use BackupVerifyResult(false, "不允许的根路径：${entry.path}")
                    }
                    if (entry.size < 0) {
                        return@use BackupVerifyResult(false, "条目大小非法：${entry.path}")
                    }
                    if (entry.size > limits.maxSingleFile) {
                        return@use BackupVerifyResult(false, "单文件过大：${entry.path}")
                    }

                    val zipEntry = zipEntries[entry.path]
                        ?: return@use BackupVerifyResult(false, "zip 缺少条目：${entry.path}")
                    if (zipEntry.size >= 0 && zipEntry.size != entry.size) {
                        return@use BackupVerifyResult(
                            false,
                            "大小不一致：${entry.path}（manifest=${entry.size}, zip=${zipEntry.size}）",
                        )
                    }
                    if (zipEntry.compressedSize > 0) {
                        val ratio = entry.size / zipEntry.compressedSize
                        if (ratio > limits.maxCompressionRatio) {
                            return@use BackupVerifyResult(
                                false,
                                "压缩比可疑（疑似 zip bomb）：${entry.path}",
                            )
                        }
                    }

                    total = safeAdd(total, entry.size)
                    if (total > maxTotal) {
                        return@use BackupVerifyResult(false, "解压总量超过上限：${entry.path}")
                    }

                    val digest = sha256(zip, zipEntry, entry.size)
                        ?: return@use BackupVerifyResult(false, "读取失败：${entry.path}")
                    if (!digest.equals(entry.sha256, ignoreCase = true)) {
                        return@use BackupVerifyResult(false, "sha256 不符：${entry.path}")
                    }
                }

                if (manifest.bytes > 0 && total != manifest.bytes) {
                    return@use BackupVerifyResult(
                        false,
                        "manifest.bytes=${manifest.bytes} 与实际总量 $total 不一致",
                    )
                }

                BackupVerifyResult(
                    ok = true,
                    manifest = manifest,
                    entryCount = manifest.entries.size,
                    totalUncompressed = total,
                )
            }
        }.getOrElse { e ->
            BackupVerifyResult(false, "备份无法读取：${e.message}")
        }
    }

    private fun sha256(zip: ZipFile, entry: java.util.zip.ZipEntry, expected: Long): String? {
        val digest = MessageDigest.getInstance("SHA-256")
        zip.getInputStream(entry).use { input ->
            val buffer = ByteArray(16 * 1024)
            var total = 0L
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
                total += n
                if (total > expected) return null
                digest.update(buffer, 0, n)
            }
            if (total != expected) return null
        }
        return digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun safeAdd(a: Long, b: Long): Long =
        if (Long.MAX_VALUE - a < b) Long.MAX_VALUE else a + b

    private fun safeMultiply(a: Long, b: Long): Long =
        if (a <= 0 || b <= 0) 0 else if (a > Long.MAX_VALUE / b) Long.MAX_VALUE else a * b

    private fun isSafePath(path: String): Boolean {
        if (path.isEmpty() || path.length > 512) return false
        if (path.startsWith("/") || path.contains('\\') || path.contains('\u0000')) return false
        if (path.contains(':')) return false
        val parts = path.split('/')
        return parts.all { it.isNotEmpty() && it != "." && it != ".." }
    }

    private fun isAllowedRoot(path: String): Boolean =
        path.startsWith("novels/") ||
            path.startsWith("data/") ||
            path.startsWith("lnfinder/")
}
