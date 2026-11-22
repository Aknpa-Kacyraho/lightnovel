# Round 31 · 统一升级指南（v1.9.4）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：恢复要完整，重试要对应，状态要同步，返回要可预测。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 恢复后目录不完整 | **采纳，P1** | `data/chapters.json` 合并 |
| — + — + E2 | DB 与文件目录不一致 | **采纳，P1** | commit 写入现有 storageDir |
| U2 + D2 + E3 | 重试变成整章翻译 | **采纳，P1** | `retryAction` 分派 |
| U3 + D3 + E4 | 设置页旧值 | **采纳，P2** | 持续 collect settings |
| U4 + D4 + E5 | 已移出空态误报 | **采纳，P2** | 先判断 hasFilter |
| U5 + D5 + E6 | 加书失败不可见 | **采纳，P2** | `previewError` |
| U6 + D6 + E7 | 返回栈残留 reader | **采纳，P2** | 目录替换 reader |

## 2. 实施清单

### 2.1 数据恢复（P1）

- [ ] 新增 `BackupChapter` / `data/chapters.json`。
- [ ] `BackupImportService.apply` 合并章节：已有优先、缺行补齐、空标题补全。
- [ ] `LibraryCommitter.commit(storageDirOverrides)`；`ImportCoordinator` 查本机目录。
- [ ] `BackupExporterTest` 断言章节文件；`ImportCoordinatorTest` 断言在线书章节恢复；
      `LibraryCommitterTest` 断言写入现有目录。

### 2.2 阅读器重试（P1）

- [ ] `retryAction`：翻译/润色/单段/资料更新失败分别记录。
- [ ] `retryTranslation()` 优先执行 action。
- [ ] `retranslateParagraph` 捕获取消并复位。

### 2.3 状态与导航（P2）

- [ ] `SettingsViewModel` 持续 collect settings，保留未保存输入。
- [ ] `emptyShelfCopy` 先判断 hasFilter；清除时保留 removedOnly。
- [ ] `previewError` + `BookPreviewSheet(error)`。
- [ ] 目录 navigate 使用 `popUpTo(reader) { inclusive = true }`。

### 2.4 版本与文档

- [ ] `versionCode = 68`，`versionName = "1.9.4"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不新增源站目录同步/刷新功能（留待后续）。
- 不改变备份 format 版本；新增文件可选。
- 不迁移旧 storageDir 的文件，只保证新文件写入 DB 指向的目录。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥330 tests，0 failures；新增章节/目录/空态用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 68 |
| 用户 | 目录完整、重试对应、设置同步、空态准确、加书错误可见、返回干净 |
| 发布 | 提交 + tag `v1.9.4` + 推送 |

## 5. 回滚

改动集中在 `data/backup`、`data/import`、`data/export`、`feature/reader`、
`feature/settings`、`feature/library`、`feature/discover`、`navigation`；
无 DB schema 变化。`git revert` 单提交即可。
