package com.kacyraho.lightnovel.data.translation

import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

data class ChatMessage(
    val role: String,
    val content: String,
)

data class ChatResult(
    val content: String,
    val tokensIn: Int,
    val tokensOut: Int,
    val model: String,
    val finishReason: String?,
)

class TranslationException(
    val statusCode: Int,
    message: String,
    val retryable: Boolean,
) : IOException(message)

interface TranslationClient {
    suspend fun complete(
        messages: List<ChatMessage>,
        model: String,
        maxTokens: Int = 32_000,
        temperature: Double = 0.2,
    ): ChatResult
}

class DeepSeekClient(
    private val baseUrl: String,
    private val apiKey: String,
    private val http: OkHttpClient = defaultHttp(),
) : TranslationClient {
    private val json = Json { ignoreUnknownKeys = true }

    override suspend fun complete(
        messages: List<ChatMessage>,
        model: String,
        maxTokens: Int,
        temperature: Double,
    ): ChatResult = withContext(Dispatchers.IO) {
        val payload = ChatRequest(
            model = model,
            messages = messages.map { MessageDto(it.role, it.content) },
            maxTokens = maxTokens,
            temperature = temperature,
            stream = false,
        )
        val builder = Request.Builder()
            .url(endpoint())
            .header("Content-Type", "application/json")
        if (apiKey.isNotBlank()) {
            builder.header("Authorization", "Bearer $apiKey")
        }
        val request = builder
            .post(
                json.encodeToString(ChatRequest.serializer(), payload)
                    .toRequestBody("application/json; charset=utf-8".toMediaType()),
            )
            .build()

        http.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val retryable = response.code == 429 || response.code >= 500
                throw TranslationException(
                    statusCode = response.code,
                    message = "翻译 API HTTP ${response.code}: ${body.take(500)}",
                    retryable = retryable,
                )
            }
            val parsed = try {
                json.decodeFromString(ChatResponse.serializer(), body)
            } catch (e: Exception) {
                throw TranslationException(
                    statusCode = response.code,
                    message = "翻译 API 响应无法解析：${e.message}",
                    retryable = true,
                )
            }
            val choice = parsed.choices.firstOrNull()
                ?: throw TranslationException(response.code, "翻译 API 返回空 choices", true)
            val content = choice.message.content
            if (content.isBlank()) {
                throw TranslationException(response.code, "翻译 API 返回空正文", true)
            }
            ChatResult(
                content = content,
                tokensIn = parsed.usage?.promptTokens ?: 0,
                tokensOut = parsed.usage?.completionTokens ?: 0,
                model = parsed.model ?: model,
                finishReason = choice.finishReason,
            )
        }
    }

    private fun endpoint(): String {
        val base = baseUrl.trim().trimEnd('/')
        return when {
            base.endsWith("/chat/completions") -> base
            base.endsWith("/v1") -> "$base/chat/completions"
            else -> "$base/chat/completions"
        }
    }

    companion object {
        fun defaultHttp(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(300, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()
    }
}

@Serializable
private data class ChatRequest(
    val model: String,
    val messages: List<MessageDto>,
    @SerialName("max_tokens") val maxTokens: Int,
    val temperature: Double,
    val stream: Boolean = false,
)

@Serializable
private data class MessageDto(
    val role: String,
    val content: String,
)

@Serializable
private data class ChatResponse(
    val choices: List<ChoiceDto> = emptyList(),
    val usage: UsageDto? = null,
    val model: String? = null,
)

@Serializable
private data class ChoiceDto(
    val message: MessageDto,
    @SerialName("finish_reason") val finishReason: String? = null,
)

@Serializable
private data class UsageDto(
    @SerialName("prompt_tokens") val promptTokens: Int = 0,
    @SerialName("completion_tokens") val completionTokens: Int = 0,
)
