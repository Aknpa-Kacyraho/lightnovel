package com.kacyraho.lightnovel.feature.chapters

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kacyraho.lightnovel.AppContainer
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.BookTags
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.source.SourceDetail
import com.kacyraho.lightnovel.ui.components.BookCover
import com.kacyraho.lightnovel.ui.components.BookCoverSize
import com.kacyraho.lightnovel.ui.components.BrandFilterChip
import com.kacyraho.lightnovel.ui.components.LnTag
import com.kacyraho.lightnovel.ui.components.LnTagKind
import com.kacyraho.lightnovel.ui.components.SourceBadge
import com.kacyraho.lightnovel.ui.components.StatusBadge
import com.kacyraho.lightnovel.ui.components.StatusTone

private const val TAB_INTRO = "intro"
private const val TAB_CATALOG = "catalog"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChapterListRoute(
    container: AppContainer,
    bookId: String,
    onBack: () -> Unit,
    onOpenChapter: (Int) -> Unit,
    onSearchAuthor: (String) -> Unit,
    onSearchTag: (String) -> Unit,
    onOpenMemory: (() -> Unit)? = null,
    onOpenWorldlines: (() -> Unit)? = null,
) {
    val viewModel: ChapterListViewModel = viewModel(key = "chapters-$bookId") {
        ChapterListViewModel(
            repository = container.libraryRepository,
            epubExporter = container.epubExporter,
            onlineBookService = container.directLibraryService,
            metadataService = container.metadataTranslationService,
            downloadScheduler = container.bookDownloadScheduler,
            bookId = bookId,
        )
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val snackbarHostState = remember { SnackbarHostState() }
    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.CreateDocument("application/epub+zip"),
    ) { uri ->
        uri?.let { viewModel.exportEpub(it, context.contentResolver) }
    }

    LaunchedEffect(state.message, state.error) {
        val text = state.error ?: state.message ?: return@LaunchedEffect
        viewModel.consumeMessage()
        snackbarHostState.showSnackbar(text)
    }

    ChapterListScreen(
        state = state,
        snackbarHostState = snackbarHostState,
        onBack = onBack,
        onOpenChapter = onOpenChapter,
        onToggleFavorite = viewModel::toggleFavorite,
        onDownloadAll = viewModel::downloadAll,
        onExport = {
            val title = state.book?.titleZh ?: state.book?.title ?: "lightnovel"
            launcher.launch("$title.epub")
        },
        onSearchAuthor = onSearchAuthor,
        onSearchTag = onSearchTag,
        onOpenMemory = onOpenMemory,
        onOpenWorldlines = onOpenWorldlines,
        onCatalogQueryChange = viewModel::setCatalogQuery,
        onToggleCatalogSort = viewModel::toggleCatalogSort,
        onCatalogStatusChange = viewModel::setCatalogStatus,
        onOpenSource = {
            val book = state.book
            val url = book?.let(::sourceUrl)
            if (url == null) {
                Toast.makeText(context, "没有可用的源站链接", Toast.LENGTH_SHORT).show()
            } else {
                try {
                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                } catch (_: ActivityNotFoundException) {
                    Toast.makeText(context, "没有可用浏览器", Toast.LENGTH_SHORT).show()
                }
            }
        },
        onRefresh = viewModel::refresh,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChapterListScreen(
    state: ChapterListUiState,
    snackbarHostState: SnackbarHostState,
    onBack: () -> Unit,
    onOpenChapter: (Int) -> Unit,
    onToggleFavorite: () -> Unit,
    onDownloadAll: () -> Unit,
    onExport: () -> Unit,
    onSearchAuthor: (String) -> Unit,
    onSearchTag: (String) -> Unit,
    onCatalogQueryChange: (String) -> Unit,
    onToggleCatalogSort: () -> Unit,
    onCatalogStatusChange: (String) -> Unit,
    onOpenSource: () -> Unit,
    onOpenMemory: (() -> Unit)?,
    onOpenWorldlines: (() -> Unit)?,
    onRefresh: () -> Unit,
) {
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { onRefresh() }
    var menuOpen by remember { mutableStateOf(false) }
    var selectedTab by rememberSaveable(state.book?.id) { mutableStateOf(TAB_INTRO) }
    var tabTouched by rememberSaveable(state.book?.id) { mutableStateOf(false) }
    var introExpanded by rememberSaveable(state.book?.id) { mutableStateOf(false) }
    val introListState = rememberLazyListState()
    val catalogListState = rememberLazyListState()

    LaunchedEffect(state.readState?.progressIdx) {
        if (!tabTouched && (state.readState?.progressIdx ?: 0) > 0) {
            selectedTab = TAB_CATALOG
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = state.book?.titleZh ?: state.book?.title ?: "书籍详情",
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        if (state.book != null) {
                            Text(
                                text = "${state.chapters.size} 话",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                },
                navigationIcon = {
                    TextButton(onClick = onBack) { Text("返回") }
                },
                actions = {
                    TextButton(onClick = onToggleFavorite) {
                        Text(if (state.favorite) "★" else "☆")
                    }
                    Box {
                        TextButton(onClick = { menuOpen = true }) { Text("更多") }
                        DropdownMenu(
                            expanded = menuOpen,
                            onDismissRequest = { menuOpen = false },
                        ) {
                            if (state.book?.local == false) {
                                DropdownMenuItem(
                                    text = {
                                        Text(
                                            if (state.downloading) {
                                                "下载中 ${state.downloadProgress.orEmpty()}"
                                            } else {
                                                "下载全部"
                                            },
                                        )
                                    },
                                    enabled = !state.downloading,
                                    onClick = {
                                        menuOpen = false
                                        onDownloadAll()
                                    },
                                )
                                DropdownMenuItem(
                                    text = { Text("打开源站") },
                                    onClick = {
                                        menuOpen = false
                                        onOpenSource()
                                    },
                                )
                            }
                            DropdownMenuItem(
                                text = { Text(if (state.exporting) "导出中…" else "导出 EPUB") },
                                enabled = !state.exporting,
                                onClick = {
                                    menuOpen = false
                                    onExport()
                                },
                            )
                            if (onOpenMemory != null) {
                                DropdownMenuItem(
                                    text = { Text("本书设定 / 故事记忆") },
                                    onClick = {
                                        menuOpen = false
                                        onOpenMemory()
                                    },
                                )
                            }
                            if (onOpenWorldlines != null) {
                                DropdownMenuItem(
                                    text = { Text("世界线") },
                                    onClick = {
                                        menuOpen = false
                                        onOpenWorldlines()
                                    },
                                )
                            }
                        }
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
        modifier = Modifier.testTag("chapter-list-screen"),
    ) { padding ->
        when {
            state.loading -> Box(
                Modifier
                    .fillMaxSize()
                    .padding(padding),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator()
            }

            state.error != null && state.book == null -> Box(
                Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(24.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text("加载失败：${state.error}")
            }

            state.book == null -> Box(
                Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(24.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text("找不到这本书")
            }

            else -> Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
            ) {
                if (state.downloading) {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                }
                Hero(
                    book = state.book,
                    detail = state.detail,
                    favorite = state.favorite,
                    progressIdx = state.readState?.progressIdx ?: 0,
                    onToggleFavorite = onToggleFavorite,
                    onContinue = {
                        val target = state.readState?.progressIdx?.takeIf {
                            it in 1..state.chapters.size
                        } ?: state.chapters.firstOrNull()?.idx ?: 1
                        onOpenChapter(target)
                    },
                    onSearchAuthor = onSearchAuthor,
                    onSearchTag = onSearchTag,
                )
                TabRow(selectedTabIndex = if (selectedTab == TAB_INTRO) 0 else 1) {
                    Tab(
                        selected = selectedTab == TAB_INTRO,
                        onClick = {
                            selectedTab = TAB_INTRO
                            tabTouched = true
                        },
                        text = { Text("简介") },
                    )
                    Tab(
                        selected = selectedTab == TAB_CATALOG,
                        onClick = {
                            selectedTab = TAB_CATALOG
                            tabTouched = true
                        },
                        text = { Text("目录 · ${state.chapters.size}") },
                    )
                }
                if (selectedTab == TAB_INTRO) {
                    IntroTab(
                        state = state,
                        listState = introListState,
                        expanded = introExpanded,
                        onExpand = { introExpanded = true },
                        onSearchAuthor = onSearchAuthor,
                        onSearchTag = onSearchTag,
                    )
                } else {
                    CatalogTab(
                        state = state,
                        listState = catalogListState,
                        onOpenChapter = onOpenChapter,
                        onQueryChange = onCatalogQueryChange,
                        onToggleSort = onToggleCatalogSort,
                        onStatusChange = onCatalogStatusChange,
                    )
                }
            }
        }
    }
}

@Composable
private fun Hero(
    book: BookEntity,
    detail: SourceDetail?,
    favorite: Boolean,
    progressIdx: Int,
    onToggleFavorite: () -> Unit,
    onContinue: () -> Unit,
    onSearchAuthor: (String) -> Unit,
    onSearchTag: (String) -> Unit,
) {
    val title = detail?.book?.titleZh ?: book.titleZh
        ?: detail?.book?.title?.ifBlank { book.title } ?: book.title
    val original = detail?.book?.title?.ifBlank { book.title } ?: book.title
    val author = detail?.book?.author?.takeIf { it.isNotBlank() } ?: book.author
    val tags = tagsOf(book, detail)
    Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            BookCover(
                title = title,
                modifier = Modifier.size(width = 82.dp, height = 112.dp),
                size = BookCoverSize.MEDIUM,
            )
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.headlineSmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                if (title != original) {
                    Text(
                        text = original,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (!author.isNullOrBlank()) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = "作者：",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(
                            text = author,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier
                                .weight(1f, fill = false)
                                .clickable { onSearchAuthor(author) },
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    SourceBadge(sourceLabel(book.source))
                    Text(
                        text = if (book.local) "本地导入" else "${book.episodes} 话",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        if (tags.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            TagFlow(tags = tags.take(6), onSearchTag = onSearchTag)
        }
        Spacer(Modifier.height(8.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Button(
                onClick = onContinue,
                modifier = Modifier.weight(1f),
                enabled = progressIdx > 0 || book.episodes > 0,
            ) {
                Text(if (progressIdx > 0) "继续阅读 · 第 $progressIdx 话" else "开始阅读")
            }
            TextButton(onClick = onToggleFavorite) {
                Text(if (favorite) "已收藏" else "收藏")
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun TagFlow(
    tags: List<Pair<String, String>>,
    onSearchTag: (String) -> Unit,
) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        tags.forEach { (original, localized) ->
            LnTag(
                text = localized,
                kind = LnTagKind.TYPE,
                onClick = { onSearchTag(original) },
            )
        }
    }
}

@Composable
private fun IntroTab(
    state: ChapterListUiState,
    listState: LazyListState,
    expanded: Boolean,
    onExpand: () -> Unit,
    onSearchAuthor: (String) -> Unit,
    onSearchTag: (String) -> Unit,
) {
    val book = state.book ?: return
    val detail = state.detail
    val tags = tagsOf(book, detail)
    val synopsis = detail?.book?.synopsisZh
        ?: detail?.synopsis?.takeIf { it.isNotBlank() }
        ?: detail?.book?.synopsis
        ?: "暂无简介"
    val author = detail?.book?.author?.takeIf { it.isNotBlank() } ?: book.author
    LazyColumn(
        state = listState,
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            SectionCard(title = "简介") {
                Text(
                    text = synopsis,
                    style = MaterialTheme.typography.bodyLarge,
                    maxLines = if (expanded) Int.MAX_VALUE else 6,
                    overflow = TextOverflow.Ellipsis,
                )
                if (!expanded && synopsis.length > 120) {
                    TextButton(onClick = onExpand) { Text("展开全部简介") }
                }
            }
        }
        if (tags.isNotEmpty()) {
            item {
                SectionCard(title = "标签") {
                    TagFlow(tags = tags, onSearchTag = onSearchTag)
                }
            }
        }
        item {
            SectionCard(title = "信息") {
                InfoRow("作者", author.orEmpty(), onClick = author?.let {
                    { onSearchAuthor(it) }
                })
                InfoRow("来源", sourceLabel(book.source))
                InfoRow("话数", "${state.chapters.size}")
                InfoRow("类型", if (book.local) "本地导入" else "在线书源")
            }
        }
    }
}

@Composable
private fun CatalogTab(
    state: ChapterListUiState,
    listState: LazyListState,
    onOpenChapter: (Int) -> Unit,
    onQueryChange: (String) -> Unit,
    onToggleSort: () -> Unit,
    onStatusChange: (String) -> Unit,
) {
    val filtered = remember(
        state.chapters,
        state.catalogQuery,
        state.catalogSortDesc,
        state.catalogStatus,
    ) {
        state.chapters
            .filter { chapter ->
                val query = state.catalogQuery.trim()
                (query.isEmpty() ||
                    chapter.title.orEmpty().contains(query, ignoreCase = true) ||
                    chapter.titleZh.orEmpty().contains(query, ignoreCase = true)) &&
                    when (state.catalogStatus) {
                        "translated" -> chapter.status in setOf("complete", "translated")
                        "untranslated" -> chapter.status in setOf("online", "raw", "translating")
                        "failed" -> chapter.status == "failed" || chapter.status == "missing"
                        else -> true
                    }
            }
            .let { if (state.catalogSortDesc) it.reversed() else it }
    }
    LazyColumn(
        state = listState,
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        item {
            OutlinedTextField(
                value = state.catalogQuery,
                onValueChange = onQueryChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text("搜索章节") },
                singleLine = true,
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onToggleSort) {
                    Text(if (state.catalogSortDesc) "倒序" else "正序")
                }
                BrandFilterChip(
                    selected = state.catalogStatus == "all",
                    onClick = { onStatusChange("all") },
                    label = { Text("全部") },
                )
                BrandFilterChip(
                    selected = state.catalogStatus == "translated",
                    onClick = { onStatusChange("translated") },
                    label = { Text("已译") },
                )
                BrandFilterChip(
                    selected = state.catalogStatus == "untranslated",
                    onClick = { onStatusChange("untranslated") },
                    label = { Text("未译") },
                )
                BrandFilterChip(
                    selected = state.catalogStatus == "failed",
                    onClick = { onStatusChange("failed") },
                    label = { Text("失败") },
                )
            }
            if (filtered.isEmpty()) {
                Text(
                    "没有匹配的章节",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 24.dp),
                )
            }
        }
        items(filtered, key = { it.idx }) { chapter ->
            ChapterRow(
                chapter = chapter,
                current = state.readState?.progressIdx == chapter.idx,
                onClick = { onOpenChapter(chapter.idx) },
            )
        }
    }
}

@Composable
private fun SectionCard(
    title: String,
    content: @Composable () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(16.dp)) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleSmall)
            content()
        }
    }
}

@Composable
private fun InfoRow(
    label: String,
    value: String,
    onClick: (() -> Unit)? = null,
) {
    if (value.isBlank()) return
    Row(modifier = Modifier.fillMaxWidth()) {
        Text(
            text = label,
            modifier = Modifier.width(56.dp),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            color = if (onClick != null) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.onSurface,
            modifier = Modifier
                .weight(1f)
                .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier),
            maxLines = 3,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun ChapterRow(
    chapter: ChapterEntity,
    current: Boolean,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 10.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = chapter.idx.toString(),
            modifier = Modifier.width(36.dp),
            style = MaterialTheme.typography.labelSmall,
            color = if (current) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = chapter.titleZh ?: chapter.title ?: "第 ${chapter.idx} 话",
                style = MaterialTheme.typography.bodyLarge,
                color = if (current) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.onSurface,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (current) {
                Text(
                    "正在读",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
        StatusBadge(
            text = statusLabel(chapter.status),
            tone = statusTone(chapter.status),
        )
    }
}

private fun tagsOf(book: BookEntity, detail: SourceDetail?): List<Pair<String, String>> {
    val source = detail?.book
    val original = source?.tags.orEmpty().ifEmpty { BookTags.decode(book.tagsJson) }
    val localized = source?.tagsZh.orEmpty()
    val translated = if (localized.size == original.size) localized else emptyList()
    return original.mapIndexed { index, tag ->
        tag to (translated.getOrNull(index)?.takeIf(String::isNotBlank) ?: tag)
    }
}

private fun sourceLabel(source: String): String = when (source) {
    "kakuyomu" -> "Kakuyomu"
    "syosetu" -> "成为小说家吧"
    "local" -> "本地"
    else -> source
}

private fun sourceUrl(book: BookEntity): String? = when (book.source) {
    "kakuyomu" -> "https://kakuyomu.jp/works/${book.sourceId}"
    "syosetu" -> "https://ncode.syosetu.com/${book.sourceId.lowercase()}/"
    else -> null
}

private fun statusLabel(status: String?): String = when (status) {
    "complete" -> "已译"
    "translated" -> "有译文"
    "partial" -> "未译全"
    "failed" -> "翻译失败"
    "translating" -> "翻译中"
    "raw", "online" -> "生肉"
    "missing" -> "缺文件"
    else -> ""
}

private fun statusTone(status: String?): StatusTone = when (status) {
    "complete", "translated" -> StatusTone.SUCCESS
    "translating" -> StatusTone.INFO
    "partial" -> StatusTone.WARNING
    "failed", "missing" -> StatusTone.ERROR
    else -> StatusTone.NEUTRAL
}
