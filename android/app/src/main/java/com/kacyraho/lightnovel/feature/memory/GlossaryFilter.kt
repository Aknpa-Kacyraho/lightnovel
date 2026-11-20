package com.kacyraho.lightnovel.feature.memory

import com.kacyraho.lightnovel.data.glossary.GlossaryEntry

/**
 * 术语表搜索：原文、译名、别名任一命中即可，忽略大小写。
 * 空白查询返回原列表，不做任何排序。
 */
internal fun filterGlossary(
    entries: List<GlossaryEntry>,
    query: String,
): List<GlossaryEntry> {
    val needle = query.trim()
    if (needle.isEmpty()) return entries
    return entries.filter { entry ->
        entry.source.contains(needle, ignoreCase = true) ||
            entry.target.contains(needle, ignoreCase = true) ||
            entry.aliases.any { it.contains(needle, ignoreCase = true) }
    }
}
