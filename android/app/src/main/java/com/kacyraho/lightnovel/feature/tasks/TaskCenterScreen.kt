package com.kacyraho.lightnovel.feature.tasks

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kacyraho.lightnovel.AppContainer
import com.kacyraho.lightnovel.data.local.ChapterTaskRow
import com.kacyraho.lightnovel.ui.components.BrandFilterChip
import com.kacyraho.lightnovel.ui.components.StatusBadge
import com.kacyraho.lightnovel.ui.components.StatusTone

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskCenterRoute(
    container: AppContainer,
    onOpenChapter: (String, Int) -> Unit,
) {
    val viewModel: TaskCenterViewModel = viewModel {
        TaskCenterViewModel(
            dao = container.database.libraryDao(),
            translationService = container.translationService,
            taskRegistry = container.translationTaskRegistry,
            ignoreStore = container.taskIgnoreStore,
            coordinator = container.readingTranslationCoordinator,
        )
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    var showRetryAll by remember { mutableStateOf(false) }

    if (showRetryAll) {
        AlertDialog(
            onDismissRequest = { showRetryAll = false },
            title = { Text("重试未完成任务") },
            text = {
                Text(
                    "将重试 ${state.failed + state.partial} 个失败或未译全章节，" +
                        "会消耗 API 额度。",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showRetryAll = false
                        viewModel.retryAllFailed()
                    },
                ) {
                    Text("开始重试")
                }
            },
            dismissButton = {
                TextButton(onClick = { showRetryAll = false }) { Text("取消") }
            },
        )
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text("翻译任务") }) },
        modifier = Modifier.testTag("task-center-screen"),
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = if (state.total == 0) {
                        if (state.queues.isNotEmpty()) "后台预译正在运行" else "没有待处理的翻译任务"
                    } else {
                        "共 ${state.total} 项 · 失败 ${state.failed} · " +
                            "未译全 ${state.partial} · 进行中 ${state.translating}"
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f),
                )
                if (state.failed + state.partial > 0) {
                    TextButton(onClick = { showRetryAll = true }) {
                        Text(if (state.failed > 0) "重试全部失败" else "重试未完成")
                    }
                }
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                TaskFilter.entries.forEach { filter ->
                    BrandFilterChip(
                        selected = state.filter == filter,
                        onClick = { viewModel.setFilter(filter) },
                        label = { Text(filter.label) },
                    )
                }
            }
            when {
                state.total == 0 -> Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            if (state.queues.isNotEmpty()) "预译队列正在运行" else "翻译队列是空的",
                            style = MaterialTheme.typography.titleMedium,
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            if (state.queues.isNotEmpty()) {
                                "正在准备还没开始翻译的章节，开始后会出现在这里。"
                            } else {
                                "在阅读器里翻译章节后，失败、未完成或进行中的任务会出现在这里。"
                            },
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }

                state.groups.isEmpty() -> Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "当前筛选没有任务",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }

                else -> LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(state.groups, key = { "group-" + it.bookId }) { group ->
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(
                                text = "${group.title} · ${group.tasks.size} 项",
                                style = MaterialTheme.typography.titleSmall,
                                color = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.padding(horizontal = 2.dp),
                            )
                            state.queues[group.bookId]?.let { queue ->
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Text(
                                        buildString {
                                            if (queue.paused) append("队列已暂停")
                                            else append("队列进行中")
                                            queue.runningIndex?.let { append(" · 第 $it 话") }
                                            if (queue.completed > 0) append(" · 已完成 ${queue.completed}")
                                            if (queue.remaining > 0) append(" · 剩余 ${queue.remaining}")
                                        },
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.secondary,
                                        modifier = Modifier.weight(1f),
                                    )
                                    TextButton(onClick = { viewModel.stopBook(group.bookId) }) {
                                        Text("停止本书")
                                    }
                                }
                            }
                            group.tasks.forEach { task ->
                                TaskCard(
                                    task = task,
                                    onOpen = { onOpenChapter(task.bookId, task.idx) },
                                    onRetry = {
                                        viewModel.unignore(task)
                                        viewModel.retry(task)
                                    },
                                    onCancel = { viewModel.cancel(task) },
                                    onIgnore = { viewModel.ignore(task) },
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TaskCard(
    task: ChapterTaskRow,
    onOpen: () -> Unit,
    onRetry: () -> Unit,
    onCancel: () -> Unit,
    onIgnore: () -> Unit,
) {
    val canRetry = task.status == "failed" || task.status == "partial"
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(start = 12.dp, top = 12.dp, end = 12.dp, bottom = 4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    val rawTitle = task.chapterTitleZh ?: task.chapterTitle.orEmpty()
                    val title = rawTitle.replaceFirst(
                        Regex("^第\\s*${task.idx}\\s*[话話]\\s*"),
                        "",
                    ).ifBlank { rawTitle }
                    Text(
                        text = "第 ${task.idx} 话" + if (title.isNotBlank()) " · $title" else "",
                        style = MaterialTheme.typography.titleSmall,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = when (task.status) {
                            "translating" -> "正在翻译"
                            "partial" -> "未译全，可重试"
                            "failed" -> "翻译失败，可重试"
                            else -> task.status.orEmpty()
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Spacer(Modifier.width(8.dp))
                StatusBadge(
                    text = statusLabel(task.status),
                    tone = statusTone(task.status),
                )
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
            ) {
                TextButton(onClick = onOpen) { Text("查看") }
                if (canRetry) {
                    TextButton(onClick = onRetry) { Text("重试") }
                }
                if (task.status == "translating") {
                    TextButton(onClick = onCancel) { Text("取消") }
                }
                if (canRetry) {
                    TextButton(onClick = onIgnore) { Text("忽略") }
                }
            }
        }
    }
}

private fun statusLabel(status: String?): String = when (status) {
    "translating" -> "进行中"
    "partial" -> "未译全"
    "failed" -> "失败"
    else -> status.orEmpty()
}

private fun statusTone(status: String?): StatusTone = when (status) {
    "failed" -> StatusTone.ERROR
    "partial" -> StatusTone.WARNING
    "translating" -> StatusTone.INFO
    else -> StatusTone.NEUTRAL
}
