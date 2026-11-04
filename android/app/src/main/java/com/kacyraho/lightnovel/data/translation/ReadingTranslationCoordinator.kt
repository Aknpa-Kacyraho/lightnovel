package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LibraryDao
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

object ReadingTranslationPlanner {
    fun plan(
        currentIndex: Int,
        chapters: List<ChapterEntity>,
        ahead: Int,
        backfill: Int,
    ): List<Int> {
        if (chapters.isEmpty()) return emptyList()
        val byIndex = chapters.associateBy { it.idx }
        val targets = linkedSetOf<Int>()
        val maxAhead = ahead.coerceIn(0, 10)
        val maxBackfill = backfill.coerceIn(0, 10)
        for (offset in 1..maxAhead) {
            val index = currentIndex + offset
            val chapter = byIndex[index] ?: break
            if (needsTranslation(chapter)) targets += index
        }
        var gap = 0
        var index = currentIndex - 1
        while (gap < maxBackfill && index >= 1) {
            val chapter = byIndex[index] ?: break
            if (chapter.status in TRANSLATED_STATUSES) break
            if (needsTranslation(chapter)) targets += index
            gap++
            index--
        }
        return targets.toList()
    }

    private fun needsTranslation(chapter: ChapterEntity): Boolean =
        chapter.status in setOf("online", "raw", "failed")

    private val TRANSLATED_STATUSES = setOf("complete", "translated", "partial")
}

class ReadingTranslationCoordinator(
    private val scope: CoroutineScope,
    private val translationService: TranslationService,
    private val taskRegistry: TranslationTaskRegistry,
    private val contentStore: ContentStore,
    private val dao: LibraryDao,
) {
    private val queueJobs = ConcurrentHashMap<String, Job>()

    fun request(
        book: BookEntity,
        currentIndex: Int,
        chapters: List<ChapterEntity>,
        ahead: Int,
        backfill: Int,
    ) {
        val targets = ReadingTranslationPlanner.plan(currentIndex, chapters, ahead, backfill)
        if (targets.isEmpty()) return
        val job = scope.launch {
            for (index in targets) {
                if (dao.readState(book.id)?.hidden == true) break
                if (contentStore.readZh(book.storageDir, index) != null) continue
                if (contentStore.readRaw(book.storageDir, index) == null) continue
                if (taskRegistry.isRunning(book.id, index)) continue
                val child = launch {
                    translationService.translate(book, index)
                }
                if (!taskRegistry.register(book.id, index, child)) {
                    child.cancel()
                } else {
                    child.join()
                }
            }
        }
        queueJobs.put(book.id, job)?.cancel()
    }
}
