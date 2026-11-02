package com.kacyraho.lightnovel.feature.catalog

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kacyraho.lightnovel.data.catalog.CatalogRepository
import com.kacyraho.lightnovel.data.catalog.key
import com.kacyraho.lightnovel.data.catalog.tagPairs
import com.kacyraho.lightnovel.data.catalog.toSourceBook
import com.kacyraho.lightnovel.data.local.BookTags
import com.kacyraho.lightnovel.data.local.CatalogBookEntity
import com.kacyraho.lightnovel.data.repository.LibraryRepository
import com.kacyraho.lightnovel.data.source.DirectLibraryService
import com.kacyraho.lightnovel.data.source.SourceBook
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

enum class CatalogSort(val id: String, val label: String) {
    RECENT("recent", "最近爬取"),
    UPDATED("updated", "最近更新"),
    EPISODES("episodes", "话数多"),
    CHARACTERS("characters", "字数多"),
    TITLE("title", "书名"),
    ;

    companion object {
        fun fromId(id: String): CatalogSort = entries.firstOrNull { it.id == id } ?: RECENT
    }
}

data class CatalogTag(
    val source: String,
    val label: String,
    val count: Int,
)

data class CatalogUiState(
    val loading: Boolean = true,
    val books: List<CatalogBookEntity> = emptyList(),
    val total: Int = 0,
    val tags: List<CatalogTag> = emptyList(),
    val query: String = "",
    val provider: String? = null,
    val status: String? = null,
    val selectedTags: Set<String> = emptySet(),
    val sort: CatalogSort = CatalogSort.RECENT,
    val addedKeys: Set<String> = emptySet(),
    val addingKey: String? = null,
    val error: String? = null,
)

private data class CatalogFilter(
    val query: String = "",
    val provider: String? = null,
    val status: String? = null,
    val selectedTags: Set<String> = emptySet(),
    val sort: CatalogSort = CatalogSort.RECENT,
)

private data class CatalogAction(
    val addingKey: String? = null,
    val error: String? = null,
)

class CatalogViewModel(
    private val catalog: CatalogRepository,
    private val library: LibraryRepository,
    private val directLibrary: DirectLibraryService,
) : ViewModel() {
    private val filter = MutableStateFlow(CatalogFilter())
    private val action = MutableStateFlow(CatalogAction())

    init {
        viewModelScope.launch {
            val rows = library.observeBooks().first()
                .filter { !it.local }
                .map { book ->
                    SourceBook(
                        provider = book.source,
                        id = book.sourceId,
                        title = book.title,
                        author = book.author.orEmpty(),
                        tags = BookTags.decode(book.tagsJson),
                        episodes = book.episodes,
                        titleZh = book.titleZh,
                    )
                }
            if (rows.isNotEmpty()) runCatching { catalog.remember(rows) }
        }
    }

    val state: StateFlow<CatalogUiState> = combine(
        catalog.observeAll(),
        library.observeBooks(),
        filter,
        action,
    ) { rows, books, current, currentAction ->
        val pairsByKey = rows.associate { it.key to it.tagPairs() }
        val tagCounts = linkedMapOf<String, CatalogTag>()
        rows.forEach { row ->
            pairsByKey[row.key].orEmpty().forEach { (source, label) ->
                val old = tagCounts[source]
                tagCounts[source] = CatalogTag(
                    source = source,
                    label = if (old == null || old.label == source) label else old.label,
                    count = (old?.count ?: 0) + 1,
                )
            }
        }
        val tags = tagCounts.values.sortedWith(
            compareByDescending<CatalogTag> { it.count }.thenBy { it.label },
        )
        val needle = current.query.trim()
        val visible = rows.asSequence()
            .map { row -> row to pairsByKey[row.key].orEmpty() }
            .filter { (row, rowTags) ->
                val sourceTags = rowTags.map { it.first }.toSet()
                val searchableTags = rowTags.flatMap { listOf(it.first, it.second) }
                (current.provider == null || row.provider == current.provider) &&
                    (current.status == null || row.status == current.status) &&
                    current.selectedTags.all { it in sourceTags } &&
                    (
                        needle.isBlank() ||
                            row.title.contains(needle, ignoreCase = true) ||
                            row.titleZh?.contains(needle, ignoreCase = true) == true ||
                            row.author?.contains(needle, ignoreCase = true) == true ||
                            searchableTags.any { it.contains(needle, ignoreCase = true) }
                        )
            }
            .map { it.first }
            .toList()
            .sortedWith(comparator(current.sort))
        CatalogUiState(
            loading = false,
            books = visible,
            total = rows.size,
            tags = tags,
            query = current.query,
            provider = current.provider,
            status = current.status,
            selectedTags = current.selectedTags,
            sort = current.sort,
            addedKeys = books.map { "${it.source}/${it.sourceId}" }.toSet(),
            addingKey = currentAction.addingKey,
            error = currentAction.error,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = CatalogUiState(),
    )

    fun setQuery(value: String) {
        filter.value = filter.value.copy(query = value)
    }

    fun setProvider(value: String?) {
        filter.value = filter.value.copy(provider = value)
    }

    fun setStatus(value: String?) {
        filter.value = filter.value.copy(status = value)
    }

    fun toggleTag(value: String) {
        val selected = filter.value.selectedTags
        filter.value = filter.value.copy(
            selectedTags = if (value in selected) selected - value else selected + value,
        )
    }

    fun setSort(value: String) {
        filter.value = filter.value.copy(sort = CatalogSort.fromId(value))
    }

    fun clearTags() {
        filter.value = filter.value.copy(selectedTags = emptySet())
    }

    fun clearFilters() {
        filter.value = CatalogFilter()
    }

    fun clearError() {
        action.value = action.value.copy(error = null)
    }

    fun add(book: CatalogBookEntity) {
        if (action.value.addingKey != null) return
        action.value = CatalogAction(addingKey = book.key)
        viewModelScope.launch {
            val sourceBook = book.toSourceBook()
            runCatching { catalog.remember(listOf(sourceBook)) }
            runCatching { directLibrary.addToShelf(sourceBook) }
                .onSuccess {
                    action.value = CatalogAction()
                }
                .onFailure {
                    action.value = CatalogAction(
                        error = "加入书架失败：${it.message ?: "未知错误"}",
                    )
                }
        }
    }

    private fun comparator(sort: CatalogSort): Comparator<CatalogBookEntity> = when (sort) {
        CatalogSort.RECENT -> compareByDescending { it.lastSeenAt }
        CatalogSort.UPDATED -> compareByDescending { it.updatedAt.orEmpty() }
        CatalogSort.EPISODES -> compareByDescending { it.episodes }
        CatalogSort.CHARACTERS -> compareByDescending { it.characters ?: 0 }
        CatalogSort.TITLE -> compareBy { it.titleZh ?: it.title }
    }
}
