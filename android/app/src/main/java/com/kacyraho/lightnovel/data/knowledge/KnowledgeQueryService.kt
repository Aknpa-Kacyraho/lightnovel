package com.kacyraho.lightnovel.data.knowledge

class KnowledgeQueryService(
    private val store: KnowledgeStore,
) {
    fun status(
        knowledge: KnowledgeFile,
        readAnchor: FactAnchor,
        displayAnchor: DisplayAnchor?,
        translatedThrough: Int,
        locationDegraded: Boolean,
    ): KnowledgeStatus = KnowledgeStatus(
        readAnchor = readAnchor,
        displayAnchor = displayAnchor,
        translatedThrough = translatedThrough,
        canonExtractedThrough = knowledge.canonExtractedThrough,
        translationUpdating = translatedThrough < readAnchor.chapter,
        extractionUpdating = !knowledge.extractedChapters.contains(readAnchor.chapter),
        locationDegraded = locationDegraded,
    )

    fun readerItems(
        knowledge: KnowledgeFile,
        readAnchor: FactAnchor,
    ): List<KnowledgeItemView> {
        val items = mutableListOf<KnowledgeItemView>()
        knowledge.entities.filter {
            it.readerKnown && visible(it.sourceAnchor, readAnchor, it.firstSeenChapter, knowledge)
        }.forEach {
            items += KnowledgeItemView(
                id = it.id,
                itemType = "entity",
                kind = "entity",
                entityId = it.id,
                text = it.canonicalName,
                sourceAnchor = it.sourceAnchor,
                displayAnchor = it.displayAnchor,
                status = it.status,
            )
        }
        activeFacts(knowledge.facts).filter {
            it.readerKnown && factVisible(it, readAnchor, knowledge)
        }.forEach {
            items += KnowledgeItemView(
                id = it.id,
                itemType = "fact",
                kind = it.kind,
                entityId = it.entityId,
                text = it.text,
                displayQuote = it.displayQuote,
                sourceAnchor = it.sourceAnchor,
                displayAnchor = it.displayAnchor,
                status = it.status,
            )
        }
        knowledge.relations.filter {
            it.readerKnown && relationVisible(it, readAnchor, knowledge)
        }.forEach {
            items += KnowledgeItemView(
                id = it.id,
                itemType = "relation",
                kind = "relation",
                entityId = it.fromEntityId,
                text = it.label,
                sourceAnchor = it.sourceAnchor,
                displayAnchor = it.displayAnchor,
                status = it.status,
                relationType = it.type,
                relatedEntityId = it.toEntityId,
            )
        }
        knowledge.voiceFacts.filter {
            it.readerKnown && visible(it.sourceAnchor, readAnchor, it.firstSeenChapter, knowledge)
        }.forEach {
            items += KnowledgeItemView(
                id = it.id,
                itemType = "voice",
                kind = "voice",
                entityId = it.entityId,
                text = it.text,
                sourceAnchor = it.sourceAnchor,
                displayAnchor = it.displayAnchor,
                status = it.status,
                voiceDimension = it.dimension,
            )
        }
        return items.sortedBy { it.sourceAnchor }
    }

    fun visibleNames(
        knowledge: KnowledgeFile,
        readAnchor: FactAnchor,
    ): Map<String, String> {
        val names = linkedMapOf<String, String>()
        knowledge.entities.filter {
            it.readerKnown && visible(it.sourceAnchor, readAnchor, it.firstSeenChapter, knowledge)
        }.forEach { entity ->
            entity.names().forEach { name ->
                if (name.isNotBlank()) names.putIfAbsent(name, entity.id)
            }
        }
        return names
    }

    fun queryEntries(
        knowledge: KnowledgeFile,
        readAnchor: FactAnchor,
        texts: List<String>,
    ): List<QueryEntry> {
        val body = texts.joinToString("\n")
        if (body.isBlank()) return emptyList()
        val visible = readerItems(knowledge, readAnchor)
        val counts = visible.filter { it.itemType != "entity" }
            .groupingBy { it.entityId }
            .eachCount()
        return knowledge.entities.mapNotNull { entity ->
            val hits = entity.names().sumOf { name -> occurrences(body, name) }
            if (hits == 0) return@mapNotNull null
            val count = counts[entity.id] ?: 0
            if (count == 0) return@mapNotNull null
            QueryEntry(
                entityId = entity.id,
                displayName = entity.canonicalName,
                type = entity.type,
                visibleFactCount = count,
            )
        }.sortedWith(
            compareByDescending<QueryEntry> { entry ->
                knowledge.entities.firstOrNull { it.id == entry.entityId }
                    ?.names()
                    ?.sumOf { occurrences(body, it) }
                    ?: 0
            }.thenBy { entry ->
                knowledge.entities.firstOrNull { it.id == entry.entityId }
                    ?.firstSeenChapter
                    ?: Int.MAX_VALUE
            },
        )
    }

    fun entityCard(
        knowledge: KnowledgeFile,
        entityId: String,
        readAnchor: FactAnchor,
        status: KnowledgeStatus,
    ): EntityCard? {
        val entity = knowledge.entity(entityId) ?: return null
        if (!entity.readerKnown) return null
        val facts = activeFacts(knowledge.facts)
            .filter {
                it.entityId == entityId && it.readerKnown &&
                    factVisible(it, readAnchor, knowledge)
            }
            .sortedBy { it.sourceAnchor }
        val relations = knowledge.relations
            .filter {
                (it.fromEntityId == entityId || it.toEntityId == entityId) &&
                    it.readerKnown &&
                    relationVisible(it, readAnchor, knowledge)
            }
            .sortedBy { it.sourceAnchor }
        val voices = knowledge.voiceFacts
            .filter {
                it.entityId == entityId && it.readerKnown &&
                    visible(it.sourceAnchor, readAnchor, it.firstSeenChapter, knowledge)
            }
            .sortedBy { it.sourceAnchor }
        val related = relations.flatMap { listOf(it.fromEntityId, it.toEntityId) }
            .distinct()
            .mapNotNull { id -> knowledge.entity(id)?.let { id to it.canonicalName } }
            .toMap()
        return EntityCard(entity, facts, relations, voices, status, related)
    }

    fun save(knowledge: KnowledgeFile, storageDir: String): KnowledgeFile =
        store.save(storageDir, knowledge)

    private fun activeFacts(facts: List<Fact>): List<Fact> =
        facts.filter { it.status != "source_stale" && it.status != "low_confidence" }

    private fun factVisible(
        fact: Fact,
        read: FactAnchor,
        knowledge: KnowledgeFile,
    ): Boolean {
        if (!visible(fact.sourceAnchor, read, fact.firstSeenChapter, knowledge)) return false
        val from = fact.validFromChapter
        if (from != null && from > read.chapter) return false
        val until = fact.validUntilChapter
        if (until != null && read.chapter >= until) return false
        return true
    }

    private fun relationVisible(
        relation: Relation,
        read: FactAnchor,
        knowledge: KnowledgeFile,
    ): Boolean {
        if (!visible(relation.sourceAnchor, read, relation.firstSeenChapter, knowledge)) return false
        val from = relation.validFromChapter
        if (from != null && from > read.chapter) return false
        val until = relation.validUntilChapter
        if (until != null && read.chapter >= until) return false
        return true
    }

    private fun visible(
        source: FactAnchor,
        read: FactAnchor,
        firstSeenChapter: Int,
        knowledge: KnowledgeFile,
    ): Boolean {
        if (firstSeenChapter > knowledge.canonExtractedThrough) return false
        return FactAnchorMapper.visible(source, read)
    }

    private fun occurrences(text: String, name: String): Int {
        if (name.isBlank()) return 0
        var count = 0
        var index = text.indexOf(name)
        while (index >= 0) {
            count++
            index = text.indexOf(name, index + name.length)
        }
        return count
    }
}
