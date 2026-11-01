package com.kacyraho.lightnovel.feature.reader

import android.app.Activity
import android.graphics.Typeface
import android.text.TextPaint
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.foundation.text.ClickableText
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.flow.distinctUntilChanged
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kacyraho.lightnovel.AppContainer
import com.kacyraho.lightnovel.data.knowledge.EntityHighlighter
import com.kacyraho.lightnovel.reader.ReaderPageView
import com.kacyraho.lightnovel.reader.engine.ReaderTheme
import com.kacyraho.lightnovel.reader.engine.Viewport

@Composable
fun ReaderRoute(
    container: AppContainer,
    bookId: String,
    chapterIndex: Int,
    autoRetry: Boolean = false,
    onBack: () -> Unit,
    onOpenCatalog: (() -> Unit)? = null,
    onOpenChapter: (Int) -> Unit,
    onOpenMemory: (() -> Unit)? = null,
) {
    val viewModel: ReaderViewModel = viewModel(key = "reader-$bookId-$chapterIndex") {
        ReaderViewModel(
            repository = container.libraryRepository,
            contentStore = container.contentStore,
            translationService = container.translationService,
            settingsStore = container.settingsStore,
            chapterCache = container.readerChapterCache,
            storyMemoryStore = container.storyMemoryStore,
            storyMemoryService = container.storyMemoryService,
            knowledgeStore = container.knowledgeStore,
            knowledgeExtractionService = container.knowledgeExtractionService,
            knowledgeQueryService = container.knowledgeQueryService,
            versionStore = container.versionStore,
            onlineBookService = container.directLibraryService,
            taskRegistry = container.translationTaskRegistry,
            bookId = bookId,
            chapterIndex = chapterIndex,
        )
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val translationState by viewModel.translationState.collectAsStateWithLifecycle()
    var autoRetryConsumed by rememberSaveable(autoRetry, bookId, chapterIndex) { mutableStateOf(false) }

    LaunchedEffect(autoRetry, state.loading, state.error) {
        if (autoRetry && !autoRetryConsumed && !state.loading && state.error == null) {
            autoRetryConsumed = true
            viewModel.translateChapter()
        }
    }

    ReaderContent(
        state = state,
        translationState = translationState,
        onBack = onBack,
        onOpenCatalog = onOpenCatalog,
        onOpenChapter = onOpenChapter,
        onFontSizeChange = viewModel::setFontSize,
        onViewportChanged = viewModel::onViewportChanged,
        onPageChanged = viewModel::onPageChanged,
        onScrollParagraphChanged = viewModel::onScrollParagraphChanged,
        onTranslate = viewModel::translateChapter,
        onPolish = viewModel::polishChapter,
        onOpenMemory = onOpenMemory,
        onOpenQuery = viewModel::openQuery,
        onSelectEntity = viewModel::selectEntity,
        onCloseEntity = viewModel::closeEntity,
        onUpdateKnowledge = viewModel::extractCurrentChapter,
        onToggleQueryMode = viewModel::toggleQueryMode,
        onCancelTranslation = viewModel::cancelTranslation,
        onThemeChange = viewModel::setTheme,
        onDisplayModeChange = viewModel::setDisplayMode,
        onReaderModeChange = viewModel::setReaderMode,
        onSaveGlossary = viewModel::saveGlossary,
        onDeleteGlossary = viewModel::deleteGlossary,
        onRetranslateParagraph = viewModel::retranslateParagraph,
        onEstimateGlossaryImpact = viewModel::estimateGlossaryImpact,
    )
}

@Composable
private fun ReaderContent(
    state: ReaderUiState,
    translationState: ReaderTranslationState,
    onBack: () -> Unit,
    onOpenCatalog: (() -> Unit)?,
    onOpenChapter: (Int) -> Unit,
    onFontSizeChange: (Float) -> Unit,
    onViewportChanged: (Viewport, TextPaint, Float, Float) -> Unit,
    onPageChanged: (Int) -> Unit,
    onScrollParagraphChanged: (Int) -> Unit,
    onTranslate: () -> Unit,
    onPolish: () -> Unit,
    onOpenMemory: (() -> Unit)?,
    onOpenQuery: () -> Unit,
    onSelectEntity: (String) -> Unit,
    onCloseEntity: () -> Unit,
    onUpdateKnowledge: () -> Unit,
    onToggleQueryMode: () -> Unit,
    onCancelTranslation: () -> Unit,
    onThemeChange: (String) -> Unit,
    onDisplayModeChange: (String) -> Unit,
    onReaderModeChange: (String) -> Unit,
    onSaveGlossary: (com.kacyraho.lightnovel.data.glossary.GlossaryEntry) -> Unit,
    onDeleteGlossary: (String) -> Unit,
    onRetranslateParagraph: (Int) -> Unit,
    onEstimateGlossaryImpact: (String, List<String>) -> Unit,
) {
    val density = LocalDensity.current
    val view = LocalView.current
    val context = LocalContext.current
    val tts = remember(context) { ReaderTtsController(context) }
    var showChapterInfo by remember { mutableStateOf(false) }
    var showGlossary by remember { mutableStateOf(false) }
    var showQuery by remember { mutableStateOf(false) }
    var showParagraph by remember { mutableStateOf(false) }
    var immersive by remember { mutableStateOf(false) }
    val currentParagraphId = if (state.readerMode == "scroll") {
        paragraphIdForLine(state, state.scrollParagraph)
    } else {
        state.layout
            ?.pages
            ?.getOrNull(state.pageIndex)
            ?.startAnchor
            ?.paragraphId
            ?: state.scrollParagraph
    }
    val currentParagraph = state.paragraphs.getOrNull(currentParagraphId.coerceAtLeast(0))
    val readerTheme = ReaderTheme.fromId(state.theme)
    val textColor = readerTheme.text
    val secondaryColor = readerTheme.secondary
    val buttonColors = ButtonDefaults.textButtonColors(
        contentColor = textColor,
        disabledContentColor = textColor.copy(alpha = 0.38f),
    )

    DisposableEffect(state.keepScreenOn, view) {
        view.keepScreenOn = state.keepScreenOn
        onDispose { view.keepScreenOn = false }
    }

    DisposableEffect(tts) {
        onDispose { tts.shutdown() }
    }

    DisposableEffect(readerTheme) {
        val activity = view.context as? Activity
        val controller = activity?.let { WindowCompat.getInsetsController(it.window, view) }
        val oldStatus = controller?.isAppearanceLightStatusBars
        val oldNav = controller?.isAppearanceLightNavigationBars
        val light = readerTheme != ReaderTheme.NIGHT
        controller?.isAppearanceLightStatusBars = light
        controller?.isAppearanceLightNavigationBars = light
        onDispose {
            if (oldStatus != null) controller?.isAppearanceLightStatusBars = oldStatus
            if (oldNav != null) controller?.isAppearanceLightNavigationBars = oldNav
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(readerTheme.background)
            .statusBarsPadding()
            .navigationBarsPadding()
            .testTag("reader-screen"),
    ) {
        if (!immersive) {
        ReaderTopBar(
            bookTitle = state.bookTitle,
            chapterTitle = state.chapterTitle,
            fontSizeSp = state.fontSizeSp,
            status = if (translationState.running) {
                TranslationStatus.TRANSLATING
            } else {
                state.translationStatus
            },
            textColor = textColor,
            secondaryColor = secondaryColor,
            translationRunning = translationState.running,
            onBack = onBack,
            onFontSizeChange = onFontSizeChange,
            onThemeChange = {
                val entries = ReaderTheme.entries
                val current = entries.indexOfFirst { it.id == state.theme }.coerceAtLeast(0)
                onThemeChange(entries[(current + 1) % entries.size].id)
            },
            onRetranslate = onTranslate,
            onPolish = onPolish,
            onOpenMemory = onOpenMemory,
            onOpenQuery = {
                onOpenQuery()
                showQuery = true
            },
            queryMode = state.queryMode,
            onToggleQueryMode = onToggleQueryMode,
            onShowInfo = { showChapterInfo = true },
            onShowGlossary = { showGlossary = true },
            onShowParagraph = { showParagraph = currentParagraph != null },
            onToggleImmersive = { immersive = true },
        )

        StaleBanner(
            reasons = state.staleReasons,
            reason = state.staleBannerReason,
            theme = readerTheme,
            enabled = !translationState.running && !state.loading,
            onRetranslate = onTranslate,
        )

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            LanguageModeMenu(
                mode = state.displayMode,
                hasTranslation = state.hasTranslation,
                textColor = textColor,
                onSelect = onDisplayModeChange,
            )
            TextButton(
                onClick = {
                    onReaderModeChange(
                        if (state.readerMode == "scroll") "page" else "scroll",
                    )
                },
                colors = buttonColors,
            ) {
                Text(if (state.readerMode == "scroll") "翻页" else "滚动")
            }
            TextButton(
                onClick = {
                    if (tts.speaking) {
                        tts.stop()
                    } else {
                        tts.speak(
                            text = state.chapterText,
                            japanese = state.displayMode == "raw",
                        )
                    }
                },
                enabled = tts.ready && state.chapterText.isNotBlank(),
                colors = buttonColors,
            ) {
                Text(if (tts.speaking) "停止" else "朗读")
            }
            if (translationState.running) {
                TextButton(onClick = onCancelTranslation, colors = buttonColors) { Text("取消翻译") }
            }
            val translationNote = tts.error
                ?: translationState.error
                ?: translationState.message
            if (translationNote != null) {
                Text(
                    text = translationNote,
                    style = MaterialTheme.typography.labelSmall,
                    color = if (tts.error != null || translationState.error != null) {
                        MaterialTheme.colorScheme.error
                    } else {
                        secondaryColor
                    },
                )
            }
        }
        }

        when {
            state.loading -> Box(
                Modifier
                    .fillMaxWidth()
                    .weight(1f),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(color = textColor)
            }

            state.error != null -> Box(
                Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .padding(24.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text("加载失败：${state.error}", color = textColor)
            }

            state.readerMode == "scroll" -> ScrollReader(
                state = state,
                readerTheme = readerTheme,
                onParagraphChanged = onScrollParagraphChanged,
                onSelectEntity = onSelectEntity,
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
            )

            else -> BoxWithConstraints(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
            ) {
                val widthPx = with(density) {
                    (maxWidth - (state.marginDp * 2f).dp).roundToPx().coerceAtLeast(1)
                }
                val heightPx = with(density) {
                    (maxHeight - 20.dp).roundToPx().coerceAtLeast(1)
                }
                val typeface = remember(state.fontFamily) {
                    when (state.fontFamily) {
                        "sans" -> Typeface.SANS_SERIF
                        "mono" -> Typeface.MONOSPACE
                        else -> Typeface.SERIF
                    }
                }
                val paint = remember(state.fontSizeSp, state.lineHeight, textColor, density, typeface) {
                    TextPaint().apply {
                        textSize = with(density) { state.fontSizeSp.sp.toPx() }
                        this.typeface = typeface
                        isAntiAlias = true
                        color = textColor.toArgb()
                    }
                }

                LaunchedEffect(
                    widthPx,
                    heightPx,
                    state.fontSizeSp,
                    state.lineHeight,
                    paint,
                    state.revision,
                ) {
                    onViewportChanged(
                        Viewport(widthPx, heightPx),
                        paint,
                        state.fontSizeSp,
                        state.lineHeight,
                    )
                }

                val layout = state.layout
                if (layout == null) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = textColor)
                    }
                } else {
                    val pagerState = rememberPagerState(
                        pageCount = { layout.pages.size.coerceAtLeast(1) },
                    )
                    LaunchedEffect(state.pageIndex) {
                        if (pagerState.currentPage != state.pageIndex) {
                            pagerState.scrollToPage(
                                state.pageIndex.coerceIn(0, layout.pages.lastIndex),
                            )
                        }
                    }
                    LaunchedEffect(pagerState.currentPage) {
                        onPageChanged(pagerState.currentPage)
                    }
                    HorizontalPager(
                        state = pagerState,
                        modifier = Modifier
                            .fillMaxSize()
                            .testTag("reader-pager"),
                    ) { index ->
                        val page = layout.pages.getOrNull(index) ?: layout.pages.first()
                        AndroidView(
                            factory = { context ->
                                ReaderPageView(context).also {
                                    it.onEntityClick = if (state.queryMode) onSelectEntity else null
                                }
                            },
                            update = { view ->
                                view.onEntityClick = if (state.queryMode) onSelectEntity else null
                                view.bind(layout.layout, page.slice)
                            },
                            modifier = Modifier
                                .fillMaxSize()
                                .padding(horizontal = state.marginDp.dp)
                                .padding(bottom = 20.dp),
                        )
                    }
                }
            }
        }

        val pageLabel = if (state.readerMode == "scroll") {
            val total = state.chapterBlocks.size.coerceAtLeast(1)
            "${state.scrollParagraph.coerceIn(0, total - 1) + 1}/$total"
        } else {
            state.layout?.pages?.takeIf { it.isNotEmpty() }?.let {
                "${state.pageIndex.coerceIn(0, it.lastIndex) + 1}/${it.size}"
            }
        }
        if (showParagraph && currentParagraph != null) {
            ParagraphActionSheet(
                paragraph = currentParagraph,
                theme = readerTheme,
                enabled = !translationState.running,
                onDismiss = { showParagraph = false },
                onRetranslate = {
                    showParagraph = false
                    onRetranslateParagraph(currentParagraph.id)
                },
            )
        }

        if (showGlossary) {
            GlossaryCorrectionSheet(
                entries = state.glossaryEntries,
                impact = state.glossaryImpact,
                theme = readerTheme,
                onDismiss = { showGlossary = false },
                onSave = {
                    onSaveGlossary(it)
                    showGlossary = false
                },
                onDelete = onDeleteGlossary,
                onSaveAndRetranslate = {
                    onSaveGlossary(it)
                    showGlossary = false
                    onTranslate()
                },
                onEstimate = { source, aliases ->
                    onEstimateGlossaryImpact(source, aliases)
                },
            )
        }

        if (showChapterInfo && state.chapterInfo != null) {
            ChapterInfoSheet(
                info = state.chapterInfo,
                reasons = state.staleReasons,
                theme = readerTheme,
                onDismiss = { showChapterInfo = false },
                onRetranslate = {
                    showChapterInfo = false
                    onTranslate()
                },
            )
        }

        if (showQuery) {
            QuerySheet(
                entries = state.queryEntries,
                status = state.knowledgeStatus,
                theme = readerTheme,
                onDismiss = { showQuery = false },
                onSelect = { entityId ->
                    showQuery = false
                    onSelectEntity(entityId)
                },
                onUpdate = onUpdateKnowledge,
            )
        }

        state.entityCard?.let { card ->
            EntityCardSheet(
                card = card,
                theme = readerTheme,
                onDismiss = onCloseEntity,
                onOpenChapter = { chapter ->
                    onCloseEntity()
                    onOpenChapter(chapter)
                },
            )
        }

        if (!immersive) {
            ReaderBottomBar(
                pageLabel = pageLabel,
                chapterIndex = state.chapterIndex,
                chapterCount = state.chapterCount,
                kind = state.textKind,
                textColor = textColor,
                secondaryColor = secondaryColor,
                onPrev = { onOpenChapter(state.chapterIndex - 1) },
                onNext = { onOpenChapter(state.chapterIndex + 1) },
                onToc = onOpenCatalog ?: onBack,
            )
        } else {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.End,
            ) {
                TextButton(
                    onClick = { immersive = false },
                    colors = buttonColors,
                ) {
                    Text("退出沉浸")
                }
            }
        }
    }
}

@Composable
private fun ScrollReader(
    state: ReaderUiState,
    readerTheme: ReaderTheme,
    onParagraphChanged: (Int) -> Unit,
    onSelectEntity: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val blocks = state.chapterBlocks.ifEmpty { listOf(state.chapterText) }
    val initial = state.scrollParagraph
        .coerceIn(0, (blocks.size - 1).coerceAtLeast(0))
    val listState = rememberLazyListState(initialFirstVisibleItemIndex = initial)

    LaunchedEffect(listState) {
        snapshotFlow { listState.firstVisibleItemIndex }
            .distinctUntilChanged()
            .collect(onParagraphChanged)
    }

    LazyColumn(
        state = listState,
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = state.marginDp.dp, vertical = 12.dp),
    ) {
        itemsIndexed(blocks) { _, block ->
            val names = state.queryNames
            val textStyle = TextStyle(
                color = readerTheme.text,
                fontSize = state.fontSizeSp.sp,
                fontFamily = readerFontFamily(state.fontFamily),
                lineHeight = (state.fontSizeSp * state.lineHeight).sp,
            )
            if (names.isEmpty()) {
                Text(
                    text = block,
                    style = textStyle,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = (state.fontSizeSp * 0.4f).dp + state.paragraphSpacing.dp),
                )
            } else {
                val annotated = buildAnnotatedString {
                    append(block)
                    EntityHighlighter.find(block, names).forEach { match ->
                        addStringAnnotation(
                            tag = "entity",
                            annotation = match.entityId,
                            start = match.start,
                            end = match.end,
                        )
                        addStyle(
                            SpanStyle(textDecoration = TextDecoration.Underline),
                            match.start,
                            match.end,
                        )
                    }
                }
                ClickableText(
                    text = annotated,
                    style = textStyle,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = (state.fontSizeSp * 0.4f).dp + state.paragraphSpacing.dp),
                    onClick = { offset ->
                        annotated.getStringAnnotations("entity", offset, offset)
                            .firstOrNull()
                            ?.let { onSelectEntity(it.item) }
                    },
                )
            }
        }
    }
}

private fun readerFontFamily(id: String): FontFamily = when (id) {
    "sans" -> FontFamily.SansSerif
    "mono" -> FontFamily.Monospace
    else -> FontFamily.Serif
}

private fun paragraphIdForLine(state: ReaderUiState, line: Int): Int {
    if (state.paragraphs.isEmpty()) return 0
    var cursor = 0
    state.paragraphs.forEachIndexed { index, paragraph ->
        val lines = paragraph.source.split("\n").size.coerceAtLeast(1)
        if (line < cursor + lines) return index
        cursor += lines
        if (index < state.paragraphs.lastIndex) cursor += 1
    }
    return state.paragraphs.lastIndex
}

private fun kindLabel(kind: String): String = when (kind) {
    "complete" -> "已译"
    "translated" -> "有译文"
    "partial" -> "未译完"
    "raw" -> "生肉"
    "missing" -> "缺正文"
    else -> kind
}
