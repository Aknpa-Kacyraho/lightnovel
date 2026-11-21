package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.storage.ChapterCost
import com.kacyraho.lightnovel.core.storage.ChapterSidecar
import com.kacyraho.lightnovel.core.storage.ChapterTokens
import org.junit.Assert.assertEquals
import org.junit.Test

class ParagraphRetranslationSidecarTest {
    @Test
    fun keepsOriginalConfigAndGlossaryVersions() {
        val old = ChapterSidecar(
            status = "complete",
            sourceSha256 = "source",
            contentSha256 = "old-content",
            translationConfigHash = "old-config",
            modelProvider = "deepseek",
            modelId = "old-model",
            promptVersion = "old-prompt",
            translatedAt = "2026-01-01T00:00:00Z",
            glossaryRevision = "old-glossary",
            storyRevision = "old-story",
            glossaryHash = "old-hash",
        )

        val result = retranslatedParagraphSidecar(
            old = old,
            newText = "你好。",
            tokens = ChapterTokens(1, 2),
            cost = ChapterCost(0.1, "CNY", estimated = true),
            incomplete = emptyList(),
        )

        assertEquals("old-config", result.translationConfigHash)
        assertEquals("old-model", result.modelId)
        assertEquals("old-prompt", result.promptVersion)
        assertEquals("old-glossary", result.glossaryRevision)
        assertEquals("old-story", result.storyRevision)
        assertEquals("old-hash", result.glossaryHash)
        assertEquals("complete", result.status)
        assertEquals(Hashes.sha256("你好。"), result.contentSha256)
        assertEquals(1, result.tokens.input)
        assertEquals(2, result.tokens.output)
    }

    @Test
    fun keepsPartialStatusAndReasonWhenParagraphsRemain() {
        val old = ChapterSidecar(
            status = "partial",
            sourceSha256 = "source",
            contentSha256 = "old-content",
            translationConfigHash = "old-config",
            modelProvider = "deepseek",
            modelId = "old-model",
            promptVersion = "old-prompt",
            translatedAt = "2026-01-01T00:00:00Z",
            incompleteParagraphs = listOf(1),
            incompleteReason = "provider_incomplete",
        )

        val result = retranslatedParagraphSidecar(
            old = old,
            newText = "你好。",
            tokens = ChapterTokens(1, 1),
            cost = ChapterCost(0.1, "CNY", estimated = true),
            incomplete = listOf(1),
        )

        assertEquals("partial", result.status)
        assertEquals(listOf(1), result.incompleteParagraphs)
        assertEquals("provider_incomplete", result.incompleteReason)
    }
}
