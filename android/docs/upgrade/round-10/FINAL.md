# Round 10 · 统一升级指南（v1.4.0）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：先给「标记与找回」一条完整闭环（添加 → 列表 → 同章定位 → 删除），
> 不贪多做笔记与高亮。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1–E3 | 没有书签 | **采纳，P0** | 表 + 菜单 + 列表，闭环可测 |
| U2 + D3 | 书签要回到原段落 | **采纳（同章），P1** | 同章写进度 + reload；跨章到章首 |
| U3 + D2 | 列表缺上下文 | **采纳，P1** | 章节 + 40 字预览 + 相对时间 |
| U4 | 不能删除 | **采纳，P2** | 列表内直接删，不二次确认 |

## 2. 实施清单

### 2.1 数据库 v5（P0）

- [ ] `BookmarkEntity`（book/chapter/paragraph 主键 + charOffset + preview + createdAt）。
- [ ] `MIGRATION_4_5` + `version = 5` + `schemas/5.json`。
- [ ] DAO：`observeBookmarks` / `upsertBookmark` / `deleteBookmark` / `bookmark`。
- [ ] Repository 暴露同名方法。
- [ ] `MigrationTest` 加 4→5；`LibraryDaoTest` 加去重/删除。

### 2.2 ViewModel（P0）

- [ ] `bookmarks: StateFlow<List<BookmarkEntity>>`。
- [ ] `addBookmark()`：当前 anchor + 段落预览（40 字）。
- [ ] `jumpToAnchor(anchor)`：写进度 + `anchorToRestore` + `load()`。
- [ ] 添加后轻提示「已添加书签」。

### 2.3 UI（P1）

- [ ] 菜单「阅读」组加「添加书签」/「已添加书签」；「资料」组加「书签列表」。
- [ ] `BookmarkSheet`：章节标题、两行预览、相对时间、删除、空态。
- [ ] 同章点击 → `jumpToAnchor` 并关闭 Sheet；跨章 → `onOpenChapter`。
- [ ] `relativeTime(iso, now)` 纯函数 + `BookmarkTimeTest`。

### 2.4 版本与文档

- [ ] `versionCode = 47`，`versionName = "1.4.0"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不做笔记、高亮、批注、书签导出/同步。
- 不做跨章精确段落定位（V1 到章首，再点一次书签）。
- 不改分页算法与阅读进度格式。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥239 tests，0 failures；新增迁移/DAO/时间用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 47 |
| 用户 | 添加书签、列表可看、同章可回、可删除 |
| 数据 | 迁移不丢书/进度；书签按书隔离 |
| 发布 | 提交 + tag `v1.4.0` + 推送 |

## 5. 回滚

代码 `git revert`；数据库 v5 迁移不可降级，回滚 App 会拒绝启动，需备份恢复。
发布前用 `MigrationTest` 验证 4→5。
