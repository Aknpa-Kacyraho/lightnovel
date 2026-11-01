package com.kacyraho.lightnovel.reader.engine

class ReaderChapterCache(private val maxEntries: Int = 12) {
    private val cache = object : LinkedHashMap<String, ReaderChapter>(16, 0.75f, true) {
        override fun removeEldestEntry(
            eldest: MutableMap.MutableEntry<String, ReaderChapter>?,
        ): Boolean = size > maxEntries
    }

    @Synchronized
    fun get(bookId: String, idx: Int, displayMode: String): ReaderChapter? =
        cache[key(bookId, idx, displayMode)]

    @Synchronized
    fun put(bookId: String, idx: Int, displayMode: String, chapter: ReaderChapter) {
        cache[key(bookId, idx, displayMode)] = chapter
    }

    @Synchronized
    fun clearBook(bookId: String) {
        cache.keys.removeIf { it.startsWith("$bookId:") }
    }

    private fun key(bookId: String, idx: Int, displayMode: String): String =
        "$bookId:$idx:$displayMode"
}
