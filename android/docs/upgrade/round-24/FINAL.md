# Round 24 · 统一升级指南（v1.8.2）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：滚动模式的锚点只认滚动位置；模式切换走双向映射；备份要记住导入哈希。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 滚动书签/切语言跳回旧页 | **采纳，P1** | `currentAnchor()` 滚动优先 |
| U2 + D2 + E2 | 跨模式位置跳错 | **采纳，P1** | `setReaderMode` 双向换算 |
| U3 + D3 + E3 | 恢复备份后本地导入重复 | **采纳，P2** | `import_hash` 进入备份链路 |

## 2. 实施清单

### 2.1 滚动锚点（P1）

- [ ] `currentAnchor()` 在 `readerMode == "scroll"` 时直接返回
      `ReaderAnchor(chapterIndex, currentParagraphIndex(), 0)`。
- [ ] 翻页模式保持 layout 优先，回退 `scrollParagraph`。

### 2.2 模式切换（P1）

- [ ] `setReaderMode("page")` 用 `currentParagraphIndex()` 写锚点。
- [ ] `setReaderMode("scroll")` 用 `lineForParagraph(...)` 写 `scrollParagraph`。
- [ ] 现有 `ReaderScrollMappingTest` 覆盖往返；自检说明 UI 路径。

### 2.3 导入哈希（P2）

- [ ] `CatalogItem.importHash` + `CatalogAdapter.normalize` 读取。
- [ ] `PlannedBook.importHash` + `ImportPlanner` 传入。
- [ ] `mergeBook` 新书使用备份哈希；已有书保留。
- [ ] `BackupExporter.libraryJson` 写 `import_hash`。
- [ ] `CatalogAdapterTest` / `ImportMergeTest` 覆盖。

### 2.4 版本与文档

- [ ] `versionCode = 61`，`versionName = "1.8.2"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不重写分页/滚动渲染、不改书签/搜索 UI。
- 不改本地导入哈希算法与大小限制。
- 不改备份格式版本（只加可选字段）。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥307 tests，0 failures；新增导入哈希用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 61 |
| 用户 | 滚动书签不跳页；跨模式同一段；恢复后去重有效 |
| 发布 | 提交 + tag `v1.8.2` + 推送 |

## 5. 回滚

改动集中在 `ReaderViewModel.kt`、`CatalogModels.kt`、`CatalogAdapter.kt`、
`ImportPlanner.kt`、`ImportMerge.kt`、`BackupExporter.kt` + 测试；
无 DB 迁移。`git revert` 单提交即可。
