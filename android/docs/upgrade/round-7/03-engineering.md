# Round 7 · 工程师视角升级指南（v1.3.0）

> 基线：1.2.2 / versionCode 43；220 JVM tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。
> 本轮有 Room 迁移（v3 → v4），先写迁移与测试，再做导入与排序。

## 1. 工程问题与方案

### E1. 本地导入没有身份（P0）

`LocalDocumentImporter.kt:62` 用 UUID 做 id，`books` 表没有内容指纹；
`(source, source_id)` 唯一索引对本地书无效（source_id 也是随机 id）。

**方案**：`books` 增加 `import_hash TEXT` 与唯一索引。

```kotlin
// BookEntity
@ColumnInfo(name = "import_hash") val importHash: String? = null,
```

```kotlin
val MIGRATION_3_4 = object : Migration(3, 4) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE books ADD COLUMN import_hash TEXT")
        db.execSQL(
            "CREATE UNIQUE INDEX IF NOT EXISTS index_books_import_hash ON books(import_hash)",
        )
    }
}
```

- 数据库版本 `4`，`LightnovelApp` 注册 `MIGRATION_3_4`；
- SQLite 唯一索引允许多个 `NULL`，在线书不受影响；
- `schemas/4.json` 必须提交（`exportSchema = true`）。

**迁移测试**：`MigrationTest` 加 `migration3To4AddsImportHash`：
建 v3 表 → 插入一行 → 迁移 → 断言列存在、旧行 `import_hash IS NULL`。

### E2. 导入去重与恢复（P0）

`LocalDocumentImporter`：

1. 读 bytes 后先算 SHA-256（`MessageDigest`，16KB buffer 或一次性，文件已 ≤80MB）；
2. `dao.bookByImportHash(hash)`；
3. 命中：
   - 若 `read_state.hidden = 1` → `restoreBook`（或 `updateHidden(false)`），返回 `existing = true, restored = true`；
   - 否则直接返回 `existing = true`；
4. 未命中：走现有解析与写入，`BookEntity.importHash = hash`。

返回类型改为：

```kotlin
data class LocalImportResult(
    val book: BookEntity,
    val existing: Boolean,
    val restored: Boolean,
)
```

`LibraryViewModel` 按 `existing/restored` 给三种文案：
「已导入《X》」/「《X》已在书架，没有重复添加」/「《X》已恢复到书架」。

**测试**：`LocalDocumentImporter` 依赖 ContentResolver，JVM 下用 Robolectric
`ApplicationProvider` + 临时文件 Uri 可测；至少覆盖「同 bytes 第二次导入返回 existing」。

### E3. 书架排序（P1）

新增纯函数（`feature/library/LibrarySort.kt`）：

```kotlin
enum class LibrarySort(val id: String, val label: String) {
    TITLE("title", "标题"),
    RECENT("recent", "最近阅读"),
    ADDED("added", "最近添加"),
}

internal fun sortLibrary(books: List<BookWithState>, sort: LibrarySort): List<BookWithState>
```

- TITLE：`(titleZh ?: title)` 比较，忽略大小写；
- RECENT：`state.updatedAt ?: openedAt ?: finishedAt ?: book.createdAt` 降序，空值排后；
- ADDED：`book.createdAt` 降序，空值排后；
- 全部使用稳定排序（`sortedWith` + 原始顺序 tie-break）。

`SettingsStore` 增加 `librarySort: String = "title"`（DataStore key `library_sort`），
`LibraryViewModel` 读取并 `setSort` 写回；`LibraryUiState` 增加 `sort`。
DAO 仍按 title 返回，排序在 Repository/ViewModel 层完成（避免 SQL 动态排序）。

**测试**：`LibrarySortTest` 三种排序 + 空时间 + 中文标题；`SettingsStoreTest` 默认值。

### E4. 版本与文档

- `versionCode = 44`，`versionName = "1.3.0"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. v4 迁移 + schema + 迁移测试。
2. BookEntity/DAO/importHash + 导入去重 + ViewModel 文案。
3. LibrarySort + SettingsStore + UI chip。
4. 版本、文档、全量验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥220，0 failures；lint 0 errors，warning ≤22；APK versionCode 44。

## 4. 风险

- Room 迁移与 `BookEntity` 必须完全一致，否则 `MigrationTest` 或启动校验失败。
- `import_hash` 唯一索引在极端情况下（哈希碰撞）会阻挡导入；SHA-256 可忽略。
- 排序在内存完成，书很多（>1000）时有轻微开销；当前规模可接受。
- 重复导入恢复 hidden 书会改变 `updated_at`，可能把它推到「继续阅读」前面；
  恢复后应保留 `progressIdx`，但 `updated_at` 更新是预期（用户刚操作过）。
