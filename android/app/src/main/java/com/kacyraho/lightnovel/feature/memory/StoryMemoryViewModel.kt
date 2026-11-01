package com.kacyraho.lightnovel.feature.memory

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kacyraho.lightnovel.data.glossary.GlossaryEntry
import com.kacyraho.lightnovel.data.glossary.GlossaryStore
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.local.ChapterEntity
import com.kacyraho.lightnovel.data.repository.LibraryRepository
import com.kacyraho.lightnovel.data.story.CharacterCard
import com.kacyraho.lightnovel.data.story.NameSuggestion
import com.kacyraho.lightnovel.data.story.StoryMemory
import com.kacyraho.lightnovel.data.story.StoryMemoryService
import com.kacyraho.lightnovel.data.story.StoryMemoryStore
import com.kacyraho.lightnovel.data.story.StoryStyle
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

data class StoryMemoryUiState(
    val loading: Boolean = true,
    val book: BookEntity? = null,
    val memory: StoryMemory = StoryMemory(),
    val chapters: List<ChapterEntity> = emptyList(),
    val legacyGlossaryCount: Int = 0,
    val busy: Boolean = false,
    val message: String? = null,
    val error: String? = null,
    val suggestions: List<NameSuggestion> = emptyList(),
)

class StoryMemoryViewModel(
    private val repository: LibraryRepository,
    private val storyStore: StoryMemoryStore,
    private val storyService: StoryMemoryService,
    private val legacyGlossaryStore: GlossaryStore? = null,
    private val bookId: String,
) : ViewModel() {
    private val _state = MutableStateFlow(StoryMemoryUiState())
    val state: StateFlow<StoryMemoryUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch { load() }
    }

    fun refresh() {
        viewModelScope.launch { load() }
    }

    private suspend fun load() {
        val book = repository.book(bookId)
        if (book == null) {
            _state.value = _state.value.copy(loading = false, error = "书不存在")
            return
        }
        val chapters = repository.observeChapters(bookId).first()
        val memory = storyStore.load(book.storageDir, book.id, book.title)
        val legacy = legacyGlossaryStore?.load()?.entries.orEmpty()
        _state.value = _state.value.copy(
            loading = false,
            book = book,
            chapters = chapters,
            memory = memory,
            legacyGlossaryCount = legacy.size,
            error = null,
        )
    }

    fun saveGlossary(source: String, target: String, aliases: List<String>) {
        val book = _state.value.book ?: return
        if (source.isBlank() || target.isBlank()) return
        val entry = GlossaryEntry(
            id = source.trim(),
            source = source.trim(),
            target = target.trim(),
            aliases = aliases.map(String::trim).filter(String::isNotBlank),
        )
        persist(
            _state.value.memory.copy(
                glossary = _state.value.memory.glossary
                    .filterNot { it.id == entry.id || it.source == entry.source } + entry,
            ),
        )
    }

    fun deleteGlossary(id: String) {
        persist(
            _state.value.memory.copy(
                glossary = _state.value.memory.glossary.filterNot { it.id == id },
            ),
        )
    }

    fun saveCharacter(card: CharacterCard) {
        if (card.source.isBlank() || card.target.isBlank()) return
        val clean = card.copy(
            id = card.id.ifBlank { card.source.trim() },
            source = card.source.trim(),
            target = card.target.trim(),
        )
        val current = _state.value.memory.characters
        val updated = current.filterNot {
            it.id == clean.id || it.source == clean.source
        } + clean
        persist(_state.value.memory.copy(characters = updated))
    }

    fun deleteCharacter(id: String) {
        persist(
            _state.value.memory.copy(
                characters = _state.value.memory.characters.filterNot { it.id == id },
            ),
        )
    }

    fun saveStyle(style: StoryStyle) {
        persist(_state.value.memory.copy(style = style))
    }

    fun addLesson(text: String) {
        if (text.isBlank()) return
        persist(
            _state.value.memory.copy(
                lessons = (_state.value.memory.lessons + text.trim()).distinct(),
            ),
        )
    }

    fun deleteLesson(text: String) {
        persist(
            _state.value.memory.copy(
                lessons = _state.value.memory.lessons.filterNot { it == text },
            ),
        )
    }

    fun importLegacyGlossary() {
        val book = _state.value.book ?: return
        val legacy = legacyGlossaryStore?.load() ?: return
        if (legacy.entries.isEmpty()) {
            _state.value = _state.value.copy(error = "旧全局术语表是空的")
            return
        }
        val saved = storyStore.importLegacy(book.storageDir, book.id, book.title, legacy)
        _state.value = _state.value.copy(
            memory = saved,
            message = "已导入 ${legacy.entries.size} 条旧术语（仅本书）",
            error = null,
        )
    }

    fun scanCharacters() {
        val book = _state.value.book ?: return
        if (_state.value.busy) return
        viewModelScope.launch {
            _state.value = _state.value.copy(
                busy = true,
                message = "正在扫描人物…",
                error = null,
            )
            val found = runCatching {
                storyService.extractCharacters(book, _state.value.chapters)
            }.getOrElse {
                _state.value = _state.value.copy(
                    busy = false,
                    error = it.message ?: "扫描人物失败",
                )
                return@launch
            }
            val memory = storyStore.load(book.storageDir, book.id, book.title)
            _state.value = _state.value.copy(
                busy = false,
                memory = memory,
                message = if (found.isEmpty()) "没有发现新人物" else "已更新 ${found.size} 个人物",
            )
        }
    }

    fun scanNames() {
        val book = _state.value.book ?: return
        if (_state.value.busy) return
        viewModelScope.launch {
            _state.value = _state.value.copy(
                busy = true,
                message = "正在检查译名…",
                error = null,
                suggestions = emptyList(),
            )
            val found = runCatching {
                storyService.scanNames(book, _state.value.chapters)
            }.getOrElse {
                _state.value = _state.value.copy(
                    busy = false,
                    error = it.message ?: "检查译名失败",
                )
                return@launch
            }
            _state.value = _state.value.copy(
                busy = false,
                suggestions = found,
                message = if (found.isEmpty()) "没有发现明显不一致" else "发现 ${found.size} 组候选",
            )
        }
    }

    fun applySuggestions() {
        val book = _state.value.book ?: return
        if (_state.value.suggestions.isEmpty()) return
        val memory = storyService.applySuggestions(book, _state.value.suggestions)
        _state.value = _state.value.copy(
            memory = memory,
            suggestions = emptyList(),
            message = "已写入术语表/人物卡；相关译文会标记为过期",
        )
    }

    fun regenerateSummary(index: Int) {
        val book = _state.value.book ?: return
        if (_state.value.busy) return
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true, message = "正在生成第 $index 话梗概…")
            val summary = runCatching {
                storyService.generateSummary(book, index, force = true)
            }.getOrNull()
            val memory = storyStore.load(book.storageDir, book.id, book.title)
            _state.value = _state.value.copy(
                busy = false,
                memory = memory,
                message = if (summary == null) "梗概生成失败" else "第 $index 话梗概已更新",
                error = if (summary == null) "模型没有返回可用梗概" else null,
            )
        }
    }

    fun consumeMessage() {
        _state.value = _state.value.copy(message = null, error = null)
    }

    private fun persist(memory: StoryMemory) {
        val book = _state.value.book ?: return
        val saved = storyStore.save(book.storageDir, memory)
        _state.value = _state.value.copy(memory = saved, message = "已保存", error = null)
    }
}
