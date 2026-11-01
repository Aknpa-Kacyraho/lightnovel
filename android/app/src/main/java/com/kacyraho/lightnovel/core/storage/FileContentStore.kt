package com.kacyraho.lightnovel.core.storage

import java.io.FileOutputStream
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption

class FileContentStore(
    override val root: Path,
) : ContentStore {
    init {
        Files.createDirectories(root.resolve("novels"))
    }

    override fun paths(storageDir: String): BookPaths = BookPaths(root, storageDir)

    override fun readRaw(storageDir: String, idx: Int): String? =
        readText(paths(storageDir).raw(idx))

    override fun readZh(storageDir: String, idx: Int): String? =
        readText(paths(storageDir).zh(idx))

    override fun readSidecar(storageDir: String, idx: Int): ChapterSidecar? {
        val text = readText(paths(storageDir).sidecar(idx)) ?: return null
        return SidecarJson.decodeFromString(ChapterSidecar.serializer(), text)
    }

    override fun writeRawAtomic(storageDir: String, idx: Int, text: String) {
        atomicWrite(paths(storageDir).raw(idx), text)
    }

    override fun writeZhAtomic(storageDir: String, idx: Int, text: String) {
        atomicWrite(paths(storageDir).zh(idx), text)
    }

    override fun writeSidecar(storageDir: String, idx: Int, sidecar: ChapterSidecar) {
        atomicWrite(
            paths(storageDir).sidecar(idx),
            SidecarJson.encodeToString(ChapterSidecar.serializer(), sidecar),
        )
    }

    private fun readText(path: Path): String? {
        if (!Files.isRegularFile(path)) return null
        return Files.readAllBytes(path).toString(Charsets.UTF_8)
    }

    private fun atomicWrite(path: Path, text: String) {
        Files.createDirectories(path.parent)
        val tmp = path.resolveSibling("${path.fileName}.tmp-${System.nanoTime()}")
        try {
            FileOutputStream(tmp.toFile()).use { output ->
                output.write(text.toByteArray(Charsets.UTF_8))
                output.fd.sync()
            }
            try {
                Files.move(
                    tmp,
                    path,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING,
                )
            } catch (_: AtomicMoveNotSupportedException) {
                Files.move(tmp, path, StandardCopyOption.REPLACE_EXISTING)
            }
        } finally {
            Files.deleteIfExists(tmp)
        }
    }
}
