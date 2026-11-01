package com.kacyraho.lightnovel.data.glossary

import com.kacyraho.lightnovel.data.translation.TranslationConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class GlossaryStoreTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun savesLoadsAndRevisionsTerms() {
        val store = GlossaryStore(tmp.newFolder("data").toPath())
        val first = store.save(
            listOf(
                GlossaryEntry("alice", "アリス", "爱丽丝", listOf("アリスさん")),
            ),
        )
        assertTrue(first.revision.isNotBlank())

        val loaded = store.load()
        assertEquals(1, loaded.entries.size)
        assertEquals("爱丽丝", loaded.entries.single().target)
        assertEquals(first.revision, loaded.revision)

        val second = store.save(
            listOf(
                GlossaryEntry("alice", "アリス", "艾莉丝"),
            ),
        )
        assertNotEquals(first.revision, second.revision)
        assertEquals("艾莉丝", store.load().entries.single().target)
    }

    @Test
    fun hitsSourceOrAliasAndIgnoresMissingTerms() {
        val entries = listOf(
            GlossaryEntry("alice", "アリス", "爱丽丝", listOf("アリスさん")),
            GlossaryEntry("bob", "ボブ", "鲍勃"),
        )
        val store = GlossaryStore(tmp.newFolder("data").toPath())
        assertEquals(listOf("alice"), store.hits(entries, "アリスさんが来た").map { it.id })
        assertEquals(listOf("bob"), store.hits(entries, "ボブ").map { it.id })
        assertTrue(store.hits(entries, "誰もいない").isEmpty())
    }

    @Test
    fun glossaryRevisionInvalidatesConfigKey() {
        val plain = TranslationConfig(model = "deepseek-flash")
        val withGlossary = plain.copy(glossaryRevision = "rev-1")
        assertNotEquals(plain.cacheKey(), withGlossary.cacheKey())
    }
}
