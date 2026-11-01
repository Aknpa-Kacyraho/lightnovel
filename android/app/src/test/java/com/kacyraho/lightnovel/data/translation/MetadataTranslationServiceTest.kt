package com.kacyraho.lightnovel.data.translation

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.settings.InMemoryApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LightnovelDatabase
import com.kacyraho.lightnovel.data.source.SourceBook
import com.kacyraho.lightnovel.data.source.SourceChapterRef
import com.kacyraho.lightnovel.data.source.SourceDetail
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class MetadataTranslationServiceTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun translatesBookAndChapterTitles() = runTest {
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
                title = "さよならアイリス",
                titleZh = null,
                author = "作者",
                tagsJson = null,
                genre = null,
                episodes = 1,
                local = false,
                createdAt = null,
                legacyJson = null,
            )
            val chapter = ChapterEntity(
                bookId = book.id,
                idx = 1,
                title = "第1話",
                titleZh = null,
                rawPath = null,
                zhPath = null,
                status = "online",
                tokenIn = 0,
                tokenOut = 0,
                model = null,
                updatedAt = null,
            )
            dao.upsertBooks(listOf(book))
            dao.upsertChapters(listOf(chapter))

            val fake = object : TranslationClient {
                override suspend fun complete(
                    messages: List<ChatMessage>,
                    model: String,
                    maxTokens: Int,
                    temperature: Double,
                ) = ChatResult(
                    content = """
                        {"titleZh":"再见爱丽丝","synopsisZh":"简介",
                         "tagsZh":["奇幻"],"chaptersZh":["第一话"]}
                    """.trimIndent(),
                    tokensIn = 10,
                    tokensOut = 20,
                    model = model,
                    finishReason = "stop",
                )
            }
            val service = MetadataTranslationService(
                contentStore = FileContentStore(tmp.newFolder("data").toPath()),
                dao = dao,
                settingsStore = SettingsStore(context),
                apiKeyStore = InMemoryApiKeyStore("key"),
                clientFactory = { _, _ -> fake },
            )
            val detail = SourceDetail(
                book = SourceBook(
                    provider = "kakuyomu",
                    id = "1",
                    title = "さよならアイリス",
                    author = "作者",
                    tags = listOf("百合"),
                    episodes = 1,
                ),
                chapters = listOf(SourceChapterRef("1", "第1話")),
                synopsis = "简介",
            )

            val metadata = service.translateBook(book, detail, listOf(chapter))

            assertEquals("再见爱丽丝", metadata?.titleZh)
            assertEquals("再见爱丽丝", dao.book(book.id)?.titleZh)
            assertEquals("第一话", dao.chapters(book.id).single().titleZh)
        } finally {
            db.close()
        }
    }
}
