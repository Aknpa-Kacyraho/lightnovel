package com.kacyraho.lightnovel.feature.reader

/**
 * 译文是否应该因为「术语变化」而提示过期。
 *
 * 新译文记录纯术语 hash（[sidecarGlossaryHash]），只比较术语本身；
 * 旧译文没有该字段，回退到综合 revision 比较，保持原有行为。
 */
internal fun glossaryOutdated(
    sidecarGlossaryHash: String?,
    sidecarRevision: String?,
    currentGlossaryHash: String,
    currentCombinedRevision: String,
): Boolean {
    if (!sidecarGlossaryHash.isNullOrBlank()) {
        return currentGlossaryHash.isNotBlank() &&
            sidecarGlossaryHash != currentGlossaryHash
    }
    return currentCombinedRevision.isNotBlank() &&
        sidecarRevision != currentCombinedRevision
}
