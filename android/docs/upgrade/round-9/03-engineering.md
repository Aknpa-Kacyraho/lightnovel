# Round 9 · 工程师视角升级指南（v1.3.2）

> 基线：1.3.1 / versionCode 45。本轮涉及不可逆删除：先停后台，再删库，最后删文件。
> 顺序错了会留下「有记录没文件」或「worker 删除后写回」。

## 1. 工程问题与方案

### E1. 删除顺序与后台任务（P0）

删除一本书要同时处理：

1. WorkManager 下载任务；
2. 翻译 Job（`TranslationTaskRegistry`）；
3. 预译队列（`ReadingTranslationCoordinator`）；
4. Room 记录；
5. 文件目录（`novels/<storageDir>`）。

**方案**（固定顺序）：

```kotlin
fun deleteBook(bookId: String) {
    viewModelScope.launch {
        downloadScheduler?.cancel(bookId)
        taskRegistry?.cancelBook(bookId)
        onBookRemoved?.invoke(bookId)          // coordinator.stop(bookId)
        val book = repository.deleteBook(bookId) ?: return@launch
        runCatching { contentStore.deleteBook(book.storageDir) }
            .onFailure { _messages.emit("已删除记录，但文件清理失败：${it.message}") }
    }
}
```

- 先停后台，避免删除后 worker 重新写章节；
- 先删 DB，再删文件：文件删失败时书已从书架消失，但残留目录可由后续清理；
  反之（先删文件再删 DB）会让书还在但正文消失，更糟。

### E2. `ContentStore.deleteBook`（P0）

接口增加：

```kotlin
fun deleteBook(storageDir: String)
```

`FileContentStore`：

```kotlin
override fun deleteBook(storageDir: String) {
    val dir = paths(storageDir).root       // novels/<storageDir>
    if (!Files.exists(dir)) return
    Files.walk(dir).use { stream ->
        stream.sorted(Comparator.reverseOrder()).forEach {
            runCatching { Files.deleteIfExists(it) }
        }
    }
}
```

`BookPaths` 已有 root/storageDir，直接用 `root.resolve("novels").resolve(storageDir)`；
**不要**允许删除 `root` 本身（storageDir 为空或含 `..` 时拒绝）。

### E3. DAO / Repository 删除（P0）

```kotlin
@Query("DELETE FROM chapters WHERE book_id = :bookId")
suspend fun deleteChapters(bookId: String)

@Query("DELETE FROM read_state WHERE book_id = :bookId")
suspend fun deleteReadState(bookId: String)

@Query("DELETE FROM books WHERE id = :bookId")
suspend fun deleteBook(bookId: String)
```

`RoomLibraryRepository.deleteBook(bookId): BookEntity?`：

```kotlin
val book = dao.book(bookId) ?: return null
db.withTransaction {
    dao.deleteChapters(bookId)
    dao.deleteReadState(bookId)
    dao.deleteBook(bookId)
}
return book
```

接口签名同步；`BackupImportService` 不受影响。

**测试**：`LibraryDaoTest` 插入书 + 章节 + 状态 → 删除 → 三表均无记录。

### E4. ViewModel 事件与 UI（P1）

- `LibraryViewModel` 增加 `messages: SharedFlow<String>`（`MutableSharedFlow(extraBufferCapacity=8)`）；
- 删除成功/失败通过它发 Snackbar；
- `onBookRemoved: ((String) -> Unit)?` 构造参数，AppContainer 传
  `{ container.readingTranslationCoordinator.stop(it) }`；
- `LibraryRoute` 工厂补两个参数：`contentStore = container.contentStore`、
  `onBookRemoved = { container.readingTranslationCoordinator.stop(it) }`。

UI：
- `BookRow` 增加 `showDelete: Boolean`、`onDelete: () -> Unit`；
- 菜单里条件显示「删除本地数据…」，点击打开独立确认对话框；
- `LibraryScreen` 传 `showDelete = state.removedOnly`。

### E5. 版本与文档

- `versionCode = 46`，`versionName = "1.3.2"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. `ContentStore.deleteBook` + 测试。
2. DAO/Repository 删除 + 测试。
3. ViewModel 事件、coordinator 回调、删除流程。
4. UI 确认框与菜单条件。
5. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥220，0 failures；lint 0 errors，warning ≤22；APK versionCode 46。

## 4. 风险

- **不可逆**：确认框必须默认焦点在「取消」，并在删除按钮用 error 色；
- 文件删除失败不回滚 DB：接受残留目录，错误提示用户；
- 删除世界线/知识库目录在 `novels/<storageDir>` 下，随目录一起删除；
- 备份 zip 不含已删除书（导出时从当前 DB 读取），符合预期。
