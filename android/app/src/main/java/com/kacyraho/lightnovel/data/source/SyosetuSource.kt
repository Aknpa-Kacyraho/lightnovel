package com.kacyraho.lightnovel.data.source

import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request

class SyosetuSource(
    private val http: OkHttpClient = defaultClient(),
) : WebSource {
    override val id: String = "syosetu"
    override val label: String = "成为小说家吧"

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    override suspend fun search(query: String, page: Int): List<SourceBook> {
        if (query.isBlank()) return emptyList()
        val api = runCatching {
            withTimeoutOrNull(4_000) { searchApi(query) }
        }.getOrNull()
        if (!api.isNullOrEmpty()) return api
        return searchHtml(query, page)
    }

    private suspend fun searchApi(query: String): List<SourceBook> {
        val encoded = URLEncoder.encode(query, "UTF-8").replace("+", "%20")
        val url = "https://api.syosetu.com/novelapi/api/?out=json&lim=20&word=$encoded" +
            "&of=t-n-w-s-k-g-l-e-nu-ga-ka-nt-gf-gl"
        val root = json.parseToJsonElement(fetch(url, api = true))
        val rows = root as? JsonArray ?: return emptyList()
        return rows.drop(1).mapNotNull { row ->
            (row as? JsonObject)?.toBook()
        }
    }

    private suspend fun searchHtml(query: String, page: Int): List<SourceBook> {
        val encoded = URLEncoder.encode(query, "UTF-8").replace("+", "%20")
        val url = "https://yomou.syosetu.com/search.php?word=$encoded&p=${page + 1}"
        val html = fetch(url, api = false)
        return Regex(
            """<div class="searchkekka_box">(.*?)<!--searchkekka_box-->""",
            setOf(RegexOption.DOT_MATCHES_ALL, RegexOption.IGNORE_CASE),
        ).findAll(html).mapNotNull { match -> parseSearchBlock(match.groupValues[1]) }.toList()
    }

    private fun parseSearchBlock(block: String): SourceBook? {
        val titleMatch = Regex(
            """<div class="novel_h">.*?<a[^>]*href="https://ncode\.syosetu\.com/([^/"]+)/"[^>]*>(.*?)</a>""",
            setOf(RegexOption.DOT_MATCHES_ALL, RegexOption.IGNORE_CASE),
        ).find(block) ?: return null
        val ncode = titleMatch.groupValues[1]
        val title = stripHtml(titleMatch.groupValues[2])
        if (title.isBlank()) return null
        val author = Regex("""作者：<a[^>]*>(.*?)</a>""", RegexOption.DOT_MATCHES_ALL)
            .find(block)?.groupValues?.getOrNull(1)?.let(::stripHtml).orEmpty()
        val synopsis = Regex("""<div class="ex">(.*?)</div>""", RegexOption.DOT_MATCHES_ALL)
            .find(block)?.groupValues?.getOrNull(1)?.let(::stripHtml).orEmpty()
        val episodes = Regex("""(\d+)エピソード""")
            .find(block)?.groupValues?.getOrNull(1)?.toIntOrNull()
            ?: if (block.contains("短編")) 1 else 0
        val tags = Regex(
            """search\.php\?word=[^"]*"[^>]*>(.*?)</a>""",
            setOf(RegexOption.DOT_MATCHES_ALL, RegexOption.IGNORE_CASE),
        ).findAll(block).mapNotNull { stripHtml(it.groupValues[1]).takeIf(String::isNotBlank) }
            .distinct().toList()
        val updated = Regex("""(\d{4})/(\d{2})/(\d{2})""").find(block)?.let {
            "${it.groupValues[1]}-${it.groupValues[2]}-${it.groupValues[3]}"
        }.orEmpty()
        val status = when {
            block.contains("完結済") -> "completed"
            block.contains("連載中") -> "running"
            block.contains("短編") -> "short"
            else -> null
        }
        val characters = Regex("""([0-9,]+)文字""").find(block)
            ?.groupValues?.getOrNull(1)?.replace(",", "")?.toIntOrNull()
        return SourceBook(
            provider = id,
            id = ncode.uppercase(),
            title = title,
            author = author,
            tags = tags,
            episodes = episodes,
            url = "https://ncode.syosetu.com/${ncode.lowercase()}/",
            synopsis = synopsis,
            updatedAt = updated,
            status = status,
            characters = characters,
        )
    }

    override suspend fun recommend(): List<SourceBook> {
        val api = runCatching {
            withTimeoutOrNull(4_000) {
                val url = "https://api.syosetu.com/novelapi/api/?out=json&lim=20&order=weekly" +
                    "&of=t-n-w-s-k-g-l-e-nu-ga-ka-nt-gf-gl"
                val root = json.parseToJsonElement(fetch(url, api = true))
                val rows = root as? JsonArray ?: return@withTimeoutOrNull emptyList()
                rows.drop(1).mapNotNull { row -> (row as? JsonObject)?.toBook() }
            }
        }.getOrNull()
        if (!api.isNullOrEmpty()) return api
        return recommendHtml()
    }

    private suspend fun recommendHtml(): List<SourceBook> {
        val html = fetch("https://yomou.syosetu.com/rank/list/type/weekly_total/", api = false)
        return html.split("<!-- /.c-card -->")
            .mapNotNull { block -> parseRankBlock(block) }
            .take(20)
    }

    private fun parseRankBlock(block: String): SourceBook? {
        val titleMatch = Regex(
            """<div class="p-ranklist-item__title"><a[^>]*href="https://ncode\.syosetu\.com/([^/"]+)/"[^>]*>(.*?)</a>""",
            setOf(RegexOption.DOT_MATCHES_ALL, RegexOption.IGNORE_CASE),
        ).find(block) ?: return null
        val ncode = titleMatch.groupValues[1]
        val title = stripHtml(titleMatch.groupValues[2])
        if (title.isBlank()) return null
        val author = Regex(
            """<div class="p-ranklist-item__author"><a[^>]*>(.*?)</a>""",
            RegexOption.DOT_MATCHES_ALL,
        ).find(block)?.groupValues?.getOrNull(1)?.let(::stripHtml).orEmpty()
        val synopsis = Regex(
            """<div class="p-ranklist-item__synopsis">(.*?)</div>""",
            RegexOption.DOT_MATCHES_ALL,
        ).find(block)?.groupValues?.getOrNull(1)?.let(::stripHtml).orEmpty()
        val episodes = Regex("""(\d+)エピソード""")
            .find(block)?.groupValues?.getOrNull(1)?.toIntOrNull()
            ?: if (block.contains("短編")) 1 else 0
        val tags = Regex(
            """search\.php\?word=[^"]*"[^>]*>(.*?)</a>""",
            setOf(RegexOption.DOT_MATCHES_ALL, RegexOption.IGNORE_CASE),
        ).findAll(block).mapNotNull { stripHtml(it.groupValues[1]).takeIf(String::isNotBlank) }
            .distinct().toList()
        val updated = Regex("""(\d{4})/(\d{2})/(\d{2})""").find(block)?.let {
            "${it.groupValues[1]}-${it.groupValues[2]}-${it.groupValues[3]}"
        }.orEmpty()
        val status = when {
            block.contains("完結済") -> "completed"
            block.contains("連載中") -> "running"
            block.contains("短編") -> "short"
            else -> null
        }
        val characters = Regex("""([0-9,]+)文字""").find(block)
            ?.groupValues?.getOrNull(1)?.replace(",", "")?.toIntOrNull()
        return SourceBook(
            provider = id,
            id = ncode.uppercase(),
            title = title,
            author = author,
            tags = tags,
            episodes = episodes,
            url = "https://ncode.syosetu.com/${ncode.lowercase()}/",
            synopsis = synopsis,
            updatedAt = updated,
            status = status,
            characters = characters,
        )
    }

    override suspend fun detail(bookId: String): SourceDetail {
        val base = "https://ncode.syosetu.com/${bookId.lowercase()}/"
        val first = fetch(base, api = false)
        val pages = Regex("""href="[^"]*[?&]p=(\d+)"""").findAll(first)
            .map { it.groupValues[1].toIntOrNull() ?: 1 }
            .maxOrNull() ?: 1
        val html = buildString {
            append(first)
            for (page in 2..minOf(pages, 200)) {
                append(fetch("$base?p=$page", api = false))
            }
        }
        val title = stripHtml(
            Regex("""<h1 class="p-novel__title[^"]*"[^>]*>(.*?)</h1>""", RegexOption.DOT_MATCHES_ALL)
                .find(html)?.groupValues?.get(1).orEmpty(),
        )
        val author = stripHtml(
            Regex("""<div class="p-novel__author"[^>]*>(.*?)</div>""", RegexOption.DOT_MATCHES_ALL)
                .find(html)?.groupValues?.get(1).orEmpty(),
        ).removePrefix("作者：").removePrefix("作者:")
        val chapters = linkedMapOf<String, SourceChapterRef>()
        Regex(
            """<a[^>]*href="/${Regex.escape(bookId.lowercase())}/(\d+)/"[^>]*>(.*?)</a>""",
            RegexOption.DOT_MATCHES_ALL,
        ).findAll(html).forEach { match ->
            val id = match.groupValues[1]
            chapters.putIfAbsent(
                id,
                SourceChapterRef(id, stripHtml(match.groupValues[2])),
            )
        }
        if (chapters.isEmpty() && html.contains("p-novel__body")) {
            chapters["1"] = SourceChapterRef("1", title)
        }
        val synopsis = Regex(
            """<div class="p-novel__summary"[^>]*>(.*?)</div>""",
            RegexOption.DOT_MATCHES_ALL,
        ).find(html)?.groupValues?.getOrNull(1)?.let(::stripHtml).orEmpty()
        val tags = Regex(
            """<a[^>]*href="/search\.php\?word=[^"]*"[^>]*>(.*?)</a>""",
            setOf(RegexOption.DOT_MATCHES_ALL, RegexOption.IGNORE_CASE),
        ).findAll(html).mapNotNull {
            stripHtml(it.groupValues[1]).takeIf(String::isNotBlank)
        }.distinct().toList()
        return SourceDetail(
            book = SourceBook(
                provider = id,
                id = bookId.uppercase(),
                title = title,
                author = author,
                tags = tags,
                episodes = chapters.size,
                url = base,
                synopsis = synopsis,
            ),
            chapters = chapters.values.toList(),
        )
    }

    override suspend fun chapter(bookId: String, chapterId: String): String {
        val base = "https://ncode.syosetu.com/${bookId.lowercase()}"
        val url = if (chapterId == "1") "$base/" else "$base/$chapterId/"
        val html = fetch(url, api = false)
        val start = html.indexOf("class=\"p-novel__body\"")
        if (start < 0) error("成为小说家吧页面里没有正文")
        val chunk = html.substring(start)
        val textBlocks = Regex(
            """<div class="([^"]*p-novel__text[^"]*)"[^>]*>(.*?)</div>""",
            RegexOption.DOT_MATCHES_ALL,
        ).findAll(chunk)
        val body = textBlocks.firstOrNull {
            !it.groupValues[1].contains("--preface") &&
                !it.groupValues[1].contains("--afterword")
        }?.groupValues?.get(2) ?: error("成为小说家吧正文结构变化")
        val lines = Regex("""<p[^>]*>(.*?)</p>""", RegexOption.DOT_MATCHES_ALL)
            .findAll(body)
            .map { stripHtml(it.groupValues[1]) }
            .toList()
        if (lines.isEmpty()) error("成为小说家吧正文为空")
        return lines.joinToString("\n")
    }

    private fun JsonObject.toBook(): SourceBook? {
        val ncode = this["ncode"]?.jsonPrimitive?.contentOrNull ?: return null
        return SourceBook(
            provider = id,
            id = ncode.uppercase(),
            title = this["title"]?.jsonPrimitive?.contentOrNull.orEmpty(),
            author = this["writer"]?.jsonPrimitive?.contentOrNull.orEmpty(),
            tags = (this["keyword"]?.jsonPrimitive?.contentOrNull.orEmpty())
                .split(Regex("\\s+"))
                .filter { it.isNotBlank() },
            episodes = this["general_all_no"]?.jsonPrimitive?.contentOrNull?.toIntOrNull() ?: 0,
            url = "https://ncode.syosetu.com/${ncode.lowercase()}/",
            synopsis = this["story"]?.jsonPrimitive?.contentOrNull.orEmpty(),
            updatedAt = (this["general_lastup"]?.jsonPrimitive?.contentOrNull.orEmpty()).take(10),
            status = when (this["end"]?.jsonPrimitive?.contentOrNull) {
                "1" -> "completed"
                "2" -> "short"
                "0" -> "running"
                else -> null
            },
            characters = this["length"]?.jsonPrimitive?.contentOrNull?.toIntOrNull(),
        )
    }

    private suspend fun fetch(url: String, api: Boolean): String = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", UA)
            .header(
                "Accept",
                if (api) "application/json,text/html,*/*;q=0.8"
                else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            )
            .header("Accept-Language", "ja,en-US;q=0.9,en;q=0.8")
            .header("Referer", "https://syosetu.com/")
            .get()
            .build()
        http.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw IOException("成为小说家吧 HTTP ${response.code}")
            }
            body
        }
    }

    private fun stripHtml(value: String): String =
        Regex("""<rp[^>]*>.*?</rp>|<rt[^>]*>.*?</rt>""", RegexOption.DOT_MATCHES_ALL)
            .replace(value, "")
            .let { Regex("""<[^>]+>""").replace(it, "") }
            .replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", "\"")
            .replace("&#39;", "'")
            .trim()

    private companion object {
        const val UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .build()
    }
}
