package com.kacyraho.lightnovel.feature.discover

import androidx.lifecycle.ViewModel
import com.kacyraho.lightnovel.core.settings.SearchHistoryStore
import com.kacyraho.lightnovel.core.settings.SearchPreset
import com.kacyraho.lightnovel.core.settings.SearchPresetStore
import com.kacyraho.lightnovel.core.settings.SettingsStore
import androidx.lifecycle.viewModelScope
import com.kacyraho.lightnovel.data.catalog.CatalogRepository
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
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
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
    val loadingPool: Boolean = false,
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
    private val catalog: CatalogRepository? = null,
    private val settingsStore: SettingsStore? = null,
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
    private var recommendationVersion = 0
    private var poolCrawlAttempted = false

    init {
        loadRecommendations()
    }

    fun loadRecommendations() {
        viewModelScope.launch {
            val version = ++recommendationVersion
            val shelf = runCatching { library.shelfKeys() }.getOrDefault(emptySet())
            _state.value = _state.value.copy(
                addedKeys = _state.value.addedKeys + shelf,
            )
            val store = catalog
            val existing = store?.let { repo ->
                repo.random(48).filterNot { it.key() in shelf }.take(24)
            }.orEmpty()
            _state.value = _state.value.copy(
                loadingRecommendations = existing.isEmpty(),
                recommendations = if (existing.isNotEmpty()) existing else _state.value.recommendations,
            )
            if (existing.isNotEmpty()) translateCards(existing, null, version)
            if (store == null) {
                loadSourceRecommendations()
                return@launch
            }
            val count = runCatching { store.count() }.getOrDefault(0)
            val lastCrawlAt = runCatching {
                settingsStore?.settings?.first()?.catalogCrawlAt ?: 0L
            }.getOrDefault(0L)
            val crawlFresh = lastCrawlAt > 0 &&
                System.currentTimeMillis() - lastCrawlAt < 7L * 24 * 60 * 60 * 1000
            if (count >= 200 || poolCrawlAttempted || crawlFresh) {
                if (existing.isEmpty()) loadSourceRecommendations()
                return@launch
            }
            poolCrawlAttempted = true
            _state.value = _state.value.copy(loadingPool = true)
            val pool = crawlPool()
            if (pool.isNotEmpty()) {
                val saved = runCatching { store.remember(pool) }.getOrDefault(0)
                if (saved > 0) {
                    runCatching {
                        settingsStore?.update {
                            it.copy(catalogCrawlAt = System.currentTimeMillis())
                        }
                    }
                }
                val recommendations = runCatching {
                    store.random(48).filterNot { it.key() in shelf }.take(24)
                }.getOrNull().orEmpty().ifEmpty {
                    runCatching { store.random(24) }.getOrNull().orEmpty()
                }
                _state.value = _state.value.copy(
                    loadingRecommendations = false,
                    loadingPool = false,
                    recommendations = recommendations,
                )
                if (recommendations.isNotEmpty()) translateCards(recommendations, null, version)
            } else {
                _state.value = _state.value.copy(loadingPool = false)
                if (existing.isEmpty()) loadSourceRecommendations()
            }
        }
    }

    fun shuffleRecommendations() {
        viewModelScope.launch {
            val version = ++recommendationVersion
            val shelf = runCatching { library.shelfKeys() }.getOrDefault(emptySet())
            val pool = runCatching {
                catalog?.random(48)?.filterNot { it.key() in shelf }?.take(24)
            }.getOrNull().orEmpty().ifEmpty {
                runCatching { catalog?.random(24) }.getOrNull().orEmpty()
            }
            if (pool.isEmpty()) return@launch
            _state.value = _state.value.copy(recommendations = pool, errors = emptyList())
            translateCards(pool, null, version)
        }
    }

    private suspend fun crawlPool(): List<SourceBook> {
        val gate = Semaphore(8)
        val found = coroutineScope {
            sources.map { source ->
                async {
                    (0 until 10).map { page ->
                        async {
                            gate.withPermit {
                                runCatching {
                                    withTimeoutOrNull(8_000) { source.discoverPage(page) }
                                        ?: emptyList()
                                }.getOrDefault(emptyList())
                            }
                        }
                    }.awaitAll().flatten()
                }
            }.awaitAll()
        }
        return interleave(found).distinctBy { it.provider + "/" + it.id }
    }

    private fun loadSourceRecommendations() {
        viewModelScope.launch {
            val version = ++recommendationVersion
            val shelf = runCatching { library.shelfKeys() }.getOrDefault(emptySet())
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
            ).distinctBy { it.provider + "/" + it.id }
                .filterNot { it.key() in shelf }
                .take(24)
            val errors = found.mapNotNull { (source, result) ->
                result.exceptionOrNull()?.let { errorText(source.label, it) }
            }
            _state.value = _state.value.copy(
                loadingRecommendations = false,
                recommendations = recommendations,
                addedKeys = _state.value.addedKeys + shelf,
                errors = _state.value.errors + errors,
            )
            runCatching { catalog?.remember(recommendations) }
            if (recommendations.isNotEmpty()) {
                translateCards(recommendations, null, version)
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
            runCatching { catalog?.remember(results) }
            if (results.isNotEmpty()) {
                translateCards(results, token)
            }
        }
    }

    private fun translateCards(
        items: List<SourceBook>,
        token: Int?,
        recommendationVersion: Int? = null,
    ) {
        viewModelScope.launch {
            _state.value = _state.value.copy(metadataLoading = true)
            val translated = runCatching {
                withTimeoutOrNull(45_000) {
                    metadataService?.translateCards(items)
                }
            }.getOrNull()
            if (recommendationVersion != null &&
                recommendationVersion != this@DiscoverViewModel.recommendationVersion
            ) {
                _state.value = _state.value.copy(metadataLoading = false)
                return@launch
            }
            if (token != null && token != searchToken) {
                _state.value = _state.value.copy(metadataLoading = false)
                if (!translated.isNullOrEmpty()) {
                    runCatching { catalog?.remember(translated) }
                }
                return@launch
            }
            _state.value = _state.value.copy(
                metadataLoading = false,
                recommendations = if (token == null) translated ?: _state.value.recommendations
                else _state.value.recommendations,
                results = if (token != null) translated ?: _state.value.results
                else _state.value.results,
            )
            if (!translated.isNullOrEmpty()) {
                runCatching { catalog?.remember(translated) }
            }
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
                    runCatching {
                        catalog?.remember(listOf(book))
                        catalog?.remember(listOf(library.detail(entity).book))
                    }
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

    private fun SourceBook.key(): String = "$provider/$id"

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
