package com.kacyraho.lightnovel.data.import

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import androidx.room.withTransaction
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.charset.Charset
import java.nio.charset.CodingErrorAction
import java.nio.file.Files
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class LocalDocumentImporter(
    private val database: LightnovelDatabase,
    private val contentStore: ContentStore,
) {
    suspend fun import(
        uri: Uri,
        resolver: ContentResolver,
        onProgress: (String) -> Unit = {},
    ): BookEntity = withContext(Dispatchers.IO) {
        val name = displayName(resolver, uri) ?: "本地书籍"
        displaySize(resolver, uri)?.let { size ->
            require(size <= MAX_BYTES) { "文件超过 80 MB" }
        }
        onProgress("读取文件")
        val bytes = resolver.openInputStream(uri)?.use(::readLimited)
            ?: error("无法读取文件")
        require(bytes.isNotEmpty()) { "文件是空的" }

        val extension = name.substringAfterLast('.', "").lowercase()
        val isEpub = extension == "epub" || (extension.isBlank() && bytes.size > 4 &&
            bytes[0] == 'P'.code.toByte() && bytes[1] == 'K'.code.toByte())
        val parsed = if (isEpub) {
            onProgress("解析 EPUB")
            val temp = Files.createTempFile(contentStore.root, "epub-", ".epub")
            try {
                Files.write(temp, bytes)
                LocalTextParser.parseEpub(name, temp)
            } finally {
                runCatching { Files.deleteIfExists(temp) }
            }
        } else {
            onProgress("解析 TXT")
            val text = decodeText(bytes)
            LocalTextParser.parseTxt(name, text)
        }

        val japanese = parsed.chapters.any { chapter ->
            chapter.text.count { it in '\u3040'..'\u30ff' } >= 20
        }
        val id = "local-" + UUID.randomUUID().toString().replace("-", "").take(12).lowercase()
        val now = Instant.now().toString()
        val book = BookEntity(
            id = id,
            storageDir = id,
            slug = id,
            source = "local",
            sourceId = id,
            title = parsed.title,
            titleZh = parsed.title,
            author = parsed.author,
            tagsJson = null,
            genre = null,
            episodes = parsed.chapters.size,
            local = true,
            createdAt = now,
            legacyJson = null,
        )
        val chapters = parsed.chapters.mapIndexed { index, chapter ->
            val idx = index + 1
            if (japanese) {
                contentStore.writeRawAtomic(id, idx, chapter.text)
            } else {
                contentStore.writeZhAtomic(id, idx, chapter.text)
            }
            ChapterEntity(
                bookId = id,
                idx = idx,
                title = chapter.title,
                titleZh = chapter.title,
                rawPath = null,
                zhPath = null,
                status = if (japanese) "raw" else "complete",
                tokenIn = 0,
                tokenOut = 0,
                model = if (japanese) "local-import" else "local-import-zh",
                updatedAt = now,
            )
        }
        database.withTransaction {
            val dao = database.libraryDao()
            dao.upsertBooks(listOf(book))
            dao.upsertReadStates(
                listOf(
                    ReadStateEntity(
                        bookId = id,
                        shelf = "reading",
                        favorite = false,
                        hidden = false,
                        progressIdx = 0,
                        openedAt = null,
                        finishedAt = null,
                        updatedAt = now,
                    ),
                ),
            )
            dao.upsertChapters(chapters)
        }
        book
    }

    private fun displayName(resolver: ContentResolver, uri: Uri): String? =
        resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
            ?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getString(0) else null
            }

    private fun displaySize(resolver: ContentResolver, uri: Uri): Long? =
        resolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)
            ?.use { cursor ->
                if (cursor.moveToFirst() && !cursor.isNull(0)) cursor.getLong(0) else null
            }

    private fun readLimited(input: InputStream): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(16 * 1024)
        var total = 0
        while (true) {
            val read = input.read(buffer)
            if (read < 0) break
            total += read
            require(total <= MAX_BYTES) { "文件超过 80 MB" }
            output.write(buffer, 0, read)
        }
        return output.toByteArray()
    }

    private fun decodeText(bytes: ByteArray): String {
        if (bytes.size >= 3 && bytes[0] == 0xEF.toByte() && bytes[1] == 0xBB.toByte() &&
            bytes[2] == 0xBF.toByte()
        ) {
            return String(bytes, 3, bytes.size - 3, Charsets.UTF_8)
        }
        if (bytes.size >= 2 && bytes[0] == 0xFF.toByte() && bytes[1] == 0xFE.toByte()) {
            return String(bytes, 2, bytes.size - 2, Charsets.UTF_16LE)
        }
        if (bytes.size >= 2 && bytes[0] == 0xFE.toByte() && bytes[1] == 0xFF.toByte()) {
            return String(bytes, 2, bytes.size - 2, Charsets.UTF_16BE)
        }
        val charsets = listOf(
            Charsets.UTF_8,
            Charset.forName("Shift_JIS"),
            Charset.forName("GB18030"),
            Charset.forName("Big5"),
        )
        var best = ""
        var bestScore = Int.MIN_VALUE
        for (charset in charsets) {
            val decoded = runCatching {
                charset.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString()
            }.getOrNull() ?: continue
            val score = decoded.count { it in '\u4e00'..'\u9fff' } * 2 +
                decoded.count { it in '\u3040'..'\u30ff' } * 3
            if (score > bestScore) {
                bestScore = score
                best = decoded
            }
        }
        return best.ifBlank { String(bytes, Charsets.UTF_8) }
    }

    private companion object {
        const val MAX_BYTES = 80 * 1024 * 1024
    }
}
