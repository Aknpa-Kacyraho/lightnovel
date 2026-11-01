package com.kacyraho.lightnovel.data.knowledge

data class EntityMatch(
    val start: Int,
    val end: Int,
    val entityId: String,
)

object EntityHighlighter {
    fun find(text: String, names: Map<String, String>): List<EntityMatch> {
        if (text.isBlank() || names.isEmpty()) return emptyList()
        val candidates = names.entries
            .filter { it.key.isNotBlank() && it.value.isNotBlank() }
            .sortedByDescending { it.key.length }
        val occupied = BooleanArray(text.length)
        val matches = mutableListOf<EntityMatch>()
        for ((name, entityId) in candidates) {
            var start = text.indexOf(name)
            while (start >= 0) {
                val end = start + name.length
                if (end <= text.length && (start until end).none { occupied[it] }) {
                    for (i in start until end) occupied[i] = true
                    matches += EntityMatch(start, end, entityId)
                }
                start = text.indexOf(name, start + name.length)
            }
        }
        return matches.sortedBy { it.start }
    }
}
