package com.kacyraho.lightnovel.feature.reader

import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.core.text.Paragraphs
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

internal data class TextHit(
    val paragraphId: Int,
    val before: String,
    val match: String,
    val after: String,
)

data class BookSearchHit(
    val chapterIndex: Int,
    val chapterTitle: String,
    val paragraphId: Int,
    val before: String,
    val match: String,
    val after: String,
)

/**
 * 在单章文本中找前 [max] 处匹配；每段只取第一处，前后各保留 20 字上下文。
 */
internal fun findHits(text: String, query: String, max: Int = 3): List<TextHit> {
    val needle = query.trim()
    if (needle.isEmpty() || max <= 0) return emptyList()
    val hits = mutableListOf<TextHit>()
    Paragraphs.split(text).forEachIndexed { index, paragraph ->
        if (hits.size >= max) return@forEachIndexed
        val at = paragraph.indexOf(needle, ignoreCase = true)
        if (at < 0) return@forEachIndexed
        val start = (at - 20).coerceAtLeast(0)
        val end = (at + needle.length + 20).coerceAtMost(paragraph.length)
        hits += TextHit(
            paragraphId = index,
            before = (if (start > 0) "…" else "") + paragraph.substring(start, at),
            match = paragraph.substring(at, at + needle.length),
            after = paragraph.substring(at + needle.length, end) +
                (if (end < paragraph.length) "…" else ""),
        )
    }
    return hits
}

class BookSearchService(
    private val contentStore: ContentStore,
) {
    suspend fun search(
        book: BookEntity,
        chapters: List<ChapterEntity>,
        query: String,
        preferTranslated: Boolean,
        limit: Int = 30,
    ): List<BookSearchHit> = withContext(Dispatchers.IO) {
        if (query.isBlank() || limit <= 0) return@withContext emptyList()
        val out = mutableListOf<BookSearchHit>()
        for (chapter in chapters) {
            if (out.size >= limit) break
            val preferred = if (preferTranslated) {
                contentStore.readZh(book.storageDir, chapter.idx)
                    ?: contentStore.readRaw(book.storageDir, chapter.idx)
            } else {
                contentStore.readRaw(book.storageDir, chapter.idx)
                    ?: contentStore.readZh(book.storageDir, chapter.idx)
            } ?: continue
            val title = chapter.titleZh ?: chapter.title ?: "第 ${chapter.idx} 话"
            findHits(preferred, query).forEach { hit ->
                if (out.size < limit) {
                    out += BookSearchHit(
                        chapterIndex = chapter.idx,
                        chapterTitle = title,
                        paragraphId = hit.paragraphId,
                        before = hit.before,
                        match = hit.match,
                        after = hit.after,
                    )
                }
            }
        }
        out
    }
}
