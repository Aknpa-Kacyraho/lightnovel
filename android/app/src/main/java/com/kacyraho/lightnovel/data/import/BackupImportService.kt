package com.kacyraho.lightnovel.data.import

import com.kacyraho.lightnovel.data.backup.BackupArchive
import com.kacyraho.lightnovel.data.backup.BackupBookmark
import com.kacyraho.lightnovel.data.backup.BackupVerifyResult
import com.kacyraho.lightnovel.data.backup.BackupVerifier
import com.kacyraho.lightnovel.data.catalog.Catalog
import com.kacyraho.lightnovel.data.catalog.CatalogAdapter
import com.kacyraho.lightnovel.data.local.AliasEntity
import com.kacyraho.lightnovel.data.local.BookmarkEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.LibraryDao
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import java.time.Instant
import java.nio.file.Path
import java.util.zip.ZipFile
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

data class ImportPlan(
    val verify: BackupVerifyResult,
    val catalog: Catalog,
    val report: MigrationReport,
    val chapters: List<PlannedChapter>,
    val readStates: List<PlannedReadState>,
    val bookmarks: List<BackupBookmark> = emptyList(),
)

data class ImportApplyResult(
    val books: Int,
    val readStates: Int,
    val aliases: Int,
    val chapters: Int,
    val bookmarks: Int = 0,
)

private data class ParsedBackup(
    val catalog: Catalog,
    val files: Map<String, String>,
    val sidecars: Map<String, String>,
    val bookmarks: List<BackupBookmark>,
)

class BackupImportService(
    private val verifier: BackupVerifier = BackupVerifier(),
) {
    private val json = Json { ignoreUnknownKeys = true }

    fun plan(path: Path): ImportPlan {
        val verify = verifier.verify(path)
        val manifest = verify.requireOk()
        val parsed = ZipFile(path.toFile()).use { zip ->
            val library = BackupArchive.readText(zip, "data/library.json")
            val aliases = BackupArchive.readText(zip, "data/slug-aliases.json")
            val files = linkedMapOf<String, String>()
            val sidecars = linkedMapOf<String, String>()
            for (entry in manifest.entries) {
                val parts = entry.path.split('/')
                if (parts.size == 3 && parts[0] == "data" && parts[1] == "books" &&
                    parts[2].endsWith(".json")
                ) {
                    BackupArchive.readText(zip, entry.path, 2 * 1024 * 1024)?.let {
                        files[entry.path] = it
                    }
                }
                if (parts.size == 4 && parts[0] == "novels" &&
                    parts[2] == "chapters" && parts[3].endsWith(".meta.json")
                ) {
                    val text = BackupArchive.readText(zip, entry.path, 1 * 1024 * 1024)
                    if (text != null) {
                        val status = runCatching {
                            val obj = Json.parseToJsonElement(text) as JsonObject
                            obj["status"]?.jsonPrimitive?.contentOrNull
                        }.getOrNull()
                        if (status == "complete" || status == "partial") {
                            sidecars[entry.path] = status
                        }
                    }
                }
            }
            val bookmarks = BackupArchive.readText(zip, "data/bookmarks.json", 4 * 1024 * 1024)
                ?.let { raw ->
                    runCatching {
                        json.decodeFromString<List<BackupBookmark>>(raw)
                    }.getOrNull()
                }
                .orEmpty()
            ParsedBackup(
                catalog = CatalogAdapter.load(library, aliases),
                files = files,
                sidecars = sidecars,
                bookmarks = bookmarks,
            )
        }
        val report = ImportPlanner.plan(manifest, parsed.catalog)
        val chapters = ChapterPlanner.plan(manifest, report, parsed.sidecars)
        val readStates = ReadStatePlanner.plan(parsed.files, report, parsed.catalog.aliases)
        return ImportPlan(verify, parsed.catalog, report, chapters, readStates, parsed.bookmarks)
    }

    suspend fun apply(plan: ImportPlan, dao: LibraryDao): ImportApplyResult {
        val chapterCounts = plan.chapters.groupingBy { it.bookId }.eachCount()
        val existingBooks = plan.report.books
            .mapNotNull { dao.book(it.id) }
            .associateBy { it.id }
        val books = plan.report.books.map { book ->
            mergeBook(
                existing = existingBooks[book.id],
                planned = book,
                chapterCount = chapterCounts[book.id] ?: 0,
            )
        }
        val importedStates = plan.readStates.associateBy { it.bookId }
        val existingStates = plan.report.books
            .mapNotNull { dao.readState(it.id) }
            .associateBy { it.bookId }
        val states = plan.report.books.map { book ->
            val imported = importedStates[book.id]
            if (imported == null) {
                // No state file in the backup: keep local progress instead of
                // synthesising a "newer" state that would reset it.
                existingStates[book.id] ?: defaultState(book)
            } else {
                mergeReadState(
                    existing = existingStates[book.id],
                    planned = plannedState(book, imported),
                )
            }
        }
        val aliases = plan.catalog.aliases.map { (old, final) ->
            AliasEntity(oldSlug = old, finalSlug = final)
        }
        val existingChapterKeys = plan.report.books
            .flatMap { dao.chapters(it.id) }
            .map { it.bookId to it.idx }
            .toSet()
        val chapters = missingChapters(plan.chapters, existingChapterKeys).map { chapter ->
            ChapterEntity(
                bookId = chapter.bookId,
                idx = chapter.idx,
                title = null,
                titleZh = null,
                rawPath = chapter.rawPath,
                zhPath = chapter.zhPath,
                status = chapter.status,
                tokenIn = 0,
                tokenOut = 0,
                model = null,
                updatedAt = null,
            )
        }
        val importedBookIds = plan.report.books.map { it.id }.toSet()
        val existingBookmarkKeys = dao.allBookmarks()
            .map { Triple(it.bookId, it.chapterIdx, it.paragraphId) }
            .toSet()
        val bookmarks = plan.bookmarks
            .asSequence()
            .filter { it.bookId in importedBookIds }
            .distinctBy { Triple(it.bookId, it.chapterIdx, it.paragraphId) }
            .filter { Triple(it.bookId, it.chapterIdx, it.paragraphId) !in existingBookmarkKeys }
            .map { bookmark ->
                BookmarkEntity(
                    bookId = bookmark.bookId,
                    chapterIdx = bookmark.chapterIdx,
                    paragraphId = bookmark.paragraphId,
                    charOffset = bookmark.charOffset,
                    preview = bookmark.preview,
                    createdAt = bookmark.createdAt.ifBlank { Instant.now().toString() },
                )
            }
            .toList()

        dao.upsertBooks(books)
        dao.upsertReadStates(states)
        dao.upsertAliases(aliases)
        dao.upsertChapters(chapters)
        dao.upsertBookmarks(bookmarks)
        return ImportApplyResult(
            books = books.size,
            readStates = states.size,
            aliases = aliases.size,
            chapters = chapters.size,
            bookmarks = bookmarks.size,
        )
    }

    private fun plannedState(book: PlannedBook, state: PlannedReadState): ReadStateEntity =
        ReadStateEntity(
            bookId = book.id,
            shelf = state.shelf ?: book.shelf,
            favorite = state.favorite,
            hidden = state.hidden,
            progressIdx = state.progressIdx,
            progressBlock = state.progressBlock,
            progressChar = state.progressChar,
            openedAt = state.openedAt,
            finishedAt = state.finishedAt,
            // Only trust timestamps that came from the backup's state file.
            // A missing timestamp must not let an old backup reset local progress.
            updatedAt = state.updatedAt ?: state.openedAt ?: state.finishedAt,
        )

    private fun defaultState(book: PlannedBook): ReadStateEntity =
        ReadStateEntity(
            bookId = book.id,
            shelf = book.shelf,
            favorite = book.favorite,
            hidden = book.hidden,
            progressIdx = 0,
            progressBlock = 0,
            progressChar = 0,
            openedAt = null,
            finishedAt = null,
            updatedAt = book.addedAt ?: Instant.now().toString(),
        )
}
