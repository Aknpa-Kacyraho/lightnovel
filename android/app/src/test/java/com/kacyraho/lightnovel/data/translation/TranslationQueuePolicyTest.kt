package com.kacyraho.lightnovel.data.translation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TranslationQueuePolicyTest {
    @Test
    fun manualTargetsRunBeforeAutoTargets() {
        assertEquals(30, pickNextIndex(manual = listOf(30), auto = listOf(12, 13)))
    }

    @Test
    fun autoTargetsRunWhenManualQueueIsEmpty() {
        assertEquals(12, pickNextIndex(manual = emptyList(), auto = listOf(12, 13)))
    }

    @Test
    fun noTargetsReturnsNull() {
        assertNull(pickNextIndex(manual = emptyList(), auto = emptyList()))
    }

    @Test
    fun successCountsAsCompleted() {
        assertEquals(
            TargetDisposition.COMPLETED,
            dispositionOf(success = true, skipped = false, retryable = false, alreadyRetried = false),
        )
    }

    @Test
    fun duplicateInFlightIsSkipped() {
        assertEquals(
            TargetDisposition.SKIPPED,
            dispositionOf(success = false, skipped = true, retryable = true, alreadyRetried = false),
        )
    }

    @Test
    fun retryableFailureRetriesOnce() {
        assertEquals(
            TargetDisposition.RETRY,
            dispositionOf(success = false, skipped = false, retryable = true, alreadyRetried = false),
        )
        assertEquals(
            TargetDisposition.FAILED,
            dispositionOf(success = false, skipped = false, retryable = true, alreadyRetried = true),
        )
    }

    @Test
    fun nonRetryableFailureIsFailed() {
        assertEquals(
            TargetDisposition.FAILED,
            dispositionOf(success = false, skipped = false, retryable = false, alreadyRetried = false),
        )
    }
}
