# Round 32 · 工程师视角升级指南（v1.9.5）

> 基线：1.9.4 / versionCode 68；328 JVM tests。
> 本轮收尾数据恢复边界与缓存一致性。

## 1. 问题与方案

### E1. 非连续章节 idx 的“继续阅读”（P1）

**现状**：`ChapterListScreen` 与 `ChapterListViewModel` 用
`progressIdx in 1..chapters.size` 判断。章节 idx 为 1,2,3,50 时，
进度 50 被判无效，回退到第 1 话并写入 1。

**修复**：抽纯函数：

```kotlin
internal fun continueChapterIndex(
    chapters: List<ChapterEntity>,
    progress: Int,
): Int = progress.takeIf { p -> chapters.any { it.idx == p } }
    ?: chapters.firstOrNull()?.idx
    ?: 1
```

`ChapterListScreen` 的 Hero/TranslationBatchDialog 与
`ChapterListViewModel.translateChapters` 统一使用。补 1,2,3,50 的测试。

### E2. Partial 覆盖完整译文（P1）

**现状**：`TranslationService.commit` 对 Partial 也 `writeZhAtomic`，
把旧 complete 覆盖成 partial，旧文只进 `cache/versions` 且无恢复入口。

**修复**：`commit` 先读旧 `zh`/sidecar：

```kotlin
if (outcome is Partial && oldSidecar?.status == "complete" &&
    oldText != null && oldText != text
) {
    return TranslationOutcome.Failed(
        "重译只完成了部分段落，已保留原完整译文",
        retryable = true,
    )
}
```

然后再走原有版本保存/写入。旧 sidecar 为 null 或 partial 时允许覆盖。

### E3. 唯一键冲突与 id 重映射（P1）

**现状**：`BackupImportService.apply` 只按 id 查现有书；
`@Upsert` 在 `import_hash`/`slug`/`(source, source_id)` 冲突时静默 0 行，
章节/状态/书签挂到孤儿 id。

**修复**：

1. `ImportCoordinator` 在 commit 前查 `dao.books()`，建立
   `idMap: plannedId -> existingId`，匹配顺序：
   `id` → `import_hash` → `source+sourceId` → `slug`。
2. `ImportPlan.remapBookIds(idMap)` 同步重写 `report.books[].id`、
   `chapters[].bookId`、`readStates[].bookId`、`bookmarks[].bookId`、
   `chapterMetadata[].bookId`。
3. `storageDirOverrides` 用重映射后的 id 对应现有目录。
4. `apply` 仍按 id 查 existing，此时 id 已一致。

测试：先插入 `local-bbb`（importHash=H），备份是 `local-aaa`（同 H）；
导入后 `bookCount` 仍 1，章节/进度/书签都在 `local-bbb`。

### E4. 旧备份无章节元数据（P2）

**现状**：`chapterMetadata` 为空时只按文件生成章节；在线书只剩已下载章节。

**修复**：`apply` 中，若该书 `metadata` 为空、`source != "local"`、
`episodes > 0`，合成 `1..episodes` 的占位章节：

- `title=null/titleZh=null`；
- `status="online"`，供后续 `ensureChapter` 下载；
- `rawPath=null/zhPath=null`；
- 已有文件行优先，不重复。

`episodes` 上限保护（例如 5000），避免异常备份生成过多行。

### E5. 润色/单段重译后缓存失效（P2）

**现状**：`TranslationStore` 的缓存 key 是 `sourceSha256-configHash`；
润色/单段修改后旧缓存仍在，下次整章翻译命中旧段落。

**修复**：`TranslationStore` 增加默认空实现的
`fun invalidate(storageDir: String, idx: Int)`；`FileTranslationStore`
删除 `cache/translation/<idx>/`。`TranslationService` 在
`polishChapter` / `retranslateParagraph` 的 commit 后调用。

### E6. 清除筛选保留已移出（P2）

**现状**：`LibraryScreen` 的清除按钮无条件调用
`onFavoritesOnlyChange(false)` / `onShelfChange(null)`；
`LibraryViewModel` 的 setter 无条件 `removedOnly=false`。

**修复**：只在对应筛选有值时调用 setter：

```kotlin
if (state.query.isNotBlank()) onQueryChange("")
if (state.favoritesOnly) onFavoritesOnlyChange(false)
if (state.shelf != null) onShelfChange(null)
if (!keepRemoved) onRemovedOnlyChange(false)
```

### E7. previewError 跨书（P2）

**修复**：

- `DiscoverViewModel.preview(book)` 清空 `previewError`；
- 失败时仅当 `_state.value.preview != null` 才设置；
- `add` 的 `runCatching` 换 `runCatchingCancellable`，取消透传。

## 2. 实施顺序

1. E1 纯函数 + 测试。
2. E2 commit 保护 + 测试。
3. E3 idMap + remap + 导入测试。
4. E4 旧备份占位章节 + 测试。
5. E5 缓存失效 + 测试（可用临时目录的 FileTranslationStore）。
6. E6/E7 UI 修复。
7. 版本、文档、全量验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 335，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 69。

## 4. 风险

- id 重映射会让备份的 `bookId` 全部指向现有书；如果匹配错（同 slug 不同书），
  可能把数据合并到错误的书。匹配顺序以 `id`/`import_hash` 优先，`slug` 最后。
- 旧备份合成占位章节可能一次插入很多行；上限 5000，超出只插 5000。
- Partial 保护会让“确实想用部分结果替换完整译文”的用户无法完成；
  当前没有该入口，保守优先。
- 缓存失效只清当前章，不影响其他章。
