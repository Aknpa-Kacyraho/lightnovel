package com.kacyraho.lightnovel.feature.chapters

import android.content.ContentResolver
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kacyraho.lightnovel.data.download.BookDownloadScheduler
import com.kacyraho.lightnovel.data.export.EpubExporter
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.local.ReadStateEntity
import com.kacyraho.lightnovel.data.repository.LibraryRepository
import com.kacyraho.lightnovel.data.source.DirectLibraryService
import com.kacyraho.lightnovel.data.source.SourceDetail
import com.kacyraho.lightnovel.data.translation.MetadataTranslationService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

data class ChapterListUiState(
    val loading: Boolean = true,
    val book: BookEntity? = null,
    val detail: SourceDetail? = null,
    val chapters: List<ChapterEntity> = emptyList(),
    val readState: ReadStateEntity? = null,
    val error: String? = null,
    val message: String? = null,
    val exporting: Boolean = false,
    val downloading: Boolean = false,
    val downloadProgress: String? = null,
    val favorite: Boolean = false,
    val catalogQuery: String = "",
    val catalogSortDesc: Boolean = false,
    val catalogStatus: String = "all",
)

class ChapterListViewModel(
    private val repository: LibraryRepository,
    private val epubExporter: EpubExporter,
    private val onlineBookService: DirectLibraryService,
    private val metadataService: MetadataTranslationService? = null,
    private val downloadScheduler: BookDownloadScheduler? = null,
    private val bookId: String,
) : ViewModel() {
    private val _state = MutableStateFlow(ChapterListUiState())
    val state: StateFlow<ChapterListUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            runCatching {
                val book = repository.book(bookId)
                val chapters = repository.observeChapters(bookId).first()
                val readState = repository.readState(bookId)
                val detail = book?.takeIf { !it.local }?.let {
                    runCatching { onlineBookService.detail(it) }.getOrNull()
                }
                ChapterListUiState(
                    loading = false,
                    book = book,
                    detail = detail,
                    chapters = chapters,
                    readState = readState,
                    favorite = readState?.favorite == true,
                )
            }.onSuccess { loaded ->
                _state.value = loaded
                val book = loaded.book
                if (book != null && !book.local) {
                    viewModelScope.launch {
                        val summary = runCatching {
                            metadataService?.translateSummary(book, loaded.detail)
                        }.getOrNull()
                        if (summary != null) {
                            _state.value = _state.value.copy(
                                book = book.copy(
                                    titleZh = summary.titleZh.ifBlank { book.titleZh },
                                ),
                                detail = loaded.detail?.let { detail ->
                                    detail.copy(
                                        book = detail.book.copy(
                                            titleZh = summary.titleZh.ifBlank {
                                                detail.book.titleZh
                                            },
                                            synopsisZh = summary.synopsisZh.ifBlank {
                                                detail.book.synopsisZh
                                            },
                                            tagsZh = summary.tagsZh.ifEmpty {
                                                detail.book.tagsZh
                                            },
                                        ),
                                        synopsis = summary.synopsisZh.ifBlank {
                                            detail.synopsis
                                        },
                                    )
                                },
                            )
                        }
                        if (loaded.chapters.any { it.titleZh.isNullOrBlank() }) {
                            val titles = runCatching {
                                metadataService?.translateChapterTitles(book, loaded.chapters)
                            }.getOrNull().orEmpty()
                            if (titles.any(String::isNotBlank)) {
                                _state.value = _state.value.copy(
                                    chapters = loaded.chapters.mapIndexed { index, chapter ->
                                        chapter.copy(
                                            titleZh = titles.getOrNull(index)
                                                ?.ifBlank { chapter.titleZh }
                                                ?: chapter.titleZh,
                                        )
                                    },
                                )
                            }
                        }
                    }
                }
            }.onFailure {
                _state.value = ChapterListUiState(
                    loading = false,
                    error = it.message ?: "加载失败",
                )
            }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            val book = repository.book(bookId) ?: return@launch
            val chapters = repository.observeChapters(bookId).first()
            val readState = repository.readState(bookId)
            _state.value = _state.value.copy(
                book = book.copy(titleZh = _state.value.book?.titleZh ?: book.titleZh),
                chapters = chapters,
                readState = readState,
                favorite = readState?.favorite == true,
            )
        }
    }

    fun toggleFavorite() {
        val current = _state.value
        val book = current.book ?: return
        viewModelScope.launch {
            runCatching { repository.setFavorite(book.id, !current.favorite) }
                .onSuccess {
                    _state.value = _state.value.copy(
                        favorite = !current.favorite,
                        readState = current.readState?.copy(favorite = !current.favorite),
                        message = if (!current.favorite) "已收藏" else "已取消收藏",
                    )
                }
                .onFailure {
                    _state.value = _state.value.copy(error = it.message ?: "收藏失败")
                }
        }
    }

    fun setCatalogQuery(value: String) {
        _state.value = _state.value.copy(catalogQuery = value)
    }

    fun toggleCatalogSort() {
        _state.value = _state.value.copy(catalogSortDesc = !_state.value.catalogSortDesc)
    }

    fun setCatalogStatus(value: String) {
        _state.value = _state.value.copy(catalogStatus = value)
    }

    fun downloadAll() {
        val book = _state.value.book ?: return
        if (book.local || _state.value.downloading) return
        val scheduler = downloadScheduler
        if (scheduler != null) {
            scheduler.enqueue(book.id)
            _state.value = _state.value.copy(
                downloading = false,
                downloadProgress = null,
                message = "已加入后台下载，可离开此页",
                error = null,
            )
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(
                downloading = true,
                downloadProgress = "准备下载",
                error = null,
                message = null,
            )
            runCatching {
                val chapters = _state.value.chapters
                var done = 0
                var failed = 0
                for (chapter in chapters) {
                    val ok = runCatching {
                        onlineBookService.ensureChapter(book, chapter.idx)
                    }.getOrDefault(false)
                    if (ok) done++ else failed++
                    _state.value = _state.value.copy(
                        downloadProgress = "$done/${chapters.size}" +
                            if (failed > 0) " · 失败 $failed" else "",
                    )
                }
                done to failed
            }.onSuccess { (done, failed) ->
                _state.value = _state.value.copy(
                    downloading = false,
                    downloadProgress = null,
                    message = if (failed == 0) "已缓存 $done 话" else "已缓存 $done 话，$failed 话失败",
                )
            }.onFailure {
                _state.value = _state.value.copy(
                    downloading = false,
                    downloadProgress = null,
                    error = it.message ?: "下载失败",
                )
            }
        }
    }

    fun exportEpub(uri: Uri, resolver: ContentResolver) {
        val book = _state.value.book ?: return
        if (_state.value.exporting) return
        viewModelScope.launch {
            _state.value = _state.value.copy(
                exporting = true,
                message = "正在导出 EPUB",
                error = null,
            )
            runCatching {
                resolver.openOutputStream(uri)?.use { output ->
                    epubExporter.export(book, output)
                } ?: error("无法创建 EPUB 文件")
            }.onSuccess {
                _state.value = _state.value.copy(
                    exporting = false,
                    message = "EPUB 已导出",
                )
            }.onFailure {
                _state.value = _state.value.copy(
                    exporting = false,
                    error = it.message ?: "EPUB 导出失败",
                )
            }
        }
    }

    fun consumeMessage() {
        _state.value = _state.value.copy(message = null, error = null)
    }
}
