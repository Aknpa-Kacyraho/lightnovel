# Round 17 · 工程师视角升级指南（v1.6.1）

> 基线：1.6.0 / versionCode 53。本轮修并发与跨章定位，不改数据结构。
> 竞态修复优先「取消旧请求」，跨章跳转用一次性内存锚点。

## 1. 工程问题与方案

### E1. `load()` 没有取消机制（P1）

`ReaderViewModel.load()` 每次 `viewModelScope.launch`，快速切换 displayMode 会并发。

**方案**：

```kotlin
private var loadJob: Job? = null

private fun load() {
    loadJob?.cancel()
    loadJob = viewModelScope.launch {
        withContext(Dispatchers.IO) { ... }
        ensureActive()
        _state.value = _state.value.copy(...)
    }
}
```

- `withContext(IO)` 返回后调用 `ensureActive()`，取消的旧请求不会写状态；
- `loadJob` 只保存最新一个；
- 不改变 `load()` 的调用点。

**测试**：并发竞态无稳定 JVM 测试；自检说明。

### E2. 跨章跳转（P1）

新增一次性锚点存储（`AppContainer`）：

```kotlin
class PendingReaderJump {
    private val anchors = mutableMapOf<String, ReaderAnchor>()
    fun put(bookId: String, anchor: ReaderAnchor) { anchors[bookId] = anchor }
    fun take(bookId: String): ReaderAnchor? = anchors.remove(bookId)
    fun clear(bookId: String) { anchors.remove(bookId) }
}
```

- `ReaderRoute` 的 `onJumpBookmark` / `onJumpSearchHit`：
  - 同章 → `viewModel.jumpToAnchor(anchor)`；
  - 跨章 → `container.pendingReaderJump.put(bookId, anchor)` + `onOpenChapter(idx)`。
- 新章的 `ReaderRoute`：

```kotlin
LaunchedEffect(state.loading, state.error) {
    if (!state.loading && state.error == null) {
        container.pendingReaderJump.take(bookId)?.let { anchor ->
            viewModel.jumpToAnchor(anchor)
        }
    }
}
```

- 先 take 再 jump，避免循环；
- `jumpToAnchor` 会写进度 + `load()`，定位后清除；
- 加载失败不 take，锚点留在内存（下次进入同书仍可用）；退出应用丢失，可接受。

**测试**：`PendingReaderJumpTest`（put/take/覆盖/clear）。

### E3. 提示替换（P2）

```kotlin
LaunchedEffect(Unit) {
    viewModel.bookmarkNotice.collectLatest { message ->
        bookmarkNotice = message
        delay(1_500)
        bookmarkNotice = null
    }
}
```

`collectLatest` 会取消上一条的 delay。

### E4. 版本与文档

- `versionCode = 54`，`versionName = "1.6.1"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. `loadJob` + `ensureActive`。
2. `PendingReaderJump` + 测试 + Route 接线。
3. `collectLatest` 提示。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥264，0 failures；lint 0 errors，warning ≤22；APK versionCode 54。

## 4. 风险

- `jumpToAnchor` 在目标章加载后再次 `load()`，会短暂多一次分页；可接受。
- pending 锚点只存在内存，进程被杀后丢失（跳转本身也失败）。
- `collectLatest` 在提示显示期间取消旧协程，不会泄漏。
