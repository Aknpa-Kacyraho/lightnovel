package com.kacyraho.lightnovel.feature.reader

import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * 书签列表的相对时间：刚刚 / N 分钟前 / N 小时前 / N 天前 / 具体日期。
 * 解析失败时原样返回，不抛异常。
 */
internal fun relativeTime(
    iso: String,
    now: Instant = Instant.now(),
    zone: ZoneId = ZoneId.systemDefault(),
): String {
    val then = runCatching { Instant.parse(iso) }.getOrNull() ?: return iso
    val seconds = Duration.between(then, now).seconds.coerceAtLeast(0)
    return when {
        seconds < 60 -> "刚刚"
        seconds < 3_600 -> "${seconds / 60} 分钟前"
        seconds < 86_400 -> "${seconds / 3_600} 小时前"
        seconds < 7 * 86_400 -> "${seconds / 86_400} 天前"
        else -> DateTimeFormatter.ofPattern("yyyy-MM-dd").withZone(zone).format(then)
    }
}
