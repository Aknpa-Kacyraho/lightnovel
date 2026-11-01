package com.kacyraho.lightnovel.core.settings

import android.content.Context
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

@Serializable
data class SearchPreset(
    val id: String = "",
    val query: String = "",
    val source: String? = null,
    val status: String? = null,
    val characters: String = "all",
)

class SearchPresetStore(
    context: Context,
) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    fun load(): List<SearchPreset> {
        val raw = prefs.getString(KEY, null) ?: return emptyList()
        return runCatching {
            json.decodeFromString(ListSerializer(SearchPreset.serializer()), raw)
        }.getOrDefault(emptyList()).take(MAX)
    }

    fun save(preset: SearchPreset): List<SearchPreset> {
        if (preset.query.isBlank()) return load()
        val current = load()
        val key = listOf(
            preset.query,
            preset.source.orEmpty(),
            preset.status.orEmpty(),
            preset.characters,
        ).joinToString("|")
        val next = (listOf(preset.copy(id = key)) + current.filter { it.id != key })
            .take(MAX)
        persist(next)
        return next
    }

    fun remove(id: String): List<SearchPreset> {
        val next = load().filterNot { it.id == id }
        persist(next)
        return next
    }

    private fun persist(items: List<SearchPreset>) {
        prefs.edit()
            .putString(KEY, json.encodeToString(ListSerializer(SearchPreset.serializer()), items))
            .apply()
    }

    private companion object {
        const val PREFS = "lightnovel_search_presets"
        const val KEY = "presets"
        const val MAX = 12
    }
}
