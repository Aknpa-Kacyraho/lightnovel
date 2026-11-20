package com.kacyraho.lightnovel.feature.reader

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReaderBannerTest {
    private fun visible(
        status: TranslationStatus = TranslationStatus.UNTRANSLATED,
        hasTranslation: Boolean = false,
        running: Boolean = false,
        hasTask: Boolean = false,
        hasError: Boolean = false,
        hasMessage: Boolean = false,
        queueActive: Boolean = false,
        queuePaused: Boolean = false,
        queueError: Boolean = false,
    ) = shouldShowTranslationBanner(
        status = status,
        hasTranslation = hasTranslation,
        running = running,
        hasTask = hasTask,
        hasError = hasError,
        hasMessage = hasMessage,
        queueActive = queueActive,
        queuePaused = queuePaused,
        queueError = queueError,
    )

    @Test
    fun quietUntranslatedChapterShowsNothing() {
        assertFalse(visible())
    }

    @Test
    fun runningTranslationIsVisible() {
        assertTrue(visible(running = true))
        assertTrue(visible(hasTask = true))
    }

    @Test
    fun failureIsVisible() {
        assertTrue(visible(status = TranslationStatus.FAILED))
        assertTrue(visible(hasError = true))
    }

    @Test
    fun translationQueueIsVisible() {
        assertTrue(visible(queueActive = true))
        assertTrue(visible(queuePaused = true))
        assertTrue(visible(queueError = true))
    }

    @Test
    fun translatedChapterWithoutQueueShowsNothing() {
        assertFalse(
            visible(
                status = TranslationStatus.TRANSLATED,
                hasTranslation = true,
            ),
        )
    }

    @Test
    fun oneOffMessageIsVisible() {
        assertTrue(visible(hasMessage = true))
    }
}
