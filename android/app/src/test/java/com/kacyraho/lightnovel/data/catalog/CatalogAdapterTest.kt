package com.kacyraho.lightnovel.data.catalog

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CatalogAdapterTest {
    @Test
    fun parsesV5CatalogAndMergesSidecarAliases() {
        val catalog = CatalogAdapter.load(
            libraryJson = """
                {
                  "schema_version": 1,
                  "items": {
                    "kakuyomu-1": {
                      "id": "kakuyomu-1",
                      "slug": "new-slug",
                      "source": "kakuyomu",
                      "source_id": "1",
                      "title": "Book",
                      "shelf": "reading",
                      "favorite": true,
                      "episodes": 3
                    }
                  },
                  "candidates": {},
                  "aliases": {"old-slug": "new-slug"}
                }
            """.trimIndent(),
            aliasesJson = """{"side-slug":"new-slug"}""",
        )

        val item = catalog.items.getValue("kakuyomu-1")
        assertEquals("new-slug", item.slug)
        assertEquals("kakuyomu", item.source)
        assertEquals("1", item.sourceId)
        assertEquals("reading", item.shelf)
        assertTrue(item.favorite)
        assertEquals(3, item.episodes)
        assertEquals("new-slug", catalog.aliases["old-slug"])
        assertEquals("new-slug", catalog.aliases["side-slug"])
    }

    @Test
    fun parsesLegacyFlatCatalog() {
        val catalog = CatalogAdapter.load(
            """
                {
                  "kakuyomu-9": {"title": "Want", "want": true, "favorites": true},
                  "kakuyomu-10": {"title": "Candidate"}
                }
            """.trimIndent(),
        )

        assertTrue(catalog.items.containsKey("kakuyomu-9"))
        assertTrue(catalog.candidates.containsKey("kakuyomu-10"))
        assertEquals("want", catalog.items.getValue("kakuyomu-9").shelf)
        assertTrue(catalog.items.getValue("kakuyomu-9").favorite)
        assertNull(catalog.candidates.getValue("kakuyomu-10").shelf)
    }

    @Test(expected = CatalogSchemaException::class)
    fun rejectsFutureSchema() {
        CatalogAdapter.load("""{"schema_version":2,"items":{},"candidates":{},"aliases":{}}""")
    }

    @Test
    fun resolvesAliasChainAndCycle() {
        val aliases = mapOf("a" to "b", "b" to "c", "c" to "b")
        assertEquals("b", CatalogAdapter.resolveAlias("a", aliases))
        assertEquals("b", CatalogAdapter.resolveAlias("b", aliases))
    }

    @Test
    fun choosesSlugWithoutStealing() {
        assertEquals("same-2", CatalogAdapter.chooseSlug("same", emptyMap(), listOf("same")))
        assertEquals("same-3", CatalogAdapter.chooseSlug("same", emptyMap(), listOf("same", "same-2")))
        assertEquals("old", CatalogAdapter.chooseSlug("old", mapOf("old" to "id"), emptyList(), "id"))
    }

    @Test
    fun createsStableLocalId() {
        assertTrue(CatalogAdapter.newLocalId().matches(Regex("^local-[0-9a-f]{12}$")))
    }

    @Test
    fun classifiesDirectoriesAndSources() {
        assertTrue(CatalogAdapter.isV5Conform("kakuyomu-123"))
        assertTrue(CatalogAdapter.isV5Conform("local-0123456789ab"))
        assertFalse(CatalogAdapter.isV5Conform("short"))
        assertTrue(CatalogAdapter.isLegacyShort("short"))
        assertEquals("syosetu", CatalogAdapter.inferSource("n1234ab"))
        assertEquals("kakuyomu", CatalogAdapter.inferSource("123456"))
        assertEquals("local", CatalogAdapter.inferSource("local-0123456789ab"))
        assertEquals("kakuyomu-1", CatalogAdapter.sourceSlug("kakuyomu", "1"))
    }
}
