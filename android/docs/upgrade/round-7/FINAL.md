# Round 7 · 统一升级指南（v1.3.0）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：书库先保证「不重复、可找回」，再谈排序这种优化。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 + E2 | 本地文件重复导入 | **采纳，P0** | 内容哈希 + 唯一索引，可迁移、可测试 |
| U2 + D2 + D3 + E3 | 书架只能按标题排 | **采纳，P1** | 纯函数排序 + 持久化，不动 DAO 结构 |
| U3 | 重复导入无提示 | **采纳，P1** | 与去重同一处改动 |
| U4 | 没有彻底删除 | **推迟** | 涉及文件删除与备份提示，单独设计 |

## 2. 实施清单

### 2.1 数据库 v4（P0）

- [ ] `BookEntity` 增加 `importHash: String? = null`，`books` 加唯一索引。
- [ ] `MIGRATION_3_4`：`ALTER TABLE books ADD COLUMN import_hash TEXT` +
      `CREATE UNIQUE INDEX index_books_import_hash`。
- [ ] `LightnovelDatabase.version = 4`，`LightnovelApp` 注册迁移。
- [ ] 提交生成的 `schemas/4.json`。
- [ ] `MigrationTest` 加 3→4 用例。

### 2.2 导入去重（P0）

- [ ] `LocalDocumentImporter` 读入 bytes 后计算 SHA-256，先查 `bookByImportHash`。
- [ ] 命中且 `hidden` → 恢复原书；命中且未隐藏 → 直接返回。
- [ ] 返回 `LocalImportResult(book, existing, restored)`。
- [ ] `LibraryViewModel` 三种文案：已导入 / 已存在 / 已恢复。
- [ ] 测试：同内容第二次导入 `existing = true`。

### 2.3 书架排序（P1）

- [ ] 新增 `LibrarySort`（标题 / 最近阅读 / 最近添加）与 `sortLibrary(...)` 纯函数。
- [ ] `SettingsStore.librarySort` 默认 `"title"`，`LibraryViewModel.setSort` 持久化。
- [ ] `LibraryUiState.sort`；筛选行末尾加「排序：…」chip + DropdownMenu。
- [ ] `LibrarySortTest` 覆盖三种排序、空时间、中文标题。
- [ ] 排序不改变搜索、筛选与「继续阅读」。

### 2.4 版本与文档

- [ ] `versionCode = 44`，`versionName = "1.3.0"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不做彻底删除、批量选择、拖拽排序、自定义分组。
- 不改在线书去重（`(source, source_id)` 唯一索引已存在）。
- 不改书架卡片布局与空态。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥220 tests，0 failures；新增迁移/排序/去重用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 44 |
| 用户 | 同文件导入两次书架不变；三种排序可切换且重启保持 |
| 数据 | 迁移不丢书、不丢进度；已移出的重复书可恢复 |
| 发布 | 提交 + tag `v1.3.0` + 推送 |

## 5. 回滚

代码：`git revert` 单提交。数据：v4 迁移不可自动降级；回滚 App 会因版本不匹配拒绝启动，
需要备份恢复。发布前必须用 `MigrationTest` + 真机（或 Robolectric）验证迁移。
