package com.kacyraho.lightnovel.data.online

import kotlinx.serialization.Serializable

@Serializable
data class NoveliaFavored(
    val id: String = "",
    val title: String = "",
)

@Serializable
data class NoveliaFavoredList(
    val favoredWeb: List<NoveliaFavored> = emptyList(),
    val favoredWenku: List<NoveliaFavored> = emptyList(),
)

data class NoveliaImportResult(
    val folders: Int = 0,
    val books: Int = 0,
    val history: Int = 0,
    val skipped: Int = 0,
    val message: String? = null,
)
