package com.kacyraho.lightnovel.data.knowledge

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.settings.InMemoryApiKeyStore
import com.kacyraho.lightnovel.core.settings.AppSettings
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.translation.ChatMessage
import com.kacyraho.lightnovel.data.translation.ChatResult
import com.kacyraho.lightnovel.data.translation.TranslationClient
import kotlinx.coroutines.test.runTest
import org.junit.After
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
class KnowledgeExtractionServiceTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @After
    fun resetSettings() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        kotlinx.coroutines.runBlocking {
            SettingsStore(context).update { AppSettings() }
        }
    }

    @Test
    fun extractsValidatedKnowledgeAndSecrets() = runTest {
        val env = environment()
        val result = env.service.extractChapter(env.book, 1)

        assertTrue(result.isSuccess)
        val knowledge = result.getOrThrow()
        assertEquals(listOf(1), knowledge.extractedChapters)
        val alice = knowledge.entities.first { it.canonicalName == "爱丽丝" }
        val fact = knowledge.facts.first { it.entityId == alice.id && it.kind == "persona" }
        assertEquals(0, fact.sourceAnchor.paragraph)
        assertNotNull(fact.displayAnchor)
        assertTrue(fact.knownBy.contains(alice.id))
        assertTrue(knowledge.secrets.isNotEmpty())
        assertTrue(knowledge.secrets.single().contentFactIds.isNotEmpty())
        assertTrue(knowledge.voiceFacts.isNotEmpty())
    }

    @Test
    fun rejectsFactWithoutSourceQuote() = runTest {
        val env = environment(
            reply = """
                {"facts":[{"entity":"アリス","key":"identity","kind":"persona",
                           "text":"不存在的事实","sourceQuote":"存在しない引用",
                           "displayQuote":"不存在","knownBy":["アリス"]}]}
            """.trimIndent(),
        )
        val result = env.service.extractChapter(env.book, 1)
        assertTrue(result.isFailure)
        assertEquals(0, env.store.load("book", "book-1").extractedChapters.size)
    }

    @Test
    fun keepsFactWhenDisplayQuoteCannotBeLocated() = runTest {
        val env = environment(
            reply = """
                {"entities":[{"source":"アリス","canonicalName":"爱丽丝","sourceQuote":"アリス"}],
                 "facts":[{"entity":"アリス","key":"identity","kind":"persona",
                           "text":"冷淡","sourceQuote":"「おはよう」",
                           "displayQuote":"不存在的译文","knownBy":["アリス"]}]}
            """.trimIndent(),
        )
        val knowledge = env.service.extractChapter(env.book, 1).getOrThrow()
        val fact = knowledge.facts.first { it.kind == "persona" }
        assertEquals("display_stale", fact.status)
        assertNull(fact.displayAnchor)
    }

    @Test
    fun supersedesConflictingFactKey() = runTest {
        val env = environment()
        env.service.extractChapter(env.book, 1).getOrThrow()
        env.content.writeRawAtomic("book", 2, "アリスは「おはよう」と言った。\n\n彼女は魔法を使った。")
        env.content.writeZhAtomic("book", 2, "爱丽丝说「早上好」。\n\n她使用了魔法。")
        env.client.reply = """
            {"entities":[{"source":"アリス","canonicalName":"爱丽丝","sourceQuote":"アリス"}],
             "facts":[{"entity":"アリス","key":"identity.role","kind":"persona",
                       "text":"法师","sourceQuote":"「おはよう」",
                       "displayQuote":"「早上好」","knownBy":["アリス"]}]}
        """.trimIndent()

        val knowledge = env.service.extractChapter(env.book, 2).getOrThrow()
        val old = knowledge.facts.first { it.text == "剑士" }
        val newer = knowledge.facts.first { it.text == "法师" }
        assertEquals(1, old.validUntilChapter)
        assertEquals(newer.id, old.supersededBy)
        assertEquals(old.id, newer.supersedes)
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
        content.writeRawAtomic("book", 1, "アリスは「おはよう」と言った。\n\n今日はいい天気ですね。")
        content.writeZhAtomic("book", 1, "爱丽丝说「早上好」。\n\n今天天气真好。")
        val store = KnowledgeStore(content)
        val client = FakeClient(reply ?: DEFAULT_REPLY)
        val service = KnowledgeExtractionService(
            contentStore = content,
            knowledgeStore = store,
            settingsStore = settings,
            apiKeyStore = InMemoryApiKeyStore(""),
            clientFactory = { _, _ -> client },
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
        return Env(content, store, service, client, book)
    }

    private data class Env(
        val content: FileContentStore,
        val store: KnowledgeStore,
        val service: KnowledgeExtractionService,
        val client: FakeClient,
        val book: BookEntity,
    )

    private class FakeClient(var reply: String) : TranslationClient {
        override suspend fun complete(
            messages: List<ChatMessage>,
            model: String,
            maxTokens: Int,
            temperature: Double,
        ): ChatResult = ChatResult(reply, 10, 20, model, "stop")
    }

    private companion object {
        val DEFAULT_REPLY = """
            {
              "entities":[
                {"source":"アリス","canonicalName":"爱丽丝","aliases":["アリス"],
                 "type":"character","sourceQuote":"アリス","readerKnown":true,"knownBy":["アリス"]}
              ],
              "facts":[
                {"entity":"アリス","key":"identity.role","kind":"persona",
                 "text":"剑士","sourceQuote":"「おはよう」","displayQuote":"「早上好」",
                 "readerKnown":true,"knownBy":["アリス"],"confidence":0.8}
              ],
              "relations":[
                {"from":"アリス","to":"アリス","type":"other","label":"独白",
                 "sourceQuote":"「おはよう」","displayQuote":"「早上好」",
                 "readerKnown":true,"knownBy":["アリス"],"confidence":0.6}
              ],
              "voiceFacts":[
                {"entity":"アリス","dimension":"voice","text":"短句",
                 "exampleQuote":"「おはよう」","sourceQuote":"「おはよう」",
                 "displayQuote":"「早上好」","readerKnown":true,"knownBy":["アリス"],
                 "confidence":0.8}
              ],
              "secrets":[
                {"subject":"アリス","contentFacts":[
                  {"text":"她隐藏了身份","sourceQuote":"「おはよう」",
                   "displayQuote":"「早上好」","forbiddenTerms":["身份"]}],
                 "allowedHints":["distrust"],"forbiddenTerms":["身份"]}
              ]
            }
        """.trimIndent()
    }
}
