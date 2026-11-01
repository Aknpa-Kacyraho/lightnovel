package com.kacyraho.lightnovel.feature.tasks

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kacyraho.lightnovel.data.local.ChapterTaskRow
import com.kacyraho.lightnovel.data.local.LibraryDao
import com.kacyraho.lightnovel.core.settings.TaskIgnoreStore
import com.kacyraho.lightnovel.data.translation.TranslationService
import com.kacyraho.lightnovel.data.translation.TranslationTaskRegistry
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.stateIn

enum class TaskFilter(val label: String) {
    ALL("全部"),
    FAILED("失败"),
    PARTIAL("未译全"),
    TRANSLATING("进行中"),
}

data class TaskGroup(
    val bookId: String,
    val title: String,
    val tasks: List<ChapterTaskRow>,
)

data class TaskCenterUiState(
    val groups: List<TaskGroup> = emptyList(),
    val filter: TaskFilter = TaskFilter.ALL,
    val total: Int = 0,
    val failed: Int = 0,
    val partial: Int = 0,
    val translating: Int = 0,
)

class TaskCenterViewModel(
    private val dao: LibraryDao,
    private val translationService: TranslationService,
    private val taskRegistry: TranslationTaskRegistry,
    private val ignoreStore: TaskIgnoreStore? = null,
) : ViewModel() {
    private val filter = MutableStateFlow(TaskFilter.ALL)
    private val ignored = MutableStateFlow(ignoreStore?.load().orEmpty())

    val state: StateFlow<TaskCenterUiState> = combine(
        dao.observeActiveTasks(),
        filter,
        ignored,
    ) { tasks, selected, ignoredKeys ->
        val visible = tasks.filterNot { "${it.bookId}/${it.idx}" in ignoredKeys }
        TaskCenterUiState(
            groups = TaskGrouping.group(visible, selected),
            filter = selected,
            total = visible.size,
            failed = visible.count { it.status == "failed" },
            partial = visible.count { it.status == "partial" },
            translating = visible.count { it.status == "translating" },
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = TaskCenterUiState(),
    )

    fun setFilter(value: TaskFilter) {
        filter.value = value
    }

    fun ignore(task: ChapterTaskRow) {
        ignored.value = ignoreStore?.ignore(task.bookId, task.idx)
            ?: (ignored.value + "${task.bookId}/${task.idx}")
    }

    fun unignore(task: ChapterTaskRow) {
        ignored.value = ignoreStore?.clear(task.bookId, task.idx)
            ?: (ignored.value - "${task.bookId}/${task.idx}")
    }

    fun cancel(task: ChapterTaskRow) {
        viewModelScope.launch {
            taskRegistry.cancel(task.bookId, task.idx)
            val book = dao.book(task.bookId) ?: return@launch
            translationService.markCancelled(book, task.idx)
        }
    }
}

object TaskGrouping {
    fun group(tasks: List<ChapterTaskRow>, filter: TaskFilter): List<TaskGroup> {
        val visible = when (filter) {
            TaskFilter.ALL -> tasks
            TaskFilter.FAILED -> tasks.filter { it.status == "failed" }
            TaskFilter.PARTIAL -> tasks.filter { it.status == "partial" }
            TaskFilter.TRANSLATING -> tasks.filter { it.status == "translating" }
        }
        return visible
            .groupBy { it.bookId }
            .map { (bookId, rows) ->
                TaskGroup(
                    bookId = bookId,
                    title = rows.first().bookTitleZh ?: rows.first().bookTitle,
                    tasks = rows.sortedBy { it.idx },
                )
            }
            .sortedByDescending { it.tasks.maxOfOrNull { task -> task.updatedAt.orEmpty() } }
    }
}
