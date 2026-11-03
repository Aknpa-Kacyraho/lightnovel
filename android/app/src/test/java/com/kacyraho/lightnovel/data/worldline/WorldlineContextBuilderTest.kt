package com.kacyraho.lightnovel.data.worldline

import com.kacyraho.lightnovel.core.storage.FileContentStore
import com.kacyraho.lightnovel.data.knowledge.Entity
import com.kacyraho.lightnovel.data.knowledge.Fact
import com.kacyraho.lightnovel.data.knowledge.FactAnchor
import com.kacyraho.lightnovel.data.knowledge.KnowledgeFile
import com.kacyraho.lightnovel.data.knowledge.KnowledgeStore
import com.kacyraho.lightnovel.data.knowledge.Secret
import com.kacyraho.lightnovel.data.local.BookEntity
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class WorldlineContextBuilderTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun characterViewExcludesCanonFutureAndWriterExcludesRevealContent() {
        val content = FileContentStore(tmp.newFolder("data").toPath())
        val knowledgeStore = KnowledgeStore(content)
        knowledgeStore.save(
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
                    Entity(
                        id = "ent-carol",
                        canonicalName = "卡萝尔",
                        sourceAnchor = FactAnchor(8, 0, 0, ""),
                        firstSeenChapter = 8,
                    ),
                ),
                facts = listOf(
                    Fact(
                        id = "past",
                        entityId = "ent-alice",
                        kind = "persona",
                        factKey = "trait",
                        text = "分叉点前已知",
                        sourceAnchor = FactAnchor(1, 0, 0, ""),
                        readerKnown = true,
                        knownBy = listOf("ent-alice"),
                    ),
                    Fact(
                        id = "future",
                        entityId = "ent-alice",
                        kind = "reveal_content",
                        factKey = "secret",
                        text = "未来真相",
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
            ),
        )
        val builder = WorldlineContextBuilder(knowledgeStore, null)
        val branchKnowledge = BranchKnowledgeFile(
            worldlineId = "wl-1",
            facts = listOf(
                Fact(
                    id = "branch",
                    entityId = "ent-alice",
                    kind = "event",
                    text = "分支已发生",
                    sourceAnchor = FactAnchor(1, 0, 0, ""),
                    knownBy = listOf("ent-alice"),
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
        val worldline = WorldlineFile(
            id = "wl-1",
            bookId = "book-1",
            forkChapter = 2,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        val character = builder.characterView(book, 2, 0, branchKnowledge)
        assertTrue(character.contains("分叉点前已知"))
        assertTrue(character.contains("分支已发生"))
        assertFalse(character.contains("未来真相"))

        val writer = builder.writerContext(book, 2, 0, worldline, branchKnowledge, "plan", "", "")
        assertTrue(writer.contains("分叉点前已知"))
        assertFalse(writer.contains("未来真相"))

        val planner = builder.plannerContext(book, 2, true, worldline, branchKnowledge)
        assertTrue(planner.contains("未来真相"))
        assertTrue(builder.futureOnlyTerms(book, 2).contains("卡萝尔"))
        assertTrue(builder.forbiddenTerms(book, 2).contains("妹妹"))
    }

    @Test
    fun forkTextContextStopsAtTheSelectedParagraph() {
        val builder = WorldlineContextBuilder(
            KnowledgeStore(FileContentStore(tmp.newFolder("data").toPath())),
            null,
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
            episodes = 3,
            local = true,
            createdAt = null,
            legacyJson = null,
        )
        val branch = WorldlineFile(
            id = "wl-forktext",
            bookId = "book-1",
            forkChapter = 2,
            forkParagraph = 1,
            forkText = "第一段\n\n第二段\n\n第三段",
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        val writer = builder.writerContext(book, 2, 1, branch, null, "plan", "", "")
        assertTrue(writer.contains("第一段"))
        assertTrue(writer.contains("第二段"))
        assertFalse(writer.contains("第三段"))
        val planner = builder.plannerContext(book, 2, false, branch, null)
        assertFalse(planner.contains("第三段"))
    }

    @Test
    fun branchHistoryKeepsOlderSummariesAndRecentProse() {
        val builder = WorldlineContextBuilder(
            KnowledgeStore(FileContentStore(tmp.newFolder("data").toPath())),
            null,
        )
        val branch = WorldlineFile(
            id = "wl-history",
            bookId = "book-1",
            chapters = listOf(
                BranchChapter(1, "一", "第一章正文", "第一章摘要"),
                BranchChapter(2, "二", "第二章正文", "第二章摘要"),
                BranchChapter(3, "三", "第三章正文", "第三章摘要"),
            ),
        )
        val history = builder.branchHistory(branch, 5_000)
        assertTrue(history.contains("前情摘要"))
        assertTrue(history.contains("第一章摘要"))
        assertFalse(history.contains("第一章正文"))
        assertTrue(history.contains("最近章节：第 2 章"))
        assertTrue(history.contains("最近章节：第 3 章"))
        assertTrue(history.contains("第二章正文"))
        assertTrue(history.contains("第三章正文"))
    }

    @Test
    fun canonExcerptStopsAtForkPointAndExcludesFutureChapters() {
        val content = FileContentStore(tmp.newFolder("data").toPath())
        content.writeZhAtomic("book", 1, "第一章正文。")
        content.writeZhAtomic("book", 2, "分叉前第一段。\n\n分叉后第二段。")
        content.writeZhAtomic("book", 3, "未来章节。")
        val builder = WorldlineContextBuilder(
            KnowledgeStore(content),
            null,
            content,
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
            episodes = 3,
            local = true,
            createdAt = null,
            legacyJson = null,
        )
        val excerpt = builder.canonExcerpt(book, 2, 1, 5_000)
        assertTrue(excerpt.contains("第一章正文"))
        assertTrue(excerpt.contains("分叉前第一段"))
        assertFalse(excerpt.contains("分叉后第二段"))
        assertFalse(excerpt.contains("未来章节"))

        val branch = WorldlineFile(
            id = "wl-2",
            bookId = "book-1",
            forkChapter = 2,
            forkParagraph = 1,
            intervention = Intervention("爱丽丝", "拒绝", ""),
        )
        val planner = builder.plannerContext(book, 2, false, branch, null)
        assertTrue(planner.contains("分叉前第一段"))
        assertFalse(planner.contains("分叉后第二段"))
        assertFalse(planner.contains("未来章节"))
    }
}
