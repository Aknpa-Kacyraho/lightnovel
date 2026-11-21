# Round 24 · 三视角自检（v1.8.2）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。无真机（`adb` 不可用）。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **308 tests / 0 failures / 0 errors / 1 skipped**（+1） |
| lint | **0 errors / 22 warnings**（无新增） |
| Debug 构建 | 成功，versionCode 61 / 1.8.2 |
| 数据 | 无 DB schema 变化；备份格式只加可选 `import_hash` |

## 用户视角

**已改善**

1. 滚动模式下加书签、切换原文/译文，不再跳回切滚动前的页。
2. 滚动→翻页→滚动，位置落在同一段，不再跳到末页或错误行。
3. 备份恢复后，再导入同一个本地 TXT/EPUB 会提示「已在书架」。

**仍然存在**

- bilingual 模式下源/译行数不同，行↔段映射仍是近似。
- 旧备份没有 `import_hash`，恢复的本地书仍可能重复导入一次。
- 逐段重译后整章仍提示过期（Round 23 的有意行为）。

## 设计师视角

**一致**

- 没有新增/删除控件、文案或 loading。
- 书签预览、阅读位置、模式切换的视觉行为与用户预期一致。
- 导入重复提示复用现有「已在书架，没有重复添加」。

**取舍**

- 没有为「位置已保持」加提示：这是应有行为。
- 没有在备份详情里展示 `import_hash`：这是内部去重字段。

## 工程师视角

**做对了**

- `currentAnchor()` 在滚动模式直接返回行→段映射，翻页模式才读 layout；
  书签、切语言、翻译锚点共用同一入口。
- `setReaderMode` 两个方向分别用 `currentParagraphIndex()` 与
  `lineForParagraph()`，与 Round 16 的映射函数一致。
- `importHash` 从 `CatalogItem` → `PlannedBook` → `mergeBook` → `BookEntity`
  全链路打通；已有书为空时用备份补，非空时保留。
- `BackupExporter` 只写非空哈希，旧备份兼容。
- 新增 2 条哈希测试；现有 `ReaderScrollMappingTest` 覆盖行/段往返。

**风险与限制**

- `currentAnchor()` 在滚动模式不再读 `layout`，但 `layout` 仍保留在 state 中；
  切回翻页时会重新分页，布局缓存不影响正确性。
- `CatalogAdapter` 的 `rawJson` 包含 `import_hash`，旧代码导出时会保留该字段；
  不影响解析。
- `mergeBook` 的 `importHash = existing.importHash ?: planned.importHash`
  意味着旧书第一次导入带哈希的备份时会获得哈希；之后不再变化。

**未验证**

- 真机上滚动/翻页切换的实际落点与滚动位置。
- 恢复备份后再次导入同一文件的完整 UI 路径。
- 旧备份（无 `import_hash`）恢复后的重复导入行为。

## 结论

Round 24 目标达成，可作为 1.8.2 发布。下一轮做全量审计：
若只剩设计权衡与 P3，则停止发版并给出收敛说明。
