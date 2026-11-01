package com.kacyraho.lightnovel.data.story

import com.kacyraho.lightnovel.data.glossary.GlossaryEntry
import kotlinx.serialization.Serializable

@Serializable
data class CharacterCard(
    val id: String = "",
    val source: String = "",
    val target: String = "",
    val aliases: List<String> = emptyList(),
    val description: String = "",
    val voice: String = "",
    val address: String = "",
    val lexicon: String = "",
    val syntax: String = "",
    val volume: String = "",
    val notes: String = "",
    val auto: Boolean = false,
)

@Serializable
data class StoryStyle(
    val general: String = "",
    val narrator: String = "",
    val honorifics: String = "",
    val notes: String = "",
    val guide: String = "",
    val medium: String = "",
)

@Serializable
data class ChapterSummary(
    val index: Int = 0,
    val text: String = "",
    val sourceHash: String = "",
    val updatedAt: String = "",
)

@Serializable
data class StoryMemory(
    val schemaVersion: Int = 1,
    val workId: String = "",
    val title: String = "",
    val glossary: List<GlossaryEntry> = emptyList(),
    val characters: List<CharacterCard> = emptyList(),
    val summaries: Map<Int, ChapterSummary> = emptyMap(),
    val style: StoryStyle = StoryStyle(),
    val lessons: List<String> = emptyList(),
    val revision: String = "",
) {
    fun characterFor(name: String): CharacterCard? =
        characters.firstOrNull { card ->
            card.source == name || card.target == name || name in card.aliases
        }

    fun relevantSummaries(text: String, limit: Int = 3): List<ChapterSummary> {
        val names = characters.flatMap { card ->
            listOf(card.source, card.target) + card.aliases
        }.filter(String::isNotBlank)
        if (names.isEmpty()) return emptyList()
        return summaries.values
            .sortedBy { it.index }
            .filter { summary -> names.any { it in summary.text } }
            .takeLast(limit)
    }
}
