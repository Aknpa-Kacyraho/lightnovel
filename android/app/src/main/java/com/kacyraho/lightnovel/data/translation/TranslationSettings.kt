package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.settings.AppSettings
import com.kacyraho.lightnovel.core.settings.TranslationMode
import com.kacyraho.lightnovel.core.settings.TranslationProviders
import com.kacyraho.lightnovel.data.glossary.GlossaryEntry

fun AppSettings.toTranslationConfig(
    glossary: List<GlossaryEntry> = emptyList(),
    glossaryRevision: String = "",
): TranslationConfig {
    val calibrationKey = TranslationProviders.calibrationKey(deepSeekBaseUrl, deepSeekModel)
    val calibrated = translationCalibrationKey == calibrationKey
    val selected = TranslationMode.fromWire(translationMode)
    val mode = if (selected == TranslationMode.AUTO) TranslationMode.BATCH else selected
    return TranslationConfig(
        model = deepSeekModel,
        maxChars = if (calibrated) translationMaxChars else 3_000,
        maxTokens = if (calibrated) translationMaxTokens else 8_192,
        mode = mode,
        provider = TranslationProviders.providerName(deepSeekBaseUrl),
        glossary = glossary,
        glossaryRevision = glossaryRevision,
    )
}

fun AppSettings.translationKeyScope(): String =
    TranslationProviders.keyScope(deepSeekBaseUrl)

fun AppSettings.translationRequiresKey(): Boolean =
    TranslationProviders.requiresKey(deepSeekBaseUrl)
