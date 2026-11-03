package com.kacyraho.lightnovel.feature.worldline

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.repository.LibraryRepository
import com.kacyraho.lightnovel.data.worldline.Intervention
import com.kacyraho.lightnovel.data.worldline.WorldlineFile
import com.kacyraho.lightnovel.data.worldline.WorldlineService
import com.kacyraho.lightnovel.data.worldline.WorldlineStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class WorldlineUiState(
    val loading: Boolean = true,
    val book: BookEntity? = null,
    val branches: List<WorldlineFile> = emptyList(),
    val selected: WorldlineFile? = null,
    val busy: Boolean = false,
    val message: String? = null,
    val error: String? = null,
    val titleInput: String = "",
    val forkChapterInput: String = "1",
    val modeInput: String = "exploration",
    val characterInput: String = "",
    val actionInput: String = "",
    val constraintInput: String = "",
)

class WorldlineViewModel(
    private val repository: LibraryRepository,
    private val worldlineStore: WorldlineStore,
    private val worldlineService: WorldlineService,
    private val bookId: String,
) : ViewModel() {
    private val _state = MutableStateFlow(WorldlineUiState())
    val state: StateFlow<WorldlineUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch { load() }
    }

    fun setTitle(value: String) {
        _state.value = _state.value.copy(titleInput = value)
    }

    fun setForkChapter(value: String) {
        _state.value = _state.value.copy(forkChapterInput = value)
    }

    fun setMode(value: String) {
        _state.value = _state.value.copy(
            modeInput = if (value == "comparison") "comparison" else "exploration",
        )
    }

    fun setCharacter(value: String) {
        _state.value = _state.value.copy(characterInput = value)
    }

    fun setAction(value: String) {
        _state.value = _state.value.copy(actionInput = value)
    }

    fun setConstraint(value: String) {
        _state.value = _state.value.copy(constraintInput = value)
    }

    fun select(id: String) {
        val branch = _state.value.branches.firstOrNull { it.id == id } ?: return
        _state.value = _state.value.copy(selected = branch, message = null, error = null)
    }

    fun backToList() {
        _state.value = _state.value.copy(selected = null)
    }

    fun create() {
        val book = _state.value.book ?: return
        val current = _state.value
        val forkChapter = current.forkChapterInput.toIntOrNull() ?: 1
        val intervention = Intervention(
            character = current.characterInput.trim(),
            action = current.actionInput.trim(),
            constraint = current.constraintInput.trim(),
        )
        if (intervention.character.isBlank() || intervention.action.isBlank()) {
            _state.value = current.copy(error = "角色和行动不能为空")
            return
        }
        if (forkChapter < 1 || (book.episodes > 0 && forkChapter > book.episodes)) {
            _state.value = current.copy(error = "分叉章超出范围：本书共 ${book.episodes} 章")
            return
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(
                busy = true,
                message = "正在生成分支第一章…",
                error = null,
            )
            worldlineService.createBranch(
                book = book,
                title = current.titleInput,
                forkChapter = forkChapter.coerceAtLeast(1),
                forkParagraph = 0,
                intervention = intervention,
                mode = current.modeInput,
            ).onSuccess {
                reload(selectedId = it.id)
                _state.value = _state.value.copy(
                    busy = false,
                    message = "分支已创建",
                    titleInput = "",
                    characterInput = "",
                    actionInput = "",
                    constraintInput = "",
                )
            }.onFailure {
                _state.value = _state.value.copy(
                    busy = false,
                    error = it.message ?: "生成失败",
                )
            }
        }
    }

    fun continueBranch() {
        val book = _state.value.book ?: return
        val selected = _state.value.selected ?: return
        if (_state.value.busy) return
        viewModelScope.launch {
            _state.value = _state.value.copy(
                busy = true,
                message = "正在续写第 ${selected.chapters.size + 1} 章…",
                error = null,
            )
            worldlineService.continueBranch(book, selected.id)
                .onSuccess {
                    reload(selectedId = it.id)
                    _state.value = _state.value.copy(
                        busy = false,
                        message = "已续写第 ${it.branchCursor} 章",
                    )
                }
                .onFailure {
                    _state.value = _state.value.copy(
                        busy = false,
                        error = it.message ?: "续写失败",
                    )
                }
        }
    }

    fun delete(id: String) {
        val book = _state.value.book ?: return
        viewModelScope.launch {
            val ok = worldlineStore.delete(book.storageDir, id)
            reload()
            _state.value = _state.value.copy(
                message = if (ok) "分支已删除" else "分支不存在",
            )
        }
    }

    fun refresh() {
        viewModelScope.launch { reload() }
    }

    fun consumeMessage() {
        _state.value = _state.value.copy(message = null, error = null)
    }

    private suspend fun load() {
        val book = repository.book(bookId)
        if (book == null) {
            _state.value = _state.value.copy(loading = false, error = "书不存在")
            return
        }
        val readState = repository.readState(bookId)
        _state.value = _state.value.copy(
            loading = false,
            book = book,
            forkChapterInput = (readState?.progressIdx ?: 1).coerceAtLeast(1).toString(),
        )
        reload()
    }

    private suspend fun reload(selectedId: String? = _state.value.selected?.id) {
        val book = _state.value.book ?: return
        val branches = worldlineStore.list(book.storageDir)
        _state.value = _state.value.copy(
            branches = branches,
            selected = selectedId?.let { id -> branches.firstOrNull { it.id == id } },
        )
    }
}
