package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LibraryDao
import com.kacyraho.lightnovel.data.source.ChapterFetcher
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import kotlin.coroutines.coroutineContext

data class ReadingTranslationQueueState(
    val bookId: String,
    val runningIndex: Int? = null,
    val pending: List<Int> = emptyList(),
    val completed: Int = 0,
    val failed: Int = 0,
    val paused: Boolean = false,
    val lastError: String? = null,
) {
    val active: Boolean
        get() = runningIndex != null || pending.isNotEmpty()

    val nextIndex: Int?
        get() = runningIndex ?: pending.firstOrNull()

    val remaining: Int
        get() = pending.size + if (runningIndex != null) 1 else 0
}

data class ChapterTranslatedEvent(
    val bookId: String,
    val chapterIndex: Int,
    val success: Boolean = true,
)

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

    fun needsTranslation(chapter: ChapterEntity): Boolean =
        chapter.status in setOf("online", "raw", "failed", "partial")

    private val TRANSLATED_STATUSES = setOf("complete", "translated")
}

class ReadingTranslationCoordinator(
    private val scope: CoroutineScope,
    private val translationService: TranslationService,
    private val taskRegistry: TranslationTaskRegistry,
    private val contentStore: ContentStore,
    private val dao: LibraryDao,
    private val chapterFetcher: ChapterFetcher? = null,
) {
    private class BookQueue {
        val autoTargets = linkedSetOf<Int>()
        val manualTargets = linkedSetOf<Int>()
        var runningIndex: Int? = null
        var completed: Int = 0
        var failed: Int = 0
        var paused: Boolean = false
        var lastError: String? = null
        var stopRequested: Boolean = false
        var worker: Job? = null
        var book: BookEntity? = null
    }

    private val lock = Any()
    private val queues = ConcurrentHashMap<String, BookQueue>()
    private val _states = MutableStateFlow<Map<String, ReadingTranslationQueueState>>(emptyMap())
    val states: StateFlow<Map<String, ReadingTranslationQueueState>> = _states.asStateFlow()

    private val _translated = MutableSharedFlow<ChapterTranslatedEvent>(extraBufferCapacity = 32)
    val translated: SharedFlow<ChapterTranslatedEvent> = _translated.asSharedFlow()

    fun observe(bookId: String) = states.map { it[bookId] }

    fun request(
        book: BookEntity,
        currentIndex: Int,
        chapters: List<ChapterEntity>,
        ahead: Int,
        backfill: Int,
    ) {
        val targets = ReadingTranslationPlanner.plan(currentIndex, chapters, ahead, backfill)
        synchronized(lock) {
            val queue = queues.getOrPut(book.id) { BookQueue() }
            queue.book = book
            queue.autoTargets.clear()
            queue.autoTargets.addAll(targets)
            queue.stopRequested = false
            queue.lastError = null
            publishLocked()
            ensureWorkerLocked(queue)
        }
    }

    fun enqueue(book: BookEntity, chapterIndices: List<Int>) {
        if (chapterIndices.isEmpty()) return
        synchronized(lock) {
            val queue = queues.getOrPut(book.id) { BookQueue() }
            queue.book = book
            queue.manualTargets.addAll(chapterIndices.filter { it > 0 })
            queue.paused = false
            queue.stopRequested = false
            queue.lastError = null
            publishLocked()
            ensureWorkerLocked(queue)
        }
    }

    fun pause(bookId: String) {
        synchronized(lock) {
            val queue = queues[bookId] ?: return
            queue.paused = true
            if (queue.runningIndex == null) {
                queue.worker?.cancel()
                queue.worker = null
            }
            publishLocked()
        }
    }

    fun resume(bookId: String) {
        synchronized(lock) {
            val queue = queues[bookId] ?: return
            queue.paused = false
            queue.stopRequested = false
            publishLocked()
            ensureWorkerLocked(queue)
        }
    }

    fun stop(bookId: String) {
        synchronized(lock) {
            val queue = queues[bookId] ?: return
            queue.autoTargets.clear()
            queue.manualTargets.clear()
            queue.stopRequested = true
            queue.paused = false
            queue.worker?.cancel()
            queue.worker = null
            queue.runningIndex = null
            queue.completed = 0
            queue.failed = 0
            queue.lastError = null
            publishLocked()
        }
    }

    private fun ensureWorkerLocked(queue: BookQueue) {
        if (queue.paused || queue.stopRequested) return
        if (queue.worker?.isActive == true) return
        if (queue.manualTargets.isEmpty() && queue.autoTargets.isEmpty()) return
        val worker = scope.launch(start = CoroutineStart.LAZY) { runWorker(queue) }
        queue.worker = worker
        worker.start()
    }

    private suspend fun runWorker(queue: BookQueue) {
        val self = coroutineContext[Job]
        try {
            while (true) {
                val target = synchronized(lock) {
                    if (queue.paused || queue.stopRequested) {
                        null
                    } else {
                        queue.autoTargets.firstOrNull()
                            ?: queue.manualTargets.firstOrNull()
                    }
                } ?: break
                synchronized(lock) {
                    queue.autoTargets.remove(target)
                    queue.manualTargets.remove(target)
                    queue.runningIndex = target
                    publishLocked()
                }
                val translated = try {
                    translateTarget(queue, target)
                } catch (error: CancellationException) {
                    throw error
                } catch (_: Exception) {
                    synchronized(lock) { queue.lastError = "第 $target 话翻译异常" }
                    false
                }
                synchronized(lock) {
                    queue.runningIndex = null
                    if (translated) queue.completed++ else queue.failed++
                    publishLocked()
                }
            }
        } finally {
            synchronized(lock) {
                if (queue.worker === self) {
                    queue.runningIndex = null
                    queue.worker = null
                    val shouldRestart = !queue.paused &&
                        !queue.stopRequested &&
                        (queue.autoTargets.isNotEmpty() || queue.manualTargets.isNotEmpty())
                    publishLocked()
                    if (shouldRestart) ensureWorkerLocked(queue)
                }
            }
        }
    }

    private suspend fun translateTarget(queue: BookQueue, index: Int): Boolean {
        val book = queue.book ?: return false
        if (dao.readState(book.id)?.hidden == true) {
            synchronized(lock) {
                queue.stopRequested = true
                queue.autoTargets.clear()
                queue.manualTargets.clear()
            }
            return false
        }
        if (contentStore.readZh(book.storageDir, index) != null) return true
        if (contentStore.readRaw(book.storageDir, index) == null && !book.local) {
            val fetched = runCatching { chapterFetcher?.ensureChapter(book, index) }
                .getOrNull() == true
            if (!fetched) {
                synchronized(lock) { queue.lastError = "第 $index 话原文下载失败" }
                _translated.tryEmit(ChapterTranslatedEvent(book.id, index, success = false))
                return false
            }
        }
        if (contentStore.readRaw(book.storageDir, index) == null) {
            synchronized(lock) { queue.lastError = "第 $index 话缺少原文" }
            _translated.tryEmit(ChapterTranslatedEvent(book.id, index, success = false))
            return false
        }
        if (taskRegistry.isRunning(book.id, index)) return true

        val outcome = coroutineScope {
            var result: TranslationOutcome? = null
            val child = launch(start = CoroutineStart.LAZY) {
                result = translationService.translate(book, index) { done, total ->
                    taskRegistry.reportProgress(book.id, index, done, total)
                }
            }
            if (!taskRegistry.register(book.id, index, child)) {
                child.cancel()
                return@coroutineScope null
            }
            child.start()
            child.join()
            result
        }
        return when (outcome) {
            is TranslationOutcome.Complete -> {
                synchronized(lock) { queue.lastError = null }
                _translated.tryEmit(ChapterTranslatedEvent(book.id, index))
                true
            }
            is TranslationOutcome.Partial -> {
                synchronized(lock) { queue.lastError = null }
                _translated.tryEmit(ChapterTranslatedEvent(book.id, index))
                true
            }
            is TranslationOutcome.Failed -> {
                synchronized(lock) { queue.lastError = outcome.reason }
                _translated.tryEmit(ChapterTranslatedEvent(book.id, index, success = false))
                false
            }
            null -> false
        }
    }

    private fun publishLocked() {
        _states.value = queues.mapValues { (bookId, queue) ->
            ReadingTranslationQueueState(
                bookId = bookId,
                runningIndex = queue.runningIndex,
                pending = (queue.autoTargets + queue.manualTargets).sorted(),
                completed = queue.completed,
                failed = queue.failed,
                paused = queue.paused,
                lastError = queue.lastError,
            )
        }
    }
}
