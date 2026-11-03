package com.kacyraho.lightnovel.data.worldline

import com.kacyraho.lightnovel.data.knowledge.Entity
import com.kacyraho.lightnovel.data.knowledge.Fact
import com.kacyraho.lightnovel.data.knowledge.Relation
import com.kacyraho.lightnovel.data.knowledge.Secret
import com.kacyraho.lightnovel.data.knowledge.VoiceFact
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
data class DiffItem(
    val type: String = "event",
    val branchEvent: String = "",
    val canonReference: String? = null,
    val impact: String = "",
    val causedByIntervention: Boolean = true,
)

@Serializable
data class DiffReport(
    val id: String = "",
    val chapter: Int = 0,
    val items: List<DiffItem> = emptyList(),
    val createdAt: String = "",
)

@Serializable
data class WorldlineFile(
    val schemaVersion: Int = 1,
    val id: String = "",
    val bookId: String = "",
    val title: String = "",
    val forkChapter: Int = 1,
    val forkParagraph: Int = 0,
    val forkText: String = "",
    val intervention: Intervention = Intervention(),
    val mode: String = "exploration",
    val lengthMode: String = "standard",
    val creativity: String = "balanced",
    val directive: String = "",
    val branchCursor: Int = 0,
    val branchExtractedThrough: Int = 0,
    val knowledgeStatus: String = "pending",
    val chapters: List<BranchChapter> = emptyList(),
    val chapterStates: List<BranchState> = emptyList(),
    val state: BranchState = BranchState(),
    val divergences: List<Divergence> = emptyList(),
    val diffReports: List<DiffReport> = emptyList(),
    val createdAt: String = "",
    val updatedAt: String = "",
)

@Serializable
data class BranchKnowledgeFile(
    val schemaVersion: Int = 1,
    val worldlineId: String = "",
    val entities: List<Entity> = emptyList(),
    val facts: List<Fact> = emptyList(),
    val relations: List<Relation> = emptyList(),
    val voiceFacts: List<VoiceFact> = emptyList(),
    val secrets: List<Secret> = emptyList(),
    val extractedChapters: List<Int> = emptyList(),
    val branchExtractedThrough: Int = 0,
    val updatedAt: String = "",
)
