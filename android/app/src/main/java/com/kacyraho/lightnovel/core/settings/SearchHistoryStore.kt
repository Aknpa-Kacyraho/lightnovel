package com.kacyraho.lightnovel.core.settings

import android.content.Context

class SearchHistoryStore(
    context: Context,
) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun load(): List<String> {
        val raw = prefs.getString(KEY, null) ?: return emptyList()
        return raw.split(SEPARATOR)
            .map(String::trim)
            .filter(String::isNotBlank)
            .distinct()
            .take(MAX)
    }

    fun remember(query: String): List<String> {
        val value = query.trim()
        if (value.isBlank()) return load()
        val next = (listOf(value) + load().filterNot { it == value }).take(MAX)
        prefs.edit().putString(KEY, next.joinToString(SEPARATOR)).apply()
        return next
    }

    fun clear() {
        prefs.edit().remove(KEY).apply()
    }

    private companion object {
        const val PREFS = "lightnovel_search_history"
        const val KEY = "queries"
        const val SEPARATOR = "\u001F"
        const val MAX = 10
    }
}
