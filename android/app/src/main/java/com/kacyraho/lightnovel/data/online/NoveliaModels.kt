package com.kacyraho.lightnovel.data.online

import kotlinx.serialization.Serializable

@Serializable
data class NoveliaPage<T>(
    val pageNumber: Int = 0,
    val items: List<T> = emptyList(),
)

@Serializable
data class NoveliaAuthor(
    val name: String = "",
)

@Serializable
data class NoveliaOutline(
    val providerId: String = "",
    val novelId: String = "",
    val titleJp: String = "",
    val titleZh: String? = null,
    val type: String = "",
    val attentions: List<String> = emptyList(),
    val keywords: List<String> = emptyList(),
    val total: Int = 0,
    val gpt: Int = 0,
    val sakura: Int = 0,
    val youdao: Int = 0,
    val updateAt: Long? = null,
) {
    val displayTitle: String
        get() = titleZh?.takeIf { it.isNotBlank() } ?: titleJp
}

@Serializable
data class NoveliaTocItem(
    val titleJp: String = "",
    val titleZh: String? = null,
    val chapterId: String? = null,
) {
    val displayTitle: String
        get() = titleZh?.takeIf { it.isNotBlank() } ?: titleJp
}

@Serializable
data class NoveliaDetail(
    val titleJp: String = "",
    val titleZh: String? = null,
    val authors: List<NoveliaAuthor> = emptyList(),
    val type: String = "",
    val attentions: List<String> = emptyList(),
    val keywords: List<String> = emptyList(),
    val points: Long? = null,
    val totalCharacters: Long? = null,
    val introductionJp: String = "",
    val introductionZh: String? = null,
    val toc: List<NoveliaTocItem> = emptyList(),
    val updateAt: Long? = null,
) {
    val displayTitle: String
        get() = titleZh?.takeIf { it.isNotBlank() } ?: titleJp

    val authorNames: String
        get() = authors.joinToString("、") { it.name }.ifBlank { "未知" }
}

@Serializable
data class NoveliaChapter(
    val titleJp: String = "",
    val titleZh: String? = null,
    val paragraphs: List<String> = emptyList(),
    val youdaoParagraphs: List<String>? = null,
    val gptParagraphs: List<String>? = null,
    val sakuraParagraphs: List<String>? = null,
) {
    fun bestTranslation(): List<String>? =
        sakuraParagraphs?.takeIf { it.any(String::isNotBlank) }
            ?: gptParagraphs?.takeIf { it.any(String::isNotBlank) }
            ?: youdaoParagraphs?.takeIf { it.any(String::isNotBlank) }

    fun translationModel(): String = when {
        sakuraParagraphs?.any(String::isNotBlank) == true -> "sakura"
        gptParagraphs?.any(String::isNotBlank) == true -> "gpt"
        youdaoParagraphs?.any(String::isNotBlank) == true -> "youdao"
        else -> "none"
    }
}
