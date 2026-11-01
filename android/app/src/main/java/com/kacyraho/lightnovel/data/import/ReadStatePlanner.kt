package com.kacyraho.lightnovel.data.import

import com.kacyraho.lightnovel.data.catalog.CatalogAdapter
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

data class PlannedReadState(
    val bookId: String,
    val shelf: String?,
    val favorite: Boolean,
    val hidden: Boolean,
    val progressIdx: Int,
    val progressBlock: Int = 0,
    val progressChar: Int = 0,
    val openedAt: String?,
    val finishedAt: String?,
    val updatedAt: String? = null,
)

object ReadStatePlanner {
    private const val SHELF_STATES = "want,reading,finished,dropped"
    private val json = Json { ignoreUnknownKeys = true }

    fun plan(
        files: Map<String, String>,
        report: MigrationReport,
        aliases: Map<String, String>,
    ): List<PlannedReadState> {
        if (files.isEmpty()) return emptyList()
        val byId = report.books.associateBy { it.id }
        val byStorage = report.books.associateBy { it.storageDir }
        val bySlug = report.books.associateBy { it.slug }
        val bySourceId = report.books.associateBy { "${it.source}:${it.sourceId}" }

        val out = mutableListOf<PlannedReadState>()
        for ((path, raw) in files) {
            val name = path.substringAfterLast('/').removeSuffix(".json")
            if (name.isBlank()) continue
            val source = CatalogAdapter.inferSource(name)
            val sourceId = if (name.startsWith("$source-")) {
                name.removePrefix("$source-")
            } else {
                name
            }
            val book = byId[name]
                ?: byStorage[name]
                ?: bySlug[name]
                ?: byId[CatalogAdapter.resolveAlias(name, aliases)]
                ?: bySourceId["$source:$sourceId"]
                ?: continue

            val obj = runCatching {
                json.parseToJsonElement(raw) as? JsonObject
            }.getOrNull() ?: continue

            val tracking = obj.string("tracking")
                ?.takeIf { it in SHELF_STATES.split(',') }
            val favorite = obj.bool("favorites") ?: obj.bool("favorite") ?: false
            val hidden = obj.bool("hidden") ?: false
            val progress = progressOf(obj)
            val opened = obj.string("opened")
            val finished = obj.string("finished") ?: obj.string("finished_at")
            val dropped = obj.string("dropped")
            val shelf = tracking ?: when {
                finished != null -> "finished"
                dropped != null -> "dropped"
                progress > 0 -> "reading"
                else -> null
            }

            out += PlannedReadState(
                bookId = book.id,
                shelf = shelf,
                favorite = favorite,
                hidden = hidden,
                progressIdx = progress,
                progressBlock = progressInt(obj, "block"),
                progressChar = progressInt(obj, "char"),
                openedAt = opened,
                finishedAt = finished ?: dropped,
                updatedAt = obj.string("updated_at") ?: obj.string("updatedAt"),
            )
        }
        return out.distinctBy { it.bookId }
    }

    private fun progressOf(obj: JsonObject): Int {
        val progress = obj["progress"] ?: return 0
        if (progress is JsonPrimitive) return progress.intOrNull ?: 0
        if (progress is JsonObject) {
            val chapter = progress["chapter"] ?: return 0
            if (chapter is JsonPrimitive) {
                return chapter.intOrNull ?: chapter.contentOrNull?.toIntOrNull() ?: 0
            }
        }
        return 0
    }

    private fun progressInt(obj: JsonObject, key: String): Int {
        val progress = obj["progress"] as? JsonObject ?: return 0
        val value = progress[key] as? JsonPrimitive ?: return 0
        return value.intOrNull ?: value.contentOrNull?.toIntOrNull() ?: 0
    }

    private fun JsonObject.string(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull

    private fun JsonObject.bool(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.booleanOrNull
}
