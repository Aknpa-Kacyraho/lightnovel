package com.kacyraho.lightnovel.data.worldline

import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.core.text.Paragraphs
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
    private val contentStore: ContentStore? = null,
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
                facts.sortedByDescending { it.sourceAnchor }.take(60).forEach {
                    val name = knowledge.entity(it.entityId)?.canonicalName ?: "?"
                    appendLine("$name/${it.kind}/${it.factKey}: ${it.text}")
                }
            }
            if (relations.isNotEmpty()) {
                appendLine("【分叉点前关系】")
                relations.sortedByDescending { it.sourceAnchor }.take(30).forEach {
                    val from = knowledge.entity(it.fromEntityId)?.canonicalName ?: "?"
                    val to = knowledge.entity(it.toEntityId)?.canonicalName ?: "?"
                    appendLine("$from → $to：${it.label}")
                }
            }
            if (voices.isNotEmpty()) {
                appendLine("【分叉点前角色声音】")
                voices.sortedByDescending { it.sourceAnchor }.take(30).forEach {
                    val name = knowledge.entity(it.entityId)?.canonicalName ?: "?"
                    appendLine("$name/${it.dimension}：${it.text}")
                }
            }
        }
    }

    fun canonExcerpt(
        book: BookEntity,
        forkChapter: Int,
        forkParagraph: Int,
        maxChars: Int = 8_000,
    ): String {
        val store = contentStore ?: return ""
        val blocks = mutableListOf<String>()
        for (chapter in maxOf(1, forkChapter - 2) until forkChapter) {
            val text = store.readZh(book.storageDir, chapter)
                ?: store.readRaw(book.storageDir, chapter)
                ?: continue
            if (text.isNotBlank()) {
                blocks += "【第 $chapter 章】\n${text.trim()}"
            }
        }
        if (forkParagraph > 0) {
            val current = store.readZh(book.storageDir, forkChapter)
                ?: store.readRaw(book.storageDir, forkChapter)
            if (!current.isNullOrBlank()) {
                val paragraphCount = Paragraphs.split(current).size
                if (forkParagraph <= paragraphCount) {
                    val offset = Paragraphs.startOffset(current, forkParagraph)
                        .coerceIn(0, current.length)
                    val prefix = current.take(offset).trim()
                    if (prefix.isNotBlank()) {
                        blocks += "【第 $forkChapter 章分叉前】\n$prefix"
                    }
                }
            }
        }
        if (blocks.isEmpty()) return ""
        return blocks.joinToString("\n\n").takeLast(maxChars.coerceAtLeast(1_000))
    }

    fun canonReference(
        book: BookEntity,
        forkChapter: Int,
        comparison: Boolean,
        forkParagraph: Int = 0,
    ): String {
        val knowledge = knowledgeStore.load(book.storageDir, book.id, book.title)
        val fork = fork(forkChapter, forkParagraph)
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
        else lines.distinct().takeLast(80).joinToString("\n")
    }

    private fun forkTextThrough(branch: WorldlineFile): String {
        val text = branch.forkText
        if (text.isBlank()) return ""
        val parts = Paragraphs.split(text)
        if (parts.size <= 1) return text
        val last = branch.forkParagraph.coerceIn(0, parts.lastIndex)
        val end = Paragraphs.startOffset(text, last + 1)
        return if (end > 0) text.take(end) else text
    }

    fun branchHistory(branch: WorldlineFile, maxChars: Int = 7_000): String {
        if (branch.chapters.isEmpty()) return ""
        val recent = branch.chapters.takeLast(2)
        val older = branch.chapters.dropLast(2).takeLast(20)
        return buildString {
            if (older.isNotEmpty()) {
                appendLine("【前情摘要】")
                older.forEach { chapter ->
                    val summary = chapter.summary.ifBlank {
                        chapter.text.take(220).replace('\n', ' ')
                    }
                    appendLine("第 ${chapter.index} 章：$summary")
                }
            }
            recent.forEach { chapter ->
                appendLine("【最近章节：第 ${chapter.index} 章】")
                appendLine(chapter.text.takeLast(3_000))
            }
        }.takeLast(maxChars.coerceAtLeast(1_000))
    }

    fun plannerContext(
        book: BookEntity,
        forkChapter: Int,
        comparison: Boolean,
        branch: WorldlineFile,
        branchKnowledge: BranchKnowledgeFile?,
    ): String = buildString {
        appendLine("【作品】${book.titleZh ?: book.title}")
        appendLine("【分叉点】第 $forkChapter 章第 ${branch.forkParagraph} 段")
        if (branch.directive.isNotBlank()) {
            appendLine("【作者备注（长期有效）】")
            appendLine(branch.directive.take(2_000))
        }
        appendLine(canonKnown(book, forkChapter, branch.forkParagraph))
        appendLine("【用户介入】${branch.intervention.character}：${branch.intervention.action}")
        if (branch.intervention.constraint.isNotBlank()) {
            appendLine("约束：${branch.intervention.constraint}")
        }
        val excerpt = canonExcerpt(book, forkChapter, branch.forkParagraph, 6_000)
        if (excerpt.isNotBlank()) {
            appendLine("【分叉前原文节选（只读到分叉点）】")
            appendLine(excerpt)
        }
        val forkText = forkTextThrough(branch)
        if (forkText.isNotBlank()) {
            appendLine("【用户修改后的分叉正文（以此为准，截止到分叉段）】")
            appendLine(forkText.take(8_000))
        }
        val history = branchHistory(branch, 6_000)
        if (history.isNotBlank()) {
            appendLine("【本分支前文】")
            appendLine(history)
        }
        appendLine(canonReference(book, forkChapter, comparison, branch.forkParagraph))
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
        if (branch.directive.isNotBlank()) {
            appendLine("【作者备注（长期有效，优先遵守）】")
            appendLine(branch.directive.take(2_000))
        }
        val excerpt = canonExcerpt(book, forkChapter, forkParagraph, 8_000)
        if (excerpt.isNotBlank()) {
            appendLine("【分叉前原文节选（只读到分叉点，不要续写其中已发生的内容）】")
            appendLine(excerpt)
        }
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
                .sortedByDescending { it.sourceAnchor }
                .take(60)
                .forEach { appendLine("${it.kind}/${it.factKey}: ${it.text}") }
        }
        val roleView = characterView(book, forkChapter, forkParagraph, branchKnowledge)
        if (!roleView.startsWith("（没有")) {
            appendLine("【角色知情边界】")
            appendLine(roleView.take(3_500))
        }
        val history = branchHistory(branch, 7_000)
        if (history.isNotBlank()) {
            appendLine("【本分支前文】")
            appendLine(history)
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
        val forkText = forkTextThrough(branch)
        if (forkText.isNotBlank()) {
            appendLine("【用户修改后的分叉正文（必须以此为准，截止到分叉段）】")
            appendLine(forkText.take(10_000))
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

    private fun fork(chapter: Int, paragraph: Int): FactAnchor {
        val beforeParagraph = paragraph > 0
        return FactAnchor(
            chapter = chapter,
            paragraph = if (beforeParagraph) paragraph - 1 else -1,
            charOffset = if (beforeParagraph) Int.MAX_VALUE else -1,
            quoteHash = "",
        )
    }

    private fun BranchKnowledgeFile.entityName(id: String): String? =
        entities.firstOrNull { it.id == id }?.canonicalName
}
