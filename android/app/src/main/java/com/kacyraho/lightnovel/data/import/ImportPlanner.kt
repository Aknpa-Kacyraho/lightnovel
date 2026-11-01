package com.kacyraho.lightnovel.data.import

import com.kacyraho.lightnovel.data.backup.BackupManifest
import com.kacyraho.lightnovel.data.catalog.Catalog
import com.kacyraho.lightnovel.data.catalog.CatalogAdapter
import com.kacyraho.lightnovel.data.catalog.CatalogItem
import com.kacyraho.lightnovel.data.legacy.ArchiveIndex

data class PlannedBook(
    val id: String,
    val storageDir: String,
    val slug: String,
    val source: String,
    val sourceId: String,
    val title: String,
    val titleZh: String? = null,
    val author: String? = null,
    val episodes: Int = 0,
    val shelf: String?,
    val favorite: Boolean,
    val hidden: Boolean,
    val addedAt: String?,
    val legacyJson: String?,
    val flags: Set<String> = emptySet(),
    val tags: List<String> = emptyList(),
)

data class SlugConflict(
    val id: String,
    val preferredSlug: String,
    val chosenSlug: String,
    val ownerId: String,
)

data class MigrationReport(
    val backupId: String,
    val dirClasses: Map<String, Int>,
    val books: List<PlannedBook>,
    val orphanDirs: List<String>,
    val missingDirs: List<String>,
    val conflicts: List<SlugConflict>,
)

object ImportPlanner {
    private val ACTIVE_SHELF = setOf("reading", "finished", "dropped")

    fun plan(manifest: BackupManifest, catalog: Catalog): MigrationReport {
        val dirs = dirsFrom(manifest)
        val dirClasses = classify(dirs)

        val byId = linkedMapOf<String, CatalogItem>()
        for (item in catalog.candidates.values) byId[item.id] = item
        for (item in catalog.items.values) byId[item.id] = item

        val bySlug = linkedMapOf<String, CatalogItem>()
        for (item in catalog.items.values) {
            item.slug?.let { bySlug.putIfAbsent(it, item) }
        }
        for (item in catalog.candidates.values) {
            item.slug?.let { bySlug.putIfAbsent(it, item) }
        }

        val bySourceId = linkedMapOf<String, CatalogItem>()
        for (item in catalog.items.values) {
            bySourceId.putIfAbsent("${item.source}:${item.sourceId}", item)
        }
        for (item in catalog.candidates.values) {
            bySourceId.putIfAbsent("${item.source}:${item.sourceId}", item)
        }

        val planned = mutableListOf<PlannedBook>()
        val orphanDirs = mutableListOf<String>()
        val usedIds = mutableSetOf<String>()

        for (dir in dirs) {
            val dirSource = CatalogAdapter.inferSource(dir)
            val dirSourceId = if (dir.startsWith("$dirSource-")) {
                dir.removePrefix("$dirSource-")
            } else {
                dir
            }
            val item = byId[dir]
                ?: bySlug[dir]
                ?: byId[CatalogAdapter.resolveAlias(dir, catalog.aliases)]
                ?: bySourceId["$dirSource:$dirSourceId"]

            if (item == null) {
                orphanDirs += dir
                planned += placeholder(dir)
                continue
            }

            val slug = item.slug
                ?: CatalogAdapter.resolveAlias(item.id, catalog.aliases)
            val flags = mutableSetOf<String>()
            if (!CatalogAdapter.isV5Conform(dir)) flags += "id_format_legacy"
            if (item.id != dir) flags += "id_dir_mismatch"
            if (item.id !in catalog.items) flags += "catalog_candidate"

            planned += PlannedBook(
                id = item.id,
                storageDir = dir,
                slug = slug,
                source = item.source,
                sourceId = item.sourceId,
                title = item.title.ifBlank { dir },
                titleZh = item.titleZh,
                author = item.author,
                episodes = item.episodes,
                shelf = item.shelf,
                favorite = item.favorite,
                hidden = item.hidden,
                addedAt = item.addedAt,
                legacyJson = item.rawJson,
                flags = flags,
                tags = item.tags,
            )
            usedIds += item.id
        }

        val missingDirs = catalog.items.values
            .asSequence()
            .filter { item -> item.shelf?.let { it in ACTIVE_SHELF } == true && item.id !in usedIds }
            .map { it.id }
            .sorted()
            .toList()

        val finalBooks = mutableListOf<PlannedBook>()
        val conflicts = mutableListOf<SlugConflict>()
        val taken = linkedMapOf<String, String>()

        for (book in planned.sortedBy { it.id }) {
            val preferred = book.slug
            val owner = taken[preferred]
            if (owner == null || owner == book.id) {
                taken[preferred] = book.id
                finalBooks += book
                continue
            }
            val chosen = CatalogAdapter.chooseSlug(
                candidate = preferred,
                aliases = catalog.aliases,
                taken = taken.keys,
                current = book.id,
            )
            taken[chosen] = book.id
            conflicts += SlugConflict(book.id, preferred, chosen, owner)
            finalBooks += book.copy(slug = chosen, flags = book.flags + "slug_conflict")
        }

        return MigrationReport(
            backupId = manifest.backupId,
            dirClasses = dirClasses,
            books = finalBooks,
            orphanDirs = orphanDirs.sorted(),
            missingDirs = missingDirs,
            conflicts = conflicts,
        )
    }

    private fun placeholder(dir: String): PlannedBook {
        val source = CatalogAdapter.inferSource(dir)
        val sourceId = if (dir.startsWith("$source-")) {
            dir.removePrefix("$source-")
        } else {
            dir
        }
        return PlannedBook(
            id = dir,
            storageDir = dir,
            slug = dir,
            source = source,
            sourceId = sourceId,
            title = dir,
            shelf = null,
            favorite = false,
            hidden = false,
            addedAt = null,
            legacyJson = null,
            flags = setOf("orphan_dir"),
        )
    }

    private fun dirsFrom(manifest: BackupManifest): List<String> =
        ArchiveIndex.from(manifest).books.keys.sorted()

    private fun classify(dirs: List<String>): Map<String, Int> {
        var conform = 0
        var legacyShort = 0
        var legacyOther = 0
        for (dir in dirs) {
            when {
                CatalogAdapter.isV5Conform(dir) -> conform++
                CatalogAdapter.isLegacyShort(dir) -> legacyShort++
                else -> legacyOther++
            }
        }
        return linkedMapOf(
            "v5_conform" to conform,
            "legacy_short" to legacyShort,
            "legacy_other" to legacyOther,
        )
    }
}
