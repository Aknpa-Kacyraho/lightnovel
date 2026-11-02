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
}
