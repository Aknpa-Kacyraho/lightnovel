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
import com.kacyraho.lightnovel.data.translation.ReadingTranslationCoordinator
import com.kacyraho.lightnovel.data.translation.ReadingTranslationQueueState
import com.kacyraho.lightnovel.data.translation.TranslationOutcome
import com.kacyraho.lightnovel.data.translation.TranslationService
import com.kacyraho.lightnovel.data.translation.TranslationTaskRegistry
import com.kacyraho.lightnovel.data.translation.MetadataTranslationService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.CoroutineStart

enum class TranslationBatchScope {
    CURRENT,
    AHEAD,
    ALL,
}

private val TRANSLATED_STATUSES = setOf("complete", "translated")

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
    val translating: Boolean = false,
    val downloadProgress: String? = null,
    val favorite: Boolean = false,
    val catalogQuery: String = "",
    val catalogSortDesc: Boolean = false,
    val catalogStatus: String = "all",
    val translationQueue: ReadingTranslationQueueState? = null,
)

class ChapterListViewModel(
    private val repository: LibraryRepository,
    private val epubExporter: EpubExporter,
    private val onlineBookService: DirectLibraryService,
    private val metadataService: MetadataTranslationService? = null,
    private val downloadScheduler: BookDownloadScheduler? = null,
    private val translationService: TranslationService? = null,
    private val taskRegistry: TranslationTaskRegistry? = null,
    private val readingTranslationCoordinator: ReadingTranslationCoordinator? = null,
    private val bookId: String,
) : ViewModel() {
    private val _state = MutableStateFlow(ChapterListUiState())
    val state: StateFlow<ChapterListUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            readingTranslationCoordinator?.observe(bookId)?.collect { queue ->
                _state.value = _state.value.copy(translationQueue = queue)
            }
        }
        viewModelScope.launch {
            readingTranslationCoordinator?.translated?.collect { event ->
                if (event.bookId == bookId) refresh()
            }
        }
        viewModelScope.launch {
            runCatching {
                val book = repository.book(bookId)
                val chapters = repository.observeChapters(bookId).first()
                val readState = repository.readState(bookId)
                val detail = book?.takeIf { !it.local }?.let {
                    runCatching { onlineBookService.detail(it) }.getOrNull()
                }
                if (book != null && detail != null) {
                    runCatching { onlineBookService.syncChapterTitles(book, detail) }
                }
                val titledChapters = chapters.map { chapter ->
                    if (!chapter.title.isNullOrBlank()) {
                        chapter
                    } else {
                        detail?.chapters
                            ?.getOrNull(chapter.idx - 1)
                            ?.title
                            ?.takeIf(String::isNotBlank)
                            ?.let { chapter.copy(title = it) }
                            ?: chapter
                    }
                }
                ChapterListUiState(
                    loading = false,
                    book = book,
                    detail = detail,
                    chapters = titledChapters,
                    readState = readState,
                    favorite = readState?.favorite == true,
                )
            }.onSuccess { loaded ->
                _state.value = loaded.copy(translationQueue = _state.value.translationQueue)
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

    fun translateCurrent() {
        translateChapters(TranslationBatchScope.CURRENT)
    }

    fun translateChapters(scope: TranslationBatchScope, aheadCount: Int = 3) {
        val current = _state.value
        val book = current.book ?: return
        if (current.chapters.isEmpty()) return
        val startIndex = current.readState?.progressIdx?.takeIf {
            it in 1..current.chapters.lastIndex + 1
        } ?: current.chapters.first().idx
        val candidates = when (scope) {
            TranslationBatchScope.CURRENT -> current.chapters.filter { it.idx == startIndex }
            TranslationBatchScope.AHEAD -> current.chapters
                .filter { it.idx >= startIndex }
                .take(aheadCount.coerceIn(0, 10) + 1)
            TranslationBatchScope.ALL -> current.chapters
        }
        val targets = candidates
            .filter { it.status != "translating" && it.status !in TRANSLATED_STATUSES }
            .map { it.idx }
        if (targets.isEmpty()) {
            _state.value = current.copy(
                message = if (scope == TranslationBatchScope.ALL) {
                    "全书没有待翻译章节"
                } else {
                    "选中的章节已完成或正在翻译"
                },
                error = null,
            )
            return
        }
        if (readingTranslationCoordinator != null) {
            readingTranslationCoordinator.enqueue(book, targets)
            _state.value = current.copy(
                translating = false,
                message = "已加入 ${targets.size} 章翻译队列",
                error = null,
            )
            return
        }
        val service = translationService ?: run {
            _state.value = current.copy(error = "翻译服务不可用")
            return
        }
        val target = targets.first()
        _state.value = current.copy(
            translating = true,
            message = "正在翻译第 $target 章…",
            error = null,
        )
        val job = viewModelScope.launch(start = CoroutineStart.LAZY) {
            val outcome = service.translate(book, target)
            _state.value = _state.value.copy(
                translating = false,
                message = when (outcome) {
                    is TranslationOutcome.Complete -> "第 $target 章已翻译"
                    is TranslationOutcome.Partial -> "第 $target 章已部分翻译"
                    is TranslationOutcome.Failed -> null
                },
                error = (outcome as? TranslationOutcome.Failed)?.reason,
            )
            refresh()
        }
        if (taskRegistry?.register(book.id, target, job) == false) {
            job.cancel()
            _state.value = _state.value.copy(
                translating = false,
                error = "这一章已经有翻译任务",
            )
            return
        }
        job.start()
    }

    fun stopTranslationQueue() {
        readingTranslationCoordinator?.stop(bookId)
        _state.value = _state.value.copy(message = "已停止本书翻译队列", error = null)
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
