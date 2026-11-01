package com.kacyraho.lightnovel.data.catalog

import java.util.UUID
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

object CatalogAdapter {
    const val SCHEMA_VERSION = 1
    private val SHELF_STATES = setOf("want", "reading", "finished", "dropped")
    private val KNOWN_PREFIXES = listOf("kakuyomu-", "syosetu-", "local-")
    private val LOCAL_ID = Regex("^local-[0-9a-f]{12}$")
    private val SYOSETU_LEGACY = Regex("^n\\d{4}[a-z]+$")
    private val LEGACY_SHORT = Regex("^[A-Za-z0-9_-]{1,24}$")
    private val JSON = Json { ignoreUnknownKeys = true }

    fun emptyCatalog(): Catalog = Catalog(
        schemaVersion = SCHEMA_VERSION,
        items = linkedMapOf(),
        candidates = linkedMapOf(),
        aliases = linkedMapOf(),
    )

    fun load(libraryJson: String?, aliasesJson: String? = null): Catalog {
        val catalog = if (libraryJson.isNullOrBlank()) {
            emptyCatalog()
        } else {
            val root = parse(libraryJson, "library.json")
            val obj = root as? JsonObject
                ?: throw CatalogSchemaException("library.json 必须是对象")
            val base = if (isCatalog(obj)) loadCatalogObject(obj) else fromLegacyFlat(obj)
            val aliases = linkedMapOf<String, String>()
            aliases.putAll(base.aliases)
            aliases.putAll(parseAliases(aliasesJson))
            base.copy(aliases = aliases)
        }
        return catalog
    }

    private fun isCatalog(obj: JsonObject): Boolean =
        obj.containsKey("schema_version") ||
            listOf("items", "candidates", "aliases").all { obj[it] is JsonObject }

    fun isV5Conform(dir: String): Boolean =
        LOCAL_ID.matches(dir) ||
            (dir.startsWith("kakuyomu-") && dir.length > "kakuyomu-".length) ||
            (dir.startsWith("syosetu-") && dir.length > "syosetu-".length)

    fun isLegacyShort(dir: String): Boolean = LEGACY_SHORT.matches(dir)

    fun isSyosetuLegacyId(id: String): Boolean = SYOSETU_LEGACY.matches(id)

    fun inferSource(id: String, explicit: String? = null): String {
        val source = explicit?.trim().orEmpty()
        if (source.isNotEmpty()) return source
        return when {
            id.startsWith("local-") -> "local"
            id.startsWith("kakuyomu-") -> "kakuyomu"
            id.startsWith("syosetu-") -> "syosetu"
            SYOSETU_LEGACY.matches(id) -> "syosetu"
            else -> "kakuyomu"
        }
    }

    fun sourceSlug(source: String, sourceId: String): String = "$source-$sourceId"

    fun newLocalId(): String =
        "local-" + UUID.randomUUID().toString().replace("-", "").take(12).lowercase()

    fun resolveAlias(slug: String, aliases: Map<String, String>): String {
        var current = slug
        val seen = mutableSetOf<String>()
        while (current in aliases && current !in seen) {
            seen.add(current)
            current = aliases.getValue(current)
        }
        return current
    }

    fun chooseSlug(
        candidate: String,
        aliases: Map<String, String>,
        taken: Collection<String> = emptyList(),
        current: String = "",
    ): String {
        if (candidate in aliases && aliases[candidate] == current) return candidate
        if (candidate !in aliases && candidate !in taken) return candidate
        var n = 2
        while ("$candidate-$n" in aliases || "$candidate-$n" in taken) n++
        return "$candidate-$n"
    }

    private fun loadCatalogObject(obj: JsonObject): Catalog {
        val version = (obj["schema_version"] as? JsonPrimitive)?.intOrNull
            ?: throw CatalogSchemaException("catalog.schema_version 缺失")
        if (version != SCHEMA_VERSION) {
            throw CatalogSchemaException(
                "不支持的 catalog.schema_version=$version，期望 $SCHEMA_VERSION",
            )
        }
        val items = parseZone(obj["items"], "items")
        val candidates = parseZone(obj["candidates"], "candidates")
        val aliases = linkedMapOf<String, String>()
        val aliasObj = obj["aliases"] as? JsonObject
            ?: throw CatalogSchemaException("catalog.aliases 必须是对象")
        for ((old, value) in aliasObj) {
            val final = (value as? JsonPrimitive)?.contentOrNull
                ?: throw CatalogSchemaException("catalog.aliases[$old] 必须是字符串")
            aliases[old] = final
        }
        return Catalog(SCHEMA_VERSION, items, candidates, aliases)
    }

    private fun parseZone(element: JsonElement?, name: String): LinkedHashMap<String, CatalogItem> {
        val obj = element as? JsonObject
            ?: throw CatalogSchemaException("catalog.$name 必须是对象")
        val out = linkedMapOf<String, CatalogItem>()
        for ((key, value) in obj) {
            val row = value as? JsonObject
                ?: throw CatalogSchemaException("catalog.$name[$key] 必须是对象")
            out[key] = normalize(key, row)
        }
        return out
    }

    private fun fromLegacyFlat(obj: JsonObject): Catalog {
        val items = linkedMapOf<String, CatalogItem>()
        val candidates = linkedMapOf<String, CatalogItem>()
        for ((key, value) in obj) {
            val row = value as? JsonObject ?: continue
            val item = normalize(key, row)
            if (isItem(item)) items[key] = item else candidates[key] = item
        }
        return Catalog(SCHEMA_VERSION, items, candidates, linkedMapOf())
    }

    private fun normalize(key: String, row: JsonObject): CatalogItem {
        val rawId = row.string("id") ?: key
        val source = inferSource(rawId, row.string("source"))
        val sourceId = row.string("source_id") ?: stripPrefix(rawId, source)
        val id = canonicalId(rawId, source)
        val explicitSlug = row.string("slug")
        val slug = explicitSlug ?: when {
            KNOWN_PREFIXES.any { rawId.startsWith(it) } -> rawId
            id != rawId -> id
            else -> null
        }
        val shelf = row.string("shelf")?.takeIf { it in SHELF_STATES }
            ?: if (row.bool("want") == true) "want" else null
        val title = row.string("title") ?: ""
        val titleZh = row.string("title_zh") ?: row.string("zh_title")
        val episodes = when (val e = row["episodes"]) {
            is JsonPrimitive -> e.intOrNull ?: 0
            is JsonArray -> e.size
            else -> 0
        }
        val tags = (row["tags"] as? JsonArray)
            ?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
            ?.map(String::trim)
            ?.filter(String::isNotBlank)
            ?.distinct()
            .orEmpty()
        return CatalogItem(
            id = id,
            slug = slug,
            source = source,
            sourceId = sourceId,
            title = title,
            titleZh = titleZh,
            author = row.string("author"),
            shelf = shelf,
            favorite = row.bool("favorite") ?: row.bool("favorites") ?: false,
            hidden = row.bool("hidden") == true,
            addedAt = row.string("added_at"),
            firstSeen = row.string("source_first_seen") ?: row.string("first_seen"),
            episodes = episodes,
            local = source == "local",
            rawJson = row.toString(),
            tags = tags,
        )
    }

    private fun canonicalId(rawId: String, source: String): String {
        if (KNOWN_PREFIXES.any { rawId.startsWith(it) }) return rawId
        if (source == "kakuyomu" && Regex("^\\d{5,}$").matches(rawId)) {
            return sourceSlug(source, rawId)
        }
        if (source == "syosetu" && SYOSETU_LEGACY.matches(rawId)) {
            return sourceSlug(source, rawId)
        }
        return rawId
    }

    private fun isItem(item: CatalogItem): Boolean =
        item.shelf != null || item.favorite || item.hidden || item.addedAt != null

    private fun stripPrefix(id: String, source: String): String {
        val prefix = "$source-"
        return if (id.startsWith(prefix)) id.removePrefix(prefix) else id
    }

    private fun parseAliases(json: String?): Map<String, String> {
        if (json.isNullOrBlank()) return emptyMap()
        val root = parse(json, "slug-aliases.json") as? JsonObject
            ?: throw CatalogSchemaException("slug-aliases.json 必须是对象")
        val source = (root["aliases"] as? JsonObject) ?: root
        val out = linkedMapOf<String, String>()
        for ((old, value) in source) {
            val final = (value as? JsonPrimitive)?.contentOrNull
            if (final != null) out[old] = final
        }
        return out
    }

    private fun parse(raw: String, name: String): JsonElement = try {
        JSON.parseToJsonElement(raw)
    } catch (e: Exception) {
        throw CatalogSchemaException("$name 无法解析：${e.message}")
    }

    private fun JsonObject.string(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull

    private fun JsonObject.bool(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.booleanOrNull
}
