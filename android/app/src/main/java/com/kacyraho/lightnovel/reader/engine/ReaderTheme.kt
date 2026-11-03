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
    PAPER("paper", "纸白", Color(0xFFFAFAF7), Color(0xFF242424), Color(0xFF6B6B66), Color(0xFFB3261E)),
    SEPIA("sepia", "米黄", Color(0xFFF5ECD9), Color(0xFF3A3226), Color(0xFF7A6A52), Color(0xFFB3261E)),
    GREEN("green", "护眼", Color(0xFFEFF6E9), Color(0xFF081B16), Color(0xFF4F6B5D), Color(0xFFB3261E)),
    NIGHT("night", "夜间", Color(0xFF121212), Color(0xFFC8C5BE), Color(0xFF8E8B84), Color(0xFFFFB4AB));

    companion object {
        fun fromId(id: String): ReaderTheme =
            entries.firstOrNull { it.id == id } ?: PAPER
    }
}
