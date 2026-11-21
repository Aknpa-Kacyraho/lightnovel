# Round 25 · 工程师视角升级指南（v1.8.3）

> 基线：1.8.2 / versionCode 61；308 JVM tests。
> 本轮修三个「状态范围不对」的问题：批量重试取错集合、旧翻译请求改加载状态、
> 世界线保存失败不回滚知识。

## 1. 工程问题与方案

### E1. `retryAllFailed` 取当前筛选的 groups（P2）

现状：

```kotlin
fun retryAllFailed() {
    viewModelScope.launch {
        val tasks = state.value.groups
            .flatMap { it.tasks }
            .filter { it.status == "failed" || it.status == "partial" }
        ...
    }
}
```

`state.groups` 来自 `TaskGrouping.group(visible, selected)`，已经按当前筛选
裁剪。切到 `TRANSLATING` 时 groups 里没有 failed/partial，批量重试为空。

**方案**：从 DAO 取当前全部任务，抽纯函数过滤：

```kotlin
internal fun retryableRows(
    tasks: List<ChapterTaskRow>,
    ignoredKeys: Set<String>,
): List<ChapterTaskRow> = tasks.filter {
    (it.status == "failed" || it.status == "partial") &&
        "${it.bookId}/${it.idx}" !in ignoredKeys
}

fun retryAllFailed() {
    viewModelScope.launch {
        val tasks = retryableRows(
            dao.observeActiveTasks().first(),
            ignored.value,
        )
        ...
    }
}
```

- `observeActiveTasks()` 已按 hidden 过滤、limit 300；
- `ignored` 仍生效；
- 当前筛选只影响列表，不影响批量动作。

**测试**：`TaskCenterRetryTest` 覆盖：
- failed + partial 选中，translating/complete 不选；
- ignored 的 key 被排除；
- 结果与传入的筛选无关（纯函数本身无 filter 参数）。

### E2. 旧翻译请求修改 `metadataLoading`（P2）

`DiscoverViewModel.translateCards` 现状：

```kotlin
if (token != null && token != searchToken) {
    _state.value = _state.value.copy(metadataLoading = false) // ← 旧请求也关
    ...
    return@launch
}
```

快速搜索 A→B 时，A 的翻译请求返回会提前关闭 B 的加载指示。

另外 `clearSearch()` 只取消 `searchJob`，不递增 `searchToken`；
进行中的 `translateCards` 返回时 token 仍匹配，会把结果写回已清空的列表。

**方案**：

1. 旧 token 分支不再修改 `metadataLoading`，只把翻译结果写入 catalog 缓存。
2. `clearSearch()` 增加 `searchToken++`，让进行中的翻译请求失效。

```kotlin
if (token != null && token != searchToken) {
    if (!translated.isNullOrEmpty()) {
        runCatching { catalog?.remember(translated) }
    }
    return@launch
}
```

**验证**：代码审查 + 自检说明（ViewModel 依赖多，暂无稳定 JVM 测试）。

### E3. 世界线保存失败不回滚知识（P2）

`regenerateLastChapter` 先删旧知识，再生成；`generateChapter` 失败时恢复旧知识，
但最后的 `worldlineStore.save` 失败时没有恢复。

**方案**：

```kotlin
return try {
    Result.success(worldlineStore.save(book.storageDir, updated))
} catch (error: CancellationException) {
    oldKnowledge?.let { worldlineStore.saveKnowledge(book.storageDir, it) }
    throw error
} catch (error: Exception) {
    oldKnowledge?.let { worldlineStore.saveKnowledge(book.storageDir, it) }
    Result.failure(error)
}
```

- 取消也恢复，保持与 `generateChapter` 的取消路径一致；
- 恢复失败用 `runCatching` 包住，避免覆盖原始错误。

**验证**：代码审查 + 自检说明（需要真实 store + 模型，JVM 测试成本高）。

### E4. 版本与文档

- `versionCode = 62`，`versionName = "1.8.3"`。
- 更新 `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。

## 2. 实施顺序

1. `retryableRows` + 测试；`retryAllFailed` 接入。
2. `translateCards` / `clearSearch` token 修复。
3. `regenerateLastChapter` 保存失败恢复。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 311，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 62。

## 4. 风险

- `retryAllFailed` 现在重试全部失败任务（上限 300），用户确认框里的数字
  与此一致；不再受筛选影响。
- `clearSearch` 递增 token 后，清空搜索期间返回的翻译结果只进 catalog 缓存，
  不再写 UI；下次搜索会命中缓存。
- 世界线恢复知识是覆盖写；如果恢复本身失败，保留原始错误并提示。
