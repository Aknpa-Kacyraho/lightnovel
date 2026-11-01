package com.kacyraho.lightnovel.data.story

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.settings.InMemoryApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.translation.ChatMessage
import com.kacyraho.lightnovel.data.translation.ChatResult
import com.kacyraho.lightnovel.data.translation.TranslationClient
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class StoryMemoryServiceTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun summaryIsStoredWithoutInvalidatingRevision() = runTest {
        val env = environment()
        val before = env.store.load("book", "book-1", "Book").revision
        val summary = env.service.generateSummary(env.book, 1)

        assertEquals("爱丽丝在雨中遇见少年。", summary)
        val memory = env.store.load("book", "book-1", "Book")
        assertEquals("爱丽丝在雨中遇见少年。", memory.summaries[1]?.text)
        assertEquals(before, memory.revision)
    }

    @Test
    fun extractsCharactersAndLocksGlossary() = runTest {
        val env = environment()
        val found = env.service.extractCharacters(env.book, env.chapters)

        assertTrue(found.any { it.source == "アリス" && it.target == "爱丽丝" })
        val memory = env.store.load("book", "book-1", "Book")
        assertTrue(memory.characters.any { it.source == "アリス" && it.voice.contains("冷淡") })
        assertTrue(memory.glossary.any { it.source == "アリス" && it.target == "爱丽丝" })
    }

    @Test
    fun scansAndAppliesNameSuggestions() = runTest {
        val env = environment()
        val suggestions = env.service.scanNames(env.book, env.chapters)

        assertEquals(1, suggestions.size)
        assertEquals("アリス", suggestions.single().source)
        assertEquals("爱丽丝", suggestions.single().suggested)

        val memory = env.service.applySuggestions(env.book, suggestions)
        assertTrue(memory.glossary.any { it.source == "アリス" && it.target == "爱丽丝" })
    }

    private fun environment(): Env {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val settings = SettingsStore(context)
        kotlinx.coroutines.runBlocking {
            settings.update {
                it.copy(
                    deepSeekBaseUrl = "http://127.0.0.1:1/v1",
                    deepSeekModel = "test-model",
                )
            }
        }
        val content = FileContentStore(tmp.newFolder("data").toPath())
        content.writeRawAtomic("book", 1, "アリスは「行こう」と言った。")
        content.writeZhAtomic("book", 1, "爱丽丝说：「走吧。」")
        content.writeRawAtomic("book", 2, "アリスはまた会った。")
        content.writeZhAtomic("book", 2, "爱丽丝又见面了。")
        val store = StoryMemoryStore(content)
        val service = StoryMemoryService(
            contentStore = content,
            storyStore = store,
            settingsStore = settings,
            apiKeyStore = InMemoryApiKeyStore(""),
            clientFactory = { _, _ -> FakeClient() },
        )
        val book = BookEntity(
            id = "book-1",
            storageDir = "book",
            slug = "book",
            source = "local",
            sourceId = "book-1",
            title = "Book",
            titleZh = null,
            author = null,
            tagsJson = null,
            genre = null,
            episodes = 2,
            local = true,
            createdAt = null,
            legacyJson = null,
        )
        val chapters = listOf(
            ChapterEntity("book-1", 1, "第一话", null, null, null, "raw", 0, 0, null, null),
            ChapterEntity("book-1", 2, "第二话", null, null, null, "raw", 0, 0, null, null),
        )
        return Env(store, service, book, chapters)
    }

    private data class Env(
        val store: StoryMemoryStore,
        val service: StoryMemoryService,
        val book: BookEntity,
        val chapters: List<ChapterEntity>,
    )

    private class FakeClient : TranslationClient {
        override suspend fun complete(
            messages: List<ChatMessage>,
            model: String,
            maxTokens: Int,
            temperature: Double,
        ): ChatResult {
            val system = messages.firstOrNull()?.content.orEmpty()
            val content = when {
                system.contains("剧情编辑") -> "爱丽丝在雨中遇见少年。"
                system.contains("提取有名字的人物") ->
                    """{"characters":[{"source":"アリス","target":"爱丽丝","aliases":["爱丽丝"],"description":"少女","voice":"冷淡、短句","address":"叫你","lexicon":"","syntax":"","notes":""}]}"""
                system.contains("译名校对员") ->
                    """{"items":[{"source":"アリス","variants":["爱丽丝","艾莉丝"],"suggested":"爱丽丝","evidence":"爱丽丝说"}]}"""
                else -> "1. 爱丽丝说：「走吧。」"
            }
            return ChatResult(content, 10, 20, model, "stop")
        }
    }
}
