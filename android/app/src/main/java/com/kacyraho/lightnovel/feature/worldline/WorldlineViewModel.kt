package com.kacyraho.lightnovel.feature.worldline

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kacyraho.lightnovel.data.local.BookEntity
import com.kacyraho.lightnovel.data.repository.LibraryRepository
import com.kacyraho.lightnovel.data.worldline.Intervention
import com.kacyraho.lightnovel.data.worldline.WorldlineFile
import com.kacyraho.lightnovel.data.worldline.WorldlineGeneration
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
    val lengthInput: String = "standard",
    val creativityInput: String = "balanced",
    val directiveInput: String = "",
    val continueCount: Int = 1,
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

    fun setLength(value: String) {
        _state.value = _state.value.copy(
            lengthInput = WorldlineGeneration.normalizeLength(value),
        )
    }

    fun setCreativity(value: String) {
        _state.value = _state.value.copy(
            creativityInput = WorldlineGeneration.normalizeCreativity(value),
        )
    }

    fun setDirective(value: String) {
        _state.value = _state.value.copy(directiveInput = value.take(2_000))
    }

    fun setContinueCount(value: Int) {
        _state.value = _state.value.copy(continueCount = value.coerceIn(1, 5))
    }

    fun select(id: String) {
        val branch = _state.value.branches.firstOrNull { it.id == id } ?: return
        _state.value = _state.value.copy(
            selected = branch,
            lengthInput = WorldlineGeneration.normalizeLength(branch.lengthMode),
            creativityInput = WorldlineGeneration.normalizeCreativity(branch.creativity),
            directiveInput = branch.directive,
            continueCount = 1,
            message = null,
            error = null,
        )
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
                lengthMode = current.lengthInput,
                creativity = current.creativityInput,
                directive = current.directiveInput,
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
                    error = it.message?.take(240) ?: "生成失败",
                )
            }
        }
    }

    fun continueBranch() {
        val book = _state.value.book ?: return
        val selected = _state.value.selected ?: return
        val current = _state.value
        if (current.busy) return
        val count = current.continueCount.coerceIn(1, 5)
        viewModelScope.launch {
            _state.value = current.copy(
                busy = true,
                message = if (count == 1) {
                    "正在续写第 ${selected.chapters.size + 1} 章…"
                } else {
                    "正在续写 $count 章…"
                },
                error = null,
            )
            worldlineService.continueBranch(
                book = book,
                id = selected.id,
                count = count,
                lengthMode = current.lengthInput,
                creativity = current.creativityInput,
                directive = current.directiveInput,
                onProgress = { done, total ->
                    if (total > 1) {
                        _state.value = _state.value.copy(
                            message = if (done < total) {
                                "正在续写 ${done + 1}/$total 章…"
                            } else {
                                "续写完成，正在保存…"
                            },
                        )
                    }
                },
            ).onSuccess {
                reload(selectedId = it.id)
                _state.value = _state.value.copy(
                    busy = false,
                    message = "已续写到第 ${it.branchCursor} 章",
                )
            }.onFailure {
                reload(selectedId = selected.id)
                _state.value = _state.value.copy(
                    busy = false,
                    error = it.message?.take(240) ?: "续写失败",
                )
            }
        }
    }

    fun regenerateLastChapter() {
        val book = _state.value.book ?: return
        val selected = _state.value.selected ?: return
        val current = _state.value
        if (current.busy || selected.chapters.isEmpty()) return
        viewModelScope.launch {
            _state.value = current.copy(
                busy = true,
                message = "正在重写第 ${selected.chapters.last().index} 章…",
                error = null,
            )
            worldlineService.regenerateLastChapter(
                book = book,
                id = selected.id,
                lengthMode = current.lengthInput,
                creativity = current.creativityInput,
                directive = current.directiveInput,
            ).onSuccess {
                reload(selectedId = it.id)
                _state.value = _state.value.copy(
                    busy = false,
                    message = "已重写第 ${it.branchCursor} 章",
                )
            }.onFailure {
                reload(selectedId = selected.id)
                _state.value = _state.value.copy(
                    busy = false,
                    error = it.message?.take(240) ?: "重写失败",
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
