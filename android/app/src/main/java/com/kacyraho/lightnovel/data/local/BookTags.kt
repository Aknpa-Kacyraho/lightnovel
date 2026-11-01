package com.kacyraho.lightnovel.data.local

import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json

object BookTags {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    fun encode(tags: List<String>): String? =
        tags.map(String::trim)
            .filter(String::isNotBlank)
            .distinct()
            .takeIf(List<String>::isNotEmpty)
            ?.let { json.encodeToString(ListSerializer(String.serializer()), it) }

    fun decode(raw: String?): List<String> {
        if (raw.isNullOrBlank()) return emptyList()
        runCatching {
            json.decodeFromString(ListSerializer(String.serializer()), raw)
        }.getOrNull()?.let { values ->
            return values.map(String::trim).filter(String::isNotBlank).distinct()
        }
        return raw.split('|', ',', '、')
            .map(String::trim)
            .filter(String::isNotBlank)
            .distinct()
    }
}
