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
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class TranslationServiceTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun writesSidecarTextAndRoomStatus() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val dao = db.libraryDao()
            val book = BookEntity(
                id = "kakuyomu-1",
                storageDir = "kakuyomu-1",
                slug = "kakuyomu-1",
                source = "kakuyomu",
                sourceId = "1",
                title = "Book",
                titleZh = null,
                author = null,
                tagsJson = null,
                genre = null,
                episodes = 1,
                local = false,
                createdAt = null,
                legacyJson = null,
            )
            dao.upsertBooks(listOf(book))
            dao.upsertChapters(
                listOf(
                    ChapterEntity(
                        bookId = book.id,
                        idx = 1,
                        title = "第一章",
                        titleZh = null,
                        rawPath = "raw/0001.txt",
                        zhPath = null,
                        status = "raw",
                        tokenIn = 0,
                        tokenOut = 0,
                        model = null,
                        updatedAt = null,
                    ),
                ),
            )
            val store = FileContentStore(tmp.newFolder("data").toPath())
            store.writeRawAtomic(book.storageDir, 1, "「おはよう」\n\nこれはテストです。")

            val settingsStore = SettingsStore(context)
            settingsStore.update {
                it.copy(
                    deepSeekBaseUrl = "http://127.0.0.1:1/chat/completions",
                    deepSeekModel = "deepseek-flash",
                )
            }
            val fake = object : TranslationClient {
                override suspend fun complete(
                    messages: List<ChatMessage>,
                    model: String,
                    maxTokens: Int,
                    temperature: Double,
                ) = ChatResult(
                    content = "1. 「早上好」\n2. 这是测试。",
                    tokensIn = 10,
                    tokensOut = 20,
                    model = model,
                    finishReason = "stop",
                )
            }
            val service = TranslationService(
                contentStore = store,
                dao = dao,
                settingsStore = settingsStore,
                apiKeyStore = InMemoryApiKeyStore("key"),
                clientFactory = { _, _ -> fake },
            )

            val outcome = service.translate(book, 1)

            assertTrue(outcome is TranslationOutcome.Complete)
            assertNotNull(store.readZh(book.storageDir, 1))
            assertEquals("complete", store.readSidecar(book.storageDir, 1)?.status)
            assertEquals("complete", dao.chapters(book.id).single().status)
            assertEquals(20, dao.chapters(book.id).single().tokenOut)
        } finally {
            db.close()
        }
    }

    @Test
    fun retranslatingOneParagraphKeepsChapterPartial() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val dao = db.libraryDao()
            val book = BookEntity(
                id = "kakuyomu-2",
                storageDir = "kakuyomu-2",
                slug = "kakuyomu-2",
                source = "kakuyomu",
                sourceId = "2",
                title = "Book",
                titleZh = null,
                author = null,
                tagsJson = null,
                genre = null,
                episodes = 1,
                local = false,
                createdAt = null,
                legacyJson = null,
            )
            dao.upsertBooks(listOf(book))
            dao.upsertChapters(
                listOf(
                    ChapterEntity(
                        bookId = book.id,
                        idx = 1,
                        title = "第一章",
                        titleZh = null,
                        rawPath = "raw/0001.txt",
                        zhPath = "zh/0001.txt",
                        status = "partial",
                        tokenIn = 1,
                        tokenOut = 2,
                        model = "m",
                        updatedAt = null,
                    ),
                ),
            )
            val store = FileContentStore(tmp.newFolder("data-2").toPath())
            val raw = "こんにちは。\n\nおやすみ。"
            val zh = "你好。\n\n晚安。"
            store.writeRawAtomic(book.storageDir, 1, raw)
            store.writeZhAtomic(book.storageDir, 1, zh)
            store.writeSidecar(
                book.storageDir,
                1,
                ChapterSidecar(
                    status = "partial",
                    sourceSha256 = Hashes.sha256(raw),
                    contentSha256 = Hashes.sha256(zh),
                    translationConfigHash = "old",
                    modelProvider = "deepseek",
                    modelId = "m",
                    promptVersion = "p",
                    translatedAt = "2026-01-01T00:00:00Z",
                    incompleteParagraphs = listOf(1),
                ),
            )
            val settingsStore = SettingsStore(context)
            settingsStore.update {
                it.copy(
                    deepSeekBaseUrl = "http://127.0.0.1:1/chat/completions",
                    deepSeekModel = "deepseek-flash",
                )
            }
            val fake = object : TranslationClient {
                override suspend fun complete(
                    messages: List<ChatMessage>,
                    model: String,
                    maxTokens: Int,
                    temperature: Double,
                ) = ChatResult(
                    content = "1. 你好呀。",
                    tokensIn = 1,
                    tokensOut = 2,
                    model = model,
                    finishReason = "stop",
                )
            }
            val service = TranslationService(
                contentStore = store,
                dao = dao,
                settingsStore = settingsStore,
                apiKeyStore = InMemoryApiKeyStore("key"),
                clientFactory = { _, _ -> fake },
            )

            val outcome = service.retranslateParagraph(book, 1, 0)

            assertTrue(outcome is TranslationOutcome.Partial)
            assertEquals("partial", store.readSidecar(book.storageDir, 1)?.status)
            assertEquals(listOf(1), store.readSidecar(book.storageDir, 1)?.incompleteParagraphs)
        } finally {
            db.close()
        }
    }

    @Test
    fun unexpectedFailureMarksChapterFailed() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val dao = db.libraryDao()
            val book = book("kakuyomu-3", "3")
            dao.upsertBooks(listOf(book))
            dao.upsertChapters(listOf(chapter(book.id, 1, "raw", zhPath = null)))
            val store = FileContentStore(tmp.newFolder("data-3").toPath())
            store.writeRawAtomic(book.storageDir, 1, "「おはよう」\n\nこれはテストです。")
            val settingsStore = SettingsStore(context)
            settingsStore.update {
                it.copy(
                    deepSeekBaseUrl = "http://127.0.0.1:1/chat/completions",
                    deepSeekModel = "deepseek-flash",
                )
            }
            val crashing = object : TranslationClient {
                override suspend fun complete(
                    messages: List<ChatMessage>,
                    model: String,
                    maxTokens: Int,
                    temperature: Double,
                ): ChatResult = error("disk full")
            }
            val service = TranslationService(
                contentStore = store,
                dao = dao,
                settingsStore = settingsStore,
                apiKeyStore = InMemoryApiKeyStore("key"),
                clientFactory = { _, _ -> crashing },
            )

            val outcome = service.translate(book, 1)

            assertTrue(outcome is TranslationOutcome.Failed)
            assertEquals("failed", dao.chapters(book.id).single().status)
            assertNull(store.readZh(book.storageDir, 1))
        } finally {
            db.close()
        }
    }

    @Test
    fun retranslatingOneParagraphKeepsSingleNewlineLayout() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val dao = db.libraryDao()
            val book = book("kakuyomu-4", "4")
            dao.upsertBooks(listOf(book))
            dao.upsertChapters(listOf(chapter(book.id, 1, "complete", zhPath = "zh/0001.txt")))
            val store = FileContentStore(tmp.newFolder("data-4").toPath())
            val raw = "こんにちは。\nおやすみ。\nまたね。"
            val zh = "你好。\n晚安。\n再见。"
            store.writeRawAtomic(book.storageDir, 1, raw)
            store.writeZhAtomic(book.storageDir, 1, zh)
            store.writeSidecar(
                book.storageDir,
                1,
                ChapterSidecar(
                    status = "complete",
                    sourceSha256 = Hashes.sha256(raw),
                    contentSha256 = Hashes.sha256(zh),
                    translationConfigHash = "old",
                    modelProvider = "deepseek",
                    modelId = "m",
                    promptVersion = "p",
                    translatedAt = "2026-01-01T00:00:00Z",
                ),
            )
            val settingsStore = SettingsStore(context)
            settingsStore.update {
                it.copy(
                    deepSeekBaseUrl = "http://127.0.0.1:1/chat/completions",
                    deepSeekModel = "deepseek-flash",
                )
            }
            val fake = object : TranslationClient {
                override suspend fun complete(
                    messages: List<ChatMessage>,
                    model: String,
                    maxTokens: Int,
                    temperature: Double,
                ) = ChatResult(
                    content = "1. 你好呀。",
                    tokensIn = 1,
                    tokensOut = 2,
                    model = model,
                    finishReason = "stop",
                )
            }
            val service = TranslationService(
                contentStore = store,
                dao = dao,
                settingsStore = settingsStore,
                apiKeyStore = InMemoryApiKeyStore("key"),
                clientFactory = { _, _ -> fake },
            )

            val outcome = service.retranslateParagraph(book, 1, 0)

            assertTrue(outcome is TranslationOutcome.Complete)
            assertEquals("你好呀。\n晚安。\n再见。", store.readZh(book.storageDir, 1))
        } finally {
            db.close()
        }
    }

    @Test
    fun nonRetryableParagraphFailureCallsClientOnce() = runTest {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val db = Room.inMemoryDatabaseBuilder(context, LightnovelDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        try {
            val dao = db.libraryDao()
            val book = book("kakuyomu-5", "5")
            dao.upsertBooks(listOf(book))
            dao.upsertChapters(listOf(chapter(book.id, 1, "complete", zhPath = "zh/0001.txt")))
            val store = FileContentStore(tmp.newFolder("data-5").toPath())
            val raw = "こんにちは。"
            val zh = "你好。"
            store.writeRawAtomic(book.storageDir, 1, raw)
            store.writeZhAtomic(book.storageDir, 1, zh)
            store.writeSidecar(
                book.storageDir,
                1,
                ChapterSidecar(
                    status = "complete",
                    sourceSha256 = Hashes.sha256(raw),
                    contentSha256 = Hashes.sha256(zh),
                    translationConfigHash = "old",
                    modelProvider = "deepseek",
                    modelId = "m",
                    promptVersion = "p",
                    translatedAt = "2026-01-01T00:00:00Z",
                ),
            )
            val settingsStore = SettingsStore(context)
            settingsStore.update {
                it.copy(
                    deepSeekBaseUrl = "http://127.0.0.1:1/chat/completions",
                    deepSeekModel = "deepseek-flash",
                )
            }
            var calls = 0
            val unauthorized = object : TranslationClient {
                override suspend fun complete(
                    messages: List<ChatMessage>,
                    model: String,
                    maxTokens: Int,
                    temperature: Double,
                ): ChatResult {
                    calls++
                    throw TranslationException(401, "unauthorized", retryable = false)
                }
            }
            val service = TranslationService(
                contentStore = store,
                dao = dao,
                settingsStore = settingsStore,
                apiKeyStore = InMemoryApiKeyStore("key"),
                clientFactory = { _, _ -> unauthorized },
            )

            val outcome = service.retranslateParagraph(book, 1, 0)

            assertTrue(outcome is TranslationOutcome.Failed)
            assertEquals(1, calls)
        } finally {
            db.close()
        }
    }

    private fun book(id: String, sourceId: String) = BookEntity(
        id = id,
        storageDir = id,
        slug = id,
        source = "kakuyomu",
        sourceId = sourceId,
        title = "Book",
        titleZh = null,
        author = null,
        tagsJson = null,
        genre = null,
        episodes = 1,
        local = false,
        createdAt = null,
        legacyJson = null,
    )

    private fun chapter(
        bookId: String,
        idx: Int,
        status: String,
        zhPath: String?,
    ) = ChapterEntity(
        bookId = bookId,
        idx = idx,
        title = "第一章",
        titleZh = null,
        rawPath = "raw/0001.txt",
        zhPath = zhPath,
        status = status,
        tokenIn = 0,
        tokenOut = 0,
        model = null,
        updatedAt = null,
    )
}
