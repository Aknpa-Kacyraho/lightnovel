package com.kacyraho.lightnovel.data.source

import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request

class KakuyomuSource(
    private val http: OkHttpClient = defaultClient(),
) : WebSource {
    override val id: String = "kakuyomu"
    override val label: String = "Kakuyomu"

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    override suspend fun search(query: String, page: Int): List<SourceBook> {
        val q = URLEncoder.encode(query, "UTF-8").replace("+", "%20")
        val url = if (page <= 0) {
            "https://kakuyomu.jp/search?q=$q"
        } else {
            "https://kakuyomu.jp/search?q=$q&page=${page + 1}"
        }
        return worksFromPage(fetch(url))
    }

    override suspend fun recommend(): List<SourceBook> {
        val weekly = runCatching {
            worksFromPage(fetch("https://kakuyomu.jp/rankings/all/weekly"))
        }.getOrDefault(emptyList())
        if (weekly.isNotEmpty()) return weekly
        return runCatching {
            worksFromPage(fetch("https://kakuyomu.jp/rankings/all/monthly"))
        }.getOrDefault(emptyList())
    }

    override suspend fun detail(bookId: String): SourceDetail {
        val html = fetch("https://kakuyomu.jp/works/$bookId")
        val apollo = apolloFrom(html)
        val work = apollo["Work:$bookId"]?.jsonObject
            ?: error("Kakuyomu 作品不存在或页面结构变化")
        val book = workToBook(bookId, work, apollo)
        val chapters = mutableListOf<SourceChapterRef>()
        val seen = linkedSetOf<String>()

        fun add(id: String, title: String) {
            if (id.isBlank() || !seen.add(id)) return
            chapters += SourceChapterRef(id, title.ifBlank { "第 ${chapters.size + 1} 话" })
        }

        val toc = work["tableOfContentsV2"]?.asArray()
            ?: work["tableOfContents"]?.asArray()
        toc?.forEach { chapterRef ->
            val chapter = apollo[refId(chapterRef)]?.jsonObject ?: return@forEach
            chapter["episodeUnions"]?.asArray()?.forEach { episodeRef ->
                val episode = apollo[refId(episodeRef)]?.jsonObject ?: return@forEach
                add(
                    refId(episodeRef).substringAfter(":"),
                    episode["title"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                )
            }
        }
        if (chapters.isEmpty()) {
            apollo.entries
                .filter { it.key.startsWith("Episode:") }
                .forEach { (key, value) ->
                    val episode = value.jsonObject
                    add(
                        key.substringAfter(":"),
                        episode["title"]?.jsonPrimitive?.contentOrNull.orEmpty(),
                    )
                }
        }
        if (chapters.isEmpty()) {
            Regex("""/works/\d+/episodes/(\d+)""")
                .findAll(html)
                .forEach { add(it.groupValues[1], "") }
        }
        return SourceDetail(
            book = book.copy(episodes = chapters.size),
            chapters = chapters,
            synopsis = work["introduction"]?.jsonPrimitive?.contentOrNull.orEmpty(),
        )
    }

    override suspend fun chapter(bookId: String, chapterId: String): String {
        val html = fetch("https://kakuyomu.jp/works/$bookId/episodes/$chapterId")
        val apollo = runCatching { apolloFrom(html) }.getOrDefault(emptyMap())
        val episode = apollo["Episode:$chapterId"]?.jsonObject
        val body = episode?.get("body")
        when (body) {
            is kotlinx.serialization.json.JsonPrimitive ->
                body.contentOrNull?.takeIf { it.isNotBlank() }?.let { return it }
            is JsonArray -> {
                val text = body.mapNotNull {
                    (it as? kotlinx.serialization.json.JsonPrimitive)?.contentOrNull
                }.joinToString("\n")
                if (text.isNotBlank()) return text
            }
            else -> Unit
        }
        val inner = divInner(html, "widget-episodeBody")
            ?: error("Kakuyomu 页面里没有正文")
        val lines = Regex("""<p[^>]*>(.*?)</p>""", RegexOption.DOT_MATCHES_ALL)
            .findAll(inner)
            .map { stripHtml(it.groupValues[1]) }
            .filter { it.isNotBlank() }
            .toList()
        if (lines.isEmpty()) error("Kakuyomu 正文为空")
        return lines.joinToString("\n")
    }

    private fun worksFromPage(html: String): List<SourceBook> {
        val apollo = runCatching { apolloFrom(html) }.getOrDefault(emptyMap())
        return apollo.entries
            .filter { it.key.startsWith("Work:") }
            .mapNotNull { (key, value) ->
                runCatching {
                    val work = value.jsonObject
                    if (work["title"]?.jsonPrimitive?.contentOrNull.isNullOrBlank()) return@runCatching null
                    workToBook(key.substringAfter(":"), work, apollo)
                }.getOrNull()
            }
    }

    private fun workToBook(id: String, work: JsonObject, apollo: Map<String, JsonElement>): SourceBook {
        val author = work["author"]?.let { ref ->
            apollo[refId(ref)]?.jsonObject?.let {
                it["activityName"]?.jsonPrimitive?.contentOrNull
                    ?: it["name"]?.jsonPrimitive?.contentOrNull
            }
        }
        val tags = work["tagLabels"]?.asArray()
            ?.mapNotNull { it.jsonPrimitive.contentOrNull }
            ?.filter { it.isNotBlank() }
            .orEmpty()
        return SourceBook(
            provider = "kakuyomu",
            id = id,
            title = work["title"]?.jsonPrimitive?.contentOrNull.orEmpty(),
            author = author.orEmpty(),
            tags = tags,
            episodes = work["publicEpisodeCount"]?.jsonPrimitive?.contentOrNull?.toIntOrNull() ?: 0,
            url = "https://kakuyomu.jp/works/$id",
            synopsis = work["introduction"]?.jsonPrimitive?.contentOrNull.orEmpty(),
            updatedAt = work["lastEpisodePublishedAt"]?.jsonPrimitive?.contentOrNull.orEmpty().take(10),
            status = work["serialStatus"]?.jsonPrimitive?.contentOrNull?.lowercase(),
            characters = work["totalCharacterCount"]?.jsonPrimitive?.contentOrNull?.toIntOrNull(),
            genre = work["genre"]?.jsonPrimitive?.contentOrNull,
        )
    }

    private fun apolloFrom(html: String): Map<String, JsonElement> {
        val match = Regex(
            """<script id="__NEXT_DATA__" type="application/json">(.*?)</script>""",
            RegexOption.DOT_MATCHES_ALL,
        ).find(html) ?: error("Kakuyomu 页面没有 __NEXT_DATA__")
        val root = json.parseToJsonElement(match.groupValues[1]).jsonObject
        val pageProps = root["props"]?.jsonObject?.get("pageProps")?.jsonObject
            ?: error("Kakuyomu 页面缺少 pageProps")
        return pageProps["__APOLLO_STATE__"]?.jsonObject.orEmpty()
    }

    private suspend fun fetch(url: String): String = runBlockingIo {
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", UA)
            .header("Accept-Language", "ja,en-US;q=0.9,en;q=0.8")
            .header("Referer", "https://kakuyomu.jp/")
            .get()
            .build()
        http.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) throw IOException("Kakuyomu HTTP ${response.code}")
            body
        }
    }

    private suspend fun <T> runBlockingIo(block: () -> T): T =
        withContext(Dispatchers.IO) { block() }

    private fun JsonElement.asArray(): JsonArray? = this as? JsonArray

    private fun refId(value: JsonElement): String =
        (value as? JsonObject)?.get("__ref")?.jsonPrimitive?.contentOrNull.orEmpty()

    private fun stripHtml(value: String): String =
        Regex("""<rp[^>]*>.*?</rp>|<rt[^>]*>.*?</rt>""", RegexOption.DOT_MATCHES_ALL)
            .replace(value, "")
            .let { Regex("""<[^>]+>""").replace(it, "") }
            .replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", "\"")
            .trim()

    private fun divInner(html: String, marker: String): String? {
        val start = html.indexOf(marker)
        if (start < 0) return null
        val gt = html.indexOf('>', start)
        if (gt < 0) return null
        var depth = 1
        var index = gt + 1
        while (depth > 0) {
            val open = html.indexOf("<div", index)
            val close = html.indexOf("</div", index)
            if (close < 0) return null
            if (open in 0 until close) {
                depth++
                index = open + 4
            } else {
                depth--
                if (depth == 0) return html.substring(gt + 1, close)
                index = close + 5
            }
        }
        return null
    }

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
