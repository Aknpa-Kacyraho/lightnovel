package com.kacyraho.lightnovel.data.translation

import kotlinx.coroutines.Job
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
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

    @Test
    fun exposesRunningTaskAndProgress() {
        val registry = TranslationTaskRegistry()
        val job = Job()

        registry.register("book", 4, job)
        registry.reportProgress("book", 4, 2, 5)

        val snapshot = registry.snapshot("book", 4)
        assertEquals(2, snapshot?.done)
        assertEquals(5, snapshot?.total)
        assertTrue(registry.isRunning("book", 4))

        registry.cancel("book", 4)
        assertNull(registry.snapshot("book", 4))
    }
}
