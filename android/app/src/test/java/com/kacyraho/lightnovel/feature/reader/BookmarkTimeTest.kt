package com.kacyraho.lightnovel.feature.reader

import java.time.Instant
import java.time.ZoneOffset
import org.junit.Assert.assertEquals
import org.junit.Test

class BookmarkTimeTest {
    private val now = Instant.parse("2026-11-20T12:00:00Z")
    private val zone = ZoneOffset.UTC

    @Test
    fun justNow() {
        assertEquals("刚刚", relativeTime("2026-11-20T11:59:30Z", now, zone))
    }

    @Test
    fun minutes() {
        assertEquals("5 分钟前", relativeTime("2026-11-20T11:55:00Z", now, zone))
    }

    @Test
    fun hours() {
        assertEquals("3 小时前", relativeTime("2026-11-20T09:00:00Z", now, zone))
    }

    @Test
    fun days() {
        assertEquals("2 天前", relativeTime("2026-11-18T12:00:00Z", now, zone))
    }

    @Test
    fun olderThanAWeekUsesDate() {
        assertEquals("2026-11-01", relativeTime("2026-11-01T08:00:00Z", now, zone))
    }

    @Test
    fun invalidInputIsReturnedAsIs() {
        assertEquals("not-a-date", relativeTime("not-a-date", now, zone))
    }

    @Test
    fun futureClampsToJustNow() {
        assertEquals("刚刚", relativeTime("2026-11-20T13:00:00Z", now, zone))
    }
}
