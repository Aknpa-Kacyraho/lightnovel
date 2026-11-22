# Round 30 · 统一升级指南（v1.9.3）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：先修「会丢数据」的，再修「会卡住」的，最后修「会留下坏文件」的。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 旧备份导入丢进度 | **采纳，P1** | 无状态文件不触碰本机状态 |
| U2 + D3 + E2 | 导出失败留坏文件 | **采纳，P2** | 失败/取消删除新建 URI |
| U3 + D2 + E3 | 外部取消后状态卡住 | **采纳，P2** | job 捕获取消并复位 |
| U4 + D4 + E4 | EPUB 识别弱 | **采纳，P2** | ZIP 头 + 单双引号 spine |
| — + — + E5 | 下载 worker 吞取消 | **采纳，P2** | `runCatchingCancellable` |
| — + — + E6 | 队列误计完成 | **采纳，P2** | 外部任务记为 skipped |
| — + — + E7 | 取消/重试竞态 | **采纳，P2** | 旧 job 结束前拒绝新注册 |
| — + — + E8 | 其余挂起调用吞取消 | **采纳，P2** | 统一 `runCatchingCancellable` |
| — + — + E9 | 坏 sidecar 让润色崩溃 | **采纳，P0** | 解码失败视为无翻译信息 |
| U5 + — + E10 | 书签不进入备份 | **采纳，P1** | `data/bookmarks.json` 去重补齐 |
| U6 + — + E11 | 未下载的书恢复后消失 | **采纳，P1** | 从 library 恢复书与状态 |
| — + — + E12 | 合并复制可能截断 | **采纳，P1** | `.part` + 原子移动 |
| U7 + — + E13 | 未译全重试被跳过 | **采纳，P1** | `partial` 继续翻译 |
| U9 + — + E14 | 滚动行号映射偏移 | **采纳，P1** | 段块生成 + 零高空行 |

## 2. 实施清单

### 2.1 导入进度（P1）

- [ ] `BackupImportService.apply`：`imported == null` 时保留 existing，新书用 `defaultState`。
- [ ] `plannedState` 去掉 `Instant.now()` 兜底。
- [ ] `ImportCoordinatorTest` 新增无 read_state 备份的重复导入回归。

### 2.2 导出清理（P2）

- [ ] `SettingsViewModel.exportBackup` 改 try/catch，失败/取消删除 URI，取消重抛。
- [ ] `ChapterListViewModel.exportEpub` 同上。
- [ ] 补 `CancellationException` import。

### 2.3 阅读器取消（P2）

- [ ] `translateChapter` job 捕获 `CancellationException`，running 时置「已取消翻译」。
- [ ] `polishChapter` 同上。

### 2.4 EPUB（P2）

- [ ] `LocalDocumentImporter` 按扩展名或 ZIP 头判定 EPUB。
- [ ] `LocalTextParser.parseEpub` spine 支持单双引号。
- [ ] `LocalTextParserTest` 增加单引号 spine 用例。

### 2.5 下载与队列（P2）

- [ ] `BookDownloadWorker` 改用 `runCatchingCancellable`。
- [ ] `ReadingTranslationCoordinator` 外部运行中任务返回 skipped。
- [ ] `TranslationTaskRegistry` 不在 cancel 时移除 job；register 仅接受空 key。
- [ ] `TranslationTaskRegistryTest` 增加取消后未完成时拒绝注册。
- [ ] `ReaderViewModel.load`、`ReadingTranslationCoordinator`、
      `LibraryViewModel`、`SettingsViewModel.save` 改取消透传。

### 2.6 复审追加（P0/P1）

- [ ] `FileContentStore.readSidecar` 解码失败返回 null；`polishChapter` 兜底。
- [ ] 备份写入 `data/bookmarks.json`；导入去重补齐；`ImportApplyResult.bookmarks`。
- [ ] `ImportPlanner` 恢复没有目录的书；`LibraryCommitter` 跳过缺失目录。
- [ ] `mergeDirectory` 用 `.part` + 原子移动。
- [ ] `partial` 章节不被 `readZh != null` 短路。
- [ ] `readerScrollBlocks` 统一滚动列表与段模型；空行零高度。

### 2.7 版本与文档

- [ ] `versionCode = 67`，`versionName = "1.9.3"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不新增功能、不改信息架构与视觉。
- 不改备份 format 版本、不改翻译队列调度策略。
- 不处理已发出的 OkHttp 请求无法中断的物理限制。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥320 tests，0 failures；新增导入/registry/EPUB 用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 67 |
| 用户 | 导入不丢进度；失败不留坏文件；取消后状态恢复；EPUB 识别可靠 |
| 发布 | 提交 + tag `v1.9.3` + 推送 |

## 5. 回滚

改动集中在 `BackupImportService`、两个 ViewModel、`ReaderViewModel`、
`LocalDocumentImporter`、`LocalTextParser`、`BookDownloadWorker`、
`ReadingTranslationCoordinator`、`TranslationTaskRegistry`；无数据迁移。
`git revert` 单提交即可。
