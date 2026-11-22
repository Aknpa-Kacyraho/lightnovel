package com.kacyraho.lightnovel.feature.library

enum class EmptyShelfAction {
    OPEN_DISCOVER,
    IMPORT_BACKUP,
    IMPORT_DOCUMENT,
    CLEAR_FILTERS,
}

data class EmptyShelfCopy(
    val title: String,
    val message: String,
    val primary: EmptyShelfAction,
    val secondary: List<EmptyShelfAction> = emptyList(),
)

/**
 * 书架空态只有两种真实情况：筛掉了 / 真的没有书。
 * 真的没有书时先给「去发现」主路径，再给旧备份与本地文件两个次级入口。
 */
fun emptyShelfCopy(
    query: String,
    favoritesOnly: Boolean,
    removedOnly: Boolean,
    shelf: String?,
): EmptyShelfCopy {
    val hasFilter = query.isNotBlank() || favoritesOnly || shelf != null
    return when {
        removedOnly && hasFilter -> EmptyShelfCopy(
            title = "没有匹配的已移出书籍",
            message = "清除搜索或筛选后再试；已移出的书仍保留在书架里。",
            primary = EmptyShelfAction.CLEAR_FILTERS,
        )

        removedOnly -> EmptyShelfCopy(
            title = "没有已移出的书",
            message = "移出书架的书会保留在这里，阅读进度和离线译文都不会丢。",
            primary = EmptyShelfAction.CLEAR_FILTERS,
        )

        hasFilter -> EmptyShelfCopy(
            title = "没有匹配的书",
            message = "清除搜索或筛选后再试。",
            primary = EmptyShelfAction.CLEAR_FILTERS,
        )

        else -> EmptyShelfCopy(
            title = "还没有书",
            message = "第一次用？去发现找一本日文轻小说。\n" +
                "有旧手机或旧备份？先导入备份，再继续读。",
            primary = EmptyShelfAction.OPEN_DISCOVER,
            secondary = listOf(
                EmptyShelfAction.IMPORT_BACKUP,
                EmptyShelfAction.IMPORT_DOCUMENT,
            ),
        )
    }
}
