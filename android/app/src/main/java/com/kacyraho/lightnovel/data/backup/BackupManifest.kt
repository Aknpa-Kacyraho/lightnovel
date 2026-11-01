package com.kacyraho.lightnovel.data.backup

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class BackupEntry(
    val path: String,
    val size: Long = -1,
    val sha256: String = "",
)

@Serializable
data class BackupManifest(
    val kind: String = "",
    val format: Int = 0,
    @SerialName("backup_id") val backupId: String = "",
    @SerialName("created_at") val createdAt: String = "",
    val counts: Map<String, Int> = emptyMap(),
    val files: Int = 0,
    val bytes: Long = 0,
    @SerialName("include_raw") val includeRaw: Boolean = true,
    @SerialName("include_cache") val includeCache: Boolean = true,
    val dirs: List<String> = emptyList(),
    val entries: List<BackupEntry> = emptyList(),
)

internal val BackupJson = Json {
    ignoreUnknownKeys = true
    isLenient = false
}
