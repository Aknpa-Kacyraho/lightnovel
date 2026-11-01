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
}
