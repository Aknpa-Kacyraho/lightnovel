package com.kacyraho.lightnovel.feature.library

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.SafStager
import com.kacyraho.lightnovel.data.import.ImportCoordinator
import com.kacyraho.lightnovel.data.import.LocalDocumentImporter
import com.kacyraho.lightnovel.data.local.BookWithState
import com.kacyraho.lightnovel.data.repository.LibraryRepository
import com.kacyraho.lightnovel.data.repository.ShelfFilter
import com.kacyraho.lightnovel.data.translation.MetadataTranslationService
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class LibraryUiState(
    val loading: Boolean = true,
    val books: List<BookWithState> = emptyList(),
    val shelf: String? = null,
    val query: String = "",
    val favoritesOnly: Boolean = false,
    val error: String? = null,
)

data class LibraryImportState(
    val importing: Boolean = false,
    val message: String? = null,
    val error: String? = null,
)

private data class LibraryFilter(
    val shelf: String? = null,
    val query: String = "",
    val favoritesOnly: Boolean = false,
)

class LibraryViewModel(
    private val repository: LibraryRepository,
    private val importCoordinator: ImportCoordinator,
    private val safStager: SafStager,
    private val localDocumentImporter: LocalDocumentImporter,
    settingsStore: SettingsStore,
    private val metadataService: MetadataTranslationService? = null,
) : ViewModel() {
    private val filter = MutableStateFlow(LibraryFilter())

    init {
        viewModelScope.launch {
            val books = repository.observeBooks().first()
                .filter { !it.local && it.titleZh.isNullOrBlank() }
            if (books.isNotEmpty()) {
                runCatching { metadataService?.translateTitles(books) }
            }
        }
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    val state = filter
        .flatMapLatest { current ->
            repository.observeLibrary(
                ShelfFilter(shelf = current.shelf, query = current.query),
            ).map { books ->
                val visible = if (current.favoritesOnly) {
                    books.filter { it.state?.favorite == true }
                } else {
                    books
                }
                LibraryUiState(
                    loading = false,
                    books = visible,
                    shelf = current.shelf,
                    query = current.query,
                    favoritesOnly = current.favoritesOnly,
                )
            }
        }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = LibraryUiState(),
        )

    val recent: StateFlow<List<BookWithState>> = repository.observeLibrary()
        .map { books ->
            books.filter { (it.state?.progressIdx ?: 0) > 0 }
                .sortedByDescending {
                    it.state?.updatedAt
                        ?: it.state?.openedAt
                        ?: it.state?.finishedAt
                        ?: it.book.createdAt
                        ?: ""
                }
                .take(5)
        }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = emptyList(),
        )

    fun setShelf(shelf: String?) {
        filter.value = filter.value.copy(shelf = shelf)
    }

    fun setFavoritesOnly(enabled: Boolean) {
        filter.value = filter.value.copy(favoritesOnly = enabled)
    }

    fun setQuery(query: String) {
        filter.value = filter.value.copy(query = query)
    }

    fun toggleFavorite(bookId: String, current: Boolean) {
        viewModelScope.launch {
            repository.setFavorite(bookId, !current)
        }
    }

    val lastBackupAt = settingsStore.settings
        .map { it.lastBackupAt }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = null,
        )

    private val _importState = MutableStateFlow(LibraryImportState())
    val importState: StateFlow<LibraryImportState> = _importState.asStateFlow()

    fun importDocument(uri: Uri, resolver: android.content.ContentResolver) {
        if (_importState.value.importing) return
        viewModelScope.launch {
            _importState.value = LibraryImportState(importing = true, message = "准备导入本地文件")
            runCatching {
                localDocumentImporter.import(uri, resolver) { phase ->
                    _importState.value = LibraryImportState(importing = true, message = phase)
                }
            }.onSuccess { book ->
                _importState.value = LibraryImportState(
                    importing = false,
                    message = "已导入《${book.titleZh ?: book.title}》",
                )
            }.onFailure {
                _importState.value = LibraryImportState(
                    importing = false,
                    error = it.message ?: "本地文件导入失败",
                )
            }
        }
    }

    fun import(uri: Uri) {
        if (_importState.value.importing) return
        viewModelScope.launch {
            _importState.value = LibraryImportState(importing = true, message = "准备导入")
            var staged: java.nio.file.Path? = null
            try {
                staged = safStager.stage(uri)
                val result = importCoordinator.import(staged) { phase ->
                    _importState.value = LibraryImportState(importing = true, message = phase)
                }
                _importState.value = LibraryImportState(
                    importing = false,
                    message = "导入完成：${result.applied.books} 本 / " +
                        "${result.applied.chapters} 章；建议到设置导出一次备份",
                )
            } catch (e: Exception) {
                _importState.value = LibraryImportState(
                    importing = false,
                    error = e.message ?: "导入失败",
                )
            } finally {
                safStager.cleanup(staged)
            }
        }
    }
}
