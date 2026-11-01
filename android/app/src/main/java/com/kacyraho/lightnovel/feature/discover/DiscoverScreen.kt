package com.kacyraho.lightnovel.feature.discover

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kacyraho.lightnovel.AppContainer
import com.kacyraho.lightnovel.data.source.SourceBook
import com.kacyraho.lightnovel.ui.components.BookCover
import com.kacyraho.lightnovel.ui.components.BrandFilterChip
import com.kacyraho.lightnovel.ui.components.LnTag
import com.kacyraho.lightnovel.ui.components.LnTagKind
import com.kacyraho.lightnovel.ui.components.SourceBadge

private val commonTags = listOf(
    "ざまぁ", "追放", "悪役令嬢", "転生", "チート", "溺愛",
    "異世界", "恋愛", "ファンタジー", "ハーレム", "冒険", "学園",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DiscoverRoute(
    container: AppContainer,
    initialQuery: String? = null,
    initialMode: String? = null,
    onBack: (() -> Unit)? = null,
    onOpenBook: (String) -> Unit,
) {
    val viewModel: DiscoverViewModel = viewModel {
        DiscoverViewModel(
            sources = container.directLibraryService.sources,
            library = container.directLibraryService,
            metadataService = container.metadataTranslationService,
            historyStore = container.searchHistoryStore,
            presetStore = container.searchPresetStore,
        )
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(initialQuery, initialMode) {
        if (!initialQuery.isNullOrBlank()) {
            viewModel.search(initialQuery, initialMode ?: "keyword")
        }
    }
    LaunchedEffect(state.addedBookId) {
        val id = state.addedBookId ?: return@LaunchedEffect
        viewModel.consumeAddedBook()
        val result = snackbarHostState.showSnackbar(
            message = "已加入书架",
            actionLabel = "查看",
            withDismissAction = true,
        )
        if (result == SnackbarResult.ActionPerformed) onOpenBook(id)
    }

    state.preview?.let { book ->
        BookPreviewSheet(
            book = book,
            adding = state.addingId == book.provider + "/" + book.id,
            added = book.provider + "/" + book.id in state.addedKeys,
            onDismiss = viewModel::dismissPreview,
            onAdd = { viewModel.add(book) },
            onAuthorClick = {
                viewModel.dismissPreview()
                viewModel.searchAuthor(it)
            },
            onTagClick = {
                viewModel.dismissPreview()
                viewModel.searchTag(it)
            },
        )
    }
    if (state.linkSheetOpen) {
        LinkSheet(
            value = state.urlInput,
            adding = state.addingId != null,
            onValueChange = viewModel::onUrlChange,
            onDismiss = viewModel::closeLinkSheet,
            onAdd = viewModel::addFromUrl,
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("发现") },
                navigationIcon = {
                    if (onBack != null && !initialQuery.isNullOrBlank()) {
                        TextButton(onClick = onBack) { Text("返回") }
                    }
                },
                actions = {
                    TextButton(onClick = viewModel::openLinkSheet) {
                        Text("链接加书")
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            OutlinedTextField(
                value = state.query,
                onValueChange = viewModel::onQueryChange,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                label = { Text("搜索日文标题、作者或标签") },
                singleLine = true,
                trailingIcon = {
                    TextButton(
                        onClick = { viewModel.search() },
                        enabled = !state.loading && state.query.isNotBlank(),
                    ) {
                        Text("搜索")
                    }
                },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { viewModel.search() }),
            )
            if (state.query.isBlank() && state.recentSearches.isNotEmpty()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState())
                        .padding(horizontal = 16.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        "最近搜索",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    state.recentSearches.forEach { value ->
                        LnTag(
                            text = value,
                            kind = LnTagKind.KEYWORD,
                            onClick = {
                                viewModel.onQueryChange(value)
                                viewModel.search(value)
                            },
                        )
                    }
                    TextButton(onClick = viewModel::clearSearchHistory) {
                        Text("清空")
                    }
                }
            }
            if (state.query.isBlank() && state.savedSearches.isNotEmpty()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState())
                        .padding(horizontal = 16.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        "保存的搜索",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    state.savedSearches.forEach { preset ->
                        LnTag(
                            text = preset.query,
                            kind = LnTagKind.TYPE,
                            onClick = { viewModel.applyPreset(preset) },
                        )
                    }
                }
            }
            if (state.loading) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            }
            if (state.metadataLoading) {
                Text(
                    text = "正在翻译书名 / 简介…",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.secondary,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp),
                )
            }
            state.errors.distinct().forEach { error ->
                Text(
                    text = error,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp),
                )
            }
            when {
                state.results.isNotEmpty() -> SearchResults(
                    results = state.results.filter {
                        (state.sourceFilter == null || it.provider == state.sourceFilter) &&
                            it.matchesStatus(state.statusFilter) &&
                            it.matchesCharacters(state.characterFilter)
                    },
                    sourceFilter = state.sourceFilter,
                    onSourceFilterChange = viewModel::setSourceFilter,
                    statusFilter = state.statusFilter,
                    onStatusFilterChange = viewModel::setStatusFilter,
                    characterFilter = state.characterFilter,
                    onCharacterFilterChange = viewModel::setCharacterFilter,
                    addingId = state.addingId,
                    addedKeys = state.addedKeys,
                    onAdd = viewModel::add,
                    onPreview = viewModel::preview,
                    onAuthorClick = viewModel::searchAuthor,
                    onTagClick = viewModel::searchTag,
                )

                state.searchedQuery != null && !state.loading -> Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        "没有找到「${state.searchedQuery}」",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "换个关键词，或从链接直接加书。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Spacer(Modifier.height(12.dp))
                    TextButton(onClick = viewModel::clearSearch) {
                        Text("清空搜索")
                    }
                }

                else -> DiscoverHome(
                    recommendations = state.recommendations,
                    loading = state.loadingRecommendations,
                    onAdd = viewModel::add,
                    addingId = state.addingId,
                    addedKeys = state.addedKeys,
                    onPreview = viewModel::preview,
                    onAuthorClick = viewModel::searchAuthor,
                    onTagClick = viewModel::searchTag,
                )
            }
        }
    }
}

@Composable
private fun DiscoverHome(
    recommendations: List<SourceBook>,
    loading: Boolean,
    addingId: String?,
    addedKeys: Set<String>,
    onAdd: (SourceBook) -> Unit,
    onPreview: (SourceBook) -> Unit,
    onAuthorClick: (String) -> Unit,
    onTagClick: (String) -> Unit,
) {
    val featured = recommendations.take(6)
    val more = recommendations.drop(6)
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 20.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item {
            Text(
                "本周推荐",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
            Text(
                "来自 Kakuyomu / 成为小说家吧；先看简介，再决定要不要加入书架。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
        item {
            LazyRow(
                contentPadding = PaddingValues(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(featured, key = { it.provider + "/" + it.id }) { book ->
                    RecommendationCard(
                        book = book,
                        onClick = { onPreview(book) },
                    )
                }
            }
        }
        item {
            Text(
                "热门标签",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            )
            LazyRow(
                contentPadding = PaddingValues(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(commonTags) { tag ->
                    LnTag(text = tag, kind = LnTagKind.TYPE, onClick = { onTagClick(tag) })
                }
            }
        }
        if (recommendations.isEmpty()) {
            item {
                Text(
                    if (loading) "正在加载推荐…" else "暂时拿不到推荐，可以搜索或从链接加书。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(16.dp),
                )
            }
        } else if (more.isNotEmpty()) {
            item {
                Text(
                    "更多推荐",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                )
            }
            items(more, key = { "rec-" + it.provider + "/" + it.id }) { book ->
                SourceResultCard(
                    item = book,
                    adding = addingId == book.provider + "/" + book.id,
                    added = book.provider + "/" + book.id in addedKeys,
                    onAdd = { onAdd(book) },
                    onPreview = { onPreview(book) },
                    onAuthorClick = onAuthorClick,
                    onTagClick = onTagClick,
                )
            }
        }
    }
}

@Composable
private fun SearchResults(
    results: List<SourceBook>,
    sourceFilter: String?,
    onSourceFilterChange: (String?) -> Unit,
    statusFilter: String?,
    onStatusFilterChange: (String?) -> Unit,
    characterFilter: String,
    onCharacterFilterChange: (String) -> Unit,
    addingId: String?,
    addedKeys: Set<String>,
    onAdd: (SourceBook) -> Unit,
    onPreview: (SourceBook) -> Unit,
    onAuthorClick: (String) -> Unit,
    onTagClick: (String) -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item {
            Text(
                "搜索结果 · ${results.size}",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(vertical = 4.dp),
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                BrandFilterChip(
                    selected = sourceFilter == null,
                    onClick = { onSourceFilterChange(null) },
                    label = { Text("全部来源") },
                )
                BrandFilterChip(
                    selected = sourceFilter == "kakuyomu",
                    onClick = { onSourceFilterChange("kakuyomu") },
                    label = { Text("Kakuyomu") },
                )
                BrandFilterChip(
                    selected = sourceFilter == "syosetu",
                    onClick = { onSourceFilterChange("syosetu") },
                    label = { Text("成为小说家吧") },
                )
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(vertical = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                BrandFilterChip(
                    selected = statusFilter == null,
                    onClick = { onStatusFilterChange(null) },
                    label = { Text("全部状态") },
                )
                BrandFilterChip(
                    selected = statusFilter == "running",
                    onClick = { onStatusFilterChange("running") },
                    label = { Text("连载中") },
                )
                BrandFilterChip(
                    selected = statusFilter == "completed",
                    onClick = { onStatusFilterChange("completed") },
                    label = { Text("已完结") },
                )
                BrandFilterChip(
                    selected = statusFilter == "short",
                    onClick = { onStatusFilterChange("short") },
                    label = { Text("短篇") },
                )
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(vertical = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                BrandFilterChip(
                    selected = characterFilter == "all",
                    onClick = { onCharacterFilterChange("all") },
                    label = { Text("不限字数") },
                )
                BrandFilterChip(
                    selected = characterFilter == "short",
                    onClick = { onCharacterFilterChange("short") },
                    label = { Text("10 万字以下") },
                )
                BrandFilterChip(
                    selected = characterFilter == "medium",
                    onClick = { onCharacterFilterChange("medium") },
                    label = { Text("10–30 万字") },
                )
                BrandFilterChip(
                    selected = characterFilter == "long",
                    onClick = { onCharacterFilterChange("long") },
                    label = { Text("30 万字以上") },
                )
            }
            if (results.isEmpty()) {
                Text(
                    "当前来源没有结果",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 16.dp),
                )
            }
        }
        items(results, key = { it.provider + "/" + it.id }) { item ->
            SourceResultCard(
                item = item,
                adding = addingId == item.provider + "/" + item.id,
                added = item.provider + "/" + item.id in addedKeys,
                onAdd = { onAdd(item) },
                onPreview = { onPreview(item) },
                onAuthorClick = onAuthorClick,
                onTagClick = onTagClick,
            )
        }
    }
}

@Composable
private fun RecommendationCard(
    book: SourceBook,
    onClick: () -> Unit,
) {
    Column(
        modifier = Modifier
            .width(148.dp)
            .clickable(onClick = onClick),
    ) {
        BookCover(
            title = (book.titleZh ?: book.title).ifBlank { book.id },
            modifier = Modifier
                .fillMaxWidth()
                .height(188.dp),
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = (book.titleZh ?: book.title).ifBlank { book.id },
            style = MaterialTheme.typography.titleSmall,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            text = listOfNotNull(
                book.author.takeIf { it.isNotBlank() },
                sourceLabel(book.provider),
            ).joinToString(" · "),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun SourceResultCard(
    item: SourceBook,
    adding: Boolean,
    added: Boolean,
    onAdd: () -> Unit,
    onPreview: () -> Unit,
    onAuthorClick: (String) -> Unit,
    onTagClick: (String) -> Unit,
) {
    val pairs = item.tagPairs()
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onPreview),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            BookCover(
                title = (item.titleZh ?: item.title).ifBlank { item.id },
                modifier = Modifier.size(width = 64.dp, height = 88.dp),
            )
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.Top) {
                    Text(
                        text = (item.titleZh ?: item.title).ifBlank { item.id },
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(
                        onClick = onAdd,
                        enabled = !adding && !added,
                    ) {
                        Text(
                            when {
                                added -> "已加入"
                                adding -> "加入中"
                                else -> "加入"
                            },
                        )
                    }
                }
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (item.author.isNotBlank()) {
                        Text(
                            text = item.author,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.clickable { onAuthorClick(item.author) },
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    SourceBadge(sourceLabel(item.provider))
                    if (item.episodes > 0) {
                        Text(
                            text = "${item.episodes} 话",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    if (item.updatedAt.isNotBlank()) {
                        Text(
                            text = "更新 ${item.updatedAt}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                val synopsis = item.synopsisZh ?: item.synopsis
                if (synopsis.isNotBlank()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = synopsis,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (pairs.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        itemsIndexed(pairs.take(3)) { _, pair ->
                            LnTag(
                                text = pair.second,
                                kind = LnTagKind.TYPE,
                                onClick = { onTagClick(pair.first) },
                            )
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BookPreviewSheet(
    book: SourceBook,
    adding: Boolean,
    added: Boolean,
    onDismiss: () -> Unit,
    onAdd: () -> Unit,
    onAuthorClick: (String) -> Unit,
    onTagClick: (String) -> Unit,
) {
    val pairs = book.tagPairs()
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = (book.titleZh ?: book.title).ifBlank { book.id },
                style = MaterialTheme.typography.titleLarge,
            )
            if (!book.titleZh.isNullOrBlank() && book.title.isNotBlank()) {
                Text(
                    text = book.title,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (book.author.isNotBlank()) {
                    Text(
                        text = book.author,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.clickable { onAuthorClick(book.author) },
                    )
                }
                SourceBadge(sourceLabel(book.provider))
                if (book.episodes > 0) {
                    Text(
                        text = "${book.episodes} 话",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (pairs.isNotEmpty()) {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    itemsIndexed(pairs.take(12)) { _, pair ->
                        LnTag(
                            text = pair.second,
                            kind = LnTagKind.TYPE,
                            onClick = { onTagClick(pair.first) },
                        )
                    }
                }
            }
            HorizontalDivider()
            Text("简介", style = MaterialTheme.typography.titleSmall)
            Text(
                text = (book.synopsisZh ?: book.synopsis).ifBlank { "暂无简介" },
                style = MaterialTheme.typography.bodyMedium,
            )
            Button(
                onClick = onAdd,
                enabled = !adding && !added,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    when {
                        added -> "已在书架"
                        adding -> "正在加入…"
                        else -> "加入书架"
                    },
                )
            }
            TextButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
                Text("关闭")
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LinkSheet(
    value: String,
    adding: Boolean,
    onValueChange: (String) -> Unit,
    onDismiss: () -> Unit,
    onAdd: () -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("从链接添加", style = MaterialTheme.typography.titleLarge)
            Text(
                "支持 Kakuyomu / 成为小说家吧作品链接，或 Kakuyomu 数字 ID。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedTextField(
                value = value,
                onValueChange = onValueChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text("作品链接 / 数字 ID") },
                singleLine = true,
            )
            Button(
                onClick = onAdd,
                enabled = value.isNotBlank() && !adding,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (adding) "正在加入…" else "加入书架")
            }
        }
    }
}

private fun SourceBook.tagPairs(): List<Pair<String, String>> {
    val localized = if (tagsZh.size == tags.size) tagsZh else emptyList()
    return tags.mapIndexed { index, original ->
        original to (localized.getOrNull(index)?.takeIf(String::isNotBlank) ?: original)
    }
}

private fun SourceBook.matchesStatus(filter: String?): Boolean =
    filter == null || status == filter

private fun SourceBook.matchesCharacters(filter: String): Boolean {
    val value = characters ?: return filter == "all"
    return when (filter) {
        "short" -> value < 100_000
        "medium" -> value in 100_000..300_000
        "long" -> value > 300_000
        else -> true
    }
}

private fun sourceLabel(provider: String): String =
    if (provider == "kakuyomu") "Kakuyomu" else "成为小说家吧"
