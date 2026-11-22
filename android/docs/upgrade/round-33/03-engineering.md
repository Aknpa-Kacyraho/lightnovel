# Round 33 · 工程师视角指南（v1.9.6）

> 基线：1.9.5 / versionCode 69 / DB v5 / 334 JVM tests。
> 本轮涉及 1 次 DB migration（v5 → v6），其余为纯代码与 UI。

## 1. 源站目录同步（P2，核心）

### 1.1 现状与根因

- `DirectLibraryService.detail()` 有进程内缓存，只更新 `tagsJson`/`episodes`，
  从不向 `chapters` 追加行。
- `ChapterListViewModel.init` 调 `syncChapterTitles()`，而它的 DAO
  `fillChapterTitle` 只填空标题，不会新增章节。
- `ChapterListViewModel.refresh()` 只重读 Room，不重新拉源站。
- 结论：源站新增章节永远不会进入现有书。

### 1.2 方案

新增纯函数（建议 `data/source/CatalogSync.kt`）：

```kotlin
internal data class SourceChapterAppend(val index: Int, val title: String)

internal fun planCatalogAppend(
    existingIndices: Set<Int>,
    sourceTitles: List<String>,
): List<SourceChapterAppend> =
    (1..sourceTitles.size)
        .filterNot { it in existingIndices }
        .map { SourceChapterAppend(it, sourceTitles[it - 1]) }

internal fun catalogEpisodeCount(existingMax: Int?, sourceSize: Int): Int =
    maxOf(existingMax ?: 0, sourceSize)
```

`DirectLibraryService`：

```kotlin
suspend fun detail(book: BookEntity, force: Boolean = false): SourceDetail
suspend fun syncCatalog(book: BookEntity, force: Boolean = false): CatalogSyncResult
suspend fun syncCatalog(book: BookEntity, detail: SourceDetail): CatalogSyncResult
```

约束：

- 只 `upsertChapters` 新增 idx；已有行不 copy、不改 `rawPath/zhPath/status`。
- 空标题补全沿用 `fillChapterTitle`（SQL 自带空值保护），只对 `title` 为空的
  已有章节调用，避免 N 次全量写。
- `database.withTransaction { upsertChapters + fillChapterTitle + update episodes }`。
- `episodes = maxOf(existingMaxIdx, sourceSize)`，不因源站临时少章而缩短。
- `force = true` 才绕过 `details` 缓存；拉取失败时不要清空旧缓存。
- `detail()` 现有 tags 更新逻辑保留；`episodes` 交给 sync 统一负责。

`ChapterListViewModel`：

- `init`：`detail(force = true)`，失败回退 `detail(force = false)`；随后
  `syncCatalog(book, detail)`；再读 Room。新增 > 0 时 `message = "目录已更新：新增 N 话"`。
- `refresh()` 保持只读 Room（ON_RESUME 不重复打网络）。
- 新增 `fun syncCatalog()`：`syncing` 防连点；强制拉取；总是给
  `message`（新增/已是最新）或 `error`（失败原因）。
- 新增 `ChapterListUiState.syncing: Boolean`。
- 手动同步成功后重读 book/chapters/readState，并对新章节调用
  `metadataService.translateChapterTitles`，在后台把结果写回 state。

`ChapterListScreen`：

- 在线书的「更多」菜单增加「同步目录 / 同步中…」，放在「下载全部」前。
- `LaunchedEffect(state.message, state.error)` 已能显示新增/失败提示，复用。

### 1.3 安全边界

- 不删除、不重排、不改已有标题；源站少章时本地仍可读。
- 新增章节 `status = "online"`、`titleZh/rawPath/zhPath = null`、tokens = 0。
- 不加自动下载/自动翻译，避免额度和流量意外。
- `read_state` 完全不动；进度、书签、译文保持原 idx。

## 2. 翻译失败原因持久化（P2，DB v6）

### 2.1 Schema

`ChapterEntity` 末尾新增：

```kotlin
@ColumnInfo(name = "last_error") val lastError: String? = null,
```

- `LightnovelDatabase.version = 6`
- `MIGRATION_5_6`：`ALTER TABLE chapters ADD COLUMN last_error TEXT`
- **同时把 `MIGRATION_5_6` 加进 `AppContainer.addMigrations(...)`**；
  只在 `LightnovelDatabase` 里声明、不注册，升级时会直接崩。
- 提交 `app/schemas/.../6.json`
- `ChapterTaskRow` 增加 `lastError`；`observeActiveTasks` SELECT `c.last_error`。

### 2.2 写入规则

- `updateChapterTranslation` 的 SQL 增加 `last_error = NULL`：
  开始翻译、成功、partial、取消都会自动清旧原因。
- 新增 DAO `markChapterFailure(bookId, idx, status, model, tokenIn, tokenOut,
  updatedAt, lastError)`，一次写入状态与原因。
- `TranslationService` 的 3 个失败点改用 `markChapterFailure`：
  1. `translator.translate` 抛异常；
  2. `outcome is Failed`；
  3. `commit` 写盘异常。
- 队列的「原文下载失败/缺少原文」不强行写 `failed`（章节可能仍是 online），
  只保留 `queue.lastError` 给队列行展示；避免把可下载章节误标失败。

### 2.3 展示

- `TaskCenterUiState.progress: Map<String, TranslationTaskSnapshot>`，
  由 `taskRegistry.active` 提供。
- `TaskCard` 参数增加 `progress`：
  - `translating && total > 0` 时显示 `LinearProgressIndicator` + `已译 d/t 段`；
  - `lastError` 非空时显示两行原因。
- 队列行增加 `lastError` 展示，`colorScheme.error`。

## 3. 无障碍与视觉一致性（P3）

- `ReaderRoute` 的 `ClickableText` 改为 `Text` + `buildAnnotatedString` +
  `LinkAnnotation.Clickable`（Compose BOM 2025.12.01 已支持）：
  - `tag = entityId`，`styles = TextLinkStyles(SpanStyle(underline))`；
  - `linkInteractionListener` 调 `onSelectEntity`；
  - 删除 `androidx.compose.foundation.text.ClickableText` import。
- 目录页 2 个、发现页 2 个 `ModalBottomSheet` 增加
  `shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)`，
  与阅读器一致。

## 4. 测试计划

新增/扩展：

1. `CatalogSyncTest`（纯函数）：
   - 空库 + 12 章 → 12 行；
   - 已有 1..10 + 源站 12 → 只补 11、12；
   - 源站缩到 8、本地 10 → 不新增，episodes 仍 10；
   - 稀疏 idx（1,2,5）+ 源站 8 → 补 3,4,6,7,8；
   - 空标题、重复 idx 不产生重复行。
2. `DirectLibraryService` 集成测试（Robolectric + in-memory Room + FakeSource）：
   - 已有 2 章，源站 4 章 → 追加 2 行，已有行原文/译文/状态不变；
   - `episodes` 更新；
   - 连续同步两次 → 第二次 0 新增（幂等）。
3. `MigrationTest.migration5To6AddsLastError`。
4. `LibraryDaoTest`：`markChapterFailure` 写入 `last_error`；
   再次 `updateChapterTranslation` 后清空。
5. `TaskCenterProgressTest`：`progressLabel(done,total)` 的 0/中间/完成/异常值。
6. `TranslationServiceTest`：失败 client 后章节 `lastError` 非空；
   成功翻译后 `lastError` 为空。

## 5. 验证命令

```powershell
chcp 65001 | Out-Null
cd android
$env:ANDROID_HOME="D:\Android\Sdk"; $env:ANDROID_SDK_ROOT="D:\Android\Sdk"
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

基线预期：348 tests / 0 failures / 1 skipped；lint 0 errors / ≤22 warnings。

## 6. 风险与回滚

- **索引漂移**：源站在中间插入章节时，idx 与正文可能错位；本轮只保证
  「追加在末尾」正确，不解决重排。文档继续标注为已知限制。
- **强制刷新流量**：每次进入详情会打一次源站；失败回退缓存。
  若某源站限流，只影响同步提示，不影响本地阅读。
- **Migration**：只加可空列，旧数据默认 NULL；回滚需降级 DB，不支持。
  发布前用 `MigrationTest` 和 Room schema 校验。
- 改动集中在 `data/source`、`data/local`、`data/translation`、
  `feature/chapters`、`feature/tasks`、`feature/reader`、`feature/catalog`、
  `feature/discover`。

## 7. 版本

- `versionCode = 70`，`versionName = "1.9.6"`。
- 同步 `README.md`、`CHANGELOG.md`、`04-final.md` §8.1、`PROGRESS.md`、
  `round-33/SELF-REVIEW.md`。
- tag `v1.9.6`，CI `Signed Android Release` 成功后手工创建 Release，
  资产名 `lightnovel-1.9.6-release.apk`。
