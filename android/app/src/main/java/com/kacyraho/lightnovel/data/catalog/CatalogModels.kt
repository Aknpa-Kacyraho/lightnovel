package com.kacyraho.lightnovel.data.catalog

data class CatalogItem(
    val id: String,
    val slug: String?,
    val source: String,
    val sourceId: String,
    val title: String,
    val titleZh: String?,
    val author: String?,
    val shelf: String?,
    val favorite: Boolean,
    val hidden: Boolean,
    val addedAt: String?,
    val firstSeen: String?,
    val episodes: Int,
    val local: Boolean,
    val rawJson: String,
    val tags: List<String> = emptyList(),
)

data class Catalog(
    val schemaVersion: Int,
    val items: LinkedHashMap<String, CatalogItem>,
    val candidates: LinkedHashMap<String, CatalogItem>,
    val aliases: LinkedHashMap<String, String>,
)

class CatalogSchemaException(message: String) : IllegalArgumentException(message)
