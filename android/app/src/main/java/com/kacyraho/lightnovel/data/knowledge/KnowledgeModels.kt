package com.kacyraho.lightnovel.data.knowledge

import kotlinx.serialization.Serializable

@Serializable
data class FactAnchor(
    val chapter: Int = 1,
    val paragraph: Int = 0,
    val charOffset: Int = 0,
    val quoteHash: String = "",
) : Comparable<FactAnchor> {
    override fun compareTo(other: FactAnchor): Int {
        if (chapter != other.chapter) return chapter.compareTo(other.chapter)
        if (paragraph != other.paragraph) return paragraph.compareTo(other.paragraph)
        return charOffset.compareTo(other.charOffset)
    }
}

@Serializable
data class DisplayAnchor(
    val chapter: Int = 1,
    val paragraph: Int = 0,
    val charOffset: Int = 0,
    val quoteHash: String = "",
)

@Serializable
data class Entity(
    val id: String = "",
    val scope: String = "canon",
    val branchId: String? = null,
    val type: String = "character",
    val canonicalName: String = "",
    val aliases: List<String> = emptyList(),
    val sourceLang: String = "ja",
    val sourceQuote: String = "",
    val sourceAnchor: FactAnchor = FactAnchor(),
    val displayQuote: String? = null,
    val displayAnchor: DisplayAnchor? = null,
    val readerKnown: Boolean = true,
    val knownBy: List<String> = emptyList(),
    val firstSeenChapter: Int = 1,
    val lastConfirmedChapter: Int = 1,
    val status: String = "active",
    val createdAt: String = "",
    val updatedAt: String = "",
) {
    fun names(): List<String> =
        (listOf(canonicalName) + aliases).filter(String::isNotBlank).distinct()
}

@Serializable
data class Fact(
    val id: String = "",
    val scope: String = "canon",
    val branchId: String? = null,
    val entityId: String = "",
    val kind: String = "persona",
    val factKey: String = "",
    val text: String = "",
    val participantEntityIds: List<String> = emptyList(),
    val sourceLang: String = "ja",
    val sourceQuote: String = "",
    val sourceAnchor: FactAnchor = FactAnchor(),
    val displayQuote: String? = null,
    val displayAnchor: DisplayAnchor? = null,
    val factGroupId: String? = null,
    val secretId: String? = null,
    val readerKnown: Boolean = true,
    val knownBy: List<String> = emptyList(),
    val firstSeenChapter: Int = 1,
    val lastConfirmedChapter: Int = 1,
    val validFromChapter: Int? = null,
    val validUntilChapter: Int? = null,
    val supersedes: String? = null,
    val supersededBy: String? = null,
    val confidence: Double = 0.7,
    val status: String = "active",
    val forbiddenTerms: List<String> = emptyList(),
    val createdAt: String = "",
    val updatedAt: String = "",
)

@Serializable
data class Relation(
    val id: String = "",
    val scope: String = "canon",
    val branchId: String? = null,
    val fromEntityId: String = "",
    val toEntityId: String = "",
    val type: String = "other",
    val label: String = "",
    val sourceLang: String = "ja",
    val sourceQuote: String = "",
    val sourceAnchor: FactAnchor = FactAnchor(),
    val displayQuote: String? = null,
    val displayAnchor: DisplayAnchor? = null,
    val readerKnown: Boolean = true,
    val knownBy: List<String> = emptyList(),
    val firstSeenChapter: Int = 1,
    val lastConfirmedChapter: Int = 1,
    val validFromChapter: Int? = null,
    val validUntilChapter: Int? = null,
    val supersedes: String? = null,
    val supersededBy: String? = null,
    val confidence: Double = 0.7,
    val status: String = "active",
    val createdAt: String = "",
    val updatedAt: String = "",
)

@Serializable
data class VoiceFact(
    val id: String = "",
    val scope: String = "canon",
    val branchId: String? = null,
    val entityId: String = "",
    val dimension: String = "voice",
    val text: String = "",
    val exampleQuote: String? = null,
    val sourceLang: String = "ja",
    val sourceQuote: String = "",
    val sourceAnchor: FactAnchor = FactAnchor(),
    val displayQuote: String? = null,
    val displayAnchor: DisplayAnchor? = null,
    val readerKnown: Boolean = true,
    val knownBy: List<String> = emptyList(),
    val firstSeenChapter: Int = 1,
    val lastConfirmedChapter: Int = 1,
    val confidence: Double = 0.7,
    val status: String = "active",
    val createdAt: String = "",
    val updatedAt: String = "",
)

@Serializable
data class Secret(
    val id: String = "",
    val subjectEntityId: String = "",
    val contentFactIds: List<String> = emptyList(),
    val canonRevealChapter: Int? = null,
    val revealPolicy: String = "unrevealed",
    val allowedAfterBranchChapter: Int? = null,
    val allowedHints: List<String> = emptyList(),
    val hintNotes: String? = null,
    val forbiddenTerms: List<String> = emptyList(),
)

@Serializable
data class KnowledgeFile(
    val schemaVersion: Int = 1,
    val workId: String = "",
    val title: String = "",
    val entities: List<Entity> = emptyList(),
    val facts: List<Fact> = emptyList(),
    val relations: List<Relation> = emptyList(),
    val voiceFacts: List<VoiceFact> = emptyList(),
    val secrets: List<Secret> = emptyList(),
    val extractedChapters: List<Int> = emptyList(),
    val canonExtractedThrough: Int = 0,
    val updatedAt: String = "",
) {
    fun entity(id: String): Entity? = entities.firstOrNull { it.id == id }
}

@Serializable
data class KnowledgeItemView(
    val id: String,
    val itemType: String,
    val kind: String,
    val entityId: String,
    val text: String,
    val displayQuote: String? = null,
    val sourceAnchor: FactAnchor,
    val displayAnchor: DisplayAnchor? = null,
    val status: String,
    val hiddenReason: String? = null,
    val relationType: String? = null,
    val relatedEntityId: String? = null,
    val voiceDimension: String? = null,
)

@Serializable
data class KnowledgeStatus(
    val readAnchor: FactAnchor,
    val displayAnchor: DisplayAnchor? = null,
    val translatedThrough: Int = 0,
    val canonExtractedThrough: Int = 0,
    val branchReadAnchor: FactAnchor? = null,
    val branchExtractedThrough: Int = 0,
    val branchCursor: Int = 0,
    val translationUpdating: Boolean = false,
    val extractionUpdating: Boolean = false,
    val locationDegraded: Boolean = false,
)

@Serializable
data class QueryEntry(
    val entityId: String,
    val displayName: String,
    val type: String,
    val visibleFactCount: Int,
    val hasMore: Boolean = false,
)

data class EntityCard(
    val entity: Entity,
    val facts: List<Fact>,
    val relations: List<Relation>,
    val voiceFacts: List<VoiceFact>,
    val status: KnowledgeStatus,
    val relatedNames: Map<String, String> = emptyMap(),
)
