package com.kacyraho.lightnovel.core.settings

import java.net.URI

enum class TranslationMode(val wire: String) {
    AUTO("auto"),
    BATCH("batch"),
    SAKURA("sakura"),
    ;

    companion object {
        fun fromWire(value: String?): TranslationMode =
            entries.firstOrNull { it.wire == value?.trim()?.lowercase() } ?: AUTO
    }
}

data class TranslationProviderPreset(
    val id: String,
    val label: String,
    val baseUrl: String,
    val defaultModel: String,
    val hint: String,
    val local: Boolean = false,
)

object TranslationProviders {
    val presets: List<TranslationProviderPreset> = listOf(
        TranslationProviderPreset(
            id = "deepseek",
            label = "DeepSeek",
            baseUrl = "https://api.deepseek.com/chat/completions",
            defaultModel = "deepseek-flash",
            hint = "官方端点；也可填 deepseek-chat / deepseek-reasoner。",
        ),
        TranslationProviderPreset(
            id = "openai",
            label = "OpenAI",
            baseUrl = "https://api.openai.com/v1/chat/completions",
            defaultModel = "gpt-4o-mini",
            hint = "官方 OpenAI；模型名可按账号可用范围修改。",
        ),
        TranslationProviderPreset(
            id = "openrouter",
            label = "OpenRouter",
            baseUrl = "https://openrouter.ai/api/v1/chat/completions",
            defaultModel = "openai/gpt-4o-mini",
            hint = "聚合平台；模型名要带供应商前缀，如 google/gemini-2.0-flash-001。",
        ),
        TranslationProviderPreset(
            id = "siliconflow",
            label = "硅基流动",
            baseUrl = "https://api.siliconflow.cn/v1/chat/completions",
            defaultModel = "Qwen/Qwen2.5-7B-Instruct",
            hint = "国内 OpenAI 兼容端点；模型名以控制台为准。",
        ),
        TranslationProviderPreset(
            id = "moonshot",
            label = "Moonshot",
            baseUrl = "https://api.moonshot.cn/v1/chat/completions",
            defaultModel = "moonshot-v1-8k",
            hint = "Kimi 的 OpenAI 兼容端点。",
        ),
        TranslationProviderPreset(
            id = "gemini",
            label = "Gemini 兼容",
            baseUrl = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            defaultModel = "gemini-2.0-flash",
            hint = "Google 的 OpenAI 兼容入口；需要 Google AI Studio 的 Key。",
        ),
        TranslationProviderPreset(
            id = "ollama",
            label = "Ollama",
            baseUrl = "http://127.0.0.1:11434/v1/chat/completions",
            defaultModel = "qwen2.5:7b",
            hint = "手机本机跑 Ollama 时用；通常不需要 Key。",
            local = true,
        ),
        TranslationProviderPreset(
            id = "lmstudio",
            label = "LM Studio",
            baseUrl = "http://127.0.0.1:1234/v1/chat/completions",
            defaultModel = "local-model",
            hint = "手机本机跑 LM Studio 时用；通常不需要 Key。",
            local = true,
        ),
        TranslationProviderPreset(
            id = "custom",
            label = "自定义",
            baseUrl = "",
            defaultModel = "",
            hint = "任何 OpenAI 兼容的 Chat Completions 端点，包括 one-api 网关。",
        ),
    )

    fun preset(id: String): TranslationProviderPreset =
        presets.firstOrNull { it.id == id } ?: presets.last()

    fun detectId(baseUrl: String): String {
        val normalized = normalizeBaseUrl(baseUrl)
        val uri = runCatching { URI(normalized) }.getOrNull()
        val host = uri?.host?.lowercase() ?: hostOf(normalized)
        val port = uri?.port ?: -1
        return when {
            host.contains("deepseek") -> "deepseek"
            host == "api.openai.com" -> "openai"
            host.contains("openrouter") -> "openrouter"
            host.contains("siliconflow") -> "siliconflow"
            host.contains("moonshot") -> "moonshot"
            host.contains("generativelanguage.googleapis.com") -> "gemini"
            host in LOCAL_HOSTS && port == 11434 -> "ollama"
            host in LOCAL_HOSTS && port == 1234 -> "lmstudio"
            else -> "custom"
        }
    }

    fun normalizeBaseUrl(raw: String): String {
        var value = raw.trim()
        if (value.isEmpty()) return ""
        if (!value.contains("://")) {
            val host = value.substringBefore('/').substringBefore(':').lowercase()
            value = if (host in LOCAL_HOSTS || host.startsWith("127.")) {
                "http://$value"
            } else {
                "https://$value"
            }
        }
        return value.trimEnd('/')
    }

    fun hostOf(baseUrl: String): String {
        val normalized = normalizeBaseUrl(baseUrl)
        if (normalized.isEmpty()) return ""
        val host = runCatching { URI(normalized).host }
            .getOrNull()
            ?.lowercase()
            .orEmpty()
        if (host.isNotEmpty()) return host
        return Regex("^[a-zA-Z][a-zA-Z0-9+.-]*://([^/]+)")
            .find(normalized)
            ?.groupValues
            ?.getOrNull(1)
            ?.substringBefore(':')
            ?.lowercase()
            .orEmpty()
    }

    fun keyScope(baseUrl: String): String {
        val normalized = normalizeBaseUrl(baseUrl)
        if (normalized.isEmpty()) return "default"
        val uri = runCatching { URI(normalized) }.getOrNull()
        val host = uri?.host?.lowercase() ?: hostOf(normalized)
        if (host.isBlank()) return "default"
        val port = uri?.port ?: -1
        return if (port > 0) "$host:$port" else host
    }

    fun isLocal(baseUrl: String): Boolean {
        val host = hostOf(baseUrl)
        return host in LOCAL_HOSTS || host.startsWith("127.")
    }

    fun requiresKey(baseUrl: String): Boolean = !isLocal(baseUrl)

    fun providerName(baseUrl: String): String {
        val host = hostOf(baseUrl)
        return when {
            host.contains("deepseek") -> "deepseek"
            isLocal(baseUrl) -> "local"
            host == "api.openai.com" -> "openai"
            else -> "openai-compatible"
        }
    }

    fun calibrationKey(baseUrl: String, model: String): String =
        "${normalizeBaseUrl(baseUrl)}|${model.trim()}"

    private val LOCAL_HOSTS = setOf(
        "127.0.0.1",
        "localhost",
        "::1",
        "[::1]",
        "0.0.0.0",
        "10.0.2.2",
    )
}
