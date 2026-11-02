package com.kacyraho.lightnovel.feature.catalog

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kacyraho.lightnovel.AppContainer
import com.kacyraho.lightnovel.data.catalog.TextSanitizer
import com.kacyraho.lightnovel.data.catalog.key
import com.kacyraho.lightnovel.data.catalog.tagPairs
import com.kacyraho.lightnovel.data.local.CatalogBookEntity
import com.kacyraho.lightnovel.ui.components.BookCover
import com.kacyraho.lightnovel.ui.components.BookCoverSize
import com.kacyraho.lightnovel.ui.components.BrandFilterChip
import com.kacyraho.lightnovel.ui.components.LnTag
import com.kacyraho.lightnovel.ui.components.LnTagKind
import com.kacyraho.lightnovel.ui.components.SourceBadge

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CatalogRoute(
    container: AppContainer,
    onBack: () -> Unit,
) {
    val viewModel: CatalogViewModel = viewModel {
        CatalogViewModel(
            catalog = container.catalogRepository,
            library = container.libraryRepository,
            directLibrary = container.directLibraryService,
        )
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    var preview by remember { mutableStateOf<CatalogBookEntity?>(null) }

    preview?.let { book ->
        CatalogPreviewSheet(
            book = book,
            added = book.key in state.addedKeys,
            adding = state.addingKey == book.key,
            onDismiss = { preview = null },
            onAdd = {
                viewModel.add(book)
                preview = null
            },
        )
    }

    CatalogScreen(
        state = state,
        onBack = onBack,
        onQueryChange = viewModel::setQuery,
        onProviderChange = viewModel::setProvider,
        onStatusChange = viewModel::setStatus,
        onTagToggle = viewModel::toggleTag,
        onSortChange = viewModel::setSort,
        onClearFilters = viewModel::clearFilters,
        onClearTags = viewModel::clearTags,
        onPreview = { preview = it },
        onAdd = viewModel::add,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CatalogScreen(
    state: CatalogUiState,
    onBack: () -> Unit,
    onQueryChange: (String) -> Unit,
    onProviderChange: (String?) -> Unit,
    onStatusChange: (String?) -> Unit,
    onTagToggle: (String) -> Unit,
    onSortChange: (String) -> Unit,
    onClearFilters: () -> Unit,
    onClearTags: () -> Unit,
    onPreview: (CatalogBookEntity) -> Unit,
    onAdd: (CatalogBookEntity) -> Unit,
) {
    var showTags by remember { mutableStateOf(false) }
    var tagQuery by remember { mutableStateOf("") }
    val visibleTags = remember(state.tags, state.selectedTags) {
        state.tags.sortedWith(
            compareByDescending<CatalogTag> { it.source in state.selectedTags }
                .thenByDescending { it.count },
        )
    }
    val inlineTags = remember(visibleTags) { visibleTags.take(10) }
    if (showTags) {
        TagPickerSheet(
            tags = visibleTags,
            selected = state.selectedTags,
            query = tagQuery,
            onQueryChange = { tagQuery = it },
            onToggle = onTagToggle,
            onClear = onClearTags,
            onDismiss = { showTags = false },
        )
    }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("大书库 · ${state.total} 本") },
                navigationIcon = {
                    TextButton(onClick = onBack) { Text("返回") }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            OutlinedTextField(
                value = state.query,
                onValueChange = onQueryChange,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp),
                label = { Text("搜索书名 / 作者 / 标签") },
                singleLine = true,
            )
            LazyRow(
                contentPadding = PaddingValues(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                item {
                    BrandFilterChip(
                        selected = state.provider == null,
                        onClick = { onProviderChange(null) },
                        label = { Text("全部来源") },
                    )
                }
                item {
                    BrandFilterChip(
                        selected = state.provider == "kakuyomu",
                        onClick = { onProviderChange("kakuyomu") },
                        label = { Text("Kakuyomu") },
                    )
                }
                item {
                    BrandFilterChip(
                        selected = state.provider == "syosetu",
                        onClick = { onProviderChange("syosetu") },
                        label = { Text("成为小说家吧") },
                    )
                }
            }
            LazyRow(
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                item {
                    BrandFilterChip(
                        selected = state.status == null,
                        onClick = { onStatusChange(null) },
                        label = { Text("全部状态") },
                    )
                }
                item {
                    BrandFilterChip(
                        selected = state.status == "running",
                        onClick = { onStatusChange("running") },
                        label = { Text("连载中") },
                    )
                }
                item {
                    BrandFilterChip(
                        selected = state.status == "completed",
                        onClick = { onStatusChange("completed") },
                        label = { Text("已完结") },
                    )
                }
                item {
                    BrandFilterChip(
                        selected = state.status == "short",
                        onClick = { onStatusChange("short") },
                        label = { Text("短篇") },
                    )
                }
            }
            LazyRow(
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(CatalogSort.entries.toList(), key = { it.id }) { sort ->
                    BrandFilterChip(
                        selected = state.sort == sort,
                        onClick = { onSortChange(sort.id) },
                        label = { Text(sort.label) },
                    )
                }
            }
            if (state.tags.isNotEmpty()) {
                LazyRow(
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 2.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    item {
                        Text(
                            "标签 · 多选",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    item {
                        LnTag(
                            text = "全部",
                            kind = if (state.selectedTags.isEmpty()) {
                                LnTagKind.TYPE
                            } else {
                                LnTagKind.KEYWORD
                            },
                            onClick = onClearTags,
                        )
                    }
                    if (visibleTags.isNotEmpty()) {
                        item {
                            LnTag(
                                text = "更多",
                                kind = LnTagKind.KEYWORD,
                                onClick = { showTags = true },
                            )
                        }
                    }
                    items(inlineTags, key = { it.source }) { tag ->
                        LnTag(
                            text = tag.label,
                            kind = if (tag.source in state.selectedTags) {
                                LnTagKind.TYPE
                            } else {
                                LnTagKind.KEYWORD
                            },
                            onClick = { onTagToggle(tag.source) },
                        )
                    }
                }
            }
            if (state.query.isNotBlank() || state.provider != null ||
                state.status != null || state.selectedTags.isNotEmpty()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        "筛选后 ${state.books.size} 本",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(onClick = onClearFilters) { Text("清除筛选") }
                }
            }
            state.error?.let { error ->
                Text(
                    text = error,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }
            when {
                state.loading -> Box(
                    Modifier
                        .fillMaxSize()
                        .weight(1f),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator()
                }

                state.books.isEmpty() -> Box(
                    Modifier
                        .fillMaxSize()
                        .weight(1f)
                        .padding(24.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        if (state.total == 0) {
                            "还没有书。去发现页搜索。"
                        } else {
                            "没有匹配结果。"
                        },
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }

                else -> LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(state.books, key = { it.key }, contentType = { "catalog-book" }) { book ->
                        CatalogRow(
                            book = book,
                            added = book.key in state.addedKeys,
                            adding = state.addingKey == book.key,
                            onClick = { onPreview(book) },
                            onAdd = { onAdd(book) },
                            selectedTags = state.selectedTags,
                            onTagToggle = onTagToggle,
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TagPickerSheet(
    tags: List<CatalogTag>,
    selected: Set<String>,
    query: String,
    onQueryChange: (String) -> Unit,
    onToggle: (String) -> Unit,
    onClear: () -> Unit,
    onDismiss: () -> Unit,
) {
    val filtered = remember(tags, query) {
        if (query.isBlank()) {
            tags
        } else {
            tags.filter {
                it.label.contains(query, ignoreCase = true) ||
                    it.source.contains(query, ignoreCase = true)
            }
        }
    }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(0.9f)
                .padding(horizontal = 20.dp)
                .padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    if (selected.isEmpty()) "标签" else "标签 · 已选 ${selected.size}",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = onClear, enabled = selected.isNotEmpty()) {
                    Text("清除")
                }
            }
            OutlinedTextField(
                value = query,
                onValueChange = onQueryChange,
                modifier = Modifier.fillMaxWidth(),
                label = { Text("搜索标签") },
                singleLine = true,
            )
            LazyColumn(modifier = Modifier.weight(1f)) {
                items(filtered, key = { it.source }) { tag ->
                    val checked = tag.source in selected
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onToggle(tag.source) }
                            .padding(vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = if (checked) "✓" else "",
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.width(24.dp),
                        )
                        Text(
                            text = tag.label,
                            modifier = Modifier.weight(1f),
                            color = if (checked) {
                                MaterialTheme.colorScheme.primary
                            } else {
                                MaterialTheme.colorScheme.onSurface
                            },
                        )
                        Text(
                            text = tag.count.toString(),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                }
            }
            Button(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
                Text("完成")
            }
        }
    }
}

@Composable
private fun CatalogRow(
    book: CatalogBookEntity,
    added: Boolean,
    adding: Boolean,
    onClick: () -> Unit,
    onAdd: () -> Unit,
    selectedTags: Set<String>,
    onTagToggle: (String) -> Unit,
) {
    val tags = remember(book.tagsJson, book.tagsZhJson) { book.tagPairs() }
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            BookCover(
                title = book.titleZh ?: book.title,
                modifier = Modifier.size(width = 64.dp, height = 88.dp),
                size = BookCoverSize.SMALL,
            )
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.Top) {
                    Text(
                        text = (book.titleZh ?: book.title).ifBlank { book.sourceId },
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(onClick = onAdd, enabled = !added && !adding) {
                        Text(
                            when {
                                added -> "已在书架"
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
                    book.author?.takeIf { it.isNotBlank() }?.let {
                        Text(
                            text = it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.weight(1f, fill = false),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    SourceBadge(sourceLabel(book.provider))
                    if (book.episodes > 0) {
                        Text(
                            "${book.episodes} 话",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    book.characters?.takeIf { it > 0 }?.let {
                        Text(
                            formatCount(it),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                val synopsis = (book.synopsisZh ?: book.synopsis)
                    ?.let(TextSanitizer::decode)
                if (!synopsis.isNullOrBlank()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = synopsis,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (tags.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        tags.take(3).forEach { (source, label) ->
                            LnTag(
                                text = label,
                                kind = if (source in selectedTags) {
                                    LnTagKind.TYPE
                                } else {
                                    LnTagKind.KEYWORD
                                },
                                onClick = { onTagToggle(source) },
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
private fun CatalogPreviewSheet(
    book: CatalogBookEntity,
    added: Boolean,
    adding: Boolean,
    onDismiss: () -> Unit,
    onAdd: () -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = (book.titleZh ?: book.title).ifBlank { book.sourceId },
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
                book.author?.takeIf { it.isNotBlank() }?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.weight(1f, fill = false),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                SourceBadge(sourceLabel(book.provider))
                if (book.episodes > 0) {
                    Text(
                        "${book.episodes} 话",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            HorizontalDivider()
            Text("简介", style = MaterialTheme.typography.titleSmall)
            Text(
                TextSanitizer.decode(book.synopsisZh ?: book.synopsis.orEmpty())
                    .ifBlank { "暂无简介" },
                style = MaterialTheme.typography.bodyMedium,
            )
            Button(
                onClick = onAdd,
                enabled = !added && !adding,
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
        }
    }
}

private fun formatCount(value: Int): String =
    if (value >= 10_000) {
        String.format(java.util.Locale.US, "%.1f 万字", value / 10_000f)
    } else {
        "$value 字"
    }

private fun sourceLabel(provider: String): String =
    if (provider == "kakuyomu") "Kakuyomu" else "成为小说家吧"
