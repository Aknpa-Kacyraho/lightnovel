package com.kacyraho.lightnovel.data.source

internal data class SourceChapterAppend(
    val index: Int,
    val title: String,
)

/**
 * Source chapters are positional: index N is the N-th chapter on the site.
 * Sync only fills positions missing from the local shelf. Existing rows are
 * never rewritten, deleted or reordered.
 */
internal fun planCatalogAppend(
    existingIndices: Set<Int>,
    sourceTitles: List<String>,
): List<SourceChapterAppend> =
    (1..sourceTitles.size)
        .filterNot { it in existingIndices }
        .map { index -> SourceChapterAppend(index, sourceTitles[index - 1]) }

/**
 * A site that temporarily drops chapters must not make the local book shorter.
 */
internal fun catalogEpisodeCount(existingMax: Int?, sourceSize: Int): Int =
    maxOf(existingMax ?: 0, sourceSize)
