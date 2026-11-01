package com.kacyraho.lightnovel.data.translation

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.settings.InMemoryApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.ChapterSidecar
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.data.story.StoryMemoryStore
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
class TranslationServicePolishTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun polishedTextIsWrittenOnlyAfterValidation() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val dao = db.libraryDao()
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
                episodes = 1,
                local = true,
                createdAt = null,
                legacyJson = null,
            )
            dao.upsertBooks(listOf(book))
            dao.upsertChapters(
                listOf(
                    ChapterEntity("book-1", 1, "第一话", null, null, null, "complete", 0, 0, null, null),
                ),
            )
            val raw = "「おはよう」\n\n今日はいい天気ですね。"
            val zh = "「早上好」\n\n今天天气真好。"
            val content = FileContentStore(tmp.newFolder("data").toPath())
            content.writeRawAtomic("book", 1, raw)
            content.writeZhAtomic("book", 1, zh)
            content.writeSidecar(
                "book",
                1,
                ChapterSidecar(
                    status = "complete",
                    sourceSha256 = Hashes.sha256(raw),
                    contentSha256 = Hashes.sha256(zh),
                    translationConfigHash = "old",
                    modelProvider = "test",
                    modelId = "test-model",
                    promptVersion = "android-a2-v3",
                    translatedAt = "2026-11-01T00:00:00Z",
                ),
            )
            val settings = SettingsStore(context)
            settings.update {
                it.copy(deepSeekBaseUrl = "http://127.0.0.1:1/v1", deepSeekModel = "test-model")
            }
            val service = TranslationService(
                contentStore = content,
                dao = dao,
                settingsStore = settings,
                apiKeyStore = InMemoryApiKeyStore(""),
                storyMemoryStore = StoryMemoryStore(content),
                clientFactory = { _, _ ->
                    object : TranslationClient {
                        override suspend fun complete(
                            messages: List<ChatMessage>,
                            model: String,
                            maxTokens: Int,
                            temperature: Double,
                        ) = ChatResult(
                            content = "「早上好呀」\n\n今天天气真不错。",
                            tokensIn = 10,
                            tokensOut = 20,
                            model = model,
                            finishReason = "stop",
                        )
                    }
                },
            )

            val outcome = service.polishChapter(book, 1)

            assertTrue(outcome is TranslationOutcome.Complete)
            assertEquals("「早上好呀」\n\n今天天气真不错。", content.readZh("book", 1))
            assertEquals("complete", dao.chapters("book-1").single().status)
        } finally {
            db.close()
        }
    }
}
