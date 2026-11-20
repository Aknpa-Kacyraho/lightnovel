package com.kacyraho.lightnovel.core.storage

import java.nio.file.Path

interface ContentStore {
    val root: Path

    fun paths(storageDir: String): BookPaths

    fun readRaw(storageDir: String, idx: Int): String?

    fun readZh(storageDir: String, idx: Int): String?

    fun readSidecar(storageDir: String, idx: Int): ChapterSidecar?

    fun writeRawAtomic(storageDir: String, idx: Int, text: String)

    fun writeZhAtomic(storageDir: String, idx: Int, text: String)

    fun writeSidecar(storageDir: String, idx: Int, sidecar: ChapterSidecar)

    /** 删除一本书的全部本地文件（novels/<storageDir>）；目录不存在时静默返回。 */
    fun deleteBook(storageDir: String)
}
