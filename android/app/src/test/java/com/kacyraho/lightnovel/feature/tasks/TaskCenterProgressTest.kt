package com.kacyraho.lightnovel.feature.tasks

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TaskCenterProgressTest {
    @Test
    fun hidesProgressWithoutATotal() {
        assertNull(taskProgressLabel(0, 0))
        assertNull(taskProgressLabel(3, 0))
    }

    @Test
    fun formatsPartialProgress() {
        assertEquals("已译 12/34 段", taskProgressLabel(12, 34))
    }

    @Test
    fun clampsOutOfRangeValues() {
        assertEquals("已译 0/10 段", taskProgressLabel(-3, 10))
        assertEquals("已译 10/10 段", taskProgressLabel(99, 10))
    }
}
