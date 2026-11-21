package com.kacyraho.lightnovel.data.translation

import com.kacyraho.lightnovel.core.storage.ChapterCost
import com.kacyraho.lightnovel.core.storage.ChapterSidecar
import com.kacyraho.lightnovel.core.storage.ChapterTokens
import java.time.Instant

/**
 * 单段重译后的 sidecar：只更新内容相关字段。
 *
 * 其他段落仍是旧术语/旧配置，因此整章的 `translationConfigHash`、
 * `glossaryRevision`、`storyRevision`、`glossaryHash` 必须保留翻译时的值，
 * 让阅读器继续提示过期，直到用户整章重译。
 */
internal fun retranslatedParagraphSidecar(
    old: ChapterSidecar,
    newText: String,
    tokens: ChapterTokens,
    cost: ChapterCost,
    incomplete: List<Int>,
): ChapterSidecar = old.copy(
    status = if (incomplete.isEmpty()) "complete" else "partial",
    contentSha256 = Hashes.sha256(newText),
    translatedAt = Instant.now().toString(),
    tokens = tokens,
    cost = cost,
    incompleteParagraphs = incomplete,
    incompleteReason = if (incomplete.isEmpty()) null else old.incompleteReason,
)
