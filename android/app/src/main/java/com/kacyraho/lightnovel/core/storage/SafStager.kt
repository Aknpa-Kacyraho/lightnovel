package com.kacyraho.lightnovel.core.storage

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.File
import java.nio.file.Path
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class SafStager(
    private val context: Context,
) {
    suspend fun stage(uri: Uri): Path = withContext(Dispatchers.IO) {
        val displayName = queryName(uri) ?: "import-${System.currentTimeMillis()}.zip"
        val safeName = File(displayName).name.ifBlank { "import.zip" }
        val dir = File(context.cacheDir, "imports").apply { mkdirs() }
        val dest = File(dir, "${System.currentTimeMillis()}-$safeName")
        val input = context.contentResolver.openInputStream(uri)
            ?: error("无法打开选择的文件")
        input.use { source ->
            dest.outputStream().use { target -> source.copyTo(target) }
        }
        dest.toPath()
    }

    fun cleanup(path: Path?) {
        if (path == null) return
        runCatching { java.nio.file.Files.deleteIfExists(path) }
    }

    private fun queryName(uri: Uri): String? {
        val projection = arrayOf(OpenableColumns.DISPLAY_NAME)
        return context.contentResolver.query(uri, projection, null, null, null)?.use { cursor ->
            val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else null
        }
    }
}
