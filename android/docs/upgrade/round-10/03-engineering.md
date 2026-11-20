# Round 10 · 工程师视角升级指南（v1.4.0）

> 基线：1.3.2 / versionCode 46；239 JVM tests / 0 failures / 1 skipped。
> 本轮新增数据库 v5（书签）。先迁移与 DAO，再 ViewModel，最后 UI。

## 1. 工程问题与方案

### E1. 书签存储（P0）

`bookmarks` 表：

```kotlin
@Entity(
    tableName = "bookmarks",
    primaryKeys = ["book_id", "chapter_idx", "paragraph_id"],
    indices = [Index(value = ["book_id", "chapter_idx"])],
)
data class BookmarkEntity(
    @ColumnInfo(name = "book_id") val bookId: String,
    @ColumnInfo(name = "chapter_idx") val chapterIdx: Int,
    @ColumnInfo(name = "paragraph_id") val paragraphId: Int,
    @ColumnInfo(name = "char_offset") val charOffset: Int,
    val preview: String,
    @ColumnInfo(name = "created_at") val createdAt: String,
)
```

- 主键 = 书 + 章 + 段：同一段重复添加是幂等 upsert；
- `MIGRATION_4_5` 建表与索引；`version = 5`，`schemas/5.json` 提交；
- 迁移测试：建 v4 的 `books/read_state/chapters` 最小表 → 迁移 → 断言 `bookmarks` 存在。

### E2. DAO / Repository（P0）

```kotlin
@Query("SELECT * FROM bookmarks WHERE book_id = :bookId ORDER BY chapter_idx, paragraph_id")
fun observeBookmarks(bookId: String): Flow<List<BookmarkEntity>>

@Upsert
suspend fun upsertBookmark(bookmark: BookmarkEntity)

@Query("DELETE FROM bookmarks WHERE book_id = :bookId AND chapter_idx = :chapterIdx AND paragraph_id = :paragraphId")
suspend fun deleteBookmark(bookId: String, chapterIdx: Int, paragraphId: Int)

@Query("SELECT * FROM bookmarks WHERE book_id = :bookId AND chapter_idx = :chapterIdx AND paragraph_id = :paragraphId LIMIT 1")
suspend fun bookmark(bookId: String, chapterIdx: Int, paragraphId: Int): BookmarkEntity?
```

`LibraryRepository` 增加对应方法（书签属于阅读数据，沿用现有仓库）。

**测试**：`LibraryDaoTest`：
- 插入两条不同段书签 → `observeBookmarks` 数量 2；
- 同段重复 upsert → 仍 1 条，preview 更新；
- 删除 → 0 条。

### E3. ViewModel（P0）

```kotlin
val bookmarks: StateFlow<List<BookmarkEntity>> = repository
    .observeBookmarks(bookId)
    .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

fun addBookmark() {
    val anchor = currentAnchor()
        ?: if (_state.value.readerMode == "scroll") {
            ReaderAnchor(chapterIndex, _state.value.scrollParagraph, 0)
        } else null
        ?: return
    val preview = _state.value.paragraphs
        .getOrNull(anchor.paragraphId)
        ?.text
        ?.trim()
        ?.take(40)
        .orEmpty()
    viewModelScope.launch {
        repository.upsertBookmark(
            BookmarkEntity(
                bookId = bookId,
                chapterIdx = chapterIndex,
                paragraphId = anchor.paragraphId,
                charOffset = anchor.charOffset,
                preview = preview.ifBlank { "第 ${anchor.paragraphId + 1} 段" },
                createdAt = Instant.now().toString(),
            ),
        )
        _bookmarkNotice.emit("已添加书签")
    }
}

fun jumpToAnchor(anchor: ReaderAnchor) {
    viewModelScope.launch {
        repository.updateProgress(bookId, anchor)
        anchorToRestore = anchor
        lastKey = null
        load()
    }
}
```

- `currentAnchor()` 已有，直接复用；
- 同章跳转写进度 + `load()`；`load()` 里的 `restore` 会读到刚写的进度，定位一致；
- **跨章不在此处理**：Route 判断 `bookmark.chapterIdx != state.chapterIndex` 时调
  `onOpenChapter(chapterIdx)`，落在该章开头（V1 明确限制）。

### E4. 菜单与 Sheet（P1）

- `ReaderMenu.kt` 增加 `ADD_BOOKMARK`、`OPEN_BOOKMARKS`；
  「添加书签」放 `READING` 组，「书签列表」放 `REFERENCE` 组；
- `readerMenuItems(...)` 增加 `hasBookmarkHere: Boolean`，文案变「已添加书签」；
- 新增 `BookmarkSheet.kt`：`ModalBottomSheet`，列表 + 删除 + 空态；
- 时间格式化抽纯函数 `relativeTime(iso, now)`（刚刚/N 分钟前/N 小时前/N 天前/日期）。

**测试**：`BookmarkTimeTest` 覆盖刚刚、分钟、小时、天、7 天以上、非法输入。

### E5. 版本与文档

- `versionCode = 47`，`versionName = "1.4.0"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. DB v5 + Entity/DAO + 迁移测试。
2. Repository + ViewModel（bookmarks、add、jump）。
3. 菜单项 + BookmarkSheet + 时间格式化。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥239，0 failures；lint 0 errors，warning ≤22；APK versionCode 47。

## 4. 风险

- 书签主键含 `paragraph_id`：分页/译文变化后段落 ID 可能漂移；
  `charOffset` 暂不参与定位，V1 接受。后续可用 charOffset + 文本指纹重定位。
- 同章跳转写进度会改变「继续阅读」位置，符合用户预期（跳转即阅读位置）。
- 跨章书签只到章首；文档与空态都要说明，避免用户以为坏了。
