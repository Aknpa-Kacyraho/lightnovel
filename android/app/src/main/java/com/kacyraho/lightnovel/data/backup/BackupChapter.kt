package com.kacyraho.lightnovel.data.backup

import kotlinx.serialization.Serializable

/**
 * Portable chapter metadata for backups. Chapter bodies stay in `novels/`;
 * this file preserves the chapter list and titles for books whose files were
 * never downloaded (online-only) or whose titles came from a local import.
 */
@Serializable
data class BackupChapter(
    val bookId: String,
    val idx: Int,
    val title: String? = null,
    val titleZh: String? = null,
    val status: String? = null,
)
