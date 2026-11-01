package com.kacyraho.lightnovel.core.storage

import java.nio.file.Path

data class BookPaths(
    val root: Path,
    val storageDir: String,
) {
    init {
        require(storageDir.isNotBlank()) { "storageDir 不能为空" }
        require(!storageDir.contains('/') && !storageDir.contains('\\')) {
            "storageDir 不能包含路径分隔符"
        }
    }

    val bookDir: Path = root.resolve("novels").resolve(storageDir)

    fun raw(idx: Int): Path = bookDir.resolve("raw").resolve("${pad(idx)}.txt")

    fun zh(idx: Int): Path = bookDir.resolve("chapters").resolve("${pad(idx)}.txt")

    fun sidecar(idx: Int): Path = bookDir.resolve("chapters").resolve("${pad(idx)}.meta.json")

    fun cacheDir(): Path = bookDir.resolve("cache")

    private fun pad(idx: Int): String {
        require(idx > 0) { "章节号必须 > 0" }
        return idx.toString().padStart(4, '0')
    }
}
