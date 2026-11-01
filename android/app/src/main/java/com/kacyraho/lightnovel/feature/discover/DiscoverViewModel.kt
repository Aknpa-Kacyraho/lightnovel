package com.kacyraho.lightnovel.feature.discover

import androidx.lifecycle.ViewModel
import com.kacyraho.lightnovel.core.settings.SearchHistoryStore
import com.kacyraho.lightnovel.core.settings.SearchPreset
import com.kacyraho.lightnovel.core.settings.SearchPresetStore
import androidx.lifecycle.viewModelScope
import com.kacyraho.lightnovel.data.source.DirectLibraryService
import com.kacyraho.lightnovel.data.source.SourceBook
import com.kacyraho.lightnovel.data.source.WebSource
import com.kacyraho.lightnovel.data.translation.MetadataTranslationService
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

data class DiscoverUiState(
    val query: String = "",
    val urlInput: String = "",
    val mode: String = "keyword",
    val loading: Boolean = false,
    val addingId: String? = null,
    val addedKeys: Set<String> = emptySet(),
    val results: List<SourceBook> = emptyList(),
    val recommendations: List<SourceBook> = emptyList(),
    val loadingRecommendations: Boolean = false,
    val metadataLoading: Boolean = false,
    val recentSearches: List<String> = emptyList(),
    val savedSearches: List<SearchPreset> = emptyList(),
    val sourceFilter: String? = null,
    val searchedQuery: String? = null,
    val statusFilter: String? = null,
    val characterFilter: String = "all",
    val preview: SourceBook? = null,
    val linkSheetOpen: Boolean = false,
    val errors: List<String> = emptyList(),
    val addedBookId: String? = null,
)

class DiscoverViewModel(
    private val sources: List<WebSource>,
    private val library: DirectLibraryService,
    private val metadataService: MetadataTranslationService? = null,
    private val historyStore: SearchHistoryStore? = null,
    private val presetStore: SearchPresetStore? = null,
) : ViewModel() {
    private val _state = MutableStateFlow(
        DiscoverUiState(
            recentSearches = historyStore?.load().orEmpty(),
            savedSearches = presetStore?.load().orEmpty(),
        ),
    )
    val state: StateFlow<DiscoverUiState> = _state.asStateFlow()
    private var searchJob: Job? = null
    private var searchToken = 0

    init {
        loadRecommendations()
    }

    fun loadRecommendations() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loadingRecommendations = true)
            val found = coroutineScope {
                sources.map { source ->
                    async {
                        source to runCatching {
                            withTimeoutOrNull(8_000) { source.recommend() } ?: emptyList()
                        }
                    }
                }.awaitAll()
            }
            val recommendations = interleave(
                found.map { (_, result) -> result.getOrDefault(emptyList()) },
            ).distinctBy { it.provider + "/" + it.id }.take(12)
            val errors = found.mapNotNull { (source, result) ->
                result.exceptionOrNull()?.let { errorText(source.label, it) }
            }
            _state.value = _state.value.copy(
                loadingRecommendations = false,
                recommendations = recommendations,
                errors = _state.value.errors + errors,
            )
            if (recommendations.isNotEmpty()) {
                translateCards(recommendations, null)
            }
        }
    }

    fun onQueryChange(query: String) {
        _state.value = _state.value.copy(query = query)
    }

    fun clearSearch() {
        searchJob?.cancel()
        _state.value = _state.value.copy(
            query = "",
            results = emptyList(),
            searchedQuery = null,
            loading = false,
            errors = emptyList(),
        )
    }

    fun onUrlChange(value: String) {
        _state.value = _state.value.copy(urlInput = value)
    }

    fun openLinkSheet() {
        _state.value = _state.value.copy(linkSheetOpen = true, errors = emptyList())
    }

    fun closeLinkSheet() {
        _state.value = _state.value.copy(linkSheetOpen = false)
    }

    fun searchTag(tag: String) {
        search(tag, "tag")
    }

    fun searchAuthor(author: String) {
        search(author, "author")
    }

    fun search(
        query: String = _state.value.query,
        mode: String = _state.value.mode,
    ) {
        if (query.isBlank()) return
        searchJob?.cancel()
        val token = ++searchToken
        searchJob = viewModelScope.launch {
            val recent = historyStore?.remember(query) ?: _state.value.recentSearches
            _state.value = _state.value.copy(
                query = query,
                mode = mode,
                loading = true,
                results = emptyList(),
                searchedQuery = null,
                recentSearches = recent,
                errors = emptyList(),
            )
            val found = coroutineScope {
                sources.map { source ->
                    async {
                        source to runCatching {
                            withTimeoutOrNull(8_000) { source.search(query) } ?: emptyList()
                        }
                    }
                }.awaitAll()
            }
            if (token != searchToken) return@launch
            val results = interleave(
                found.map { (_, result) -> result.getOrDefault(emptyList()) },
            ).distinctBy { it.provider + "/" + it.id }
                .take(20)
            val errors = found.mapNotNull { (source, result) ->
                result.exceptionOrNull()?.let { errorText(source.label, it) }
            }
            _state.value = _state.value.copy(
                loading = false,
                results = results,
                searchedQuery = query,
                errors = errors,
            )
            if (results.isNotEmpty()) {
                translateCards(results, token)
            }
        }
    }

    private fun translateCards(items: List<SourceBook>, token: Int?) {
        viewModelScope.launch {
            _state.value = _state.value.copy(metadataLoading = true)
            val translated = runCatching {
                metadataService?.translateCards(items)
            }.getOrNull()
            if (token != null && token != searchToken) {
                _state.value = _state.value.copy(metadataLoading = false)
                return@launch
            }
            _state.value = _state.value.copy(
                metadataLoading = false,
                recommendations = if (token == null) translated ?: _state.value.recommendations
                else _state.value.recommendations,
                results = if (token != null) translated ?: _state.value.results
                else _state.value.results,
            )
        }
    }

    fun setSourceFilter(provider: String?) {
        _state.value = _state.value.copy(sourceFilter = provider)
    }

    fun clearSearchHistory() {
        historyStore?.clear()
        _state.value = _state.value.copy(recentSearches = emptyList())
    }

    fun saveCurrentSearch() {
        val current = _state.value
        if (current.query.isBlank()) return
        val preset = SearchPreset(
            query = current.query.trim(),
            source = current.sourceFilter,
            status = current.statusFilter,
            characters = current.characterFilter,
        )
        _state.value = current.copy(savedSearches = presetStore?.save(preset).orEmpty())
    }

    fun applyPreset(preset: SearchPreset) {
        _state.value = _state.value.copy(
            query = preset.query,
            sourceFilter = preset.source,
            statusFilter = preset.status,
            characterFilter = preset.characters,
        )
        search(preset.query, _state.value.mode)
    }

    fun removePreset(id: String) {
        _state.value = _state.value.copy(savedSearches = presetStore?.remove(id).orEmpty())
    }

    fun setStatusFilter(value: String?) {
        _state.value = _state.value.copy(statusFilter = value)
    }

    fun setCharacterFilter(value: String) {
        if (value !in setOf("all", "short", "medium", "long")) return
        _state.value = _state.value.copy(characterFilter = value)
    }

    fun preview(book: SourceBook) {
        _state.value = _state.value.copy(preview = book)
    }

    fun dismissPreview() {
        _state.value = _state.value.copy(preview = null)
    }

    fun add(book: SourceBook) {
        if (_state.value.addingId != null) return
        val key = book.provider + "/" + book.id
        viewModelScope.launch {
            _state.value = _state.value.copy(addingId = key, errors = emptyList())
            runCatching { library.addToShelf(book) }
                .onSuccess { entity ->
                    _state.value = _state.value.copy(
                        addingId = null,
                        preview = null,
                        linkSheetOpen = false,
                        addedKeys = _state.value.addedKeys + key,
                        addedBookId = entity.id,
                    )
                }
                .onFailure {
                    _state.value = _state.value.copy(
                        addingId = null,
                        errors = _state.value.errors + (it.message ?: "加入书架失败"),
                    )
                }
        }
    }

    fun addFromUrl() {
        val input = _state.value.urlInput.trim()
        val kakuyomuId = Regex("""kakuyomu\.jp/works/(\d+)""")
            .find(input)?.groupValues?.getOrNull(1)
            ?: input.takeIf { Regex("""^\d{6,}$""").matches(it) }
        val syosetu = Regex(
            """(?:ncode|novel18)\.syosetu\.com/([nN][0-9A-Za-z]+)""",
        ).find(input)
        val book = when {
            kakuyomuId != null -> SourceBook(
                provider = "kakuyomu",
                id = kakuyomuId,
                title = "",
            )
            syosetu != null -> SourceBook(
                provider = "syosetu",
                id = syosetu.groupValues[1].uppercase(),
                title = "",
            )
            else -> {
                _state.value = _state.value.copy(
                    errors = listOf("只支持 Kakuyomu / 成为小说家吧作品链接"),
                )
                return
            }
        }
        add(book)
    }

    fun consumeAddedBook() {
        _state.value = _state.value.copy(addedBookId = null)
    }

    private fun <T> interleave(lists: List<List<T>>): List<T> {
        val result = mutableListOf<T>()
        val max = lists.maxOfOrNull { it.size } ?: 0
        for (index in 0 until max) {
            lists.forEach { list ->
                list.getOrNull(index)?.let { result += it }
            }
        }
        return result
    }

    private fun errorText(label: String, error: Throwable): String {
        val message = error.message.orEmpty()
        return if (message.contains("failed to connect", ignoreCase = true) ||
            message.contains("timeout", ignoreCase = true) ||
            error is java.io.IOException
        ) {
            "$label：暂时不可达"
        } else {
            "$label：${message.take(120).ifBlank { "请求失败" }}"
        }
    }
}
