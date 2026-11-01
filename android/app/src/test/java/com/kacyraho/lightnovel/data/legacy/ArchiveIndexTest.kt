package com.kacyraho.lightnovel.data.legacy

import com.kacyraho.lightnovel.fixture.ZipFixture
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ArchiveIndexTest {
    @Test
    fun indexesBooksAndChapterFiles() {
        val manifest = ZipFixture()
            .add("novels/kakuyomu-1/meta.json", "{\"title\":\"A\"}")
            .add("novels/kakuyomu-1/raw/0001.txt", "raw")
            .add("novels/kakuyomu-1/chapters/0001.txt", "zh")
            .add("novels/kakuyomu-1/chapters/0001.meta.json", "{}")
            .add("novels/short-2/raw/0002.txt", "raw2")
            .add("data/library.json", "{}")
            .manifest()

        val index = ArchiveIndex.from(manifest)
        val book = index.books.getValue("kakuyomu-1")

        assertEquals("novels/kakuyomu-1/meta.json", book.metaPath)
        assertEquals(1, book.chapters.size)
        val chapter = book.chapters.getValue(1)
        assertEquals("novels/kakuyomu-1/raw/0001.txt", chapter.rawPath)
        assertEquals("novels/kakuyomu-1/chapters/0001.txt", chapter.zhPath)
        assertEquals("novels/kakuyomu-1/chapters/0001.meta.json", chapter.sidecarPath)

        assertTrue(index.books.containsKey("short-2"))
        assertEquals(2, index.books.getValue("short-2").chapters.getValue(2).idx)
    }

    @Test
    fun ignoresUnrelatedAndMalformedEntries() {
        val manifest = ZipFixture()
            .add("novels/kakuyomu-1/raw/not-a-number.txt", "x")
            .add("novels/kakuyomu-1/other/0001.txt", "x")
            .add("data/library.json", "{}")
            .manifest()

        val index = ArchiveIndex.from(manifest)
        assertTrue(index.books.getValue("kakuyomu-1").chapters.isEmpty())
    }
}
