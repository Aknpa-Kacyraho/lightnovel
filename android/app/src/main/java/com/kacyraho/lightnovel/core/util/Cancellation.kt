package com.kacyraho.lightnovel.core.util

import kotlinx.coroutines.CancellationException

/**
 * `runCatching` that lets coroutine cancellation pass through.
 *
 * `runCatching` catches every `Throwable`, including `CancellationException`;
 * wrapping a suspending call with it turns cancellation into an ordinary failure
 * and lets the caller keep running. Use this for suspend calls, keep plain
 * `runCatching` for pure parsing/IO that cannot be cancelled.
 */
suspend inline fun <T> runCatchingCancellable(
    crossinline block: suspend () -> T,
): Result<T> = try {
    Result.success(block())
} catch (error: CancellationException) {
    throw error
} catch (error: Exception) {
    Result.failure(error)
}
