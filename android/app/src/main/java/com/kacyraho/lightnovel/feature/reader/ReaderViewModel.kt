package com.kacyraho.lightnovel.feature.reader

import android.text.TextPaint
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kacyraho.lightnovel.core.model.ReaderAnchor
import com.kacyraho.lightnovel.core.settings.SettingsStore
import com.kacyraho.lightnovel.core.storage.ContentStore
import com.kacyraho.lightnovel.data.glossary.GlossaryEntry
import com.kacyraho.lightnovel.data.glossary.GlossaryStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.source.ChapterFetcher
import com.kacyraho.lightnovel.data.repository.LibraryRepository
import com.kacyraho.lightnovel.data.translation.Hashes
import com.kacyraho.lightnovel.data.translation.TranslationConfig
import com.kacyraho.lightnovel.data.translation.toTranslationConfig
import com.kacyraho.lightnovel.data.translation.TranslationOutcome
import com.kacyraho.lightnovel.data.translation.TranslationService
import com.kacyraho.lightnovel.data.translation.TranslationTaskRegistry
import com.kacyraho.lightnovel.data.translation.TranslationVersionStore
import com.kacyraho.lightnovel.reader.engine.MonoPaginator
import com.kacyraho.lightnovel.reader.engine.MonoStyle
import com.kacyraho.lightnovel.reader.engine.ReaderBlock
import com.kacyraho.lightnovel.reader.engine.ReaderChapter
import com.kacyraho.lightnovel.reader.engine.ReaderChapterCache
import com.kacyraho.lightnovel.reader.engine.ReaderLayout
import com.kacyraho.lightnovel.reader.engine.Viewport
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class ReaderUiState(
    val loading: Boolean = true,
    val error: String? = null,
    val bookTitle: String = "",
    val chapterTitle: String = "",
    val chapterIndex: Int,
    val chapterCount: Int = 0,
    val textKind: String = "raw",
    val fontSizeSp: Float = 18f,
    val lineHeight: Float = 1.7f,
    val marginDp: Float = 16f,
    val paragraphSpacing: Float = 8f,
    val fontFamily: String = "serif",
    val keepScreenOn: Boolean = false,
    val theme: String = "paper",
    val displayMode: String = "translated",
    val readerMode: String = "page",
    val chapterText: String = "",
    val chapterBlocks: List<String> = emptyList(),
    val scrollParagraph: Int = 0,
    val layout: ReaderLayout? = null,
    val pageIndex: Int = 0,
    val revision: Int = 0,
    val translationStatus: TranslationStatus = TranslationStatus.UNTRANSLATED,
    val staleReasons: Set<StaleReason> = emptySet(),
    val staleBannerReason: StaleBannerReason? = null,
    val chapterInfo: ReaderChapterInfo? = null,
    val hasTranslation: Boolean = false,
    val glossaryEntries: List<GlossaryEntry> = emptyList(),
    val glossaryImpact: GlossaryImpact? = null,
    val paragraphs: List<ReaderParagraph> = emptyList(),
)

data class ReaderTranslationState(
    val running: Boolean = false,
    val message: String? = null,
    val error: String? = null,
    val partial: Boolean = false,
)

class ReaderViewModel(
    private val repository: LibraryRepository,
    private val contentStore: ContentStore,
    private val translationService: TranslationService,
    private val settingsStore: SettingsStore,
    private val chapterCache: ReaderChapterCache,
    private val glossaryStore: GlossaryStore? = null,
    private val versionStore: TranslationVersionStore? = null,
    private val onlineBookService: ChapterFetcher? = null,
    private val taskRegistry: TranslationTaskRegistry? = null,
    private val bookId: String,
    private val chapterIndex: Int,
) : ViewModel() {
    private val _state = MutableStateFlow(ReaderUiState(chapterIndex = chapterIndex))
    val state: StateFlow<ReaderUiState> = _state.asStateFlow()

    private val _translationState = MutableStateFlow(ReaderTranslationState())
    val translationState: StateFlow<ReaderTranslationState> = _translationState.asStateFlow()

    private var readerChapter: ReaderChapter? = null
    private var bookEntity: BookEntity? = null
    private var chapterList: List<ChapterEntity> = emptyList()
    private var rawText: String? = null
    private var anchorToRestore: ReaderAnchor? = null
    private var paginationJob: Job? = null
    private var saveJob: Job? = null
    private var translationJob: Job? = null
    private var settingsJob: Job? = null
    private var lastKey: String? = null
    private var currentConfigHash: String? = null
    private var currentLegacyConfigHash: String? = null
    private var currentTranslationConfig: TranslationConfig? = null
    private var currentGlossaryRevision: String = ""

    private val taskKey: String = "$bookId/$chapterIndex"

    init {
        viewModelScope.launch {
            taskRegistry?.cancelled?.collect { key ->
                if (key == taskKey) {
                    _translationState.value = ReaderTranslationState(message = "已取消")
                    load()
                }
            }
        }
        viewModelScope.launch {
            val settings = settingsStore.settings.first()
            val glossary = glossaryStore?.load()
            currentGlossaryRevision = glossary?.revision.orEmpty()
            val translationConfig = settings.toTranslationConfig(
                glossary = glossary?.entries.orEmpty(),
                glossaryRevision = currentGlossaryRevision,
            )
            currentTranslationConfig = translationConfig
            currentConfigHash = translationConfig.cacheKey()
            currentLegacyConfigHash = translationConfig.legacyCacheKey()
            _state.value = _state.value.copy(
                fontSizeSp = settings.readerFontSizeSp,
                lineHeight = settings.readerLineHeight,
                marginDp = settings.readerMarginDp,
                paragraphSpacing = settings.readerParagraphSpacing,
                fontFamily = settings.readerFontFamily,
                keepScreenOn = settings.readerKeepScreenOn,
                theme = settings.readerTheme,
                displayMode = settings.readerDisplayMode,
                readerMode = settings.readerMode,
            )
            load()
        }
    }

    fun setFontSize(sizeSp: Float) {
        val value = sizeSp.coerceIn(12f, 30f)
        _state.value = _state.value.copy(fontSizeSp = value)
        persistSettings()
    }

    fun setLineHeight(lineHeight: Float) {
        val value = lineHeight.coerceIn(1.2f, 2.4f)
        _state.value = _state.value.copy(lineHeight = value)
        persistSettings()
    }

    fun setTheme(theme: String) {
        _state.value = _state.value.copy(theme = theme)
        persistSettings()
    }

    fun setReaderMargin(value: Float) {
        _state.value = _state.value.copy(marginDp = value.coerceIn(8f, 48f))
        persistSettings()
    }

    fun setParagraphSpacing(value: Float) {
        _state.value = _state.value.copy(paragraphSpacing = value.coerceIn(0f, 32f))
        persistSettings()
    }

    fun setFontFamily(value: String) {
        if (value !in setOf("serif", "sans", "mono")) return
        _state.value = _state.value.copy(fontFamily = value)
        lastKey = null
        persistSettings()
    }

    fun setKeepScreenOn(value: Boolean) {
        _state.value = _state.value.copy(keepScreenOn = value)
        persistSettings()
    }

    fun setReaderMode(mode: String) {
        if (mode == _state.value.readerMode) return
        if (mode == "page") {
            anchorToRestore = ReaderAnchor(
                chapterIndex = chapterIndex,
                paragraphId = _state.value.scrollParagraph,
                charOffset = 0,
            )
            lastKey = null
        } else {
            val pageAnchor = currentAnchor()
            if (pageAnchor != null) {
                _state.value = _state.value.copy(scrollParagraph = pageAnchor.paragraphId)
            }
        }
        _state.value = _state.value.copy(
            readerMode = mode,
            revision = _state.value.revision + 1,
        )
        persistSettings()
    }

    fun setDisplayMode(mode: String) {
        if (mode == _state.value.displayMode) return
        val currentAnchor = currentAnchor()
            ?: if (_state.value.readerMode == "scroll") {
                ReaderAnchor(chapterIndex, _state.value.scrollParagraph, 0)
            } else {
                null
            }
        _state.value = _state.value.copy(displayMode = mode)
        persistSettings()
        anchorToRestore = currentAnchor
        load()
    }

    fun onViewportChanged(
        viewport: Viewport,
        paint: TextPaint,
        fontSizeSp: Float,
        lineHeight: Float,
    ) {
        val chapter = readerChapter ?: return
        val key = "${viewport.widthPx}x${viewport.heightPx}:$fontSizeSp:$lineHeight:" +
            "${paint.typeface}:${paint.color}:${chapter.text.hashCode()}"
        if (key == lastKey) return
        lastKey = key
        paginationJob?.cancel()
        paginationJob = viewModelScope.launch {
            val layout = withContext(Dispatchers.Default) {
                MonoPaginator().paginate(
                    chapter = chapter,
                    viewport = viewport,
                    paint = paint,
                    style = MonoStyle(fontSizeSp, lineHeight),
                )
            }
            val target = anchorToRestore?.let { anchor ->
                pageForAnchor(layout, anchor)
            } ?: _state.value.pageIndex.coerceIn(0, layout.pages.lastIndex)
            anchorToRestore = null
            _state.value = _state.value.copy(layout = layout, pageIndex = target)
        }
    }

    fun translateChapter() {
        if (_translationState.value.running) return
        if (taskRegistry?.isRunning(bookId, chapterIndex) == true) return
        val book = bookEntity ?: return
        val raw = rawText ?: return
        _translationState.value = ReaderTranslationState(
            running = true,
            message = "准备翻译",
        )
        _state.value = _state.value.copy(translationStatus = TranslationStatus.TRANSLATING)
        val job = viewModelScope.launch {
            val currentAnchor = _state.value.layout
                ?.pages
                ?.getOrNull(_state.value.pageIndex)
                ?.startAnchor
                ?: if (_state.value.readerMode == "scroll") {
                    ReaderAnchor(chapterIndex, _state.value.scrollParagraph, 0)
                } else {
                    null
                }
            val outcome = translationService.translate(book, chapterIndex) { done, total ->
                _translationState.value = ReaderTranslationState(
                    running = true,
                    message = "翻译中 $done/$total",
                )
            }
            when (outcome) {
                is TranslationOutcome.Complete -> {
                    _translationState.value = ReaderTranslationState(
                        message = summary("翻译完成", outcome.sidecar),
                    )
                    chapterCache.clearBook(bookId)
                    anchorToRestore = currentAnchor
                    load()
                }

                is TranslationOutcome.Partial -> {
                    _translationState.value = ReaderTranslationState(
                        message = summary(
                            "部分完成：${outcome.sidecar.incompleteParagraphs.size} 段保留原文",
                            outcome.sidecar,
                        ),
                        partial = true,
                    )
                    chapterCache.clearBook(bookId)
                    anchorToRestore = currentAnchor
                    load()
                }

                is TranslationOutcome.Failed -> {
                    _translationState.value = ReaderTranslationState(
                        error = outcome.reason,
                    )
                    load()
                }
            }
            if (raw.isBlank()) {
                _translationState.value = ReaderTranslationState(error = "原文为空")
            }
        }
        translationJob = job
        if (taskRegistry?.register(bookId, chapterIndex, job) == false) {
            translationJob = null
            _translationState.value = ReaderTranslationState(message = "已有翻译任务在运行")
            return
        }
    }

    fun retranslateParagraph(paragraphIndex: Int) {
        if (_translationState.value.running) return
        if (taskRegistry?.isRunning(bookId, chapterIndex) == true) return
        val book = bookEntity ?: return
        if (paragraphIndex < 0) return
        _translationState.value = ReaderTranslationState(
            running = true,
            message = "正在重译第 ${paragraphIndex + 1} 段",
        )
        _state.value = _state.value.copy(translationStatus = TranslationStatus.TRANSLATING)
        val job = viewModelScope.launch {
            val outcome = translationService.retranslateParagraph(book, chapterIndex, paragraphIndex)
            when (outcome) {
                is TranslationOutcome.Complete -> {
                    _translationState.value = ReaderTranslationState(
                        message = summary("段落重译完成", outcome.sidecar),
                    )
                    chapterCache.clearBook(bookId)
                    load()
                }

                is TranslationOutcome.Partial -> {
                    _translationState.value = ReaderTranslationState(
                        message = summary("段落重译完成，但本章仍不完整", outcome.sidecar),
                        partial = true,
                    )
                    chapterCache.clearBook(bookId)
                    load()
                }

                is TranslationOutcome.Failed -> {
                    _translationState.value = ReaderTranslationState(error = outcome.reason)
                    load()
                }
            }
        }
        translationJob = job
        if (taskRegistry?.register(bookId, chapterIndex, job) == false) {
            translationJob = null
            _translationState.value = ReaderTranslationState(message = "已有翻译任务在运行")
            return
        }
    }

    fun estimateGlossaryImpact(source: String, aliases: List<String>) {
        val book = bookEntity ?: return
        val terms = (listOf(source) + aliases).map(String::trim).filter(String::isNotBlank)
        if (terms.isEmpty()) {
            _state.value = _state.value.copy(glossaryImpact = GlossaryImpact(0, 0, 0.0))
            return
        }
        viewModelScope.launch(Dispatchers.IO) {
            var chapters = 0
            var characters = 0
            chapterList.forEach { chapter ->
                val raw = contentStore.readRaw(book.storageDir, chapter.idx) ?: return@forEach
                if (terms.any { it in raw }) {
                    chapters++
                    characters += raw.length
                }
            }
            val tokensIn = characters * 0.65
            val tokensOut = characters * 0.80
            val cost = tokensIn / 1_000_000.0 * 2.0 + tokensOut / 1_000_000.0 * 8.0
            _state.value = _state.value.copy(
                glossaryImpact = GlossaryImpact(chapters, characters, cost),
            )
        }
    }

    fun saveGlossary(entry: GlossaryEntry) {
        val store = glossaryStore ?: return
        val current = _state.value.glossaryEntries
        val updated = current.filterNot { it.id == entry.id || it.source == entry.source } + entry
        val saved = store.save(updated)
        currentGlossaryRevision = saved.revision
        currentTranslationConfig = currentTranslationConfig?.copy(
            glossary = saved.entries,
            glossaryRevision = currentGlossaryRevision,
        )
        currentConfigHash = currentTranslationConfig?.cacheKey()
        currentLegacyConfigHash = currentTranslationConfig?.legacyCacheKey()
        _state.value = _state.value.copy(glossaryEntries = saved.entries)
        load()
    }

    fun deleteGlossary(id: String) {
        val store = glossaryStore ?: return
        val saved = store.save(_state.value.glossaryEntries.filterNot { it.id == id })
        currentGlossaryRevision = saved.revision
        currentTranslationConfig = currentTranslationConfig?.copy(
            glossary = saved.entries,
            glossaryRevision = currentGlossaryRevision,
        )
        currentConfigHash = currentTranslationConfig?.cacheKey()
        currentLegacyConfigHash = currentTranslationConfig?.legacyCacheKey()
        _state.value = _state.value.copy(glossaryEntries = saved.entries)
        load()
    }

    fun cancelTranslation() {
        taskRegistry?.cancel(bookId, chapterIndex)
        translationJob?.cancel()
        translationJob = null
        _translationState.value = ReaderTranslationState(message = "已取消")
        val book = bookEntity
        if (book != null) {
            viewModelScope.launch {
                translationService.markCancelled(book, chapterIndex)
                load()
            }
        } else {
            load()
        }
    }

    fun onPageChanged(pageIndex: Int) {
        val layout = _state.value.layout ?: return
        if (pageIndex !in layout.pages.indices) return
        _state.value = _state.value.copy(pageIndex = pageIndex)
        val anchor = layout.pages[pageIndex].startAnchor
        saveJob?.cancel()
        saveJob = viewModelScope.launch {
            delay(500)
            repository.updateProgress(bookId, anchor)
        }
    }

    private fun load() {
        viewModelScope.launch {
            val loaded = runCatching {
                val book = repository.book(bookId) ?: error("书不存在")
                val chapters = repository.observeChapters(bookId).first()
                val chapter = chapters.firstOrNull { it.idx == chapterIndex }
                    ?: error("章节不存在")
                if (!book.local &&
                    contentStore.readRaw(book.storageDir, chapterIndex) == null &&
                    contentStore.readZh(book.storageDir, chapterIndex) == null
                ) {
                    _state.value = _state.value.copy(loading = true, error = null)
                    onlineBookService?.ensureChapter(book, chapterIndex)
                }
                val readState = repository.readState(bookId)
                val displayMode = _state.value.displayMode
                val cached = chapterCache.get(bookId, chapterIndex, displayMode)
                val readerChapter = cached ?: buildChapter(book, chapter, displayMode).also {
                    chapterCache.put(bookId, chapterIndex, displayMode, it)
                }
                val restore = if (readState?.progressIdx == chapterIndex) {
                    ReaderAnchor(
                        chapterIndex = chapterIndex,
                        paragraphId = readState.progressBlock,
                        charOffset = readState.progressChar,
                    )
                } else {
                    null
                }
                Triple(book, readerChapter, chapters) to restore
            }

            loaded.onSuccess { (payload, restore) ->
                val (book, readerChapter, chapters) = payload
                anchorToRestore = restore ?: anchorToRestore
                bookEntity = book
                chapterList = chapters
                val raw = contentStore.readRaw(book.storageDir, chapterIndex)
                val zh = contentStore.readZh(book.storageDir, chapterIndex)
                rawText = raw
                val sidecar = runCatching {
                    contentStore.readSidecar(book.storageDir, chapterIndex)
                }.getOrNull()
                val stale = staleReasons(raw, sidecar, _state.value.displayMode)
                val previous = versionStore?.latest(book.storageDir, chapterIndex)
                val changedParagraphs = if (previous != null && zh != null) {
                    versionStore?.diffParagraphs(previous.text, zh) ?: 0
                } else {
                    0
                }
                this@ReaderViewModel.readerChapter = readerChapter
                lastKey = null
                _state.value = _state.value.copy(
                    loading = false,
                    error = null,
                    bookTitle = book.titleZh ?: book.title,
                    chapterTitle = readerChapter.title,
                    chapterCount = chapters.size,
                    textKind = readerChapter.textKind,
                    chapterText = readerChapter.text,
                    chapterBlocks = readerChapter.text
                        .split("\n")
                        .map { it.trimEnd() }
                        .ifEmpty { listOf(readerChapter.text) },
                    scrollParagraph = restore?.paragraphId ?: 0,
                    revision = _state.value.revision + 1,
                    translationStatus = statusFor(
                        zh = zh,
                        sidecar = sidecar,
                        stale = stale,
                        chapterStatus = chapters.firstOrNull { it.idx == chapterIndex }?.status,
                    ),
                    hasTranslation = zh != null,
                    staleReasons = stale,
                    staleBannerReason = staleBannerReason(stale),
                    chapterInfo = sidecar?.let {
                        ReaderChapterInfo(
                            model = it.modelId,
                            translatedAt = it.translatedAt,
                            tokensIn = it.tokens.input,
                            tokensOut = it.tokens.output,
                            costCny = it.cost.amount,
                            incompleteParagraphs = it.incompleteParagraphs.size,
                            cacheKey = it.contentSha256.take(12),
                            oldVersionAvailable = previous != null,
                            oldTranslatedAt = previous?.sidecar?.translatedAt,
                            changedParagraphs = changedParagraphs,
                        )
                    },
                    glossaryEntries = glossaryStore?.load()?.entries.orEmpty(),
                    paragraphs = buildParagraphs(raw, zh),
                )
                prefetchAdjacent(book, chapters, _state.value.displayMode)
            }.onFailure { error ->
                _state.value = _state.value.copy(
                    loading = false,
                    error = error.message ?: "加载失败",
                )
            }
        }
    }

    private fun buildChapter(
        book: BookEntity,
        chapter: ChapterEntity,
        displayMode: String,
    ): ReaderChapter {
        val zh = contentStore.readZh(book.storageDir, chapter.idx)
        val raw = contentStore.readRaw(book.storageDir, chapter.idx)
        val sidecar = runCatching {
            contentStore.readSidecar(book.storageDir, chapter.idx)
        }.getOrNull()
        val textKind = when {
            zh != null && sidecar?.status == "partial" -> "partial"
            zh != null && sidecar?.status == "complete" -> "complete"
            zh != null -> "translated"
            raw != null -> "raw"
            else -> "missing"
        }
        val text = when (displayMode) {
            "raw" -> raw ?: zh
            "bilingual" -> bilingualText(raw, zh)
            else -> zh ?: raw
        } ?: "（本章暂无正文）"
        val normalized = text.replace("\r\n", "\n")
        return ReaderChapter(
            bookId = book.id,
            idx = chapter.idx,
            title = chapter.titleZh ?: chapter.title ?: "第 ${chapter.idx} 章",
            blocks = normalized.split("\n\n").mapIndexed { index, value ->
                ReaderBlock(index, value)
            },
            text = normalized,
            textKind = textKind,
        )
    }

    private fun staleReasons(
        raw: String?,
        sidecar: com.kacyraho.lightnovel.core.storage.ChapterSidecar?,
        displayMode: String,
    ): Set<StaleReason> {
        if (sidecar == null) return emptySet()
        return buildSet {
            if (raw != null && sidecar.sourceSha256 != Hashes.sha256(raw)) {
                add(StaleReason.SOURCE)
                if (displayMode == "raw") add(StaleReason.ORIGINAL_REFRESH)
            }
            val glossaryChanged = sidecar.glossaryRevision.orEmpty() != currentGlossaryRevision
            if (glossaryChanged) {
                add(StaleReason.GLOSSARY)
            } else {
                val configHash = currentConfigHash
                val legacyConfigHash = currentLegacyConfigHash
                if (configHash != null &&
                    sidecar.translationConfigHash != configHash &&
                    sidecar.translationConfigHash != legacyConfigHash
                ) {
                    add(StaleReason.MODEL_PROMPT)
                }
            }
        }
    }

    private fun statusFor(
        zh: String?,
        sidecar: com.kacyraho.lightnovel.core.storage.ChapterSidecar?,
        stale: Set<StaleReason>,
        chapterStatus: String?,
    ): TranslationStatus {
        if (zh == null) {
            return when {
                sidecar?.status == "partial" -> TranslationStatus.FAILED
                chapterStatus == "failed" -> TranslationStatus.FAILED
                chapterStatus == "translating" -> TranslationStatus.FAILED
                else -> TranslationStatus.UNTRANSLATED
            }
        }
        if (stale.isNotEmpty()) return TranslationStatus.STALE
        return when (sidecar?.status) {
            "partial" -> TranslationStatus.FAILED
            else -> TranslationStatus.TRANSLATED
        }
    }

    private fun buildParagraphs(raw: String?, zh: String?): List<ReaderParagraph> {
        val sources = raw?.replace("\r\n", "\n")?.split("\n\n").orEmpty()
        val translated = zh?.replace("\r\n", "\n")?.split("\n\n").orEmpty()
        val size = maxOf(sources.size, translated.size)
        return (0 until size).map { index ->
            ReaderParagraph(
                id = index,
                source = sources.getOrNull(index).orEmpty(),
                translated = translated.getOrNull(index)?.takeIf { it.isNotBlank() },
            )
        }
    }

    private fun bilingualText(raw: String?, zh: String?): String? {
        if (raw == null) return zh
        if (zh == null) return raw
        val rawParagraphs = raw.replace("\r\n", "\n").split("\n\n")
        val zhParagraphs = zh.replace("\r\n", "\n").split("\n\n")
        val size = maxOf(rawParagraphs.size, zhParagraphs.size)
        return (0 until size).joinToString("\n\n") { index ->
            listOfNotNull(
                rawParagraphs.getOrNull(index)?.takeIf { it.isNotBlank() },
                zhParagraphs.getOrNull(index)?.takeIf { it.isNotBlank() },
            ).joinToString("\n")
        }
    }

    private fun prefetchAdjacent(
        book: BookEntity,
        chapters: List<ChapterEntity>,
        displayMode: String,
    ) {
        if (!book.local) return
        for (idx in listOf(chapterIndex - 1, chapterIndex + 1)) {
            val chapter = chapters.firstOrNull { it.idx == idx } ?: continue
            if (chapterCache.get(bookId, idx, displayMode) != null) continue
            viewModelScope.launch(Dispatchers.IO) {
                runCatching {
                    chapterCache.put(
                        bookId,
                        idx,
                        displayMode,
                        buildChapter(book, chapter, displayMode),
                    )
                }
            }
        }
    }

    fun onScrollParagraphChanged(paragraphId: Int) {
        if (paragraphId == _state.value.scrollParagraph) return
        val safe = paragraphId.coerceAtLeast(0)
        _state.value = _state.value.copy(scrollParagraph = safe, pageIndex = 0)
        saveJob?.cancel()
        saveJob = viewModelScope.launch {
            delay(500)
            repository.updateProgress(
                bookId,
                ReaderAnchor(
                    chapterIndex = chapterIndex,
                    paragraphId = safe,
                    charOffset = 0,
                ),
            )
        }
    }

    private fun currentAnchor(): ReaderAnchor? =
        _state.value.layout?.pages?.getOrNull(_state.value.pageIndex)?.startAnchor

    private fun persistSettings() {
        settingsJob?.cancel()
        settingsJob = viewModelScope.launch {
            delay(300)
            val current = _state.value
            settingsStore.update {
                it.copy(
                    readerFontSizeSp = current.fontSizeSp,
                    readerLineHeight = current.lineHeight,
                    readerMarginDp = current.marginDp,
                    readerParagraphSpacing = current.paragraphSpacing,
                    readerFontFamily = current.fontFamily,
                    readerKeepScreenOn = current.keepScreenOn,
                    readerTheme = current.theme,
                    readerDisplayMode = current.displayMode,
                    readerMode = current.readerMode,
                )
            }
        }
    }

    private fun summary(prefix: String, sidecar: com.kacyraho.lightnovel.core.storage.ChapterSidecar): String {
        val cost = String.format(java.util.Locale.US, "%.4f", sidecar.cost.amount)
        return "$prefix · ${sidecar.tokens.input}/${sidecar.tokens.output} tok · ¥$cost"
    }

    private fun pageForAnchor(layout: ReaderLayout, anchor: ReaderAnchor): Int {
        val index = layout.pages.indexOfFirst { page ->
            compare(page.startAnchor, anchor) <= 0 && compare(anchor, page.endAnchor) < 0
        }
        return if (index >= 0) index else 0
    }

    private fun compare(a: ReaderAnchor, b: ReaderAnchor): Int {
        val chapter = a.chapterIndex.compareTo(b.chapterIndex)
        if (chapter != 0) return chapter
        val paragraph = a.paragraphId.compareTo(b.paragraphId)
        if (paragraph != 0) return paragraph
        return a.charOffset.compareTo(b.charOffset)
    }
}
