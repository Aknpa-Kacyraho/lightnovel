package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.storage.FileContentStore
import java.nio.file.Path
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ChapterTranslatorTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private fun store(): TranslationStore = FileTranslationStore(
        FileContentStore(tmp.newFolder("data").toPath()),
    )

    @Test
    fun translatesCompleteChapterAndReusesCache() = runTest {
        val fake = FakeClient("1. 「早上好」\n2. 这是测试。")
        val translator = ChapterTranslator(fake, store())
        val source = "「おはよう」\n\nこれはテストです。\n\n――――――"

        val first = translator.translate("b1", 1, source)
        assertTrue(first is TranslationOutcome.Complete)
        val complete = first as TranslationOutcome.Complete
        assertEquals("「早上好」\n\n这是测试。\n\n――――――", complete.text)
        assertEquals("complete", complete.sidecar.status)
        assertTrue(complete.sidecar.incompleteParagraphs.isEmpty())
        assertEquals(1, fake.calls)

        val second = translator.translate("b1", 1, source)
        assertTrue(second is TranslationOutcome.Complete)
        assertEquals(1, fake.calls)
    }

    @Test
    fun translatesSingleParagraph() = runTest {
        val fake = FakeClient("1. 早上好")
        val translator = ChapterTranslator(fake, store())

        val result = translator.translateOne("おはよう")

        assertEquals("早上好", result?.text)
        assertEquals(1, fake.calls)
    }

    @Test
    fun marksMissingParagraphAsPartial() = runTest {
        val fake = FakeClient("1. 「早上好」")
        val translator = ChapterTranslator(fake, store())
        val source = "「おはよう」\n\nこれはテストです。"

        val outcome = translator.translate("b1", 1, source)
        assertTrue(outcome is TranslationOutcome.Partial)
        val partial = outcome as TranslationOutcome.Partial
        assertEquals("partial", partial.sidecar.status)
        assertTrue(partial.sidecar.incompleteParagraphs.isNotEmpty())
        assertTrue(partial.text.contains("これはテストです。"))
        assertEquals(3, fake.calls)
    }

    @Test
    fun translatesSakuraBlockAndKeepsFormatting() = runTest {
        val fake = FixedClient("「早上好」\n\n今天天气真好。\n\n――――")
        val translator = ChapterTranslator(fake, store())
        val source = "「おはよう」\n\n今日はいい天気ですね。\n\n――――"

        val outcome = translator.translate(
            storageDir = "b2",
            chapterIndex = 1,
            sourceText = source,
            config = TranslationConfig(mode = com.kacyraho.lightnovel.core.settings.TranslationMode.SAKURA),
        )

        assertTrue(outcome is TranslationOutcome.Complete)
        assertEquals(
            "「早上好」\n\n今天天气真好。\n\n――――",
            (outcome as TranslationOutcome.Complete).text,
        )
        assertEquals(1, fake.calls)
    }

    @Test
    fun marksSakuraBlockPartialWhenDialogueIsMissing() = runTest {
        val fake = FixedClient("「早上好」")
        val translator = ChapterTranslator(fake, store())
        val source = "「おはよう」\n\n「いい天気だね」"

        val outcome = translator.translate(
            storageDir = "b3",
            chapterIndex = 1,
            sourceText = source,
            config = TranslationConfig(mode = com.kacyraho.lightnovel.core.settings.TranslationMode.SAKURA),
        )

        assertTrue(outcome is TranslationOutcome.Partial)
        val partial = outcome as TranslationOutcome.Partial
        assertEquals("partial", partial.sidecar.status)
        assertTrue(partial.text.contains("「おはよう」"))
        assertEquals(3, fake.calls)
    }

    @Test
    fun usesPreviousTranslatedChunkAsContext() = runTest {
        val fake = CapturingClient()
        val translator = ChapterTranslator(fake, store())
        val source = "こんにちは\n\nさようなら"

        val outcome = translator.translate(
            storageDir = "b4",
            chapterIndex = 1,
            sourceText = source,
            config = TranslationConfig(maxChars = 6),
        )

        assertTrue(outcome is TranslationOutcome.Complete)
        assertEquals(2, fake.prompts.size)
        val second = fake.prompts[1]
        assertTrue(second.contains("第一段中文译文"))
        assertTrue(!second.contains("こんにちは"))
    }

    private class CapturingClient : TranslationClient {
        val prompts = mutableListOf<String>()

        override suspend fun complete(
            messages: List<ChatMessage>,
            model: String,
            maxTokens: Int,
            temperature: Double,
        ): ChatResult {
            val user = messages.last().content
            prompts += user
            val reply = if (prompts.size == 1) {
                "1. 你好，这是第一段中文译文。"
            } else {
                "1. 再见，这是第二段中文译文。"
            }
            return ChatResult(reply, 10, 20, model, "stop")
        }
    }

    private class FixedClient(
        private val reply: String,
    ) : TranslationClient {
        var calls = 0

        override suspend fun complete(
            messages: List<ChatMessage>,
            model: String,
            maxTokens: Int,
            temperature: Double,
        ): ChatResult {
            calls++
            return ChatResult(
                content = reply,
                tokensIn = 10,
                tokensOut = 20,
                model = model,
                finishReason = "stop",
            )
        }
    }

    private class FakeClient(
        private val reply: String,
    ) : TranslationClient {
        var calls = 0
        override suspend fun complete(
            messages: List<ChatMessage>,
            model: String,
            maxTokens: Int,
            temperature: Double,
        ): ChatResult {
            calls++
            return ChatResult(
                content = reply,
                tokensIn = 10,
                tokensOut = 20,
                model = model,
                finishReason = "stop",
            )
        }
    }
}
