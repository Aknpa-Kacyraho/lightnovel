# Round 30 · 工程师视角升级指南（v1.9.3）

> 基线：1.9.2 / versionCode 66；316 JVM tests。
> 本批只修失败路径与状态一致性，不新增功能、不改视觉。

## 1. 问题与方案

### E1. 导入备份覆盖本机阅读进度（P1）

`BackupImportService.apply` 对每本书都调用 `plannedState`：

```kotlin
updatedAt = state?.updatedAt
    ?: state?.openedAt
    ?: state?.finishedAt
    ?: book.addedAt
    ?: Instant.now().toString(),
```

当备份没有 `data/books/<id>.json` 且 library 条目没有 `added_at` 时，
`updatedAt` 被合成成「现在」，`mergeReadState` 判定备份更新，
把本机 `progressIdx` 覆盖为 0。

**修复**：

```kotlin
val states = plan.report.books.map { book ->
    val imported = importedStates[book.id]
    if (imported == null) {
        // 备份没有状态文件：不触碰本机状态；新书才建默认状态。
        existingStates[book.id] ?: defaultState(book)
    } else {
        mergeReadState(existingStates[book.id], plannedState(book, imported))
    }
}
```

- `plannedState` 的 `updatedAt` 去掉 `Instant.now()` 兜底，保留
  `state?.updatedAt ?: state?.openedAt ?: state?.finishedAt ?: book.addedAt`。
- `defaultState(book)` 仅用于新书：`progress = 0`，`updatedAt = book.addedAt ?: now`。
- 现有 `mergeReadState` 的「备份更新才覆盖」规则不变。

**测试**：新增 `ImportCoordinatorTest.importWithoutReadStateKeepsLocalProgress`：
构造一个没有 `data/books/*.json`、library 条目没有 `added_at` 的备份，
首次导入后手动把进度改到 5/10，再次导入，断言进度仍是 5/10。

### E2. 导出失败留下半成品（P2）

`SettingsViewModel.exportBackup` 与 `ChapterListViewModel.exportEpub` 都用
`runCatching { resolver.openOutputStream(uri)?.use { ... } }`：

- `runCatching` 吞掉 `CancellationException`；
- 失败时已创建的 SAF 文档不会被删除。

**修复**：改为 `try/catch`，失败与取消都
`runCatching { resolver.delete(uri, null, null) }`，取消再重抛。
只处理 `CreateDocument` 新建的 URI，不碰用户已有文件。

### E3. 外部取消后阅读器状态卡住（P2）

`ReaderViewModel.translateChapter` / `polishChapter` 的 job 只处理
`Complete/Partial/Failed`，没有取消出口。任务中心取消后
`_translationState.running` 仍为 true。

**修复**：job 外层加：

```kotlin
try {
    // 现有 when(outcome)
} catch (error: CancellationException) {
    if (_translationState.value.running) {
        _translationState.value = ReaderTranslationState(message = "已取消翻译")
    }
    throw error
}
```

手动 `cancelTranslation` 已先置 `running=false`，不会被覆盖。

### E4. EPUB 识别与 spine 兼容（P2）

- `LocalDocumentImporter.isEpub` 只看扩展名；`.txt` 的 EPUB 会被当文本解码。
  改为扩展名或 ZIP 文件头（`PK`）任一命中即走 `parseEpub`。
- `LocalTextParser.parseEpub` 的 itemref 正则只接受双引号：

```kotlin
Regex("""<itemref\b[^>]*\bidref\s*=\s*"([^"]+)"""")
```

改为 `["']([^"']+)["']`，单双引号都接受。

**测试**：`LocalTextParserTest` 增加单引号 spine 的 EPUB；
`LocalDocumentImporter` 的文件头判定抽成 internal 纯函数并测试。

### E5. 下载 worker 吞取消（P2）

`BookDownloadWorker` 用 `runCatching` 包 `ensureChapter`（suspend）。
worker 被停止时取消被吞，循环继续并可能把结果记成 failed。

**修复**：改用 `core/util/Cancellation.kt` 的 `runCatchingCancellable`，
让取消穿透到 WorkManager。

### E6. 队列把外部任务算作已完成（P2）

`ReadingTranslationCoordinator.translateTarget`：

```kotlin
if (taskRegistry.isRunning(book.id, index)) return TargetResult(true)
```

外部任务还在跑就把本章计为 COMPLETED。改为
`TargetResult(success = false, skipped = true)`，不计完成、不重试。

### E7. 取消与重试的注册竞态（P2）

`TranslationTaskRegistry.cancel` 先把 job 从 map 移除再取消；
此时 `register` 可以接受新 job，而旧 job 仍在 `NonCancellable` 中写状态。

**修复**：

- `cancel` / `cancelBook` 不再立即 `jobs.remove`，只 `job.cancel()`；
- `invokeOnCompletion` 负责移除；
- `register` 只接受 `previous == null` 的 key（旧 job 完全结束后才允许新任务）。

**测试**：`TranslationTaskRegistryTest` 增加
「取消后旧 job 未完成时 register 被拒绝」。

### E8. 其余挂起调用的取消语义（P2）

上一轮只改了模型/网络层。以下位置仍用 `runCatching` 包 suspend：

- `ReaderViewModel.load()` 包 `onlineBookService.ensureChapter`；
- `ReadingTranslationCoordinator.translateTarget` 包 `chapterFetcher.ensureChapter`；
- `LibraryViewModel.importDocument` / `import` 包本地导入；
- `SettingsViewModel.save` 包 `settingsStore.update`。

统一改 `runCatchingCancellable` 或显式重抛 `CancellationException`，
避免取消被当成普通失败并在已取消的协程里继续写 UI 状态。

### E9. 坏 sidecar 让润色崩溃（P0）

`FileContentStore.readSidecar` 直接 `decodeFromString`，旧备份缺字段时抛
`SerializationException`；`polishChapter` 的调用没有兜底，异常进入
`appScope`，无 `CoroutineExceptionHandler` 时崩溃进程。

**修复**：`readSidecar` 解码失败返回 null；`polishChapter` 再用
`runCatching` 包一层，返回 `Failed("缺少章节翻译信息，无法安全写回")`。

### E10. 书签进入备份（P1）

- 新增 `BackupBookmark`（`bookId/chapterIdx/paragraphId/charOffset/preview/createdAt`）。
- `BackupExporter` 写 `data/bookmarks.json`；DAO 增加 `allBookmarks()` 与
  `upsertBookmarks(List)`。
- `BackupImportService` 解析可选文件，只补本机缺失的
  `(bookId, chapterIdx, paragraphId)`，过滤已不存在的书。
- `ImportApplyResult` 增加 `bookmarks`，导入完成消息显示数量。

### E11. 没有目录的书也要恢复（P1）

`ImportPlanner.plan` 把 `missingDirs`（含 `want`）转成 `PlannedBook`：
`storageDir = id`、`flags = missing_dir`，`episodes` 来自 library。
`LibraryCommitter` 对 `missing_dir` 且没有 staging 目录的书跳过文件提交，
数据库仍写入书与阅读状态，章节后续按需下载。

### E12. 合并复制改为原子写（P1）

`mergeDirectory` 的 `Files.copy` 直接写目标，中断会留下截断文件且重试跳过。
改为写 `<name>.part` 后 `ATOMIC_MOVE`；失败删除临时文件。仍保持
「现有文件优先，只补缺失」，不按大小覆盖用户本地文件。

### E13. 未译全章节不再被短路（P1）

`translateTarget` 原来只要 `readZh != null` 就返回完成。改为读取 sidecar：
`hasFinalTranslation(status) = status != "partial"`，`partial` 继续翻译。

### E14. 滚动行号映射与真实列表一致（P1）

`chapterBlocks` 原来用 `text.split("\n")`，与 `Paragraphs.split` 的段模型
不一致。改为 `readerScrollBlocks(blocks, text)`：按段展开，段间插入一个空串，
`ScrollReader` 对空串渲染零高度 `Spacer`。`lineForParagraph` /
`paragraphIndexForLine` 的 `+1` 假设从此成立；`ReaderScrollMappingTest`
增加单换行文本用例。

## 2. 实施顺序

1. 导入进度保护 + 回归测试。
2. 导出失败清理 + 取消透传。
3. 阅读器取消状态 + registry 竞态。
4. EPUB 识别/spine + 下载取消 + 队列统计。
5. 版本、文档、全量验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 320，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 67。

## 4. 风险

- 导入状态修复只影响「备份无状态文件」的路径；有状态文件的正常恢复不变。
- 导出删除只针对 `CreateDocument` 新建 URI；部分 provider 不支持 delete 时静默失败。
- registry 严格注册会让「取消后立刻重试」短暂提示已有任务，属预期。
- EPUB 文件头判定会把 ZIP 误判为 EPUB，解析失败会明确报错而不是乱码。
