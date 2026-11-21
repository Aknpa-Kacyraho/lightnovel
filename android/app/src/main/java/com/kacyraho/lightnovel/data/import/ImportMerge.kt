package com.kacyraho.lightnovel.data.import

import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.BookTags
import com.kacyraho.lightnovel.data.local.ReadStateEntity

/**
 * 备份导入的合并规则：已存在的数据优先，只补缺失字段。
 *
 * 导入备份的语义是「找回丢失的内容」，不是「把书架回滚到备份时刻」。
 * 直接用 `@Upsert` 会把旧备份的空值覆盖现有翻译标题、标签、进度与 token 统计。
 */
internal fun mergeBook(
    existing: BookEntity?,
    planned: PlannedBook,
    chapterCount: Int,
): BookEntity {
    if (existing == null) {
        return BookEntity(
            id = planned.id,
            storageDir = planned.storageDir,
            slug = planned.slug,
            source = planned.source,
            sourceId = planned.sourceId,
            title = planned.title,
            titleZh = planned.titleZh,
            author = planned.author,
            tagsJson = BookTags.encode(planned.tags),
            genre = null,
            episodes = maxOf(planned.episodes, chapterCount),
            local = planned.source == "local",
            createdAt = planned.addedAt,
            legacyJson = planned.legacyJson,
        )
    }
    return existing.copy(
        storageDir = existing.storageDir.ifBlank { planned.storageDir },
        slug = existing.slug?.takeIf(String::isNotBlank) ?: planned.slug,
        title = existing.title.ifBlank { planned.title },
        titleZh = existing.titleZh?.takeIf(String::isNotBlank) ?: planned.titleZh,
        author = existing.author?.takeIf(String::isNotBlank) ?: planned.author,
        tagsJson = existing.tagsJson?.takeIf(String::isNotBlank)
            ?: BookTags.encode(planned.tags),
        episodes = maxOf(existing.episodes, planned.episodes, chapterCount),
        createdAt = existing.createdAt ?: planned.addedAt,
        legacyJson = existing.legacyJson ?: planned.legacyJson,
    )
}

/**
 * 阅读状态合并：按 `updated_at` 取较新的一方；收藏取并集；已移出状态保留现有。
 */
internal fun mergeReadState(
    existing: ReadStateEntity?,
    planned: ReadStateEntity,
): ReadStateEntity {
    if (existing == null) return planned
    val existingAt = existing.updatedAt.orEmpty()
    val plannedAt = planned.updatedAt.orEmpty()
    val usePlanned = plannedAt.isNotBlank() && plannedAt > existingAt
    return if (usePlanned) {
        planned.copy(
            bookId = existing.bookId,
            favorite = existing.favorite || planned.favorite,
            hidden = existing.hidden,
        )
    } else {
        existing.copy(
            shelf = existing.shelf?.takeIf(String::isNotBlank) ?: planned.shelf,
            favorite = existing.favorite || planned.favorite,
            openedAt = existing.openedAt ?: planned.openedAt,
            finishedAt = existing.finishedAt ?: planned.finishedAt,
        )
    }
}

/**
 * 只插入本地缺失的章节；已存在的章节保留标题、token 与模型信息。
 */
internal fun missingChapters(
    planned: List<PlannedChapter>,
    existingKeys: Set<Pair<String, Int>>,
): List<PlannedChapter> = planned
    .distinctBy { it.bookId to it.idx }
    .filter { (it.bookId to it.idx) !in existingKeys }
