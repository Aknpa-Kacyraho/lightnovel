package com.kacyraho.lightnovel.feature.reader

internal enum class ReaderMenuGroup(val label: String) {
    READING("阅读"),
    TRANSLATION("翻译"),
    REFERENCE("资料"),
    WORLDLINE("世界线"),
}

internal enum class ReaderMenuAction {
    TOGGLE_THEME,
    IMMERSIVE,
    TRANSLATE,
    POLISH,
    CHAPTER_INFO,
    STORY_MEMORY,
    NEARBY_ENTITIES,
    QUERY_MODE,
    GLOSSARY,
    PARAGRAPH,
    ADD_BOOKMARK,
    OPEN_BOOKMARKS,
    SEARCH_BOOK,
    TYPOGRAPHY,
    TOGGLE_READER_MODE,
    WORLDLINE,
}

internal data class ReaderMenuItem(
    val group: ReaderMenuGroup,
    val action: ReaderMenuAction,
    val label: String,
    val enabled: Boolean = true,
)

/**
 * 阅读器「更多」菜单的唯一事实来源：分组、文案、可用条件都在这里。
 * 渲染层只负责按组输出，新增功能时不会再把项散落在 Composable 里。
 */
internal fun readerMenuItems(
    fontSizeSp: Float,
    hasTranslation: Boolean,
    translationEnabled: Boolean,
    hasStoryMemory: Boolean,
    queryMode: Boolean,
    charCount: Int = 0,
    costLabel: String? = null,
    hasBookmarkHere: Boolean = false,
    readerMode: String = "page",
): List<ReaderMenuItem> = buildList {
    val reading = ReaderMenuGroup.READING
    val translation = ReaderMenuGroup.TRANSLATION
    val reference = ReaderMenuGroup.REFERENCE
    val worldline = ReaderMenuGroup.WORLDLINE
    val detail = listOfNotNull(formatCharCount(charCount), costLabel?.takeIf { it.isNotBlank() })
        .joinToString(" · ")
    val detailSuffix = detail.takeIf { it.isNotBlank() }?.let { "（$it）" }.orEmpty()

    add(ReaderMenuItem(reading, ReaderMenuAction.TOGGLE_THEME, "切换纸色"))
    add(ReaderMenuItem(reading, ReaderMenuAction.TYPOGRAPHY, "排版"))
    add(
        ReaderMenuItem(
            reading,
            ReaderMenuAction.TOGGLE_READER_MODE,
            if (readerMode == "scroll") "滚动模式" else "翻页模式",
        ),
    )
    add(ReaderMenuItem(reading, ReaderMenuAction.IMMERSIVE, "沉浸阅读"))
    add(
        ReaderMenuItem(
            reading,
            ReaderMenuAction.ADD_BOOKMARK,
            if (hasBookmarkHere) "已添加书签" else "添加书签",
        ),
    )

    add(
        ReaderMenuItem(
            translation,
            ReaderMenuAction.TRANSLATE,
            (if (hasTranslation) "重译本章" else "翻译本章") + detailSuffix,
            enabled = translationEnabled,
        ),
    )
    add(
        ReaderMenuItem(
            translation,
            ReaderMenuAction.POLISH,
            "润色本章",
            enabled = translationEnabled && hasTranslation,
        ),
    )
    add(ReaderMenuItem(translation, ReaderMenuAction.CHAPTER_INFO, "本章信息"))

    if (hasStoryMemory) {
        add(ReaderMenuItem(reference, ReaderMenuAction.STORY_MEMORY, "本书设定"))
    }
    add(ReaderMenuItem(reference, ReaderMenuAction.NEARBY_ENTITIES, "附近词条"))
    add(
        ReaderMenuItem(
            reference,
            ReaderMenuAction.QUERY_MODE,
            if (queryMode) "查询模式：开" else "查询模式：关",
        ),
    )
    add(ReaderMenuItem(reference, ReaderMenuAction.GLOSSARY, "术语表"))
    add(ReaderMenuItem(reference, ReaderMenuAction.PARAGRAPH, "当前段落"))
    add(ReaderMenuItem(reference, ReaderMenuAction.OPEN_BOOKMARKS, "书签列表"))
    add(ReaderMenuItem(reference, ReaderMenuAction.SEARCH_BOOK, "搜索本书"))

    add(ReaderMenuItem(worldline, ReaderMenuAction.WORLDLINE, "编辑并生成世界线"))
}

/**
 * 翻译前的规模提示：0 不显示，千字以内按整字，超过按千字保留一位小数。
 */
internal fun formatCharCount(count: Int): String? = when {
    count <= 0 -> null
    count < 1000 -> "约 $count 字"
    else -> "约 %.1f 千字".format(java.util.Locale.US, count / 1000f)
}
