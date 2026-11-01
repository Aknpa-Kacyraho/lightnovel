package com.kacyraho.lightnovel.data.source

data class SourceBook(
    val provider: String,
    val id: String,
    val title: String,
    val author: String = "",
    val tags: List<String> = emptyList(),
    val episodes: Int = 0,
    val url: String = "",
    val synopsis: String = "",
    val updatedAt: String = "",
    val status: String? = null,
    val characters: Int? = null,
    val genre: String? = null,
    val titleZh: String? = null,
    val synopsisZh: String? = null,
    val tagsZh: List<String> = emptyList(),
)

data class SourceChapterRef(
    val id: String,
    val title: String,
)

data class SourceDetail(
    val book: SourceBook,
    val chapters: List<SourceChapterRef>,
    val synopsis: String = "",
)

interface WebSource {
    val id: String
    val label: String

    suspend fun search(query: String, page: Int = 0): List<SourceBook>

    suspend fun recommend(): List<SourceBook> = emptyList()

    suspend fun detail(bookId: String): SourceDetail

    suspend fun chapter(bookId: String, chapterId: String): String
}

interface ChapterFetcher {
    suspend fun ensureChapter(book: com.kacyraho.lightnovel.data.local.BookEntity, idx: Int): Boolean
}
