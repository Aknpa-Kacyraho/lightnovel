package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.settings.AppSettings
import com.kacyraho.lightnovel.core.settings.TranslationMode
import com.kacyraho.lightnovel.core.settings.TranslationProviders
import com.kacyraho.lightnovel.data.story.StoryMemory

fun AppSettings.toTranslationConfig(
    memory: StoryMemory? = null,
    previousChapterTail: String = "",
): TranslationConfig {
    val calibrationKey = TranslationProviders.calibrationKey(deepSeekBaseUrl, deepSeekModel)
    val calibrated = translationCalibrationKey == calibrationKey
    val selected = TranslationMode.fromWire(translationMode)
    val mode = if (selected == TranslationMode.AUTO) TranslationMode.BATCH else selected
    val revision = memory?.revision.orEmpty()
    return TranslationConfig(
        model = deepSeekModel,
        maxChars = if (calibrated) translationMaxChars else 3_000,
        maxTokens = if (calibrated) translationMaxTokens else 8_192,
        mode = mode,
        provider = TranslationProviders.providerName(deepSeekBaseUrl),
        glossary = memory?.glossary.orEmpty(),
        glossaryRevision = revision,
        workId = memory?.workId.orEmpty(),
        workTitle = memory?.title.orEmpty(),
        characters = memory?.characters.orEmpty(),
        summaries = memory?.summaries.orEmpty(),
        style = memory?.style ?: com.kacyraho.lightnovel.data.story.StoryStyle(),
        lessons = memory?.lessons.orEmpty(),
        storyRevision = revision,
        previousChapterTail = previousChapterTail,
    )
}

fun AppSettings.translationKeyScope(): String =
    TranslationProviders.keyScope(deepSeekBaseUrl)

fun AppSettings.translationRequiresKey(): Boolean =
    TranslationProviders.requiresKey(deepSeekBaseUrl)
