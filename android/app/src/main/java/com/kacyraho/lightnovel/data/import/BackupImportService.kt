package com.kacyraho.lightnovel.data.import

import com.kacyraho.lightnovel.data.backup.BackupArchive
import com.kacyraho.lightnovel.data.backup.BackupVerifyResult
import com.kacyraho.lightnovel.data.backup.BackupVerifier
import com.kacyraho.lightnovel.data.catalog.Catalog
import com.kacyraho.lightnovel.data.catalog.CatalogAdapter
import com.kacyraho.lightnovel.data.local.AliasEntity
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.BookTags
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
)

data class ImportApplyResult(
    val books: Int,
    val readStates: Int,
    val aliases: Int,
    val chapters: Int,
)

class BackupImportService(
    private val verifier: BackupVerifier = BackupVerifier(),
) {
    fun plan(path: Path): ImportPlan {
        val verify = verifier.verify(path)
        val manifest = verify.requireOk()
        val (catalog, readStateFiles, sidecarStatuses) = ZipFile(path.toFile()).use { zip ->
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
            Triple(CatalogAdapter.load(library, aliases), files, sidecars)
        }
        val report = ImportPlanner.plan(manifest, catalog)
        val chapters = ChapterPlanner.plan(manifest, report, sidecarStatuses)
        val readStates = ReadStatePlanner.plan(readStateFiles, report, catalog.aliases)
        return ImportPlan(verify, catalog, report, chapters, readStates)
    }

    suspend fun apply(plan: ImportPlan, dao: LibraryDao): ImportApplyResult {
        val books = plan.report.books.map { book ->
            BookEntity(
                id = book.id,
                storageDir = book.storageDir,
                slug = book.slug,
                source = book.source,
                sourceId = book.sourceId,
                title = book.title,
                titleZh = book.titleZh,
                author = book.author,
                tagsJson = BookTags.encode(book.tags),
                genre = null,
                episodes = book.episodes,
                local = book.source == "local",
                createdAt = book.addedAt,
                legacyJson = book.legacyJson,
            )
        }
        val importedStates = plan.readStates.associateBy { it.bookId }
        val states = plan.report.books.map { book ->
            val state = importedStates[book.id]
            ReadStateEntity(
                bookId = book.id,
                shelf = state?.shelf ?: book.shelf,
                favorite = state?.favorite ?: book.favorite,
                hidden = state?.hidden ?: book.hidden,
                progressIdx = state?.progressIdx ?: 0,
                progressBlock = state?.progressBlock ?: 0,
                progressChar = state?.progressChar ?: 0,
                openedAt = state?.openedAt,
                finishedAt = state?.finishedAt,
                updatedAt = state?.updatedAt
                    ?: state?.openedAt
                    ?: state?.finishedAt
                    ?: book.addedAt
                    ?: Instant.now().toString(),
            )
        }
        val aliases = plan.catalog.aliases.map { (old, final) ->
            AliasEntity(oldSlug = old, finalSlug = final)
        }
        val chapters = plan.chapters.map { chapter ->
            com.kacyraho.lightnovel.data.local.ChapterEntity(
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
        dao.upsertBooks(books)
        dao.upsertReadStates(states)
        dao.upsertAliases(aliases)
        dao.upsertChapters(chapters)
        return ImportApplyResult(books.size, states.size, aliases.size, chapters.size)
    }
}
