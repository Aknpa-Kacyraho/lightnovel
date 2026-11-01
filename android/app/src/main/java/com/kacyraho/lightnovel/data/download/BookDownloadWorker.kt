package com.kacyraho.lightnovel.data.download

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.kacyraho.lightnovel.LightnovelApp

class BookDownloadWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val bookId = inputData.getString(KEY_BOOK_ID) ?: return Result.failure()
        val container = (applicationContext as LightnovelApp).container
        val dao = container.database.libraryDao()
        val book = dao.book(bookId) ?: return Result.failure()
        if (book.local) return Result.failure()
        val chapters = dao.chapters(bookId)
        if (chapters.isEmpty()) return Result.success()
        var done = 0
        var failed = 0
        for (chapter in chapters) {
            if (isStopped) return Result.retry()
            val ok = runCatching {
                container.directLibraryService.ensureChapter(book, chapter.idx)
            }.getOrDefault(false)
            if (ok) done++ else failed++
            setProgress(
                workDataOf(
                    "done" to done,
                    "failed" to failed,
                    "total" to chapters.size,
                ),
            )
        }
        val output = workDataOf(
            "done" to done,
            "failed" to failed,
            "total" to chapters.size,
        )
        return when {
            failed == 0 -> Result.success(output)
            runAttemptCount < 3 -> Result.retry()
            else -> Result.failure(output)
        }
    }

    companion object {
        const val KEY_BOOK_ID = "book_id"
        fun uniqueName(bookId: String): String = "book-download-$bookId"
    }
}
