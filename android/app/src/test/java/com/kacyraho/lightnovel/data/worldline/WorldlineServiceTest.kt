package com.kacyraho.lightnovel.data.worldline

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.kacyraho.lightnovel.core.settings.AppSettings
import com.kacyraho.lightnovel.core.settings.InMemoryApiKeyStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.knowledge.Fact
import com.kacyraho.lightnovel.data.knowledge.FactAnchor
import com.kacyraho.lightnovel.data.knowledge.KnowledgeFile
import com.kacyraho.lightnovel.data.knowledge.KnowledgeStore
import com.kacyraho.lightnovel.data.knowledge.Secret
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.translation.ChatMessage
import com.kacyraho.lightnovel.data.translation.ChatResult
import com.kacyraho.lightnovel.data.translation.TranslationClient
import com.kacyraho.lightnovel.data.translation.TranslationException
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class WorldlineServiceTest {
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
    fun createsAndContinuesBranchWithoutFutureCanon() = runTest {
        val env = environment()
        val result = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝跟主角走", "不能使用魔法"),
        )
        assertTrue(result.isSuccess)
        val branch = result.getOrThrow()
        assertTrue(branch.branchCursor == 1)
        val writerPrompts = env.client.prompts.filter {
            it.contains("【分叉点前已知事实】") && it.contains("【本章 plan】")
        }
        assertTrue(writerPrompts.isNotEmpty())
        assertFalse(writerPrompts.any { it.contains("未来事实") })
        assertTrue(writerPrompts.any { it.contains("分叉点前已知事实") })

        val next = env.service.continueBranch(env.book, branch.id)
        assertTrue(next.isSuccess)
        assertTrue(next.getOrThrow().branchCursor == 2)
        assertTrue(env.client.prompts.any { it.contains("上一章梗概") })
        assertTrue(env.client.prompts.any { it.contains("【本分支前文】") })
    }

    @Test
    fun createsBranchFromEditedCanonText() = runTest {
        val env = environment()
        val result = env.service.createBranch(
            book = env.book,
            title = "",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention(),
            forkText = "爱丽丝没有拒绝，而是把信收进了口袋。",
        )

        assertTrue(result.isSuccess)
        val branch = result.getOrThrow()
        assertTrue(branch.forkText.contains("把信收进了口袋"))
        assertTrue(
            env.client.prompts.any { it.contains("用户修改后的分叉正文") },
        )
    }

    @Test
    fun rejectsShortOutputAndDoesNotAdvanceCursor() = runTest {
        val env = environment(shortWriter = true)
        val result = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        assertTrue(result.isFailure)
        assertTrue(env.store.list(env.book.storageDir).isEmpty())
    }

    @Test
    fun rejectsForbiddenRevealTerm() = runTest {
        val env = environment(forbiddenWriter = true)
        val result = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        assertTrue(result.isFailure)
    }

    @Test
    fun validatorViolationStopsBranchAndDoesNotWrite() = runTest {
        val env = environment(validatorViolation = true)
        val result = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        assertTrue(result.isFailure)
        assertTrue(env.store.list(env.book.storageDir).isEmpty())
    }

    @Test
    fun acceptsObjectShapedPlanBeats() = runTest {
        val env = environment(planObject = true)
        val result = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        assertTrue(result.isSuccess)
        assertEquals(1, result.getOrThrow().chapters.size)
    }

    @Test
    fun comparisonModeAsksForDiffButWriterNeverSeesRevealContent() = runTest {
        val env = environment(comparison = true)
        val result = env.service.createBranch(
            book = env.book,
            title = "对照分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
            mode = "comparison",
        )
        assertTrue(result.isSuccess)
        assertTrue(result.getOrThrow().diffReports.isNotEmpty())
        assertFalse(
            env.client.prompts.filter {
                it.contains("【分叉点前已知事实】") && it.contains("【本章 plan】")
            }.any { it.contains("未来事实") },
        )
    }

    @Test
    fun retriesTransientPlannerFailure() = runTest {
        val env = environment(failPlanOnce = true)
        val result = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        assertTrue(result.isSuccess)
        assertTrue(env.client.plannerCalls >= 2)
    }

    @Test
    fun replansWhenFirstPlanUsesFutureEntity() = runTest {
        val env = environment(planFutureFirst = true)
        val result = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        assertTrue(result.isSuccess)
        assertTrue(env.client.plannerCalls >= 2)
    }

    @Test
    fun acceptsArrayRootPlan() = runTest {
        val env = environment(planArray = true)
        val result = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        assertTrue(result.isSuccess)
    }

    @Test
    fun retriesUnparseableWriterOutput() = runTest {
        val env = environment(badWriterOnce = true)
        val result = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        assertTrue(result.isSuccess)
        assertTrue(env.client.writerCalls >= 2)
    }

    @Test
    fun continuesMultipleChaptersAndTracksStates() = runTest {
        val env = environment()
        val created = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        ).getOrThrow()
        var progress = 0
        val result = env.service.continueBranch(
            book = env.book,
            id = created.id,
            count = 3,
            onProgress = { done, total ->
                if (done <= total) progress = done
            },
        )
        assertTrue(result.isSuccess)
        val branch = result.getOrThrow()
        assertEquals(4, branch.chapters.size)
        assertEquals(4, branch.branchCursor)
        assertEquals(4, branch.chapterStates.size)
        assertTrue(progress >= 1)
    }

    @Test
    fun regeneratesLastChapterWithoutTouchingEarlierChapters() = runTest {
        val env = environment()
        val created = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        ).getOrThrow()
        val extended = env.service.continueBranch(env.book, created.id)
            .getOrThrow()
        assertEquals(2, extended.chapters.size)
        val result = env.service.regenerateLastChapter(env.book, created.id)
        assertTrue(result.isSuccess)
        val regenerated = result.getOrThrow()
        assertEquals(2, regenerated.chapters.size)
        assertEquals(2, regenerated.chapters.last().index)
        assertEquals(2, regenerated.chapterStates.size)
        assertEquals(
            extended.chapters.first().text,
            regenerated.chapters.first().text,
        )
    }

    @Test
    fun persistsLengthCreativityAndDirectiveIntoGeneration() = runTest {
        val env = environment()
        val result = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
            lengthMode = "short",
            creativity = "stable",
            directive = "保持爱丽丝视角，不要急着揭秘。",
        )
        assertTrue(result.isSuccess)
        val branch = result.getOrThrow()
        assertEquals("short", branch.lengthMode)
        assertEquals("stable", branch.creativity)
        assertEquals("保持爱丽丝视角，不要急着揭秘。", branch.directive)
        assertTrue(env.client.prompts.any { it.contains("目标 1200 字") })
        assertTrue(env.client.prompts.any { it.contains("保持爱丽丝视角") })
        assertTrue(env.client.temperatures.any { it == 0.55 })
    }

    @Test
    fun acceptsContentFieldAndMissingSummaryFromRealModels() = runTest {
        val env = environment(contentWriter = true)
        val result = env.service.createBranch(
            book = env.book,
            title = "分支",
            forkChapter = 2,
            forkParagraph = 0,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        assertTrue(result.isSuccess)
        val branch = result.getOrThrow()
        val chapter = branch.chapters.single()
        assertTrue(chapter.text.startsWith("模型有时把正文放在 content"))
        assertTrue(chapter.summary.isNotBlank())
        assertTrue(branch.state.summary.isNotBlank())
        assertTrue(branch.divergences.single().summary.isNotBlank())
    }

    private fun environment(
        shortWriter: Boolean = false,
        forbiddenWriter: Boolean = false,
        comparison: Boolean = false,
        validatorViolation: Boolean = false,
        planObject: Boolean = false,
        failPlanOnce: Boolean = false,
        planFutureFirst: Boolean = false,
        planArray: Boolean = false,
        badWriterOnce: Boolean = false,
        contentWriter: Boolean = false,
    ): Env {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val settings = SettingsStore(context)
        kotlinx.coroutines.runBlocking {
            settings.update {
                it.copy(deepSeekBaseUrl = "http://127.0.0.1:1/v1", deepSeekModel = "test-model")
            }
        }
        val content = FileContentStore(tmp.newFolder("data").toPath())
        content.writeRawAtomic("book", 1, "アリスは「行こう」と言った。")
        content.writeZhAtomic("book", 1, "爱丽丝说「走吧」。")
        val knowledgeStore = KnowledgeStore(content)
        knowledgeStore.save(
            "book",
            KnowledgeFile(
                workId = "book-1",
                title = "Book",
                entities = listOf(
                    com.kacyraho.lightnovel.data.knowledge.Entity(
                        id = "ent-alice",
                        canonicalName = "爱丽丝",
                        aliases = listOf("アリス"),
                        sourceAnchor = FactAnchor(1, 0, 0, ""),
                        readerKnown = true,
                    ),
                    com.kacyraho.lightnovel.data.knowledge.Entity(
                        id = "ent-future",
                        canonicalName = "未来人",
                        sourceAnchor = FactAnchor(8, 0, 0, ""),
                        firstSeenChapter = 8,
                    ),
                ),
                facts = listOf(
                    Fact(
                        id = "past",
                        entityId = "ent-alice",
                        kind = "persona",
                        factKey = "voice",
                        text = "分叉点前已知事实",
                        sourceAnchor = FactAnchor(1, 0, 0, ""),
                        readerKnown = true,
                        knownBy = listOf("ent-alice"),
                    ),
                    Fact(
                        id = "future",
                        entityId = "ent-alice",
                        kind = "persona",
                        factKey = "future",
                        text = "未来事实",
                        sourceAnchor = FactAnchor(8, 0, 0, ""),
                        readerKnown = true,
                    ),
                ),
                secrets = listOf(
                    Secret(
                        id = "s1",
                        subjectEntityId = "ent-alice",
                        canonRevealChapter = 8,
                        forbiddenTerms = listOf("妹妹"),
                    ),
                ),
                extractedChapters = (1..10).toList(),
                canonExtractedThrough = 10,
            ),
        )
        val store = WorldlineStore(content)
        val client = FakeClient(
            shortWriter = shortWriter,
            forbiddenWriter = forbiddenWriter,
            validatorViolation = validatorViolation,
            planObject = planObject,
            failPlanOnce = failPlanOnce,
            planFutureFirst = planFutureFirst,
            planArray = planArray,
            badWriterOnce = badWriterOnce,
            contentWriter = contentWriter,
        )
        val service = WorldlineService(
            contentStore = content,
            knowledgeStore = knowledgeStore,
            storyMemoryStore = null,
            worldlineStore = store,
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
            episodes = 10,
            local = true,
            createdAt = null,
            legacyJson = null,
        )
        return Env(content, knowledgeStore, store, service, client, book)
    }

    private data class Env(
        val content: FileContentStore,
        val knowledge: KnowledgeStore,
        val store: WorldlineStore,
        val service: WorldlineService,
        val client: FakeClient,
        val book: BookEntity,
    )

    private class FakeClient(
        private val shortWriter: Boolean,
        private val forbiddenWriter: Boolean,
        private val validatorViolation: Boolean,
        private val planObject: Boolean,
        private val failPlanOnce: Boolean,
        private val planFutureFirst: Boolean,
        private val planArray: Boolean,
        private val badWriterOnce: Boolean,
        private val contentWriter: Boolean,
    ) : TranslationClient {
        val prompts = mutableListOf<String>()
        val temperatures = mutableListOf<Double>()
        var writerCount = 0
        var plannerCalls = 0
        var writerCalls = 0

        override suspend fun complete(
            messages: List<ChatMessage>,
            model: String,
            maxTokens: Int,
            temperature: Double,
        ): ChatResult {
            val system = messages.first().content
            prompts += messages.last().content
            temperatures += temperature
            val reply = when {
                system.contains("分支剧情规划师") -> {
                    plannerCalls++
                    if (failPlanOnce && plannerCalls == 1) {
                        throw TranslationException(503, "service busy", true)
                    }
                    when {
                        planFutureFirst && plannerCalls == 1 -> PLAN_FUTURE
                        planArray -> PLAN_ARRAY
                        planObject -> PLAN_OBJECT
                        else -> PLAN
                    }
                }
                system.contains("分支续写作者") -> {
                    writerCount++
                    writerCalls++
                    when {
                        contentWriter ->
                            """{"title":"模型分支","content":"模型有时把正文放在 content 字段。""" +
                                "正文".repeat(300) + """"}"""
                        badWriterOnce && writerCalls == 1 -> "这不是 JSON"
                        shortWriter -> """{"title":"短","text":"太短","summary":"短"}"""
                        forbiddenWriter -> chapterJson("妹妹出现了。" + "正文".repeat(300))
                        writerCount == 1 -> chapterJson()
                        else -> chapterJson("第二章正文。" + "正文".repeat(300))
                    }
                }
                system.contains("分支一致性校对员") ->
                    if (validatorViolation) {
                        """{"violations":[{"type":"knowledge","quote":"","reason":"角色知道了未知信息"}],"canProceed":false}"""
                    } else {
                        """{"violations":[],"canProceed":true}"""
                    }
                system.contains("世界线差异分析员") ->
                    """{"items":[{"type":"event","branchEvent":"爱丽丝拒绝了主角","canonReference":"原作中她跟随了主角","impact":"后续同行剧情不会发生","causedByIntervention":true}]}"""
                else -> "{}"
            }
            return ChatResult(reply, 10, 20, model, "stop")
        }
    }

    private companion object {
        const val PLAN =
            """{"beats":["爱丽丝拒绝同行","主角独自离开"],"characters":["爱丽丝"],"intendedDivergence":"爱丽丝没有跟随主角","futureRisks":[],"stateChanges":["关系变化"]}"""

        const val PLAN_OBJECT =
            """{"beats":[{"beat":"爱丽丝拒绝同行"},{"text":"主角独自离开"}],"characters":[{"name":"爱丽丝"}],"intendedDivergence":{"text":"爱丽丝没有跟随主角"},"futureRisks":[],"stateChanges":[{"change":"关系变化"}]}"""

        const val PLAN_FUTURE =
            """{"beats":["未来人提前登场","主角离开"],"characters":["爱丽丝"],"intendedDivergence":"爱丽丝没有跟随主角","futureRisks":[],"stateChanges":["关系变化"]}"""

        const val PLAN_ARRAY =
            """["爱丽丝拒绝同行","主角独自离开"]"""

        fun chapterJson(text: String = "分支正文。" + "正文".repeat(300)): String =
            """{"title":"分支章","text":"$text","summary":"分支梗概","state":{"time":"夜","location":"车站","summary":"局势","facts":[],"openThreads":[]},"divergence":{"type":"event","summary":"爱丽丝拒绝了主角","canonSummary":null,"causedByIntervention":true}}"""
    }
}
