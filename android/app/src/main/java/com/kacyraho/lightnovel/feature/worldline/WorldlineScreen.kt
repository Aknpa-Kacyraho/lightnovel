package com.kacyraho.lightnovel.feature.worldline

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
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
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kacyraho.lightnovel.AppContainer
import com.kacyraho.lightnovel.data.worldline.BranchChapter
import com.kacyraho.lightnovel.data.worldline.WorldlineFile
import com.kacyraho.lightnovel.data.worldline.WorldlineGeneration
import com.kacyraho.lightnovel.ui.components.BrandFilterChip

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

    LaunchedEffect(state.message, state.error, state.busy) {
        val text = state.error ?: state.message?.takeIf { !state.busy } ?: return@LaunchedEffect
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
        onLengthChange = viewModel::setLength,
        onCreativityChange = viewModel::setCreativity,
        onDirectiveChange = viewModel::setDirective,
        onContinueCountChange = viewModel::setContinueCount,
        onCreate = viewModel::create,
        onSelect = viewModel::select,
        onBackToList = viewModel::backToList,
        onContinue = viewModel::continueBranch,
        onRegenerate = viewModel::regenerateLastChapter,
        onDelete = viewModel::delete,
        onRefresh = viewModel::refresh,
        onCancel = viewModel::cancelOperation,
    )
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
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
    onLengthChange: (String) -> Unit,
    onCreativityChange: (String) -> Unit,
    onDirectiveChange: (String) -> Unit,
    onContinueCountChange: (Int) -> Unit,
    onCreate: () -> Unit,
    onSelect: (String) -> Unit,
    onBackToList: () -> Unit,
    onContinue: () -> Unit,
    onRegenerate: () -> Unit,
    onDelete: (String) -> Unit,
    onRefresh: () -> Unit,
    onCancel: () -> Unit,
) {
    var deleteId by remember { mutableStateOf<String?>(null) }
    var confirmRegenerate by remember { mutableStateOf(false) }
    var lastSelectedId by remember { mutableStateOf<String?>(null) }
    var lastCursor by remember { mutableIntStateOf(0) }
    val scrollState = rememberScrollState()
    LaunchedEffect(state.selected?.id, state.selected?.branchCursor) {
        val selected = state.selected
        if (selected == null) {
            lastSelectedId = null
            lastCursor = 0
            scrollState.scrollTo(0)
            return@LaunchedEffect
        }
        if (lastSelectedId == selected.id && selected.branchCursor > lastCursor) {
            kotlinx.coroutines.delay(120)
            scrollState.animateScrollTo(scrollState.maxValue)
        } else if (lastSelectedId != selected.id) {
            scrollState.scrollTo(0)
        }
        lastSelectedId = selected.id
        lastCursor = selected.branchCursor
    }
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
                    if (state.busy) {
                        TextButton(onClick = onCancel) { Text("取消生成") }
                    } else {
                        TextButton(onClick = onRefresh) { Text("刷新") }
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
        modifier = Modifier.testTag("worldline-screen"),
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (state.busy) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                state.message?.let { message ->
                    Text(
                        message,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                    )
                }
            }
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .imePadding()
                    .verticalScroll(scrollState)
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
                    onLengthChange = onLengthChange,
                    onCreativityChange = onCreativityChange,
                    onDirectiveChange = onDirectiveChange,
                    onCreate = onCreate,
                )
                HorizontalDivider()
                Text("已有分支", style = MaterialTheme.typography.titleMedium)
                if (state.branches.isEmpty()) {
                    Text(
                        "还没有分支。填好角色和行动，或从阅读器里选中一段正文开始改写。",
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
                    state = state,
                    onLengthChange = onLengthChange,
                    onCreativityChange = onCreativityChange,
                    onDirectiveChange = onDirectiveChange,
                    onContinueCountChange = onContinueCountChange,
                    onContinue = onContinue,
                    onRegenerate = { confirmRegenerate = true },
                    onDelete = { deleteId = state.selected?.id },
                )
            }
        }
        }
    }

    deleteId?.let { id ->
        AlertDialog(
            onDismissRequest = { deleteId = null },
            title = { Text("删除这个分支？") },
            text = { Text("只删除这条世界线，不影响原书、译文和书架。") },
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

    if (confirmRegenerate && state.selected != null) {
        val number = state.selected.chapters.lastOrNull()?.index ?: 1
        AlertDialog(
            onDismissRequest = { confirmRegenerate = false },
            title = { Text("重写第 $number 章？") },
            text = { Text("会删除当前最后一章及其分支知识，再按现在的设置重新生成；前面的章节不变。") },
            confirmButton = {
                TextButton(onClick = {
                    confirmRegenerate = false
                    onRegenerate()
                }) { Text("重写") }
            },
            dismissButton = {
                TextButton(onClick = { confirmRegenerate = false }) { Text("取消") }
            },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun CreateForm(
    state: WorldlineUiState,
    onTitleChange: (String) -> Unit,
    onForkChapterChange: (String) -> Unit,
    onModeChange: (String) -> Unit,
    onCharacterChange: (String) -> Unit,
    onActionChange: (String) -> Unit,
    onConstraintChange: (String) -> Unit,
    onLengthChange: (String) -> Unit,
    onCreativityChange: (String) -> Unit,
    onDirectiveChange: (String) -> Unit,
    onCreate: () -> Unit,
) {
    Text("新建分支", style = MaterialTheme.typography.titleLarge)
    Text(
        "从指定章节分叉，写一条属于你的世界线。长度、创作强度和作者备注会保存在分支里。",
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
    Text("模式", style = MaterialTheme.typography.labelLarge)
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
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
        if (state.modeInput == "comparison") "对照型：同时生成 canon 差异报告" else "探索型：只写分支",
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
    WorldlineSettingsCard(
        lengthMode = state.lengthInput,
        creativity = state.creativityInput,
        directive = state.directiveInput,
        continueCount = state.continueCount,
        showContinueCount = false,
        busy = state.busy,
        onLengthChange = onLengthChange,
        onCreativityChange = onCreativityChange,
        onDirectiveChange = onDirectiveChange,
        onContinueCountChange = {},
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

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun WorldlineSettingsCard(
    lengthMode: String,
    creativity: String,
    directive: String,
    continueCount: Int,
    showContinueCount: Boolean,
    busy: Boolean,
    onLengthChange: (String) -> Unit,
    onCreativityChange: (String) -> Unit,
    onDirectiveChange: (String) -> Unit,
    onContinueCountChange: (Int) -> Unit,
) {
    val length = WorldlineGeneration.length(lengthMode)
    val style = WorldlineGeneration.creativity(creativity)
    Card(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Text("续写设置", style = MaterialTheme.typography.titleSmall)
                Spacer(Modifier.weight(1f))
                Text(
                    length.rangeLabel,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text("每章长度", style = MaterialTheme.typography.labelMedium)
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                WorldlineGeneration.lengthOptions.forEach { option ->
                    BrandFilterChip(
                        selected = option.id == length.id,
                        onClick = { if (!busy) onLengthChange(option.id) },
                        label = { Text(option.label) },
                    )
                }
            }
            Text("创作强度", style = MaterialTheme.typography.labelMedium)
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                WorldlineGeneration.creativityOptions.forEach { option ->
                    BrandFilterChip(
                        selected = option.id == style.id,
                        onClick = { if (!busy) onCreativityChange(option.id) },
                        label = { Text(option.label) },
                    )
                }
            }
            Text(
                style.hint,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedTextField(
                value = directive,
                onValueChange = onDirectiveChange,
                label = { Text("作者备注（长期生效）") },
                placeholder = {
                    Text("例如：保持林晚视角；不要急着揭秘；每章结尾留钩子。")
                },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2,
                maxLines = 5,
                enabled = !busy,
                supportingText = { Text("${directive.length}/2000") },
            )
            Text(
                "设置会在下一次续写或重写时保存。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (showContinueCount) {
                Text("连续续写", style = MaterialTheme.typography.labelMedium)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(1, 3, 5).forEach { count ->
                        BrandFilterChip(
                            selected = continueCount == count,
                            onClick = { if (!busy) onContinueCountChange(count) },
                            label = { Text("$count 章") },
                        )
                    }
                }
            }
        }
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
                "分叉：第 ${branch.forkChapter} 章 · 已写 ${branch.branchCursor} 章 · " +
                    "${WorldlineGeneration.length(branch.lengthMode).label} / " +
                    WorldlineGeneration.creativity(branch.creativity).label,
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

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BranchDetail(
    branch: WorldlineFile,
    state: WorldlineUiState,
    onLengthChange: (String) -> Unit,
    onCreativityChange: (String) -> Unit,
    onDirectiveChange: (String) -> Unit,
    onContinueCountChange: (Int) -> Unit,
    onContinue: () -> Unit,
    onRegenerate: () -> Unit,
    onDelete: () -> Unit,
) {
    Text(branch.title, style = MaterialTheme.typography.titleLarge)
    Text(
        "分叉：第 ${branch.forkChapter} 章 · 已写 ${branch.branchCursor} 章 · " +
            "${branch.chapters.sumOf { it.text.length }} 字",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Text(
        "资料：${if (branch.knowledgeStatus == "ready") "已抽取" else "未抽取"} · " +
            "已覆盖到第 ${branch.branchExtractedThrough} 章",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Text(
        "介入：${branch.intervention.character} · ${branch.intervention.action}",
        style = MaterialTheme.typography.bodyMedium,
    )
    if (branch.intervention.constraint.isNotBlank()) {
        Text(
            "约束：${branch.intervention.constraint}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
    WorldlineSettingsCard(
        lengthMode = state.lengthInput,
        creativity = state.creativityInput,
        directive = state.directiveInput,
        continueCount = state.continueCount,
        showContinueCount = true,
        busy = state.busy,
        onLengthChange = onLengthChange,
        onCreativityChange = onCreativityChange,
        onDirectiveChange = onDirectiveChange,
        onContinueCountChange = onContinueCountChange,
    )
    Button(
        onClick = onContinue,
        enabled = !state.busy,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            if (state.busy) {
                "生成中…"
            } else if (state.continueCount == 1) {
                "续写下一章"
            } else {
                "连续续写 ${state.continueCount} 章"
            },
        )
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(
            onClick = onRegenerate,
            enabled = !state.busy && branch.chapters.isNotEmpty(),
            modifier = Modifier.weight(1f),
        ) {
            Text("重写本章")
        }
        OutlinedButton(
            onClick = onDelete,
            enabled = !state.busy,
            modifier = Modifier.weight(1f),
        ) {
            Text("删除分支")
        }
    }
    if (branch.divergences.isNotEmpty()) {
        HorizontalDivider()
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
        HorizontalDivider()
        Text("差异报告（对照型）", style = MaterialTheme.typography.titleSmall)
        Text(
            "给原著读者的参照，不会反向透露给角色。",
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
                        "  原著参照：$it",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
    HorizontalDivider()
    Text("正文", style = MaterialTheme.typography.titleSmall)
    branch.chapters.forEach { chapter ->
        ChapterBlock(chapter)
    }
}

@Composable
private fun ChapterBlock(chapter: BranchChapter) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                "第 ${chapter.index} 章 · ${chapter.title}",
                style = MaterialTheme.typography.titleSmall,
            )
            SelectionContainer {
                Text(chapter.text, style = MaterialTheme.typography.bodyMedium)
            }
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
