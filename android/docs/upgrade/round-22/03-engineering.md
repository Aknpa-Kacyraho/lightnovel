# Round 22 · 工程师视角升级指南（v1.8.0）

> 基线：1.7.2 / versionCode 58；293 JVM tests。
> 本轮修「备份导入整行覆盖」：`@Upsert` 会把已存在的书/状态/章节全部替换。

## 1. 工程问题与方案

### E1. `@Upsert` 的语义（P1）

`LibraryDao.upsertBooks/upsertReadStates/upsertChapters` 都是 `@Upsert`。
Room 的 `@Upsert` 在冲突时执行 **UPDATE 全列**，用传入 entity 的值覆盖。
`BackupImportService.apply` 直接传入备份数据，于是：

- 书：`title_zh/author/tags_json/episodes/import_hash` 被旧备份覆盖；
- 状态：`progress_* / shelf / favorite / hidden` 回退；
- 章节：`title_zh / token_in / token_out / model / updated_at` 清零。

**方案**：在 `apply` 前查询现有行，用纯函数合并后再 upsert。

新增 `data/import/ImportMerge.kt`：

```kotlin
internal fun mergeBook(
    existing: BookEntity?,
    planned: PlannedBook,
    chapterCount: Int,
): BookEntity

internal fun mergeReadState(
    existing: ReadStateEntity?,
    planned: ReadStateEntity,
): ReadStateEntity

internal fun missingChapters(
    planned: List<PlannedChapter>,
    existingKeys: Set<Pair<String, Int>>,
): List<PlannedChapter>
```

### E2. 书的合并规则（P1）

新书：按现有逻辑构造，`episodes = maxOf(planned.episodes, chapterCount)`，
`importHash = null`（备份格式没有该字段）。

已存在：**现有非空优先，缺失才用备份补**：

```kotlin
existing.copy(
    storageDir = existing.storageDir.ifBlank { planned.storageDir },
    slug = existing.slug?.takeIf(String::isNotBlank) ?: planned.slug,
    title = existing.title.ifBlank { planned.title },
    titleZh = existing.titleZh?.takeIf(String::isNotBlank) ?: planned.titleZh,
    author = existing.author?.takeIf(String::isNotBlank) ?: planned.author,
    tagsJson = existing.tagsJson?.takeIf(String::isNotBlank)
        ?: BookTags.encode(planned.tags).takeIf { planned.tags.isNotEmpty() },
    episodes = maxOf(existing.episodes, planned.episodes, chapterCount),
    createdAt = existing.createdAt ?: planned.addedAt,
    legacyJson = existing.legacyJson ?: planned.legacyJson,
)
```

- `importHash`、`local`、`source/sourceId` 保留现有，不参与合并；
- 不覆盖 `createdAt`，避免书架排序跳变。

### E3. 阅读状态的合并规则（P1）

```kotlin
val usePlanned = planned.updatedAt.orEmpty().isNotBlank() &&
    planned.updatedAt!! > existing.updatedAt.orEmpty()
```

- `usePlanned`：采用备份的 `shelf/progress/openedAt/finishedAt`，
  但 `hidden` 保留现有、`favorite` 取并集；
- 否则：保留现有进度，只补缺失的 `shelf/openedAt/finishedAt`，
  `favorite` 取并集；
- 备份没有 `updated_at` 时一律保留现有进度（旧备份不倒退）。

### E4. 章节只补缺失（P2）

```kotlin
val existingKeys = plan.report.books
    .flatMap { dao.chapters(it.id) }
    .map { it.bookId to it.idx }
    .toSet()
val chapters = missingChapters(plan.chapters, existingKeys)
```

- 已存在章节完全不动；
- `missingChapters` 内部 `distinctBy { it.bookId to it.idx }`，避免同批重复；
- 新章节仍按原逻辑构造（`title/titleZh/token/model/updatedAt` 为 null）。

### E5. 文件目录合并（P1）

`LibraryCommitter.commit` 现状：目标目录存在且 `sameTree` 不同 → 把整个目标
目录移到 `.bak`，再移动 staging 目录进去。

后果：备份之后新增的 `zh/<idx>.txt`、`raw/<idx>.txt` 不在旧备份里，直接被
替换掉；DB 章节行还在，阅读器却找不到译文。

**方案**：目标目录存在时改为逐文件合并：

```kotlin
private fun mergeDirectory(source: Path, dest: Path): Int {
    var copied = 0
    Files.walk(source).use { stream ->
        stream.filter { Files.isRegularFile(it) }.forEach { from ->
            val to = dest.resolve(source.relativize(from))
            if (!Files.exists(to)) {
                Files.createDirectories(to.parent)
                Files.copy(from, to)
                copied++
            }
        }
    }
    return copied
}
```

- 现有文件优先，不覆盖、不移动；
- 只补本地缺失文件；
- `CommitResult` 增加 `merged` 计数（UI 不依赖）；
- 目标目录不存在时仍整体移动（首次导入路径不变）；
- `sameTree` 相同仍走 `unchanged` 快路径；
- 合并复制的文件不参与 `rollback`（只新增，不破坏现有数据）。

### E6. 测试

- `ImportMergeTest`（纯 JVM）：
  - 新书 `episodes = maxOf`、`importHash = null`；
  - 已存在书保留 `titleZh/importHash`，补齐缺失 `author`；
  - 现有状态较新：保留进度；收藏并集；`hidden` 保留；
  - 备份状态较新：采用备份进度；
  - `missingChapters` 只返回缺失 key。
- `ImportCoordinatorTest` 增加真实回归：第一次导入后改书名/章节名/进度，
  第二次导入同一 zip，断言修改仍在。
- `LibraryCommitterTest` 增加：
  - 目标目录已有 `zh/0001.txt`，staging 只有 `raw/0001.txt` 与 `raw/0002.txt`：
    合并不删除 `zh`，补上 `raw/0002.txt`，保留原有 `raw/0001.txt` 内容。

### E7. 版本与文档

- `versionCode = 59`，`versionName = "1.8.0"`。
- 更新 `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。

## 2. 实施顺序

1. `ImportMerge` 纯函数 + 测试。
2. `BackupImportService.apply` 接入合并。
3. `LibraryCommitter` 目录合并 + 测试。
4. `ImportCoordinatorTest` 真实重复导入回归。
5. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 300，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 59。

## 4. 风险

- 「保留现有」意味着用户不能靠导入旧备份回退书名/标签/文件；这是有意的数据保护。
- `updated_at` 字符串按 ISO-8601 字典序比较；旧数据格式不一致时可能误判，
  缺失时间戳一律保留现有，偏保守。
- 目录合并只补缺失文件；备份中同名但内容不同的文件不会覆盖现有，
  用户若确实想恢复旧正文，需要手动处理 `.bak` 或删除本地文件后再导入。
