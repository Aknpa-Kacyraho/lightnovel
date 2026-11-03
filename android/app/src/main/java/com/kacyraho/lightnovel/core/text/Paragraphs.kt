package com.kacyraho.lightnovel.core.text

object Paragraphs {
    private val blankLine = Regex("""\n\s*\n""")

    fun split(text: String): List<String> {
        val normalized = text.replace("\r\n", "\n").replace('\r', '\n')
        if (normalized.isBlank()) return emptyList()
        val blankSeparated = blankLine.split(normalized)
            .map(String::trim)
            .filter(String::isNotEmpty)
        if (blankSeparated.size > 1) return blankSeparated
        return normalized.split('\n')
            .map(String::trim)
            .filter(String::isNotEmpty)
            .ifEmpty { listOf(normalized.trim()) }
    }

    fun startOffset(text: String, paragraphIndex: Int): Int {
        if (paragraphIndex <= 0 || text.isEmpty()) return 0
        val parts = split(text)
        var cursor = 0
        for (index in 0 until minOf(paragraphIndex, parts.size)) {
            val part = parts[index]
            val found = text.indexOf(part, cursor)
            if (found < 0) return cursor.coerceIn(0, text.length)
            cursor = found + part.length
        }
        val target = parts.getOrNull(paragraphIndex) ?: return cursor.coerceIn(0, text.length)
        return text.indexOf(target, cursor).takeIf { it >= 0 } ?: cursor.coerceIn(0, text.length)
    }
}
