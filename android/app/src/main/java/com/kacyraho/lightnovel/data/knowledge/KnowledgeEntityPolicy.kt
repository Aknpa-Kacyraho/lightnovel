package com.kacyraho.lightnovel.data.knowledge

object KnowledgeEntityPolicy {
    private val namedTypes = setOf("character", "place", "organization", "item")

    fun isQueryable(entity: Entity): Boolean = entity.type in namedTypes

    fun isGlossaryTerm(type: String): Boolean = type in namedTypes
}
