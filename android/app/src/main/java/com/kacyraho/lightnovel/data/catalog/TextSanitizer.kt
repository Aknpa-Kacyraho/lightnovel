package com.kacyraho.lightnovel.data.catalog

object TextSanitizer {
    private val numericEntity = Regex("""&#(x?[0-9A-Fa-f]+);""")

    fun decode(value: String): String =
        value.replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", "\"")
            .replace("&#39;", "'")
            .let { text ->
                numericEntity.replace(text) { match ->
                    val raw = match.groupValues[1]
                    val code = if (raw.startsWith("x")) raw.drop(1).toIntOrNull(16)
                    else raw.toIntOrNull()
                    code?.takeIf(Character::isValidCodePoint)
                        ?.let { String(Character.toChars(it)) }
                        ?: match.value
                }
            }
}
