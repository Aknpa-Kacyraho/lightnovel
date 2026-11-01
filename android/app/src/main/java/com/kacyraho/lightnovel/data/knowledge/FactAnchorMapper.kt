package com.kacyraho.lightnovel.data.knowledge

import com.kacyraho.lightnovel.data.translation.Hashes
import com.kacyraho.lightnovel.data.translation.TranslationValidators
import java.text.Normalizer

object FactAnchorMapper {
    fun normalize(text: String): String {
        var value = Normalizer.normalize(text, Normalizer.Form.NFC)
        value = value.replace("\r\n", "\n").replace('\r', '\n')
        value = value.replace(Regex("[\\u200B-\\u200D\\uFEFF]"), "")
        value = value.lines().joinToString("\n") { it.trimEnd() }
        value = value.replace(Regex("\\s+"), " ")
        return value.trim()
    }

    fun quoteHash(quote: String): String = Hashes.sha256(normalize(quote))

    fun locate(text: String, quote: String): Pair<Int, Int>? {
        val normalizedQuote = normalize(quote)
        if (normalizedQuote.isBlank()) return null
        val paragraphs = TranslationValidators.splitParagraphs(text)
        for ((index, paragraph) in paragraphs.withIndex()) {
            val offset = normalize(paragraph).indexOf(normalizedQuote)
            if (offset >= 0) return index to offset
        }
        return null
    }

    fun anchor(
        chapter: Int,
        paragraph: Int,
        quote: String,
    ): FactAnchor = FactAnchor(
        chapter = chapter,
        paragraph = paragraph,
        charOffset = 0,
        quoteHash = quoteHash(quote),
    )

    fun displayAnchor(
        chapter: Int,
        paragraph: Int,
        quote: String?,
    ): DisplayAnchor? {
        if (quote.isNullOrBlank()) return null
        return DisplayAnchor(
            chapter = chapter,
            paragraph = paragraph,
            charOffset = 0,
            quoteHash = quoteHash(quote),
        )
    }

    fun readAnchor(
        chapter: Int,
        paragraph: Int,
        degraded: Boolean = false,
    ): FactAnchor = FactAnchor(
        chapter = chapter,
        paragraph = if (degraded) -1 else paragraph,
        charOffset = if (degraded) -1 else Int.MAX_VALUE,
        quoteHash = "",
    )

    fun visible(source: FactAnchor, read: FactAnchor): Boolean {
        if (read.paragraph < 0) return source.chapter < read.chapter
        return source.compareTo(read) <= 0
    }
}
