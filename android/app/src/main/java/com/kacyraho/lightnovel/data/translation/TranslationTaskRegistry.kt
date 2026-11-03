package com.kacyraho.lightnovel.data.translation

import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow

class TranslationTaskRegistry {
    private val jobs = ConcurrentHashMap<String, Job>()
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
        job.invokeOnCompletion { jobs.remove(key, job) }
        return true
    }

    fun cancel(bookId: String, chapterIndex: Int): Boolean {
        val key = key(bookId, chapterIndex)
        val job = jobs.remove(key) ?: return false
        _cancelled.tryEmit(key)
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
                _cancelled.tryEmit(key)
                job.cancel()
            }
    }

    private fun key(bookId: String, chapterIndex: Int): String = "$bookId/$chapterIndex"
}
