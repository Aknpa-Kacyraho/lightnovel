package com.kacyraho.lightnovel.core.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TranslationProvidersTest {
    @Test
    fun normalizesBaseUrlAndDetectsProviders() {
        assertEquals(
            "https://api.openai.com/v1/chat/completions",
            TranslationProviders.normalizeBaseUrl(" https://api.openai.com/v1/chat/completions/ "),
        )
        assertEquals(
            "https://example.com/v1",
            TranslationProviders.normalizeBaseUrl("example.com/v1"),
        )
        assertEquals("deepseek", TranslationProviders.detectId("https://api.deepseek.com/chat/completions"))
        assertEquals("openai", TranslationProviders.detectId("https://api.openai.com/v1/chat/completions"))
        assertEquals("ollama", TranslationProviders.detectId("http://127.0.0.1:11434/v1/chat/completions"))
        assertEquals("custom", TranslationProviders.detectId("https://gateway.example.com/v1/chat/completions"))
    }

    @Test
    fun localEndpointsDoNotRequireKey() {
        assertTrue(TranslationProviders.isLocal("http://127.0.0.1:11434/v1"))
        assertTrue(TranslationProviders.isLocal("http://localhost:1234/v1"))
        assertFalse(TranslationProviders.requiresKey("http://127.0.0.1:11434/v1"))
        assertTrue(TranslationProviders.requiresKey("https://api.deepseek.com/chat/completions"))
        assertEquals("127.0.0.1:11434", TranslationProviders.keyScope("http://127.0.0.1:11434/v1"))
        assertEquals("api.deepseek.com", TranslationProviders.keyScope("https://api.deepseek.com/chat/completions"))
    }

    @Test
    fun calibrationKeyIsStableAcrossTrailingSlashes() {
        assertEquals(
            TranslationProviders.calibrationKey("https://api.deepseek.com/chat/completions/", "m"),
            TranslationProviders.calibrationKey("https://api.deepseek.com/chat/completions", "m"),
        )
    }

    @Test
    fun everyPresetHasAUniqueId() {
        assertEquals(
            TranslationProviders.presets.size,
            TranslationProviders.presets.map { it.id }.toSet().size,
        )
        assertTrue(TranslationProviders.presets.any { it.id == "deepseek" })
        assertTrue(TranslationProviders.presets.any { it.id == "custom" })
    }
}
