package com.kacyraho.lightnovel.core.util

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CancellationTest {
    @Test
    fun rethrowsCancellation() {
        val error = CancellationException("stop")

        val thrown = runCatching {
            runBlocking {
                runCatchingCancellable<Unit> { throw error }
            }
        }.exceptionOrNull()

        assertEquals(error, thrown)
    }

    @Test
    fun wrapsOrdinaryExceptions() = runBlocking {
        val result = runCatchingCancellable<Unit> { error("boom") }

        assertTrue(result.isFailure)
        assertEquals("boom", result.exceptionOrNull()?.message)
    }
}
