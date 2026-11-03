package com.kacyraho.lightnovel.feature.library

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
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
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kacyraho.lightnovel.AppContainer
import com.kacyraho.lightnovel.data.local.BookWithState
import com.kacyraho.lightnovel.ui.components.BookCover
import com.kacyraho.lightnovel.ui.components.BookCoverSize
import com.kacyraho.lightnovel.ui.components.BrandFilterChip

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryRoute(
    container: AppContainer,
    onOpenBook: (String) -> Unit,
    onContinue: (String, Int) -> Unit,
    onOpenSettings: () -> Unit,
    onDiscover: () -> Unit,
) {
    val viewModel: LibraryViewModel = viewModel {
        LibraryViewModel(
            repository = container.libraryRepository,
            importCoordinator = container.importCoordinator,
            safStager = container.safStager,
            localDocumentImporter = container.localDocumentImporter,
            settingsStore = container.settingsStore,
            metadataService = container.metadataTranslationService,
            downloadScheduler = container.bookDownloadScheduler,
            taskRegistry = container.translationTaskRegistry,
        )
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val importState by viewModel.importState.collectAsStateWithLifecycle()
    val recent by viewModel.recent.collectAsStateWithLifecycle()
    val lastBackupAt by viewModel.lastBackupAt.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument(),
    ) { uri ->
        uri?.let(viewModel::import)
    }
    val documentLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument(),
    ) { uri ->
        uri?.let { viewModel.importDocument(it, context.contentResolver) }
    }
    LibraryScreen(
        state = state,
        recent = recent,
        importState = importState,
        lastBackupAt = lastBackupAt,
        onOpenBook = onOpenBook,
        onContinue = onContinue,
        onDiscover = onDiscover,
        onOpenSettings = onOpenSettings,
        onShelfChange = viewModel::setShelf,
        onFavoritesOnlyChange = viewModel::setFavoritesOnly,
        onRemovedOnlyChange = viewModel::setRemovedOnly,
        onQueryChange = viewModel::setQuery,
        onRemoveBook = viewModel::removeBook,
        onRestoreBook = viewModel::restoreBook,
        onImport = { launcher.launch(arrayOf("*/*")) },
        onImportDocument = {
            documentLauncher.launch(arrayOf("*/*"))
        },
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen(
    state: LibraryUiState,
    recent: List<BookWithState>,
    importState: LibraryImportState,
    lastBackupAt: String?,
    onOpenBook: (String) -> Unit,
    onContinue: (String, Int) -> Unit,
    onDiscover: () -> Unit,
    onOpenSettings: () -> Unit,
    onShelfChange: (String?) -> Unit,
    onFavoritesOnlyChange: (Boolean) -> Unit,
    onRemovedOnlyChange: (Boolean) -> Unit,
    onQueryChange: (String) -> Unit,
    onRemoveBook: (String) -> Unit,
    onRestoreBook: (String) -> Unit,
    onImport: () -> Unit,
    onImportDocument: () -> Unit,
) {
    var menuOpen by remember { mutableStateOf(false) }
    var showBackupNotice by rememberSaveable { mutableStateOf(true) }
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
            TopAppBar(
                title = { Text("Ka小说家") },
                actions = {
                    Box {
                        TextButton(onClick = { menuOpen = true }) { Text("更多") }
                        DropdownMenu(
                            expanded = menuOpen,
                            onDismissRequest = { menuOpen = false },
                        ) {
                            DropdownMenuItem(
                                text = { Text(if (importState.importing) "导入中…" else "导入备份") },
                                enabled = !importState.importing,
                                onClick = {
                                    menuOpen = false
                                    onImport()
                                },
                            )
                            DropdownMenuItem(
                                text = { Text("导入 TXT / EPUB") },
                                enabled = !importState.importing,
                                onClick = {
                                    menuOpen = false
                                    onImportDocument()
                                },
                            )
                            DropdownMenuItem(
                                text = { Text("设置") },
                                onClick = {
                                    menuOpen = false
                                    onOpenSettings()
                                },
                            )
                        }
                    }
                },
            )
        },
        modifier = Modifier.testTag("library-screen"),
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (lastBackupAt == null && state.books.isNotEmpty() && showBackupNotice) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = "还没有备份，卸载 App 会丢失本地书库。",
                        modifier = Modifier.weight(1f),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.tertiary,
                    )
                    TextButton(onClick = onOpenSettings) { Text("去设置") }
                    TextButton(onClick = { showBackupNotice = false }) { Text("关闭") }
                }
            }

            if (recent.isNotEmpty()) {
                Text(
                    "继续阅读",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
                )
                LazyRow(
                    contentPadding = PaddingValues(horizontal = 16.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(recent, key = { "recent-" + it.book.id }) { item ->
                        ContinueCard(
                            item = item,
                            onClick = {
                                onContinue(item.book.id, item.state?.progressIdx ?: 1)
                            },
                        )
                    }
                }
            }

            OutlinedTextField(
                value = state.query,
                onValueChange = onQueryChange,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp),
                label = { Text("搜索标题 / 作者 / 标签") },
                singleLine = true,
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                BrandFilterChip(
                    selected = state.shelf == null && !state.favoritesOnly && !state.removedOnly,
                    onClick = {
                        onShelfChange(null)
                        onFavoritesOnlyChange(false)
                        onRemovedOnlyChange(false)
                    },
                    label = { Text("全部") },
                )
                BrandFilterChip(
                    selected = state.shelf == "reading",
                    onClick = { onShelfChange("reading") },
                    label = { Text("在读") },
                )
                BrandFilterChip(
                    selected = state.shelf == "want",
                    onClick = { onShelfChange("want") },
                    label = { Text("想读") },
                )
                BrandFilterChip(
                    selected = state.shelf == "finished",
                    onClick = { onShelfChange("finished") },
                    label = { Text("读完") },
                )
                BrandFilterChip(
                    selected = state.favoritesOnly,
                    onClick = { onFavoritesOnlyChange(!state.favoritesOnly) },
                    label = { Text("收藏") },
                )
                BrandFilterChip(
                    selected = state.removedOnly,
                    onClick = { onRemovedOnlyChange(!state.removedOnly) },
                    label = { Text("已移出") },
                )
            }

            val note = importState.error?.let { "导入失败：$it" } ?: importState.message
            if (note != null) {
                Text(
                    text = note,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = if (importState.error != null) {
                        MaterialTheme.colorScheme.error
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
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
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            if (state.removedOnly) "没有已移出的书" else "还没有书",
                            style = MaterialTheme.typography.titleMedium,
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            when {
                                state.removedOnly -> "移出书架的书会保留在这里，阅读进度和离线译文都不会丢。"
                                state.query.isNotBlank() || state.favoritesOnly || state.shelf != null ->
                                    "没有匹配的书；清除搜索或筛选后再试。"
                                else -> "导入备份，或去发现找一本日文轻小说。"
                            },
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Spacer(Modifier.height(16.dp))
                        if (state.query.isNotBlank() || state.favoritesOnly || state.removedOnly || state.shelf != null) {
                            Button(onClick = {
                                onQueryChange("")
                                onFavoritesOnlyChange(false)
                                onRemovedOnlyChange(false)
                                onShelfChange(null)
                            }) {
                                Text("清除筛选")
                            }
                        } else {
                            Button(onClick = onImport) { Text("导入备份") }
                            Spacer(Modifier.height(8.dp))
                            TextButton(onClick = onImportDocument) { Text("导入 TXT / EPUB") }
                            TextButton(onClick = onDiscover) { Text("去发现") }
                        }
                    }
                }

                else -> LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(state.books, key = { it.book.id }) { item ->
                        BookRow(
                            item = item,
                            onClick = { onOpenBook(item.book.id) },
                            onRemove = {
                                val id = item.book.id
                                val title = item.book.titleZh ?: item.book.title
                                onRemoveBook(id)
                                scope.launch {
                                    val result = snackbarHostState.showSnackbar(
                                        message = "已移出《$title》，阅读进度已保留",
                                        actionLabel = "撤销",
                                    )
                                    if (result == SnackbarResult.ActionPerformed) {
                                        onRestoreBook(id)
                                    }
                                }
                            },
                            onRestore = { onRestoreBook(item.book.id) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ContinueCard(
    item: BookWithState,
    onClick: () -> Unit,
) {
    Card(
        modifier = Modifier
            .width(230.dp)
            .clickable(onClick = onClick),
    ) {
        Row(
            modifier = Modifier.padding(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BookCover(
                title = item.book.titleZh ?: item.book.title,
                modifier = Modifier.size(width = 46.dp, height = 62.dp),
                size = BookCoverSize.COMPACT,
            )
            Spacer(Modifier.width(10.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = item.book.titleZh ?: item.book.title,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text = "第 ${item.state?.progressIdx ?: 1} 话",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}

@Composable
private fun BookRow(
    item: BookWithState,
    onClick: () -> Unit,
    onRemove: () -> Unit,
    onRestore: () -> Unit,
) {
    val removed = item.state?.hidden == true
    var menuOpen by remember { mutableStateOf(false) }
    var confirmRemove by remember { mutableStateOf(false) }
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
    ) {
        Row(
            modifier = Modifier.padding(start = 12.dp, top = 12.dp, bottom = 12.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BookCover(
                title = item.book.titleZh ?: item.book.title,
                modifier = Modifier.size(width = 52.dp, height = 72.dp),
                size = BookCoverSize.TINY,
            )
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = item.book.titleZh ?: item.book.title,
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text = listOfNotNull(
                        item.book.author,
                        if (removed) "已移出" else shelfLabel(item.state?.shelf),
                        item.state?.progressIdx?.takeIf { it > 0 }?.let { "读到第 $it 话" },
                    ).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                val progress = item.state?.progressIdx ?: 0
                if (progress > 0 && item.book.episodes > 0) {
                    Spacer(Modifier.height(5.dp))
                    LinearProgressIndicator(
                        progress = { (progress.toFloat() / item.book.episodes).coerceIn(0f, 1f) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
            Box {
                TextButton(
                    onClick = { menuOpen = true },
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp),
                ) {
                    Text("⋮", style = MaterialTheme.typography.titleLarge)
                }
                DropdownMenu(
                    expanded = menuOpen,
                    onDismissRequest = { menuOpen = false },
                ) {
                    DropdownMenuItem(
                        text = { Text(if (removed) "移回书架" else "移出书架") },
                        onClick = {
                            menuOpen = false
                            if (removed) onRestore() else confirmRemove = true
                        },
                    )
                }
            }
        }
    }
    if (confirmRemove) {
        AlertDialog(
            onDismissRequest = { confirmRemove = false },
            title = { Text("移出《${item.book.titleZh ?: item.book.title}》？") },
            text = { Text("只移出书架，离线正文、译文、世界线和阅读进度都会保留，之后可在「已移出」移回。") },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmRemove = false
                        onRemove()
                    },
                ) {
                    Text("移出")
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmRemove = false }) { Text("取消") }
            },
        )
    }
}

private fun shelfLabel(shelf: String?): String? = when (shelf) {
    "want" -> "想读"
    "reading" -> "在读"
    "finished" -> "读完"
    "dropped" -> "弃文"
    else -> null
}
