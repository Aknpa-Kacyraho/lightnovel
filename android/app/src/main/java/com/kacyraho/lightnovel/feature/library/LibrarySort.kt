package com.kacyraho.lightnovel.feature.library

import com.kacyraho.lightnovel.data.local.BookWithState

enum class LibrarySort(val id: String, val label: String) {
    TITLE("title", "标题"),
    RECENT("recent", "最近阅读"),
    ADDED("added", "最近添加"),
    ;

    companion object {
        fun fromId(id: String?): LibrarySort = entries.firstOrNull { it.id == id } ?: TITLE
    }
}

/**
 * 书架排序只作用于完整列表，不影响「继续阅读」与筛选。
 * 时间字段缺失时排到最后；同值时保留原顺序（稳定排序）。
 */
internal fun sortLibrary(books: List<BookWithState>, sort: LibrarySort): List<BookWithState> =
    when (sort) {
        LibrarySort.TITLE -> books.sortedWith(
            compareBy(String.CASE_INSENSITIVE_ORDER) { it.book.titleZh ?: it.book.title },
        )

        LibrarySort.RECENT -> books.sortedByDescending {
            it.state?.updatedAt
                ?: it.state?.openedAt
                ?: it.state?.finishedAt
                ?: it.book.createdAt
                ?: ""
        }

        LibrarySort.ADDED -> books.sortedByDescending { it.book.createdAt ?: "" }
    }
