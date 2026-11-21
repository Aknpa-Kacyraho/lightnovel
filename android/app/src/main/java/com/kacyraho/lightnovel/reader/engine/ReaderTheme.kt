package com.kacyraho.lightnovel.reader.engine

import androidx.compose.ui.graphics.Color

enum class ReaderTheme(
    val id: String,
    val label: String,
    val background: Color,
    val text: Color,
    val secondary: Color,
    val danger: Color,
) {
    // AUTO 只保存偏好，渲染前必须调用 resolve(dark)；这里的颜色只是占位。
    AUTO(
        "auto",
        "跟随系统",
        Color(0xFFF8F5EE),
        Color(0xFF2A2824),
        Color(0xFF6E675C),
        Color(0xFFB3261E),
    ),
    PAPER("paper", "纸白", Color(0xFFF8F5EE), Color(0xFF2A2824), Color(0xFF6E675C), Color(0xFFB3261E)),
    SEPIA("sepia", "米黄", Color(0xFFF3E9D2), Color(0xFF3A3226), Color(0xFF7A6A52), Color(0xFFB3261E)),
    GREEN("green", "护眼", Color(0xFFEDF2E6), Color(0xFF22302A), Color(0xFF4F6B5D), Color(0xFFB3261E)),
    NIGHT("night", "夜间", Color(0xFF171614), Color(0xFFB8B3A8), Color(0xFF8F8A80), Color(0xFFFFB4AB)),
    ;

    /** 把用户偏好解析成可渲染的纸色；AUTO 按系统深浅色落到纸白或夜间。 */
    fun resolve(dark: Boolean): ReaderTheme = when {
        this != AUTO -> this
        dark -> NIGHT
        else -> PAPER
    }

    companion object {
        fun fromId(id: String): ReaderTheme =
            entries.firstOrNull { it.id == id } ?: PAPER
    }
}
