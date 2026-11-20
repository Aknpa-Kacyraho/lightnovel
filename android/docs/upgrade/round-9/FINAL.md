# Round 9 · 统一升级指南（v1.3.2）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：书库要能清理，但删除必须「只在已移出视图、二次确认、先停后台」。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + D2 + E1–E3 | 已移出的书无法彻底删除 | **采纳，P0** | 有前提的删除 + 固定顺序，风险可控 |
| U2 | 删除入口不能出现在在读的书 | **采纳，P0** | 仅 `removedOnly` 显示 |
| U3 + D4 | 删除/移出后队列仍在跑 | **采纳，P1** | 先停 WorkManager/Job/coordinator |
| U4 + D3 + E4 | 删除无反馈 | **采纳，P2** | SharedFlow → Snackbar |

## 2. 实施清单

### 2.1 文件与数据库（P0）

- [ ] `ContentStore.deleteBook(storageDir)`；`FileContentStore` 递归删除
      `novels/<storageDir>`，拒绝空/非法 storageDir。
- [ ] DAO 增加 `deleteChapters` / `deleteReadState` / `deleteBook`。
- [ ] `LibraryRepository.deleteBook(bookId): BookEntity?` 事务删三表。
- [ ] `LibraryDaoTest` 断言删除后三表无记录。

### 2.2 删除流程（P0）

- [ ] ViewModel：先 `downloadScheduler.cancel`、`taskRegistry.cancelBook`、
      `onBookRemoved(bookId)`，再删 DB，最后删文件。
- [ ] 文件删除失败：保留「记录已删」并提示，不回滚。
- [ ] `onBookRemoved` 由 `AppContainer.readingTranslationCoordinator.stop` 提供。

### 2.3 UI（P0/P1）

- [ ] `BookRow` 增加 `showDelete` 与 `onDelete`；仅 `removedOnly` 显示菜单项。
- [ ] 独立确认对话框：列出正文/译文、世界线与资料库、阅读进度；
      提示无法恢复与备份建议；「删除」用 error 色，默认焦点「取消」。
- [ ] 成功 Snackbar「已删除《书名》与本地文件」；失败提示原因。

### 2.4 版本与文档

- [ ] `versionCode = 46`，`versionName = "1.3.2"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不做批量删除、回收站、定时清理。
- 不删备份与 `data/` 全局数据。
- 不改「移出书架」的可撤销行为。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥220 tests，0 failures；新增删除级联/文件删除用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 46 |
| 用户 | 已移出视图可删除；在读视图无删除；确认框信息完整 |
| 数据 | 删除后目录消失、任务页无残留；文件失败有提示 |
| 发布 | 提交 + tag `v1.3.2` + 推送 |

## 5. 回滚

代码可 `git revert`；**已删除的用户数据无法恢复**。
因此本轮发布前只做本地构建与单元测试，不提供「一键清理」入口给非已移出视图。

## 6. 三轮收束（Round 7–9）

- Round 7：书库不再重复、书架可排序；
- Round 8：翻译状态可信、费用可判断、失败可自愈；
- Round 9：书库可清理，删除有前提、有确认、有后台停止。
