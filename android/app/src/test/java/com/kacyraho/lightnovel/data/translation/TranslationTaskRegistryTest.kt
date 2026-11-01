package com.kacyraho.lightnovel.data.translation

import kotlinx.coroutines.Job
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TranslationTaskRegistryTest {
    @Test
    fun registersAndCancelsRunningChapter() {
        val registry = TranslationTaskRegistry()
        val job = Job()

        registry.register("book", 3, job)
        assertTrue(registry.isRunning("book", 3))
        assertTrue(registry.cancel("book", 3))
        assertTrue(job.isCancelled)
        assertFalse(registry.isRunning("book", 3))
    }

    @Test
    fun cancelUnknownTaskReturnsFalse() {
        assertFalse(TranslationTaskRegistry().cancel("missing", 1))
    }
}
