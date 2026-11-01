package com.kacyraho.lightnovel.core.settings

import android.content.Context

class TaskIgnoreStore(
    context: Context,
) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun load(): Set<String> {
        val raw = prefs.getString(KEY, null) ?: return emptySet()
        return raw.split(SEPARATOR).filter(String::isNotBlank).toSet()
    }

    fun ignore(bookId: String, chapterIndex: Int): Set<String> {
        val next = load() + "$bookId/$chapterIndex"
        prefs.edit().putString(KEY, next.joinToString(SEPARATOR)).apply()
        return next
    }

    fun clear(bookId: String, chapterIndex: Int): Set<String> {
        val next = load() - "$bookId/$chapterIndex"
        prefs.edit().putString(KEY, next.joinToString(SEPARATOR)).apply()
        return next
    }

    private companion object {
        const val PREFS = "lightnovel_task_ignore"
        const val KEY = "tasks"
        const val SEPARATOR = "\u001F"
    }
}
