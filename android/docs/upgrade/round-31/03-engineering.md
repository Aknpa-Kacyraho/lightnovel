# Round 31 · 工程师视角升级指南（v1.9.4）

> 基线：1.9.3 / versionCode 67；325 JVM tests。
> 本轮只补数据恢复、失败重试、状态同步与导航返回栈。

## 1. 问题与方案

### E1. 备份章节元数据（P1）

**现状**：`BackupExporter` 只导出 `data/library.json`、`data/books/*.json`、
`data/bookmarks.json`；`ChapterPlanner` 只从 `novels/` 文件生成章节。
恢复后在线书只剩已下载章节，本地书标题变 null。

**修复**：

- 新增 `BackupChapter(bookId, idx, title, titleZh, status)`。
- `BackupExporter` 写 `data/chapters.json`（`dao.allChapters()`）。
- `ImportPlan.chapterMetadata` 保存解析结果。
- `apply` 按书合并：
  - 现有行：只补空 `title`/`titleZh`，不覆盖 token、状态、路径；
  - 文件行缺失：插入（title 来自 metadata，路径来自文件）；
  - metadata 行缺失：插入 `rawPath=null/zhPath=null`，状态用 metadata。
- `ImportApplyResult.chapters` 只计新插入行。

### E2. storageDir 一致性（P1）

`mergeBook` 保留本机 `storageDir`，但 `LibraryCommitter` 按备份的
`planned.storageDir` 写文件，导致 DB 指向旧目录。

**修复**：`LibraryCommitter.commit` 增加
`storageDirOverrides: Map<bookId, destDir>`；`ImportCoordinator` 在 commit 前
查询本机 `books()`，把同名书映射到现有目录。`source` 仍用备份目录，
`dest` 用现有目录。

### E3. 重试原操作（P1）

**现状**：`retryTranslation()` 无条件 `translateChapter()`；润色、单段重译、
资料更新失败都会变成整章翻译。

**修复**：`ReaderViewModel` 增加 `retryAction: (() -> Unit)?`：

- 各操作开始时清空；
- 失败分支设置对应 action；
- 取消时清空；
- `retryTranslation()` 优先执行 `retryAction`，否则回退整章。
- `retranslateParagraph` 同时补 `CancellationException` 处理。

### E4. 设置页跟随 store（P2）

**现状**：`SettingsViewModel.init` 只 `first()` 读一次；阅读器写回后设置页旧值。

**修复**：改为 `settingsStore.settings.collect`：

- 首次加载 cache usage 与 `hasKey`；
- 后续只更新已保存字段（阅读排版、主题、备份时间、预译设置）；
- `baseUrl` / `model` / `maxTokensInput` / `keyInput` 保留用户编辑。

### E5. 已移出 + 搜索空态（P2）

`emptyShelfCopy` 先判断 `removedOnly`，再判断 query。改为先算
`hasFilter = query/favorites/shelf`：

- `removedOnly && hasFilter` → 「没有匹配的已移出书籍」；
- `removedOnly` → 「没有已移出的书」；
- `hasFilter` → 「没有匹配的书」。

`LibraryScreen` 的清除按钮：若 `removedOnly` 且还有其它筛选，
只清 query/favorites/shelf，保留 `removedOnly`。

### E6. 预览加书错误（P2）

`DiscoverUiState` 增加 `previewError`；`add` 开始/成功清空，失败设置；
`dismissPreview` 清空。`BookPreviewSheet` 增加 `error` 参数，在按钮上方显示。

### E7. 目录替换旧 reader（P2）

`LightnovelNavHost.readerRoute.onOpenCatalog` 的非章节来源分支：
navigate 目录时加 `popUpTo(entry.destination.id) { inclusive = true }`，
把当前 reader 从返回栈移除。

## 2. 实施顺序

1. 章节元数据备份 + 合并 + 测试。
2. storageDir override + 测试。
3. retryAction + 取消处理。
4. 设置 collect、空态、预览错误、返回栈。
5. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 330，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 68。

## 4. 风险

- `data/chapters.json` 是可选文件，旧备份没有时行为不变。
- 章节元数据可能很大（数千行），限制 8MB；超出时忽略该文件，不影响书与进度。
- `storageDirOverrides` 只影响写入位置，不迁移旧目录文件；同名书以现有目录为准。
- 设置 collect 不覆盖输入框，但 `save()` 后 store 更新会刷新已保存字段。
- 目录替换 reader 后，返回直接到上级；用户不能再从目录返回原章节（预期）。
