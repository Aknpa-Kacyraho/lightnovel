# Round 33 · 统一升级指南（v1.9.6）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：目录补齐不重置、失败可解释、进度不编造、视觉走 token。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 源站新章节不进入现有书 | **采纳，P2** | 追加缺失 idx，只补不改 |
| U2 + D2 + E2 | 翻译失败没有原因 | **采纳，P2** | DB v6 `last_error` |
| U3 + D3 + E3 | 翻译中没有进度 | **采纳，P3** | 复用 `taskRegistry.active` |
| U4 + D4 + E4 | 队列错误不可见 | **采纳，P3** | 队列行显示 `lastError` |
| U5 + D5 + E5 | 人物名不是链接语义 | **采纳，P3** | `LinkAnnotation.Clickable` |
| U6 + D6 + E6 | 非阅读器 Sheet 28dp | **采纳，P3** | 统一 20dp |

## 2. 实施清单

### 2.1 目录同步（P2）

- [ ] 新增 `CatalogSync.kt`：`planCatalogAppend` / `catalogEpisodeCount`。
- [ ] `DirectLibraryService.detail(force)` + `syncCatalog(book[, detail])`：
      事务内只追加缺失 idx、补空标题、更新 `episodes`。
- [ ] `ChapterListViewModel`：打开时静默同步；新增 `syncCatalog()` 手动入口；
      `syncing` 防连点；成功/最新/失败文案；新章节后台翻译标题。
- [ ] `ChapterListScreen`：「更多 → 同步目录」，同步中禁用。
- [ ] 保证：不删章节、不改已有行、不动进度/书签/译文。

### 2.2 失败原因（P2，DB v6）

- [ ] `ChapterEntity.lastError` + `ChapterTaskRow.lastError`。
- [ ] `MIGRATION_5_6`、`version = 6`、提交 `6.json`。
- [ ] `updateChapterTranslation` 清空 `last_error`；
      `markChapterFailure` 一次写状态与原因。
- [ ] `TranslationService` 三个失败点改用 `markChapterFailure`。
- [ ] 任务卡显示原因（两行）；重试/成功后消失。

### 2.3 进度与队列错误（P3）

- [ ] `TaskCenterUiState.progress` 来自 `taskRegistry.active`。
- [ ] `TaskCard`：`translating && total > 0` 时进度条 + `已译 d/t 段`。
- [ ] 队列行显示 `lastError`，`colorScheme.error`，两行截断。

### 2.4 无障碍与视觉（P3）

- [ ] `ReaderRoute`：`ClickableText` → `Text` + `LinkAnnotation.Clickable`。
- [ ] 目录/发现 4 个 `ModalBottomSheet` 顶角 20dp。

### 2.5 版本与文档

- [ ] `versionCode = 70`，`versionName = "1.9.6"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。
- [ ] tag `v1.9.6` + push + CI artifact + 手工 Release。

## 3. 非目标

- 不处理源站中间插入/重排/下架导致的 idx 漂移。
- 不自动下载或自动翻译新章节。
- 不迁移旧 `storageDir` 历史文件。
- 不新增「强制覆盖完整译文」入口。
- 不做 `data/chapters.json` 的 8MB 上限改造。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | 348 tests / 0 failures / 1 skipped；新增同步、迁移、DAO、进度用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 70 / 1.9.6 |
| 目录 | 新增章节可见；无变化不重复；源站少章不删除；断网可读 |
| 数据 | 进度、译文、书签、下载文件不变；旧备份仍可导入 |
| 任务中心 | 原因可读且持久；进度只在有数据时显示 |
| 视觉 | 非阅读器 Sheet 20dp；无新增硬编码颜色/字号 |
| 发布 | 提交 + tag `v1.9.6` + CI success + Release 资产 |

## 5. 回滚

- 代码：`git revert` 本轮提交即可；目录同步与 UI 相互独立。
- DB：v6 只加可空列，旧代码无法读 v6；回滚需同时恢复 v5 数据库或
  保留 `last_error` 列并降级 `version`（不推荐）。
- 发布后不覆盖既有 Release 资产；新版本用新 `versionCode`。
