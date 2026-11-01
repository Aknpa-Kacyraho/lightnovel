package com.kacyraho.lightnovel.data.worldline

import com.kacyraho.lightnovel.data.knowledge.Fact
import com.kacyraho.lightnovel.data.knowledge.FactAnchor
import com.kacyraho.lightnovel.data.knowledge.FactAnchorMapper
import com.kacyraho.lightnovel.data.knowledge.KnowledgeFile
import com.kacyraho.lightnovel.data.knowledge.KnowledgeStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.story.StoryMemoryStore

class WorldlineContextBuilder(
    private val knowledgeStore: KnowledgeStore,
    private val storyMemoryStore: StoryMemoryStore?,
) {
    fun canonKnown(book: BookEntity, forkChapter: Int, forkParagraph: Int): String {
        val knowledge = knowledgeStore.load(book.storageDir, book.id, book.title)
        val fork = fork(forkChapter, forkParagraph)
        val facts = knowledge.facts.filter {
            it.kind != "reveal_content" &&
                it.status != "source_stale" && it.status != "low_confidence" &&
                (it.readerKnown || it.knownBy.isNotEmpty()) &&
                FactAnchorMapper.visible(it.sourceAnchor, fork) &&
                (it.validUntilChapter == null || forkChapter < it.validUntilChapter)
        }
        val relations = knowledge.relations.filter {
            (it.readerKnown || it.knownBy.isNotEmpty()) &&
                FactAnchorMapper.visible(it.sourceAnchor, fork)
        }
        val voices = knowledge.voiceFacts.filter {
            (it.readerKnown || it.knownBy.isNotEmpty()) &&
                FactAnchorMapper.visible(it.sourceAnchor, fork)
        }
        return buildString {
            if (facts.isNotEmpty()) {
                appendLine("【分叉点前已知事实】")
                facts.take(60).forEach {
                    val name = knowledge.entity(it.entityId)?.canonicalName ?: "?"
                    appendLine("$name/${it.kind}/${it.factKey}: ${it.text}")
                }
            }
            if (relations.isNotEmpty()) {
                appendLine("【分叉点前关系】")
                relations.take(30).forEach {
                    val from = knowledge.entity(it.fromEntityId)?.canonicalName ?: "?"
                    val to = knowledge.entity(it.toEntityId)?.canonicalName ?: "?"
                    appendLine("$from → $to：${it.label}")
                }
            }
            if (voices.isNotEmpty()) {
                appendLine("【分叉点前角色声音】")
                voices.take(30).forEach {
                    val name = knowledge.entity(it.entityId)?.canonicalName ?: "?"
                    appendLine("$name/${it.dimension}：${it.text}")
                }
            }
        }
    }

    fun canonReference(
        book: BookEntity,
        forkChapter: Int,
        comparison: Boolean,
    ): String {
        val knowledge = knowledgeStore.load(book.storageDir, book.id, book.title)
        val fork = fork(forkChapter, 0)
        val facts = knowledge.facts.filter {
            !FactAnchorMapper.visible(it.sourceAnchor, fork) &&
                it.status != "source_stale" && it.status != "low_confidence" &&
                (comparison || it.kind == "persona" || it.kind == "direction")
        }
        return buildString {
            if (facts.isNotEmpty()) {
                appendLine("【canon 参照（只给 Planner/Validator/Diff，不得让角色知道）】")
                facts.take(40).forEach {
                    val name = knowledge.entity(it.entityId)?.canonicalName ?: "?"
                    appendLine("$name/${it.kind}: ${it.text}")
                }
            }
        }
    }

    fun characterView(
        book: BookEntity,
        forkChapter: Int,
        forkParagraph: Int,
        branchKnowledge: BranchKnowledgeFile?,
    ): String {
        val knowledge = knowledgeStore.load(book.storageDir, book.id, book.title)
        val fork = fork(forkChapter, forkParagraph)
        val lines = mutableListOf<String>()
        val canonFacts = knowledge.facts.filter {
            it.knownBy.isNotEmpty() && it.kind != "reveal_content" &&
                FactAnchorMapper.visible(it.sourceAnchor, fork)
        }
        canonFacts.forEach { fact ->
            val names = fact.knownBy.mapNotNull { id -> knowledge.entity(id)?.canonicalName }
            if (names.isNotEmpty()) {
                lines += "${names.joinToString("、")}知道：${fact.text}"
            }
        }
        branchKnowledge?.facts.orEmpty()
            .filter { it.knownBy.isNotEmpty() && it.kind != "reveal_content" }
            .forEach { fact ->
                val names = fact.knownBy.mapNotNull { id ->
                    branchKnowledge?.entityName(id) ?: knowledge.entity(id)?.canonicalName
                }
                if (names.isNotEmpty()) {
                    lines += "${names.joinToString("、")}知道：${fact.text}"
                }
            }
        return if (lines.isEmpty()) "（没有明确记录的角色已知信息）"
        else lines.distinct().take(80).joinToString("\n")
    }

    fun plannerContext(
        book: BookEntity,
        forkChapter: Int,
        comparison: Boolean,
        branch: WorldlineFile,
        branchKnowledge: BranchKnowledgeFile?,
    ): String = buildString {
        appendLine("【作品】${book.titleZh ?: book.title}")
        appendLine("【分叉点】第 $forkChapter 章")
        appendLine("【用户介入】${branch.intervention.character}：${branch.intervention.action}")
        if (branch.intervention.constraint.isNotBlank()) {
            appendLine("约束：${branch.intervention.constraint}")
        }
        appendLine(canonReference(book, forkChapter, comparison))
        appendLine("【当前分支状态】")
        appendLine("时间：${branch.state.time}；地点：${branch.state.location}")
        appendLine(branch.state.summary)
        if (branch.state.openThreads.isNotEmpty()) {
            appendLine("未解决线索：${branch.state.openThreads.joinToString("；")}")
        }
        branchKnowledge?.facts.orEmpty()
            .filter { it.kind != "reveal_content" }
            .take(40)
            .forEach { appendLine("分支事实：${it.text}") }
    }

    fun writerContext(
        book: BookEntity,
        forkChapter: Int,
        forkParagraph: Int,
        branch: WorldlineFile,
        branchKnowledge: BranchKnowledgeFile?,
        plan: String,
        previousSummary: String,
        previousTail: String,
    ): String = buildString {
        appendLine("【作品】${book.titleZh ?: book.title}")
        appendLine("【分叉点】第 $forkChapter 章第 $forkParagraph 段")
        appendLine(canonKnown(book, forkChapter, forkParagraph))
        val memory = storyMemoryStore?.load(book.storageDir, book.id, book.title)
        if (memory?.glossary?.isNotEmpty() == true) {
            appendLine("【锁定译名】")
            memory.glossary.take(40).forEach { appendLine("${it.source}=${it.target}") }
        }
        memory?.style?.let { style ->
            val lines = listOf(
                style.general,
                style.narrator,
                style.honorifics,
                style.notes,
                style.guide,
            ).filter(String::isNotBlank)
            if (lines.isNotEmpty()) {
                appendLine("【本书风格】")
                lines.forEach { appendLine(it.take(300)) }
            }
        }
        if (branchKnowledge != null) {
            appendLine("【本分支已知事实】")
            branchKnowledge.facts
                .filter { it.kind != "reveal_content" }
                .take(60)
                .forEach { appendLine("${it.kind}/${it.factKey}: ${it.text}") }
        }
        appendLine("【当前分支状态】")
        appendLine("时间：${branch.state.time}；地点：${branch.state.location}")
        appendLine(branch.state.summary)
        if (branch.state.openThreads.isNotEmpty()) {
            appendLine("未解决线索：${branch.state.openThreads.joinToString("；")}")
        }
        appendLine("【用户介入】${branch.intervention.character}：${branch.intervention.action}")
        if (branch.intervention.constraint.isNotBlank()) {
            appendLine("约束：${branch.intervention.constraint}")
        }
        if (previousSummary.isNotBlank()) appendLine("【上一章梗概】$previousSummary")
        if (previousTail.isNotBlank()) appendLine("【上一章结尾】$previousTail")
        appendLine("【本章 plan】")
        appendLine(plan)
        appendLine("【未揭示秘密约束】")
        secretConstraints(book, forkChapter).forEach(::appendLine)
    }

    fun futureOnlyTerms(book: BookEntity, forkChapter: Int): List<String> {
        val knowledge = knowledgeStore.load(book.storageDir, book.id, book.title)
        return knowledge.entities
            .filter { it.firstSeenChapter > forkChapter }
            .flatMap { it.names() }
            .filter(String::isNotBlank)
            .distinct()
    }

    fun forbiddenTerms(book: BookEntity, forkChapter: Int): List<String> {
        val knowledge = knowledgeStore.load(book.storageDir, book.id, book.title)
        return knowledge.secrets
            .filter { it.canonRevealChapter == null || it.canonRevealChapter > forkChapter }
            .flatMap { it.forbiddenTerms }
            .map(String::trim)
            .filter(String::isNotBlank)
            .distinct()
    }

    private fun secretConstraints(book: BookEntity, forkChapter: Int): List<String> {
        val knowledge = knowledgeStore.load(book.storageDir, book.id, book.title)
        return knowledge.secrets
            .filter { it.canonRevealChapter == null || it.canonRevealChapter > forkChapter }
            .map {
                val subject = knowledge.entity(it.subjectEntityId)?.canonicalName ?: "?"
                "关于 $subject 的未揭示秘密；允许表现：${it.allowedHints.joinToString("、")}；" +
                    "禁止写出：${it.forbiddenTerms.joinToString("、")}"
            }
    }

    private fun fork(chapter: Int, paragraph: Int) = FactAnchor(
        chapter = chapter,
        paragraph = paragraph,
        charOffset = Int.MAX_VALUE,
        quoteHash = "",
    )

    private fun BranchKnowledgeFile.entityName(id: String): String? =
        entities.firstOrNull { it.id == id }?.canonicalName
}
