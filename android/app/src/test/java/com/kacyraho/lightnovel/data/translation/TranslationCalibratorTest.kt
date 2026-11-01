package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.settings.TranslationMode
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TranslationCalibratorTest {
    @Test
    fun picksLargestSafeBatchBlock() = runTest {
        val fake = FakeClient(batchLimit = 5_000)
        val outcome = TranslationCalibrator().calibrate(
            client = fake,
            model = "test-model",
            maxTokens = 8_192,
            preferredMode = TranslationMode.AUTO,
            isLocal = false,
        )

        val result = (outcome as CalibrationOutcome.Success).result
        assertEquals(TranslationMode.BATCH, result.mode)
        assertEquals(4_500, result.testedChars)
        assertEquals(4_050, result.maxChars)
        assertTrue(fake.calls >= 2)
    }

    @Test
    fun fallsBackToSakuraWhenNumberedProtocolFails() = runTest {
        val fake = FakeClient(batchWorks = false, sakuraLimit = 2_500)
        val outcome = TranslationCalibrator().calibrate(
            client = fake,
            model = "sakura-model",
            maxTokens = 8_192,
            preferredMode = TranslationMode.AUTO,
            isLocal = true,
        )

        val result = (outcome as CalibrationOutcome.Success).result
        assertEquals(TranslationMode.SAKURA, result.mode)
        assertEquals(2_400, result.testedChars)
        assertEquals(2_160, result.maxChars)
    }

    @Test
    fun stopsOnAuthenticationFailure() = runTest {
        val outcome = TranslationCalibrator().calibrate(
            client = FakeClient(authFailure = true),
            model = "test-model",
            maxTokens = 8_192,
            preferredMode = TranslationMode.AUTO,
        )

        assertTrue(outcome is CalibrationOutcome.Failure)
        assertTrue((outcome as CalibrationOutcome.Failure).message.contains("401"))
    }

    @Test
    fun probeDetectsBatchWithoutFullCalibration() = runTest {
        val fake = FakeClient()
        val outcome = TranslationCalibrator().probe(
            client = fake,
            model = "test-model",
            maxTokens = 8_192,
            preferredMode = TranslationMode.AUTO,
        )

        val result = (outcome as CalibrationOutcome.Success).result
        assertEquals(TranslationMode.BATCH, result.mode)
        assertEquals(1, fake.calls)
    }

    private class FakeClient(
        private val batchLimit: Int = Int.MAX_VALUE,
        private val sakuraLimit: Int = Int.MAX_VALUE,
        private val batchWorks: Boolean = true,
        private val sakuraWorks: Boolean = true,
        private val authFailure: Boolean = false,
    ) : TranslationClient {
        var calls = 0

        override suspend fun complete(
            messages: List<ChatMessage>,
            model: String,
            maxTokens: Int,
            temperature: Double,
        ): ChatResult {
            calls++
            if (authFailure) {
                throw TranslationException(401, "HTTP 401 unauthorized", false)
            }
            val user = messages.lastOrNull()?.content.orEmpty()
            if (user.startsWith(TranslationPrompts.SAKURA_USER_PREFIX)) {
                val block = user.removePrefix(TranslationPrompts.SAKURA_USER_PREFIX)
                val text = if (sakuraWorks && block.length <= sakuraLimit) {
                    sakuraTranslation(block)
                } else {
                    "没有译完。"
                }
                return ChatResult(text, 10, 20, model, "stop")
            }

            val body = user.substringAfter("【待翻译段落】", "")
            val paragraphs = body.lineSequence().mapNotNull { line ->
                val match = Regex("^\\s*(\\d+)\\.\\s*(.*)$").find(line)
                match?.let { it.groupValues[1].toInt() to it.groupValues[2] }
            }.toList()
            val size = paragraphs.sumOf { it.second.length }
            val accepted = if (batchWorks && size <= batchLimit) {
                paragraphs
            } else {
                paragraphs.dropLast(1)
            }
            val reply = accepted.joinToString("\n") { (index, source) ->
                "$index. ${batchTranslation(source)}"
            }
            return ChatResult(reply, 10, 20, model, "stop")
        }

        private fun batchTranslation(source: String): String {
            val filler = "这是用于校准的中文译文，内容足够长。".repeat(5)
            return buildString {
                append(filler)
                for (c in source) {
                    if (c in "「『“‘」』”’") append(c)
                }
            }
        }

        private fun sakuraTranslation(source: String): String {
            val filler = "这是用于校准的中文译文，内容足够长。"
                .repeat((source.length / 18).coerceAtLeast(2))
            return filler + source.filter { it in "「『“‘" }
        }
    }
}
