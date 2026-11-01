package com.kacyraho.lightnovel.data.worldline

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.settings.InMemoryApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.knowledge.Entity
import com.kacyraho.lightnovel.data.knowledge.FactAnchor
import com.kacyraho.lightnovel.data.knowledge.KnowledgeFile
import com.kacyraho.lightnovel.data.knowledge.KnowledgeStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.translation.ChatMessage
import com.kacyraho.lightnovel.data.translation.ChatResult
import com.kacyraho.lightnovel.data.translation.TranslationClient
import kotlinx.coroutines.test.runTest
import org.junit.After
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
class BranchKnowledgeExtractorTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @After
    fun resetSettings() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        kotlinx.coroutines.runBlocking {
            SettingsStore(context).update {
                com.kacyraho.lightnovel.core.settings.AppSettings()
            }
        }
    }

    @Test
    fun extractsBranchFactsWithValidatedSourceQuote() = runTest {
        val env = environment()
        val result = env.extractor.extract(env.book, env.worldline, 1)
        assertTrue(result.isSuccess)
        val knowledge = result.getOrThrow()
        assertEquals(1, knowledge.branchExtractedThrough)
        assertTrue(knowledge.facts.any { it.scope == "branch" && it.text == "她拒绝了主角" })
        assertTrue(knowledge.facts.first().knownBy.contains("ent-alice"))
    }

    @Test
    fun rejectsFactWithoutBranchSourceQuote() = runTest {
        val env = environment(reply = """
            {"entities":[{"source":"爱丽丝","canonicalName":"爱丽丝","sourceQuote":"爱丽丝"}],
             "facts":[{"entity":"爱丽丝","key":"x","kind":"persona","text":"不存在",
                       "sourceQuote":"不存在的引用","knownBy":["爱丽丝"]}]}
        """.trimIndent())
        val result = env.extractor.extract(env.book, env.worldline, 1)
        assertTrue(result.isFailure)
        assertTrue(env.store.loadKnowledge("book", "wl-1")?.facts.orEmpty().isEmpty())
    }

    private fun environment(reply: String? = null): Env {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val settings = SettingsStore(context)
        kotlinx.coroutines.runBlocking {
            settings.update {
                it.copy(deepSeekBaseUrl = "http://127.0.0.1:1/v1", deepSeekModel = "test-model")
            }
        }
        val content = FileContentStore(tmp.newFolder("data").toPath())
        val knowledge = KnowledgeStore(content)
        knowledge.save(
            "book",
            KnowledgeFile(
                workId = "book-1",
                entities = listOf(
                    Entity(
                        id = "ent-alice",
                        canonicalName = "爱丽丝",
                        aliases = listOf("アリス"),
                        sourceAnchor = FactAnchor(1, 0, 0, ""),
                    ),
                ),
            ),
        )
        val store = WorldlineStore(content)
        val client = FakeClient(reply ?: """
            {"entities":[{"source":"爱丽丝","canonicalName":"爱丽丝","sourceQuote":"爱丽丝"}],
             "facts":[{"entity":"爱丽丝","key":"decision","kind":"event",
                       "text":"她拒绝了主角","sourceQuote":"我拒绝","knownBy":["爱丽丝"]}]}
        """.trimIndent())
        val extractor = BranchKnowledgeExtractor(
            worldlineStore = store,
            knowledgeStore = knowledge,
            settingsStore = settings,
            apiKeyStore = InMemoryApiKeyStore(""),
            clientFactory = { _, _ -> client },
        )
        val worldline = WorldlineFile(
            id = "wl-1",
            bookId = "book-1",
            chapters = listOf(
                BranchChapter(
                    index = 1,
                    title = "一",
                    text = "爱丽丝说：「我拒绝。」".repeat(40),
                    summary = "她拒绝了",
                ),
            ),
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
            episodes = 10,
            local = true,
            createdAt = null,
            legacyJson = null,
        )
        return Env(store, extractor, book, worldline)
    }

    private data class Env(
        val store: WorldlineStore,
        val extractor: BranchKnowledgeExtractor,
        val book: BookEntity,
        val worldline: WorldlineFile,
    )

    private class FakeClient(private val reply: String) : TranslationClient {
        override suspend fun complete(
            messages: List<ChatMessage>,
            model: String,
            maxTokens: Int,
            temperature: Double,
        ): ChatResult = ChatResult(reply, 10, 20, model, "stop")
    }
}
