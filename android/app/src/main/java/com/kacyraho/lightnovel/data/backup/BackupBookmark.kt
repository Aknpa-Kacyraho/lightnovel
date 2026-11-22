package com.kacyraho.lightnovel.data.backup

import kotlinx.serialization.Serializable

/**
 * Portable bookmark row for backups. Kept separate from the Room entity so the
 * backup format does not depend on database column names.
 */
@Serializable
data class BackupBookmark(
    val bookId: String,
    val chapterIdx: Int,
    val paragraphId: Int,
    val charOffset: Int = 0,
    val preview: String = "",
    val createdAt: String = "",
)
