package com.kacyraho.lightnovel.data.import

import java.nio.file.Path
import java.util.zip.ZipFile

data class ParsedChapter(
    val title: String,
    val text: String,
)

data class ParsedDocument(
    val title: String,
    val author: String?,
    val chapters: List<ParsedChapter>,
)

object LocalTextParser {
    private val chapterHeading = Regex(
        """^\s*(第[0-9零一二三四五六七八九十百千万两]+[章回节卷部篇].*|Chapter\s+\d+.*|序章.*|楔子.*|终章.*|尾声.*)\s*$""",
        RegexOption.IGNORE_CASE,
    )

    fun parseTxt(fileName: String, raw: String): ParsedDocument {
        val text = raw.removePrefix("\uFEFF")
            .replace("\r\n", "\n")
            .replace('\r', '\n')
            .trim()
        require(text.isNotBlank()) { "TXT 文件是空的" }
        val lines = text.lines()
        val starts = lines.indices.filter { index ->
            val line = lines[index].trim()
            chapterHeading.matches(line) &&
                line.length <= 40 &&
                !line.endsWith("。") &&
                !line.endsWith("！") &&
                !line.endsWith("？")
        }
        val chapters = if (starts.isEmpty()) {
            splitByLength(text)
        } else {
            buildList {
                val preface = lines.subList(0, starts.first()).joinToString("\n").trim()
                if (preface.isNotBlank()) add(ParsedChapter("前言", preface))
                starts.forEachIndexed { index, start ->
                    val end = starts.getOrNull(index + 1) ?: lines.size
                    val title = lines[start].trim()
                    val body = lines.subList(start + 1, end).joinToString("\n").trim()
                    if (body.isNotBlank()) add(ParsedChapter(title, body))
                }
            }
        }
        require(chapters.isNotEmpty()) { "TXT 里没有找到可阅读的正文" }
        return ParsedDocument(
            title = cleanName(fileName),
            author = null,
            chapters = chapters,
        )
    }

    fun parseEpub(fileName: String, path: Path): ParsedDocument {
        ZipFile(path.toFile()).use { zip ->
            val container = zip.readText("META-INF/container.xml").orEmpty()
            val opfPath = Regex("""full-path\s*=\s*["']([^"']+)["']""")
                .find(container)?.groupValues?.getOrNull(1)
                ?: zip.entries().asSequence()
                    .firstOrNull { it.name.endsWith(".opf", ignoreCase = true) }
                    ?.name
                ?: error("EPUB 缺少 content.opf")
            val opf = zip.readText(opfPath) ?: error("EPUB 无法读取 content.opf")
            val title = xmlTag(opf, "dc:title")
                ?.takeIf(String::isNotBlank)
                ?: cleanName(fileName)
            val author = xmlTag(opf, "dc:creator")?.takeIf(String::isNotBlank)
            val manifest = parseManifest(opf)
            val spine = Regex("""<itemref\b[^>]*\bidref\s*=\s*"([^"]+)"""")
                .findAll(opf)
                .mapNotNull { it.groupValues.getOrNull(1) }
                .toList()
            val opfDir = opfPath.substringBeforeLast('/', "")
            val entries = if (spine.isNotEmpty()) {
                spine.mapNotNull { id -> manifest[id] }
            } else {
                manifest.values.toList()
            }
            val chapters = entries.mapNotNull { href ->
                val entryPath = resolveZipPath(opfDir, href)
                val html = zip.readText(entryPath) ?: return@mapNotNull null
                val body = Regex(
                    """<body\b[^>]*>(.*?)</body>""",
                    setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL),
                ).find(html)?.groupValues?.getOrNull(1) ?: html
                val chapterTitle = Regex(
                    """<h[12]\b[^>]*>(.*?)</h[12]>""",
                    setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL),
                ).find(body)?.groupValues?.getOrNull(1)
                    ?.let(::stripHtml)
                    ?.takeIf(String::isNotBlank)
                    ?: entryPath.substringAfterLast('/').substringBeforeLast('.')
                val text = stripHtml(body)
                if (text.isBlank()) null else ParsedChapter(chapterTitle, text)
            }
            require(chapters.isNotEmpty()) { "EPUB 里没有找到可阅读的正文" }
            return ParsedDocument(
                title = decodeEntities(title).trim().ifBlank { cleanName(fileName) },
                author = author?.let(::decodeEntities)?.trim()?.takeIf(String::isNotBlank),
                chapters = chapters,
            )
        }
    }

    private fun splitByLength(text: String): List<ParsedChapter> {
        val paragraphs = text.split(Regex("\\n{2,}"))
            .map(String::trim)
            .filter(String::isNotBlank)
        val chunks = mutableListOf<String>()
        val current = StringBuilder()
        fun flush() {
            if (current.isNotEmpty()) {
                chunks += current.toString()
                current.clear()
            }
        }
        for (paragraph in paragraphs) {
            var remaining = paragraph
            while (remaining.length > 18_000) {
                flush()
                chunks += remaining.take(18_000)
                remaining = remaining.drop(18_000)
            }
            if (current.isNotEmpty() && current.length + remaining.length > 18_000) {
                flush()
            }
            if (current.isNotEmpty()) current.append("\n\n")
            current.append(remaining)
        }
        if (current.isNotEmpty()) chunks += current.toString()
        if (chunks.isEmpty()) chunks += text
        return chunks.mapIndexed { index, chunk ->
            ParsedChapter("第 ${index + 1} 部分", chunk)
        }
    }

    private fun parseManifest(opf: String): Map<String, String> {
        val result = linkedMapOf<String, String>()
        Regex("""<item\b[^>]*>""", RegexOption.IGNORE_CASE).findAll(opf).forEach { match ->
            val tag = match.value
            val id = attr(tag, "id") ?: return@forEach
            val href = attr(tag, "href") ?: return@forEach
            val type = attr(tag, "media-type").orEmpty()
            if (type.contains("xhtml", true) || type.contains("html", true) ||
                href.endsWith(".xhtml", true) || href.endsWith(".html", true)
            ) {
                result[id] = href
            }
        }
        return result
    }

    private fun attr(tag: String, name: String): String? =
        Regex("""\b${Regex.escape(name)}\s*=\s*["']([^"']*)["']""")
            .find(tag)?.groupValues?.getOrNull(1)

    private fun xmlTag(xml: String, tag: String): String? =
        Regex(
            """<$tag\b[^>]*>(.*?)</$tag>""",
            setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL),
        ).find(xml)?.groupValues?.getOrNull(1)

    private fun resolveZipPath(baseDir: String, href: String): String {
        val cleanHref = runCatching {
            java.net.URLDecoder.decode(href.substringBefore('#'), "UTF-8")
        }.getOrDefault(href.substringBefore('#'))
        val raw = if (baseDir.isBlank()) cleanHref else "$baseDir/$cleanHref"
        val parts = ArrayDeque<String>()
        raw.replace('\\', '/').split('/').forEach { part ->
            when (part) {
                "", "." -> Unit
                ".." -> if (parts.isNotEmpty()) parts.removeLast()
                else -> parts.addLast(part)
            }
        }
        return parts.joinToString("/")
    }

    private fun ZipFile.readText(name: String): String? =
        getEntry(name)?.let { entry ->
            getInputStream(entry).bufferedReader(Charsets.UTF_8).use { it.readText() }
        }

    private fun stripHtml(html: String): String {
        val withBreaks = html
            .replace(Regex("""<br\s*/?>""", RegexOption.IGNORE_CASE), "\n")
            .replace(Regex("""</p\s*>""", RegexOption.IGNORE_CASE), "\n\n")
            .replace(Regex("""</h[1-6]\s*>""", RegexOption.IGNORE_CASE), "\n\n")
            .replace(Regex("""</div\s*>""", RegexOption.IGNORE_CASE), "\n\n")
        return decodeEntities(withBreaks.replace(Regex("<[^>]+>"), ""))
            .replace("\r\n", "\n")
            .lines()
            .joinToString("\n") { it.trim() }
            .replace(Regex("\\n{3,}"), "\n\n")
            .trim()
    }

    private fun decodeEntities(value: String): String {
        var text = value
            .replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", "\"")
            .replace("&#39;", "'")
            .replace("&apos;", "'")
        text = Regex("""&#(x?)([0-9A-Fa-f]+);""").replace(text) { match ->
            val code = match.groupValues[2].toIntOrNull(if (match.groupValues[1].isEmpty()) 10 else 16)
            code?.takeIf { it in 0..0x10FFFF }?.let { String(Character.toChars(it)) } ?: match.value
        }
        return text
    }

    private fun cleanName(fileName: String): String =
        fileName.substringAfterLast('/').substringBeforeLast('.')
            .trim()
            .ifBlank { "本地书籍" }
}
