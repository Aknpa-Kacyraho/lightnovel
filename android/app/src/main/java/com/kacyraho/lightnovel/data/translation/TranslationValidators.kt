package com.kacyraho.lightnovel.data.translation

object TranslationValidators {
    private const val QUOTE_OPEN = "「『“‘"
    private const val QUOTE_CLOSE = "」』”’"
    private val KANA = Regex("[\\u3040-\\u30ff]")
    private val HANZI = Regex("[\\u3400-\\u4dbf\\u4e00-\\u9fff]")
    private val URL = Regex("https?://\\S+|www\\.\\S+")
    private val WORD = Regex("[A-Za-z]{2,}")
    private val QUOTE_SPAN = Regex("[「『“‘][^」』”’]*[」』”’]")
    private val KAOMOJI = Regex("[（(][^）)\\n]{0,60}[）)]")
    private val DECOR = Regex("[゛゜ー]+")
    private val ZH_PUNCT = "，。！？；：、（）【】《》…—“”‘’"

    data class IndexedParagraph(
        val index: Int,
        val text: String,
    )

    fun splitParagraphs(text: String): List<String> {
        val normalized = text.replace("\r\n", "\n")
        if (!Regex("""\n[ \t]*\n""").containsMatchIn(normalized)) {
            return normalized.split('\n')
                .map(String::trim)
                .filter(String::isNotEmpty)
        }
        val lines = normalized.split("\n")
        val out = mutableListOf<String>()
        val buffer = mutableListOf<String>()
        for (line in lines) {
            if (line.isBlank()) {
                if (buffer.isNotEmpty()) {
                    out += buffer.joinToString("\n")
                    buffer.clear()
                }
                out += ""
            } else {
                buffer += line
            }
        }
        if (buffer.isNotEmpty()) out += buffer.joinToString("\n")
        return out
    }

    fun hasTranslatable(text: String): Boolean {
        if (text.isBlank()) return false
        if (KANA.containsMatchIn(text) || HANZI.containsMatchIn(text)) return true
        return WORD.findAll(URL.replace(text, " ")).count() >= 3
    }

    fun dialogueCount(text: String): Int =
        text.count { it in "「“‘" }

    fun missingDialogue(source: String, translated: String): Boolean {
        val sourceCount = dialogueCount(source)
        return sourceCount > 0 && dialogueCount(translated) < sourceCount
    }

    fun blockIssue(source: String, translated: String): String? {
        if (!detectChinese(translated)) return "不是简体中文"
        if (isEcho(translated, source) && KANA.containsMatchIn(source)) {
            return "译文与原文相同"
        }

        val sourceQuotes = openQuoteCount(source)
        val translatedQuotes = openQuoteCount(translated)
        if (sourceQuotes > 0 && translatedQuotes < sourceQuotes) {
            return "对白数量少于原文（$translatedQuotes/$sourceQuotes）"
        }

        val sourceLength = source.count { !it.isWhitespace() }
        val translatedLength = translated.count { !it.isWhitespace() }
        if (sourceLength >= 40) {
            val ratio = translatedLength.toDouble() / sourceLength
            if (ratio < 0.25 || ratio > 2.80) return "译文长度异常"
        }
        return null
    }

    fun openQuoteCount(text: String): Int =
        text.count { it in "「『“‘" }

    fun blockRanges(
        paragraphs: List<String>,
        maxChars: Int,
    ): List<IntRange> {
        if (paragraphs.isEmpty()) return emptyList()
        val ranges = mutableListOf<IntRange>()
        var start = 0
        var size = 0
        for (i in paragraphs.indices) {
            val length = paragraphs[i].length + 1
            if (i > start && size + length > maxChars) {
                ranges += start until i
                start = i
                size = 0
            }
            size += length
        }
        if (start < paragraphs.size) ranges += start until paragraphs.size
        return ranges
    }

    fun paragraphIssue(source: String, translated: String): String? {
        if (!detectChinese(translated)) return "不是简体中文"
        if (isEcho(translated, source) && KANA.containsMatchIn(source)) {
            return "译文与原文相同"
        }

        val sourceQuotes = dialogueCount(source)
        val translatedQuotes = dialogueCount(translated)
        if (sourceQuotes != translatedQuotes) return "对白引号数量不一致"
        if (sourceQuotes > 0 && quoteSequence(source) != quoteSequence(translated)) {
            return "对白引号结构不一致"
        }

        val sourceLength = source.count { !it.isWhitespace() }
        val translatedLength = translated.count { !it.isWhitespace() }
        if (sourceLength >= 40) {
            val ratio = translatedLength.toDouble() / sourceLength
            if (ratio < 0.30 || ratio > 2.50) return "译文长度异常"
        }
        return null
    }

    fun alignQuotes(translated: String, source: String): String {
        if (translated.isBlank() || source.isBlank()) return translated
        val sourceQuotes = source.filter { it in QUOTE_OPEN || it in QUOTE_CLOSE }
        val translatedQuotes = translated.filter { it in QUOTE_OPEN || it in QUOTE_CLOSE }
        if (sourceQuotes.isEmpty() || translatedQuotes.isEmpty()) return translated
        if (sourceQuotes.length != translatedQuotes.length) return translated
        if (quoteSequence(source) != quoteSequence(translated)) return translated
        val out = StringBuilder(translated.length)
        var i = 0
        for (c in translated) {
            if (c in QUOTE_OPEN || c in QUOTE_CLOSE) {
                out.append(sourceQuotes[i])
                i++
            } else {
                out.append(c)
            }
        }
        return out.toString()
    }

    fun detectChinese(text: String): Boolean {
        if (text.isBlank()) return false
        val normalized = URL.replace(text, "")
        var zh = 0
        var jp = 0
        var en = 0
        for (c in normalized) {
            when {
                HANZI.matches(c.toString()) || c in ZH_PUNCT -> zh++
                KANA.matches(c.toString()) -> jp++
                c.isAsciiAlpha() -> en++
            }
        }
        val n = normalized.length.coerceAtLeast(1)
        val pzh = zh.toDouble() / n
        val pjp = jp.toDouble() / n
        val pen = en.toDouble() / n
        if (pjp > 0.15 || (jp >= 8 && pjp > 0.05)) return false
        return pzh > 0.75 ||
            (pzh > pjp && pjp < 0.1 && pzh > pen) ||
            (pzh > 0.15 && pjp < 0.05 && pzh > pen * 0.5)
    }

    fun isEcho(translated: String, source: String): Boolean =
        normalize(translated) == normalize(source)

    fun kanaOutsideQuotes(text: String): Int {
        val body = KAOMOJI.replace(QUOTE_SPAN.replace(text, ""), "")
        return DECOR.replace(body, "").count { it in '\u3040'..'\u30ff' }
    }

    fun chunkIndexed(
        paragraphs: List<IndexedParagraph>,
        maxChars: Int = 6_000,
    ): List<List<IndexedParagraph>> {
        if (paragraphs.isEmpty()) return emptyList()
        val chunks = mutableListOf<List<IndexedParagraph>>()
        var current = mutableListOf<IndexedParagraph>()
        var size = 0
        for (paragraph in paragraphs) {
            val length = paragraph.text.length
            if (current.isNotEmpty() && size + length > maxChars) {
                chunks += current
                current = mutableListOf()
                size = 0
            }
            current += paragraph
            size += length
        }
        if (current.isNotEmpty()) chunks += current
        return chunks
    }

    fun parseNumbered(reply: String): Map<Int, String> {
        val out = linkedMapOf<Int, String>()
        var current: Int? = null
        val buffer = StringBuilder()
        fun flush() {
            val index = current ?: return
            val value = buffer.toString().trim()
            if (value.isNotEmpty()) out[index] = value
            buffer.clear()
        }
        for (rawLine in reply.replace("\r\n", "\n").split("\n")) {
            val match = Regex("^\\s*\\**\\s*(\\d+)\\s*[.、)．]\\s*(.*)$").find(rawLine)
            if (match != null) {
                flush()
                current = match.groupValues[1].toIntOrNull()
                buffer.append(match.groupValues[2])
            } else if (current != null && rawLine.isNotBlank()) {
                if (buffer.isNotEmpty()) buffer.append('\n')
                buffer.append(rawLine.trim())
            }
        }
        flush()
        return out
    }

    private fun quoteSequence(text: String): String = buildString {
        for (c in text) {
            if (c in QUOTE_OPEN) append('o')
            else if (c in QUOTE_CLOSE) append('c')
        }
    }

    private fun normalize(text: String): String =
        text.replace(Regex("\\s+"), "").trim()

    private fun Char.isAsciiAlpha(): Boolean =
        (this in 'a'..'z') || (this in 'A'..'Z')
}
