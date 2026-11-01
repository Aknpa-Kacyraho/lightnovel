package com.kacyraho.lightnovel.data.online

import java.io.IOException
import java.net.URLEncoder
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class NoveliaClient(
    initialBaseUrl: String = "https://n.novelia.cc/api/",
    private val http: OkHttpClient = defaultClient(),
) {
    @Volatile
    var baseUrl: String = initialBaseUrl
        private set

    fun setBaseUrl(value: String) {
        val normalized = value.trim().trimEnd('/') + "/"
        if (normalized.startsWith("https://") || normalized.startsWith("http://")) {
            baseUrl = normalized
        }
    }

    @Volatile
    private var token: String? = null

    fun setToken(value: String?) {
        token = value?.takeIf { it.isNotBlank() }
    }

    fun hasToken(): Boolean = token != null

    suspend fun login(authBaseUrl: String, username: String, password: String): String {
        val url = authBaseUrl.trimEnd('/') + "/login"
        val body = json.encodeToString(
            LoginBody(username = username, password = password),
        )
        val request = Request.Builder()
            .url(url)
            .header("Accept", "application/json")
            .header("Content-Type", "application/json")
            .post(body.toRequestBody("application/json".toMediaType()))
            .build()
        return withContext(Dispatchers.IO) {
            http.newCall(request).execute().use { response ->
                val text = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw IOException("登录失败（${response.code}）：${text.take(300)}")
                }
                text.trim().trim('"').also { if (it.isBlank()) error("登录返回空 token") }
            }
        }
    }

    suspend fun favored(): NoveliaFavoredList = get("user/favored")

    suspend fun favoredWeb(
        favoredId: String,
        page: Int = 0,
        pageSize: Int = 20,
    ): NoveliaPage<NoveliaOutline> = get(
        "user/favored-web/${segment(favoredId)}",
        mapOf(
            "page" to page.toString(),
            "pageSize" to pageSize.toString(),
            "provider" to "kakuyomu,syosetu,novelup,hameln,pixiv,alphapolis",
            "type" to "0",
            "level" to "0",
            "translate" to "0",
            "sort" to "update",
        ),
    )

    suspend fun readHistory(
        page: Int = 0,
        pageSize: Int = 30,
    ): NoveliaPage<NoveliaOutline> = get(
        "user/read-history",
        mapOf("page" to page.toString(), "pageSize" to pageSize.toString()),
    )

    suspend fun favoriteWeb(favoredId: String, provider: String, novelId: String) {
        request("PUT", "user/favored-web/${segment(favoredId)}/${segment(provider)}/${segment(novelId)}")
    }

    suspend fun unfavoriteWeb(provider: String, novelId: String) {
        request("DELETE", "user/favored-web/default/${segment(provider)}/${segment(novelId)}")
    }

    suspend fun recordHistory(provider: String, novelId: String, chapterId: String) {
        request(
            "PUT",
            "user/read-history/${segment(provider)}/${segment(novelId)}",
            body = json.encodeToString(chapterId),
        )
    }

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
        val body = request("GET", path, params)
        return json.decodeFromString<T>(body)
    }

    private suspend fun request(
        method: String,
        path: String,
        params: Map<String, String> = emptyMap(),
        body: String? = null,
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
        token?.let { builder.header("Authorization", "Bearer $it") }
        if (method == "GET" || method == "HEAD") {
            builder.method(method, null)
        } else {
            builder.method(
                method,
                (body ?: "").toRequestBody("application/json".toMediaType()),
            )
        }
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

    @Serializable
    private data class LoginBody(
        val username: String,
        val password: String,
        val app: String = "legado",
    )

    companion object {
        private fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .followRedirects(true)
            .build()
    }
}
