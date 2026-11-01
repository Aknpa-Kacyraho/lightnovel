package com.kacyraho.lightnovel.data.import

import java.nio.file.Files
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class LocalTextParserTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun splitsTxtByChapterHeadings() {
        val parsed = LocalTextParser.parseTxt(
            "测试小说.txt",
            """
            前言内容。

            第一章 开始
            第一章正文。

            第二章 继续
            第二章正文。
            """.trimIndent(),
        )

        assertEquals("测试小说", parsed.title)
        assertEquals(listOf("前言", "第一章 开始", "第二章 继续"), parsed.chapters.map { it.title })
        assertTrue(parsed.chapters[1].text.contains("第一章正文"))
    }

    @Test
    fun parsesBasicEpub() {
        val file = tmp.newFile("book.epub").toPath()
        ZipOutputStream(Files.newOutputStream(file)).use { zip ->
            zip.putNextEntry(ZipEntry("META-INF/container.xml"))
            zip.write(
                """<?xml version="1.0"?><container><rootfiles>
                <rootfile full-path="OEBPS/content.opf"/></rootfiles></container>"""
                    .toByteArray(),
            )
            zip.closeEntry()
            zip.putNextEntry(ZipEntry("OEBPS/content.opf"))
            zip.write(
                """<?xml version="1.0"?><package>
                <metadata><dc:title>测试 EPUB</dc:title><dc:creator>作者</dc:creator></metadata>
                <manifest><item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/></manifest>
                <spine><itemref idref="c1"/></spine></package>"""
                    .toByteArray(),
            )
            zip.closeEntry()
            zip.putNextEntry(ZipEntry("OEBPS/chapter1.xhtml"))
            zip.write(
                """<html><body><h1>第一章</h1><p>正文第一段。</p><p>正文第二段。</p></body></html>"""
                    .toByteArray(),
            )
            zip.closeEntry()
        }

        val parsed = LocalTextParser.parseEpub("book.epub", file)

        assertEquals("测试 EPUB", parsed.title)
        assertEquals("作者", parsed.author)
        assertEquals(1, parsed.chapters.size)
        assertEquals("第一章", parsed.chapters.single().title)
        assertTrue(parsed.chapters.single().text.contains("正文第二段"))
    }
}
