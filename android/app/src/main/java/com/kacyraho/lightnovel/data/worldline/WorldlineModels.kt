package com.kacyraho.lightnovel.data.worldline

import kotlinx.serialization.Serializable

@Serializable
data class Intervention(
    val character: String = "",
    val action: String = "",
    val constraint: String = "",
)

@Serializable
data class BranchChapter(
    val index: Int = 0,
    val title: String = "",
    val text: String = "",
    val summary: String = "",
    val createdAt: String = "",
)

@Serializable
data class BranchState(
    val time: String = "",
    val location: String = "",
    val summary: String = "",
    val facts: List<String> = emptyList(),
    val openThreads: List<String> = emptyList(),
)

@Serializable
data class Divergence(
    val type: String = "event",
    val summary: String = "",
    val canonSummary: String? = null,
    val causedByIntervention: Boolean = true,
)

@Serializable
data class WorldlineFile(
    val schemaVersion: Int = 1,
    val id: String = "",
    val bookId: String = "",
    val title: String = "",
    val forkChapter: Int = 1,
    val forkParagraph: Int = 0,
    val intervention: Intervention = Intervention(),
    val mode: String = "exploration",
    val branchCursor: Int = 0,
    val chapters: List<BranchChapter> = emptyList(),
    val state: BranchState = BranchState(),
    val divergences: List<Divergence> = emptyList(),
    val createdAt: String = "",
    val updatedAt: String = "",
)
