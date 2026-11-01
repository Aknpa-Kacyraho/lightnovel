package com.kacyraho.lightnovel.data.export

import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.LibraryDao
import java.io.OutputStream
import java.util.UUID
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class EpubExporter(
    private val dao: LibraryDao,
    private val contentStore: ContentStore,
) {
    suspend fun export(book: BookEntity, output: OutputStream) = withContext(Dispatchers.IO) {
        val chapters = dao.chapters(book.id)
        val title = book.titleZh ?: book.title
        ZipOutputStream(output).use { zip ->
            zip.putNextEntry(ZipEntry("mimetype").apply {
                method = ZipEntry.STORED
                size = MIMETYPE.toByteArray().size.toLong()
                compressedSize = size
                crc = crc32(MIMETYPE.toByteArray())
            })
            zip.write(MIMETYPE.toByteArray())
            zip.closeEntry()

            put(zip, "META-INF/container.xml", containerXml())
            put(zip, "OEBPS/content.opf", contentOpf(book, title, chapters))
            put(zip, "OEBPS/nav.xhtml", navXhtml(title, chapters))
            put(zip, "OEBPS/style.css", STYLE)

            chapters.forEachIndexed { index, chapter ->
                val text = contentStore.readZh(book.storageDir, chapter.idx)
                    ?: contentStore.readRaw(book.storageDir, chapter.idx)
                    ?: ""
                val chapterTitle = chapter.titleZh ?: chapter.title ?: "第 ${chapter.idx} 章"
                put(zip, "OEBPS/chapter-${chapter.idx}.xhtml", chapterXhtml(chapterTitle, text))
            }
            zip.finish()
        }
    }

    private fun put(zip: ZipOutputStream, path: String, text: String) {
        zip.putNextEntry(ZipEntry(path))
        zip.write(text.toByteArray(Charsets.UTF_8))
        zip.closeEntry()
    }

    private fun containerXml(): String =
        """<?xml version="1.0" encoding="UTF-8"?>
        <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
          <rootfiles>
            <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
          </rootfiles>
        </container>""".trimIndent()

    private fun contentOpf(book: BookEntity, title: String, chapters: List<com.kacyraho.lightnovel.data.local.ChapterEntity>): String {
        val manifest = buildString {
            append("<item id=\"nav\" href=\"nav.xhtml\" media-type=\"application/xhtml+xml\" properties=\"nav\"/>")
            append("<item id=\"css\" href=\"style.css\" media-type=\"text/css\"/>")
            for (chapter in chapters) {
                append("<item id=\"c${chapter.idx}\" href=\"chapter-${chapter.idx}.xhtml\" media-type=\"application/xhtml+xml\"/>")
            }
        }
        val spine = chapters.joinToString("") { "<itemref idref=\"c${it.idx}\"/>" }
        return """<?xml version="1.0" encoding="UTF-8"?>
        <package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
          <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
            <dc:identifier id="bookid">urn:uuid:${UUID.randomUUID()}</dc:identifier>
            <dc:title>${xml(title)}</dc:title>
            <dc:language>zh-CN</dc:language>
            <dc:creator>${xml(book.author ?: "")}</dc:creator>
          </metadata>
          <manifest>$manifest</manifest>
          <spine>$spine</spine>
        </package>""".trimIndent()
    }

    private fun navXhtml(title: String, chapters: List<com.kacyraho.lightnovel.data.local.ChapterEntity>): String =
        """<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
        <head><title>${xml(title)}</title></head>
        <body><nav epub:type="toc"><h1>${xml(title)}</h1><ol>
        ${chapters.joinToString("") { "<li><a href=\"chapter-${it.idx}.xhtml\">${xml(it.titleZh ?: it.title ?: "第 ${it.idx} 章")}</a></li>" }}
        </ol></nav></body></html>""".trimIndent()

    private fun chapterXhtml(title: String, text: String): String {
        val body = text.replace("\r\n", "\n").split("\n\n").joinToString("") { paragraph ->
            "<p>" + xml(paragraph).replace("\n", "<br/>") + "</p>"
        }
        return """<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head><title>${xml(title)}</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
        <body><h1>${xml(title)}</h1>$body</body></html>""".trimIndent()
    }

    private fun xml(value: String): String = value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")

    private fun crc32(bytes: ByteArray): Long {
        val crc = java.util.zip.CRC32()
        crc.update(bytes)
        return crc.value
    }

    private companion object {
        const val MIMETYPE = "application/epub+zip"
        const val STYLE = "body { font-family: serif; line-height: 1.7; margin: 1em; } h1 { font-size: 1.3em; } p { text-indent: 2em; margin: 0.5em 0; }"
    }
}
