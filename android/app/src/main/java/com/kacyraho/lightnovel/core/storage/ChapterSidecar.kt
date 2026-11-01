package com.kacyraho.lightnovel.core.storage

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class ChapterTokens(
    val input: Int = 0,
    val output: Int = 0,
)

@Serializable
data class ChapterCost(
    val amount: Double = 0.0,
    val currency: String = "CNY",
    val estimated: Boolean = true,
)

@Serializable
data class ChapterSidecar(
    @SerialName("schema_version") val schemaVersion: Int = 1,
    val status: String,
    @SerialName("source_sha256") val sourceSha256: String,
    @SerialName("content_sha256") val contentSha256: String,
    @SerialName("translation_config_hash") val translationConfigHash: String,
    @SerialName("model_provider") val modelProvider: String,
    @SerialName("model_role") val modelRole: String = "translate",
    @SerialName("model_id") val modelId: String,
    @SerialName("prompt_version") val promptVersion: String,
    @SerialName("translated_at") val translatedAt: String,
    val tokens: ChapterTokens = ChapterTokens(),
    val cost: ChapterCost = ChapterCost(),
    @SerialName("incomplete_paragraphs") val incompleteParagraphs: List<Int> = emptyList(),
    @SerialName("incomplete_reason") val incompleteReason: String? = null,
    @SerialName("glossary_revision") val glossaryRevision: String? = null,
)

internal val SidecarJson = Json {
    ignoreUnknownKeys = false
    explicitNulls = false
    prettyPrint = true
}

