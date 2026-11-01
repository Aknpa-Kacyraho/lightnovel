package com.kacyraho.lightnovel.data.download

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.NetworkType
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import java.util.concurrent.TimeUnit

class BookDownloadScheduler(
    context: Context,
) {
    private val workManager = WorkManager.getInstance(context)

    fun enqueue(bookId: String) {
        val request = OneTimeWorkRequestBuilder<BookDownloadWorker>()
            .setInputData(workDataOf(BookDownloadWorker.KEY_BOOK_ID to bookId))
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build(),
            )
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        workManager.enqueueUniqueWork(
            BookDownloadWorker.uniqueName(bookId),
            ExistingWorkPolicy.KEEP,
            request,
        )
    }

    fun cancel(bookId: String) {
        workManager.cancelUniqueWork(BookDownloadWorker.uniqueName(bookId))
    }
}
