package com.kacyraho.lightnovel.data.translation

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class QueueRetryPolicyTest {
    @Test
    fun retryableFailureIsRetriedOnce() {
        assertTrue(shouldRetryAfterFailure(3, retried = emptySet(), retryable = true))
    }

    @Test
    fun alreadyRetriedIsNotRetriedAgain() {
        assertFalse(shouldRetryAfterFailure(3, retried = setOf(3), retryable = true))
    }

    @Test
    fun nonRetryableFailureIsNotRetried() {
        assertFalse(shouldRetryAfterFailure(3, retried = emptySet(), retryable = false))
    }

    @Test
    fun otherChaptersKeepTheirOwnRetry() {
        assertTrue(shouldRetryAfterFailure(4, retried = setOf(3), retryable = true))
    }
}
