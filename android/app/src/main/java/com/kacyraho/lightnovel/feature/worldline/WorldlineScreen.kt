package com.kacyraho.lightnovel.feature.worldline

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kacyraho.lightnovel.AppContainer
import com.kacyraho.lightnovel.ui.components.BrandFilterChip
import com.kacyraho.lightnovel.data.worldline.BranchChapter
import com.kacyraho.lightnovel.data.worldline.WorldlineFile

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WorldlineRoute(
    container: AppContainer,
    bookId: String,
    onBack: () -> Unit,
) {
    val viewModel: WorldlineViewModel = viewModel(key = "worldline-$bookId") {
        WorldlineViewModel(
            repository = container.libraryRepository,
            worldlineStore = container.worldlineStore,
            worldlineService = container.worldlineService,
            bookId = bookId,
        )
    }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(state.message, state.error) {
        val text = state.error ?: state.message ?: return@LaunchedEffect
        viewModel.consumeMessage()
        snackbarHostState.showSnackbar(text)
    }

    WorldlineScreen(
        state = state,
        snackbarHostState = snackbarHostState,
        onBack = onBack,
        onTitleChange = viewModel::setTitle,
        onForkChapterChange = viewModel::setForkChapter,
        onModeChange = viewModel::setMode,
        onCharacterChange = viewModel::setCharacter,
        onActionChange = viewModel::setAction,
        onConstraintChange = viewModel::setConstraint,
        onCreate = viewModel::create,
        onSelect = viewModel::select,
        onBackToList = viewModel::backToList,
        onContinue = viewModel::continueBranch,
        onDelete = viewModel::delete,
        onRefresh = viewModel::refresh,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WorldlineScreen(
    state: WorldlineUiState,
    snackbarHostState: SnackbarHostState,
    onBack: () -> Unit,
    onTitleChange: (String) -> Unit,
    onForkChapterChange: (String) -> Unit,
    onModeChange: (String) -> Unit,
    onCharacterChange: (String) -> Unit,
    onActionChange: (String) -> Unit,
    onConstraintChange: (String) -> Unit,
    onCreate: () -> Unit,
    onSelect: (String) -> Unit,
    onBackToList: () -> Unit,
    onContinue: () -> Unit,
    onDelete: (String) -> Unit,
    onRefresh: () -> Unit,
) {
    var deleteId by remember { mutableStateOf<String?>(null) }
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(if (state.selected == null) "世界线" else "世界线 · 分支")
                        Text(
                            state.book?.titleZh ?: state.book?.title ?: "",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
                navigationIcon = {
                    TextButton(onClick = if (state.selected == null) onBack else onBackToList) {
                        Text("返回")
                    }
                },
                actions = {
                    TextButton(onClick = onRefresh, enabled = !state.busy) { Text("刷新") }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
        modifier = Modifier.testTag("worldline-screen"),
    ) { padding ->
        if (state.busy) {
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth().padding(padding))
        }
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (state.selected == null) {
                CreateForm(
                    state = state,
                    onTitleChange = onTitleChange,
                    onForkChapterChange = onForkChapterChange,
                    onModeChange = onModeChange,
                    onCharacterChange = onCharacterChange,
                    onActionChange = onActionChange,
                    onConstraintChange = onConstraintChange,
                    onCreate = onCreate,
                )
                HorizontalDivider()
                Text("已有分支", style = MaterialTheme.typography.titleMedium)
                if (state.branches.isEmpty()) {
                    Text(
                        "还没有分支。输入一个角色行动，从当前进度开始改写。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                state.branches.forEach { branch ->
                    BranchCard(
                        branch = branch,
                        onSelect = { onSelect(branch.id) },
                        onDelete = { deleteId = branch.id },
                    )
                }
            } else {
                BranchDetail(
                    branch = state.selected,
                    busy = state.busy,
                    onContinue = onContinue,
                    onDelete = { deleteId = state.selected?.id },
                )
            }
        }
    }

    deleteId?.let { id ->
        AlertDialog(
            onDismissRequest = { deleteId = null },
            title = { Text("删除这条世界线？") },
            text = { Text("只删除分支，不影响原书和别的世界线。") },
            confirmButton = {
                TextButton(onClick = {
                    onDelete(id)
                    deleteId = null
                }) { Text("删除") }
            },
            dismissButton = {
                TextButton(onClick = { deleteId = null }) { Text("取消") }
            },
        )
    }
}

@Composable
private fun CreateForm(
    state: WorldlineUiState,
    onTitleChange: (String) -> Unit,
    onForkChapterChange: (String) -> Unit,
    onModeChange: (String) -> Unit,
    onCharacterChange: (String) -> Unit,
    onActionChange: (String) -> Unit,
    onConstraintChange: (String) -> Unit,
    onCreate: () -> Unit,
) {
    Text("新建分支", style = MaterialTheme.typography.titleMedium)
    Text(
        "推荐在阅读器里编辑正文生成；这里按角色行动分叉。",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    OutlinedTextField(
        value = state.titleInput,
        onValueChange = onTitleChange,
        label = { Text("分支标题（可空）") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
    )
    OutlinedTextField(
        value = state.forkChapterInput,
        onValueChange = onForkChapterChange,
        label = { Text("从第几章分叉") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
    )
    Text("模式", style = MaterialTheme.typography.titleSmall)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        BrandFilterChip(
            selected = state.modeInput == "exploration",
            onClick = { onModeChange("exploration") },
            label = { Text("探索型") },
        )
        BrandFilterChip(
            selected = state.modeInput == "comparison",
            onClick = { onModeChange("comparison") },
            label = { Text("对照型") },
        )
    }
    Text(
        if (state.modeInput == "comparison") {
            "对照型：额外生成差异报告"
        } else {
            "探索型：只写分支"
        },
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    OutlinedTextField(
        value = state.characterInput,
        onValueChange = onCharacterChange,
        label = { Text("角色") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
    )
    OutlinedTextField(
        value = state.actionInput,
        onValueChange = onActionChange,
        label = { Text("行动") },
        modifier = Modifier.fillMaxWidth(),
    )
    OutlinedTextField(
        value = state.constraintInput,
        onValueChange = onConstraintChange,
        label = { Text("约束（可选）") },
        modifier = Modifier.fillMaxWidth(),
    )
    Button(
        onClick = onCreate,
        enabled = !state.busy &&
            state.characterInput.isNotBlank() &&
            state.actionInput.isNotBlank(),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(if (state.busy) "生成中…" else "生成分支第一章")
    }
}

@Composable
private fun BranchCard(
    branch: WorldlineFile,
    onSelect: () -> Unit,
    onDelete: () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onSelect),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(branch.title, style = MaterialTheme.typography.titleSmall)
            Text(
                "分叉：第 ${branch.forkChapter} 章 · 已写 ${branch.branchCursor} 章",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                "${branch.intervention.character}：${branch.intervention.action}",
                style = MaterialTheme.typography.bodySmall,
            )
            Row(horizontalArrangement = Arrangement.End, modifier = Modifier.fillMaxWidth()) {
                TextButton(onClick = onDelete) { Text("删除") }
            }
        }
    }
}

@Composable
private fun BranchDetail(
    branch: WorldlineFile,
    busy: Boolean,
    onContinue: () -> Unit,
    onDelete: () -> Unit,
) {
    Text(branch.title, style = MaterialTheme.typography.titleLarge)
    Text(
        "分叉：第 ${branch.forkChapter} 章 · 已写 ${branch.branchCursor} 章",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Text(
        "资料：${if (branch.knowledgeStatus == "ready") "已抽取" else "待抽取"} · 到第 ${branch.branchExtractedThrough} 章",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Text(
        "介入：${branch.intervention.character} → ${branch.intervention.action}",
        style = MaterialTheme.typography.bodyMedium,
    )
    if (branch.intervention.constraint.isNotBlank()) {
        Text(
            "约束：${branch.intervention.constraint}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
    if (branch.divergences.isNotEmpty()) {
        Text("偏离点", style = MaterialTheme.typography.titleSmall)
        branch.divergences.forEach { divergence ->
            Text(
                "· ${divergence.summary}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
    if (branch.diffReports.isNotEmpty()) {
        Text("差异报告（对照型）", style = MaterialTheme.typography.titleSmall)
        Text(
            "含原作走向参照，可能剧透。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.tertiary,
        )
        branch.diffReports.forEach { report ->
            Text("第 ${report.chapter} 章", style = MaterialTheme.typography.labelMedium)
            report.items.forEach { item ->
                Text(
                    "· ${item.branchEvent}${if (item.impact.isBlank()) "" else "（${item.impact}）"}",
                    style = MaterialTheme.typography.bodySmall,
                )
                item.canonReference?.takeIf(String::isNotBlank)?.let {
                    Text(
                        "  原作参照：$it",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
    branch.chapters.forEach { chapter ->
        ChapterBlock(chapter)
    }
    Button(
        onClick = onContinue,
        enabled = !busy,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(if (busy) "生成中…" else "续写下一章")
    }
    OutlinedButton(
        onClick = onDelete,
        enabled = !busy,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("删除这条世界线")
    }
}

@Composable
private fun ChapterBlock(chapter: BranchChapter) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("第 ${chapter.index} 章 · ${chapter.title}", style = MaterialTheme.typography.titleSmall)
            Text(chapter.text, style = MaterialTheme.typography.bodyMedium)
            if (chapter.summary.isNotBlank()) {
                Text(
                    "梗概：${chapter.summary}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
