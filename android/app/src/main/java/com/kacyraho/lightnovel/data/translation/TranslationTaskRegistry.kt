package com.kacyraho.lightnovel.data.translation

import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

data class TranslationTaskSnapshot(
    val bookId: String,
    val chapterIndex: Int,
    val done: Int = 0,
    val total: Int = 0,
) {
    val key: String
        get() = TranslationTaskRegistry.key(bookId, chapterIndex)
}

sealed interface TranslationTaskEvent {
    val bookId: String
    val chapterIndex: Int

    data class Finished(
        override val bookId: String,
        override val chapterIndex: Int,
    ) : TranslationTaskEvent

    data class Cancelled(
        override val bookId: String,
        override val chapterIndex: Int,
    ) : TranslationTaskEvent
}

class TranslationTaskRegistry {
    private val jobs = ConcurrentHashMap<String, Job>()
    private val _active = MutableStateFlow<Map<String, TranslationTaskSnapshot>>(emptyMap())
    val active: StateFlow<Map<String, TranslationTaskSnapshot>> = _active.asStateFlow()

    private val _events = MutableSharedFlow<TranslationTaskEvent>(extraBufferCapacity = 32)
    val events: SharedFlow<TranslationTaskEvent> = _events.asSharedFlow()

    private val _cancelled = MutableSharedFlow<String>(extraBufferCapacity = 16)
    val cancelled: SharedFlow<String> = _cancelled.asSharedFlow()

    fun register(bookId: String, chapterIndex: Int, job: Job): Boolean {
        val key = key(bookId, chapterIndex)
        var accepted = false
        jobs.compute(key) { _, previous ->
            if (previous?.isActive == true) {
                previous
            } else {
                accepted = true
                job
            }
        }
        if (!accepted) {
            job.cancel()
            return false
        }
        _active.update {
            it + (key to TranslationTaskSnapshot(bookId, chapterIndex))
        }
        job.invokeOnCompletion {
            jobs.remove(key, job)
            _active.update { current -> current - key }
            if (!job.isCancelled) {
                _events.tryEmit(TranslationTaskEvent.Finished(bookId, chapterIndex))
            }
        }
        return true
    }

    fun reportProgress(bookId: String, chapterIndex: Int, done: Int, total: Int) {
        val key = key(bookId, chapterIndex)
        _active.update { current ->
            if (key !in current) {
                current
            } else {
                current + (key to TranslationTaskSnapshot(bookId, chapterIndex, done, total))
            }
        }
    }

    fun snapshot(bookId: String, chapterIndex: Int): TranslationTaskSnapshot? =
        _active.value[key(bookId, chapterIndex)]

    fun cancel(bookId: String, chapterIndex: Int): Boolean {
        val key = key(bookId, chapterIndex)
        val job = jobs.remove(key) ?: return false
        _active.update { it - key }
        _cancelled.tryEmit(key)
        _events.tryEmit(TranslationTaskEvent.Cancelled(bookId, chapterIndex))
        job.cancel()
        return true
    }

    fun isRunning(bookId: String, chapterIndex: Int): Boolean =
        jobs.containsKey(key(bookId, chapterIndex))

    fun cancelBook(bookId: String) {
        jobs.keys
            .filter { it.startsWith("$bookId/") }
            .forEach { key ->
                val job = jobs.remove(key) ?: return@forEach
                val index = key.substringAfter('/').toIntOrNull() ?: return@forEach
                _active.update { it - key }
                _cancelled.tryEmit(key)
                _events.tryEmit(TranslationTaskEvent.Cancelled(bookId, index))
                job.cancel()
            }
    }

    companion object {
        fun key(bookId: String, chapterIndex: Int): String = "$bookId/$chapterIndex"
    }
}
