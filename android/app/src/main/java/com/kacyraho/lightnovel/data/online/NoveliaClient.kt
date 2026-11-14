package com.kacyraho.lightnovel.data.online

import com.kacyraho.lightnovel.core.settings.TranslationProviders
import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request

class NoveliaClient(
    initialBaseUrl: String = "https://n.novelia.cc/api/",
    http: OkHttpClient = defaultClient(),
) {
    @Volatile
    var baseUrl: String = requireSafeBaseUrl(initialBaseUrl)
        private set

    fun setBaseUrl(value: String) {
        baseUrl = requireSafeBaseUrl(value)
    }

    private val http = http.newBuilder()
        .followRedirects(false)
        .followSslRedirects(false)
        .build()

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        explicitNulls = false
    }

    suspend fun search(
        query: String,
        page: Int = 0,
        provider: String = "",
    ): NoveliaPage<NoveliaOutline> = get(
        path = "novel",
        params = mapOf(
            "page" to page.toString(),
            "pageSize" to "20",
            "query" to query,
            "provider" to provider,
            "type" to "0",
            "level" to "1",
            "translate" to "0",
            "sort" to if (query.isBlank()) "0" else "1",
        ),
    )

    suspend fun detail(provider: String, novelId: String): NoveliaDetail =
        get("novel/${segment(provider)}/${segment(novelId)}")

    suspend fun chapter(
        provider: String,
        novelId: String,
        chapterId: String,
    ): NoveliaChapter = get(
        "novel/${segment(provider)}/${segment(novelId)}/chapter/${segment(chapterId)}",
    )

    private suspend inline fun <reified T> get(
        path: String,
        params: Map<String, String> = emptyMap(),
    ): T {
        val body = getText(path, params)
        return json.decodeFromString<T>(body)
    }

    private suspend fun getText(
        path: String,
        params: Map<String, String> = emptyMap(),
    ): String = withContext(Dispatchers.IO) {
        val url = (baseUrl + path.trimStart('/')).toHttpUrl().newBuilder().apply {
            params.forEach { (key, value) -> addQueryParameter(key, value) }
        }.build()
        val builder = Request.Builder()
            .url(url)
            .header("Accept", "application/json")
            .header("Referer", "https://n.novelia.cc/")
            .header(
                "User-Agent",
                "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36",
            )
        builder.get()
        http.newCall(builder.build()).execute().use { response ->
            val text = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw IOException("Novelia HTTP ${response.code}: ${text.take(300)}")
            }
            text
        }
    }

    private fun segment(value: String): String =
        URLEncoder.encode(value, "UTF-8").replace("+", "%20")

    private fun requireSafeBaseUrl(value: String): String {
        val normalized = value.trim().trimEnd('/') + "/"
        val url = runCatching { normalized.toHttpUrl() }.getOrNull()
            ?: throw IllegalArgumentException("Novelia 地址不是有效 URL")
        require(url.username.isEmpty() && url.password.isEmpty()) {
            "Novelia 地址不能包含用户名或密码"
        }
        require(
            url.scheme == "https" ||
                (url.scheme == "http" && TranslationProviders.isLoopback(normalized)),
        ) {
            "Novelia 远端地址必须使用 HTTPS；明文 HTTP 仅允许本机调试"
        }
        return normalized
    }

    companion object {
        private fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .build()
    }
}
