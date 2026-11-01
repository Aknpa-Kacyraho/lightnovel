package com.kacyraho.lightnovel.feature.memory

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.kacyraho.lightnovel.AppContainer
import com.kacyraho.lightnovel.data.story.CharacterCard
import com.kacyraho.lightnovel.data.story.NameSuggestion
import com.kacyraho.lightnovel.data.story.StoryStyle

private const val TAB_TERMS = 0
private const val TAB_CHARACTERS = 1
private const val TAB_STYLE = 2
private const val TAB_SUMMARIES = 3

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StoryMemoryRoute(
    container: AppContainer,
    bookId: String,
    onBack: () -> Unit,
) {
    val viewModel: StoryMemoryViewModel = viewModel(key = "memory-$bookId") {
        StoryMemoryViewModel(
            repository = container.libraryRepository,
            storyStore = container.storyMemoryStore,
            storyService = container.storyMemoryService,
            legacyGlossaryStore = container.glossaryStore,
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

    StoryMemoryScreen(
        state = state,
        snackbarHostState = snackbarHostState,
        onBack = onBack,
        onSaveGlossary = viewModel::saveGlossary,
        onDeleteGlossary = viewModel::deleteGlossary,
        onSaveCharacter = viewModel::saveCharacter,
        onDeleteCharacter = viewModel::deleteCharacter,
        onSaveStyle = viewModel::saveStyle,
        onAddLesson = viewModel::addLesson,
        onDeleteLesson = viewModel::deleteLesson,
        onImportLegacy = viewModel::importLegacyGlossary,
        onScanCharacters = viewModel::scanCharacters,
        onScanNames = viewModel::scanNames,
        onApplySuggestions = viewModel::applySuggestions,
        onRegenerateSummary = viewModel::regenerateSummary,
        onRefresh = viewModel::refresh,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StoryMemoryScreen(
    state: StoryMemoryUiState,
    snackbarHostState: SnackbarHostState,
    onBack: () -> Unit,
    onSaveGlossary: (String, String, List<String>) -> Unit,
    onDeleteGlossary: (String) -> Unit,
    onSaveCharacter: (CharacterCard) -> Unit,
    onDeleteCharacter: (String) -> Unit,
    onSaveStyle: (StoryStyle) -> Unit,
    onAddLesson: (String) -> Unit,
    onDeleteLesson: (String) -> Unit,
    onImportLegacy: () -> Unit,
    onScanCharacters: () -> Unit,
    onScanNames: () -> Unit,
    onApplySuggestions: () -> Unit,
    onRegenerateSummary: (Int) -> Unit,
    onRefresh: () -> Unit,
) {
    var tab by rememberSaveable { mutableStateOf(TAB_TERMS) }
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("本书设定")
                        Text(
                            state.book?.titleZh ?: state.book?.title ?: "加载中…",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
                navigationIcon = {
                    TextButton(onClick = onBack) { Text("返回") }
                },
                actions = {
                    TextButton(onClick = onRefresh, enabled = !state.busy) { Text("刷新") }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
        modifier = Modifier.testTag("story-memory-screen"),
    ) { padding ->
        if (state.loading) {
            Column(
                modifier = Modifier.fillMaxSize().padding(padding),
                verticalArrangement = Arrangement.Center,
            ) {
                CircularProgressIndicator(Modifier.padding(24.dp))
            }
            return@Scaffold
        }
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            TabRow(selectedTabIndex = tab) {
                listOf("术语", "人物", "风格", "前情").forEachIndexed { index, label ->
                    Tab(
                        selected = tab == index,
                        onClick = { tab = index },
                        text = { Text(label) },
                    )
                }
            }
            if (state.busy) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            }
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                when (tab) {
                    TAB_TERMS -> TermsTab(
                        state = state,
                        onSaveGlossary = onSaveGlossary,
                        onDeleteGlossary = onDeleteGlossary,
                        onImportLegacy = onImportLegacy,
                    )
                    TAB_CHARACTERS -> CharactersTab(
                        state = state,
                        onSaveCharacter = onSaveCharacter,
                        onDeleteCharacter = onDeleteCharacter,
                        onScanCharacters = onScanCharacters,
                    )
                    TAB_STYLE -> StyleTab(
                        state = state,
                        onSaveStyle = onSaveStyle,
                        onAddLesson = onAddLesson,
                        onDeleteLesson = onDeleteLesson,
                    )
                    else -> SummariesTab(
                        state = state,
                        onScanNames = onScanNames,
                        onApplySuggestions = onApplySuggestions,
                        onRegenerateSummary = onRegenerateSummary,
                    )
                }
            }
        }
    }
}

@Composable
private fun TermsTab(
    state: StoryMemoryUiState,
    onSaveGlossary: (String, String, List<String>) -> Unit,
    onDeleteGlossary: (String) -> Unit,
    onImportLegacy: () -> Unit,
) {
    var source by remember { mutableStateOf("") }
    var target by remember { mutableStateOf("") }
    var aliases by remember { mutableStateOf("") }
    Text(
        "只作用于本书；保存后相关章节会标记为过期，重译时强制使用这里的译名。",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    if (state.legacyGlossaryCount > 0) {
        OutlinedButton(onClick = onImportLegacy, enabled = !state.busy) {
            Text("从旧全局术语表导入（${state.legacyGlossaryCount} 条）")
        }
    }
    state.memory.glossary.forEach { entry ->
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("${entry.source} → ${entry.target}", modifier = Modifier.weight(1f))
            TextButton(onClick = { onDeleteGlossary(entry.id) }) { Text("删除") }
        }
    }
    if (state.memory.glossary.isNotEmpty()) HorizontalDivider()
    OutlinedTextField(
        value = source,
        onValueChange = { source = it },
        label = { Text("日文原文 / 术语") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
    )
    OutlinedTextField(
        value = target,
        onValueChange = { target = it },
        label = { Text("中文锁定译名") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
    )
    OutlinedTextField(
        value = aliases,
        onValueChange = { aliases = it },
        label = { Text("原文别名，用逗号分隔") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
    )
    Button(
        onClick = {
            onSaveGlossary(source, target, splitAliases(aliases))
            source = ""
            target = ""
            aliases = ""
        },
        enabled = source.isNotBlank() && target.isNotBlank(),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("保存术语")
    }
}

@Composable
private fun CharactersTab(
    state: StoryMemoryUiState,
    onSaveCharacter: (CharacterCard) -> Unit,
    onDeleteCharacter: (String) -> Unit,
    onScanCharacters: () -> Unit,
) {
    var source by remember { mutableStateOf("") }
    var target by remember { mutableStateOf("") }
    var aliases by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var voice by remember { mutableStateOf("") }
    var address by remember { mutableStateOf("") }
    var lexicon by remember { mutableStateOf("") }
    var syntax by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    Text(
        "人物卡只在本书生效；翻译时只注入本段实际登场的人。语气/称呼/词汇习惯越具体，角色越不容易同腔。",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    OutlinedButton(onClick = onScanCharacters, enabled = !state.busy) {
        Text("扫描人物")
    }
    state.memory.characters.forEach { card ->
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("${card.source} → ${card.target}")
                val detail = listOf(card.voice, card.address, card.notes)
                    .filter(String::isNotBlank)
                    .joinToString(" · ")
                if (detail.isNotBlank()) {
                    Text(
                        detail,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                TextButton(onClick = { onDeleteCharacter(card.id) }) { Text("删除") }
            }
        }
    }
    if (state.memory.characters.isNotEmpty()) HorizontalDivider()
    OutlinedTextField(source, { source = it }, label = { Text("日文名") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
    OutlinedTextField(target, { target = it }, label = { Text("中文名") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
    OutlinedTextField(aliases, { aliases = it }, label = { Text("别名/昵称，用逗号分隔") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
    OutlinedTextField(description, { description = it }, label = { Text("身份/设定") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(voice, { voice = it }, label = { Text("语气（冷淡/傲娇/敬语…）") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(address, { address = it }, label = { Text("称呼习惯") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(lexicon, { lexicon = it }, label = { Text("词汇习惯") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(syntax, { syntax = it }, label = { Text("句法习惯") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(notes, { notes = it }, label = { Text("注意事项") }, modifier = Modifier.fillMaxWidth())
    Button(
        onClick = {
            onSaveCharacter(
                CharacterCard(
                    id = source.trim(),
                    source = source,
                    target = target,
                    aliases = splitAliases(aliases),
                    description = description,
                    voice = voice,
                    address = address,
                    lexicon = lexicon,
                    syntax = syntax,
                    notes = notes,
                ),
            )
            source = ""
            target = ""
            aliases = ""
            description = ""
            voice = ""
            address = ""
            lexicon = ""
            syntax = ""
            notes = ""
        },
        enabled = source.isNotBlank() && target.isNotBlank(),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("保存人物")
    }
}

@Composable
private fun StyleTab(
    state: StoryMemoryUiState,
    onSaveStyle: (StoryStyle) -> Unit,
    onAddLesson: (String) -> Unit,
    onDeleteLesson: (String) -> Unit,
) {
    val style = state.memory.style
    var general by remember(style) { mutableStateOf(style.general) }
    var narrator by remember(style) { mutableStateOf(style.narrator) }
    var honorifics by remember(style) { mutableStateOf(style.honorifics) }
    var notes by remember(style) { mutableStateOf(style.notes) }
    var guide by remember(style) { mutableStateOf(style.guide) }
    var medium by remember(style) { mutableStateOf(style.medium) }
    var lesson by remember { mutableStateOf("") }
    Text(
        "这些设定会进入本书每次翻译的 prompt；不要写剧情剧透。",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    OutlinedTextField(general, { general = it }, label = { Text("全篇风格") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(narrator, { narrator = it }, label = { Text("叙述者滤镜") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(honorifics, { honorifics = it }, label = { Text("称谓处理") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(notes, { notes = it }, label = { Text("特别注意") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(guide, { guide = it }, label = { Text("本书补充翻译准则") }, modifier = Modifier.fillMaxWidth())
    OutlinedTextField(medium, { medium = it }, label = { Text("发布媒介（web/paper/ebook）") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
    Button(
        onClick = {
            onSaveStyle(
                StoryStyle(
                    general = general,
                    narrator = narrator,
                    honorifics = honorifics,
                    notes = notes,
                    guide = guide,
                    medium = medium,
                ),
            )
        },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("保存风格")
    }
    HorizontalDivider()
    Text("本书经验", style = MaterialTheme.typography.titleSmall)
    state.memory.lessons.forEach { text ->
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(text, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { onDeleteLesson(text) }) { Text("删除") }
        }
    }
    OutlinedTextField(
        value = lesson,
        onValueChange = { lesson = it },
        label = { Text("新增一条经验（只适用于本书）") },
        modifier = Modifier.fillMaxWidth(),
    )
    Button(
        onClick = {
            onAddLesson(lesson)
            lesson = ""
        },
        enabled = lesson.isNotBlank(),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text("添加经验")
    }
}

@Composable
private fun SummariesTab(
    state: StoryMemoryUiState,
    onScanNames: () -> Unit,
    onApplySuggestions: () -> Unit,
    onRegenerateSummary: (Int) -> Unit,
) {
    Text(
        "梗概在每章翻译完成后自动生成，用于下一章的前情注入；不参与译文过期判定。",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    OutlinedButton(onClick = onScanNames, enabled = !state.busy) {
        Text("检查译名一致性")
    }
    if (state.suggestions.isNotEmpty()) {
        Text("候选", style = MaterialTheme.typography.titleSmall)
        state.suggestions.forEach { suggestion ->
            SuggestionRow(suggestion)
        }
        Button(onClick = onApplySuggestions, modifier = Modifier.fillMaxWidth()) {
            Text("全部写入术语表/人物卡")
        }
        HorizontalDivider()
    }
    state.memory.summaries.values.sortedBy { it.index }.forEach { summary ->
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("第 ${summary.index} 话", style = MaterialTheme.typography.titleSmall)
                Text(summary.text, style = MaterialTheme.typography.bodySmall)
                TextButton(onClick = { onRegenerateSummary(summary.index) }) {
                    Text("重新生成")
                }
            }
        }
    }
}

@Composable
private fun SuggestionRow(suggestion: NameSuggestion) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(
            "${suggestion.source} → ${suggestion.suggested}",
            style = MaterialTheme.typography.bodyMedium,
        )
        if (suggestion.variants.isNotEmpty()) {
            Text(
                "当前写法：${suggestion.variants.joinToString(" / ")}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (suggestion.evidence.isNotBlank()) {
            Text(
                suggestion.evidence.take(160),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun splitAliases(value: String): List<String> =
    value.split(',', '，', '、').map(String::trim).filter(String::isNotBlank)
