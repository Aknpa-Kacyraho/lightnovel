package com.kacyraho.lightnovel.feature.reader

enum class TranslationStatus {
    UNTRANSLATED,
    QUEUED,
    TRANSLATING,
    TRANSLATED,
    FAILED,
    STALE,
}

enum class StaleReason {
    SOURCE,
    GLOSSARY,
    MODEL_PROMPT,
    ORIGINAL_REFRESH,
}

enum class StaleBannerReason {
    GLOSSARY,
    MODEL_PROMPT,
    SOURCE,
    MERGED_SOURCE_GLOSSARY,
    MERGED_SOURCE_MODEL,
    MERGED_GLOSSARY_MODEL,
    MERGED_ALL,
    COLLAPSED,
    ORIGINAL_REFRESH,
}

fun staleBannerReason(reasons: Set<StaleReason>): StaleBannerReason? {
    if (reasons.isEmpty()) return null
    if (StaleReason.ORIGINAL_REFRESH in reasons) return StaleBannerReason.ORIGINAL_REFRESH
    val source = StaleReason.SOURCE in reasons
    val glossary = StaleReason.GLOSSARY in reasons
    val model = StaleReason.MODEL_PROMPT in reasons
    return when {
        source && glossary && model -> StaleBannerReason.MERGED_ALL
        source && glossary -> StaleBannerReason.MERGED_SOURCE_GLOSSARY
        source && model -> StaleBannerReason.MERGED_SOURCE_MODEL
        glossary && model -> StaleBannerReason.MERGED_GLOSSARY_MODEL
        source -> StaleBannerReason.SOURCE
        glossary -> StaleBannerReason.GLOSSARY
        else -> StaleBannerReason.MODEL_PROMPT
    }
}

data class ReaderParagraph(
    val id: Int,
    val source: String,
    val translated: String?,
)

data class GlossaryImpact(
    val chapters: Int,
    val characters: Int,
    val costCny: Double,
)

data class ReaderChapterInfo(
    val model: String,
    val translatedAt: String,
    val tokensIn: Int,
    val tokensOut: Int,
    val costCny: Double,
    val incompleteParagraphs: Int,
    val cacheKey: String,
    val oldVersionAvailable: Boolean = false,
    val oldTranslatedAt: String? = null,
    val changedParagraphs: Int = 0,
)
