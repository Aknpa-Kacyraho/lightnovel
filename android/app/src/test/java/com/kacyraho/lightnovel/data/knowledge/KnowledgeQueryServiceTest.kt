package com.kacyraho.lightnovel.data.knowledge

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class KnowledgeQueryServiceTest {
    private val service = KnowledgeQueryService(KnowledgeStore(NoopContentStore()))

    private val alice = Entity(
        id = "ent-alice",
        canonicalName = "爱丽丝",
        aliases = listOf("アリス"),
        readerKnown = true,
        firstSeenChapter = 1,
        lastConfirmedChapter = 10,
    )
    private val bob = Entity(
        id = "ent-bob",
        canonicalName = "鲍勃",
        aliases = listOf("ボブ"),
        readerKnown = true,
        firstSeenChapter = 2,
    )
    private val carol = Entity(
        id = "ent-carol",
        canonicalName = "卡萝尔",
        aliases = listOf("キャロル"),
        readerKnown = true,
        sourceAnchor = FactAnchor(10, 0, 0, ""),
        firstSeenChapter = 10,
    )

    private val fact3 = Fact(
        id = "f3",
        entityId = alice.id,
        kind = "persona",
        factKey = "identity.role",
        text = "剑士",
        sourceAnchor = FactAnchor(3, 0, 0, ""),
        firstSeenChapter = 3,
        lastConfirmedChapter = 3,
        validFromChapter = 3,
        validUntilChapter = 9,
        readerKnown = true,
    )
    private val fact5a = Fact(
        id = "f5a",
        entityId = alice.id,
        kind = "persona",
        factKey = "habit",
        text = "第五章中段",
        sourceAnchor = FactAnchor(5, 1, 0, ""),
        firstSeenChapter = 5,
        lastConfirmedChapter = 5,
        validFromChapter = 5,
        readerKnown = true,
    )
    private val fact5b = Fact(
        id = "f5b",
        entityId = alice.id,
        kind = "event",
        factKey = "event",
        text = "第五章后半",
        sourceAnchor = FactAnchor(5, 3, 0, ""),
        firstSeenChapter = 5,
        lastConfirmedChapter = 5,
        validFromChapter = 5,
        readerKnown = true,
    )
    private val fact10 = Fact(
        id = "f10",
        entityId = alice.id,
        kind = "persona",
        factKey = "identity.role",
        text = "法师",
        sourceAnchor = FactAnchor(10, 0, 0, ""),
        firstSeenChapter = 10,
        lastConfirmedChapter = 10,
        validFromChapter = 10,
        supersedes = "f3",
        readerKnown = true,
    )
    private val carolFact = Fact(
        id = "fc",
        entityId = carol.id,
        kind = "persona",
        factKey = "identity",
        text = "后期角色",
        sourceAnchor = FactAnchor(10, 0, 0, ""),
        firstSeenChapter = 10,
        lastConfirmedChapter = 10,
        readerKnown = true,
    )

    private val knowledge = KnowledgeFile(
        workId = "book",
        entities = listOf(alice, bob, carol),
        facts = listOf(fact3, fact5a, fact5b, fact10, carolFact),
        extractedChapters = (1..10).toList(),
        canonExtractedThrough = 10,
    )

    @Test
    fun filtersByReadAnchorAndParagraph() {
        val atMid = service.readerItems(knowledge, FactAnchor(5, 1, Int.MAX_VALUE, ""))
            .filter { it.itemType == "fact" }
            .map { it.id }
        assertTrue("f3" in atMid)
        assertTrue("f5a" in atMid)
        assertFalse("f5b" in atMid)
        assertFalse("f10" in atMid)
        assertFalse("fc" in atMid)

        val atParagraphZero = service.readerItems(
            knowledge,
            FactAnchor(5, 0, Int.MAX_VALUE, ""),
        ).filter { it.itemType == "fact" }.map { it.id }
        assertTrue("f3" in atParagraphZero)
        assertFalse("f5a" in atParagraphZero)
    }

    @Test
    fun resolvesSupersededFactsByReadChapter() {
        val atFive = service.readerItems(knowledge, FactAnchor(5, 1, Int.MAX_VALUE, ""))
            .filter { it.itemType == "fact" }
            .map { it.id }
        assertTrue("f3" in atFive)
        assertFalse("f10" in atFive)

        val atTen = service.readerItems(knowledge, FactAnchor(10, 0, Int.MAX_VALUE, ""))
            .filter { it.itemType == "fact" }
            .map { it.id }
        assertFalse("f3" in atTen)
        assertTrue("f10" in atTen)
    }

    @Test
    fun reportsExtractionLagAndDegradedLocation() {
        val status = service.status(
            knowledge = knowledge.copy(extractedChapters = listOf(1), canonExtractedThrough = 1),
            readAnchor = FactAnchor(2, 0, Int.MAX_VALUE, ""),
            displayAnchor = null,
            translatedThrough = 2,
            locationDegraded = false,
        )
        assertTrue(status.extractionUpdating)
        assertFalse(status.translationUpdating)

        val degraded = service.readerItems(
            knowledge,
            FactAnchor(2, -1, -1, ""),
        ).filter { it.itemType == "fact" }.map { it.id }
        assertTrue("f3" !in degraded)
        assertTrue(degraded.isEmpty())
    }

    @Test
    fun queryEntriesMatchAliasesAndOnlyVisibleFacts() {
        val entries = service.queryEntries(
            knowledge,
            FactAnchor(5, 1, Int.MAX_VALUE, ""),
            listOf("アリスはボブを見た。"),
        )
        val aliceEntry = entries.firstOrNull { it.entityId == alice.id }
        val bobEntry = entries.firstOrNull { it.entityId == bob.id }
        assertTrue(aliceEntry != null)
        assertTrue(aliceEntry!!.visibleFactCount >= 2)
        assertTrue(bobEntry == null)
    }

    @Test
    fun visibleNamesExcludeFutureEntities() {
        val names = service.visibleNames(knowledge, FactAnchor(5, 1, Int.MAX_VALUE, ""))
        assertTrue(names.containsKey("爱丽丝"))
        assertTrue(names.containsKey("アリス"))
        assertFalse(names.containsKey("卡萝尔"))
        assertFalse(names.containsKey("キャロル"))
    }

    @Test
    fun entityCardContainsVisibleRelationsAndVoices() {
        val relation = Relation(
            id = "r1",
            fromEntityId = alice.id,
            toEntityId = bob.id,
            type = "ally",
            label = "同伴",
            sourceAnchor = FactAnchor(2, 0, 0, ""),
            firstSeenChapter = 2,
            readerKnown = true,
        )
        val voice = VoiceFact(
            id = "v1",
            entityId = alice.id,
            dimension = "voice",
            text = "短句",
            sourceAnchor = FactAnchor(3, 0, 0, ""),
            firstSeenChapter = 3,
            readerKnown = true,
        )
        val card = service.entityCard(
            knowledge.copy(relations = listOf(relation), voiceFacts = listOf(voice)),
            alice.id,
            FactAnchor(5, 1, Int.MAX_VALUE, ""),
            service.status(
                knowledge,
                FactAnchor(5, 1, Int.MAX_VALUE, ""),
                null,
                5,
                false,
            ),
        )
        assertTrue(card != null)
        assertEquals("鲍勃", card!!.relatedNames[bob.id])
        assertEquals(1, card.relations.size)
        assertEquals(1, card.voiceFacts.size)
    }

    private class NoopContentStore : com.kacyraho.lightnovel.core.storage.ContentStore {
        override val root = java.nio.file.Paths.get(".")
        override fun paths(storageDir: String) =
            com.kacyraho.lightnovel.core.storage.BookPaths(root, storageDir)
        override fun readRaw(storageDir: String, idx: Int): String? = null
        override fun readZh(storageDir: String, idx: Int): String? = null
        override fun readSidecar(
            storageDir: String,
            idx: Int,
        ): com.kacyraho.lightnovel.core.storage.ChapterSidecar? = null
        override fun writeRawAtomic(storageDir: String, idx: Int, text: String) = Unit
        override fun writeZhAtomic(storageDir: String, idx: Int, text: String) = Unit
        override fun writeSidecar(
            storageDir: String,
            idx: Int,
            sidecar: com.kacyraho.lightnovel.core.storage.ChapterSidecar,
        ) = Unit
    }
}
