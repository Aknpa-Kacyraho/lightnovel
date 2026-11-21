# Round 24 · 工程师视角升级指南（v1.8.2）

> 基线：1.8.1 / versionCode 60；307 JVM tests。
> 本轮修两个阅读器锚点坐标 bug，并把本地导入哈希写进备份。

## 1. 工程问题与方案

### E1. `currentAnchor()` 优先旧 layout（P1）

现状：

```kotlin
private fun currentAnchor(): ReaderAnchor? =
    _state.value.layout?.pages?.getOrNull(_state.value.pageIndex)?.startAnchor
        ?: if (_state.value.readerMode == "scroll") {
            ReaderAnchor(chapterIndex, _state.value.scrollParagraph, 0)
        } else null
```

从翻页切到滚动后，`layout` 不清；`currentAnchor()` 仍返回旧页的
`startAnchor`。`addBookmark()`、`setDisplayMode()`、`translateChapter()`
都以它为锚点，导致滚动模式下的书签/切语言/翻译位置回到旧页。

**方案**：

```kotlin
private fun currentAnchor(): ReaderAnchor? {
    val state = _state.value
    if (state.readerMode == "scroll") {
        return ReaderAnchor(chapterIndex, currentParagraphIndex(), 0)
    }
    return state.layout?.pages?.getOrNull(state.pageIndex)?.startAnchor
        ?: ReaderAnchor(chapterIndex, state.scrollParagraph, 0)
}
```

- 滚动模式优先，路径唯一；
- 翻页模式保持原逻辑；
- `currentParagraphIndex()` 已做行→段映射。

### E2. `setReaderMode` 两个方向都混用坐标（P1）

现状：

```kotlin
if (mode == "page") {
    anchorToRestore = ReaderAnchor(chapterIndex, _state.value.scrollParagraph, 0)
} else {
    val pageAnchor = currentAnchor()
    _state.value = _state.value.copy(scrollParagraph = pageAnchor.paragraphId)
}
```

- `scrollParagraph` 是行号，被当成 `paragraphId`（段号）写进锚点；
- `pageAnchor.paragraphId` 是段号，被直接塞进 `scrollParagraph`（行号）。

**方案**：

```kotlin
if (mode == "page") {
    anchorToRestore = ReaderAnchor(chapterIndex, currentParagraphIndex(), 0)
    lastKey = null
} else {
    val pageAnchor = currentAnchor()
    if (pageAnchor != null) {
        _state.value = _state.value.copy(
            scrollParagraph = lineForParagraph(
                _state.value.paragraphs,
                _state.value.displayMode,
                pageAnchor.paragraphId,
            ),
        )
    }
}
```

`setReaderMode` 时 `readerMode` 尚未切换，`currentParagraphIndex()` 看到的是
旧模式，行→段/页锚点都正确。

### E3. 备份缺少 `import_hash`（P2）

`BackupExporter.libraryJson` 不写本地导入哈希；`BackupImportService` 构造
`BookEntity` 时也不带。恢复后 `bookByImportHash` 查不到，再导入同一文件
会生成新书。

**方案**：

1. `CatalogItem` 新增 `importHash: String? = null`；
   `CatalogAdapter.normalize` 读 `row.string("import_hash")`。
2. `BackupExporter.libraryJson` 写 `book.importHash`（非空时）。
3. `PlannedBook` 新增 `importHash: String? = null`；
   `ImportPlanner.plan` 从 `CatalogItem` 带入。
4. `mergeBook` 新书使用 `planned.importHash`；已存在书保留现有
   （`existing.copy` 不修改该字段）。
5. 旧备份没有字段 → null，保持兼容。

**测试**：
- `CatalogAdapterTest`：带 `import_hash` 的 item 解析后非空；不带时为 null。
- `ImportMergeTest`：新书带回备份哈希；已存在书保留现有哈希。

### E4. 版本与文档

- `versionCode = 61`，`versionName = "1.8.2"`。
- 更新 `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。

## 2. 实施顺序

1. `currentAnchor()` + `setReaderMode` 坐标修复。
2. `CatalogItem` / `ImportPlanner` / `mergeBook` / `BackupExporter` 的哈希链路。
3. 测试、版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 307，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 61。

## 4. 风险

- `currentAnchor()` 在滚动模式不再读 `layout`，如果 `paragraphs` 与
  `chapterBlocks` 不一致（bilingual 行数差异），位置仍是近似；
  这是既有映射的已知限制。
- `setReaderMode` 的 `lineForParagraph` 依赖 `state.paragraphs`；
  切换模式前 paragraphs 已由 `load()` 构建，正常。
- 旧备份恢复的本地书没有 `import_hash`，仍可能重复导入一次；
  重新导入后新生成的哈希只对新书有效。
