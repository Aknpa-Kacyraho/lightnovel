# Round 11 · 工程师视角升级指南（v1.4.1）

> 基线：1.4.0 / versionCode 47。搜索是纯 IO + 纯函数，先写可测的匹配逻辑，再接 UI。
> 不新增数据库表、不建全文索引（当前书最多几百章，逐章扫描可接受）。

## 1. 工程问题与方案

### E1. 匹配与段落定位（P0）

正文段落由 `Paragraphs.split(...)` 切分（空行优先，单换行回退），段落 ID 必须与
阅读器内部一致，否则跳转会错段。

**方案**（`feature/reader/BookSearch.kt`）：

```kotlin
data class TextHit(
    val paragraphId: Int,
    val before: String,
    val match: String,
    val after: String,
)

internal fun findHits(text: String, query: String, max: Int = 3): List<TextHit> {
    val needle = query.trim()
    if (needle.isEmpty()) return emptyList()
    val hits = mutableListOf<TextHit>()
    Paragraphs.split(text).forEachIndexed { index, paragraph ->
        if (hits.size >= max) return@forEachIndexed
        val at = paragraph.indexOf(needle, ignoreCase = true)
        if (at < 0) return@forEachIndexed
        val start = (at - 20).coerceAtLeast(0)
        val end = (at + needle.length + 20).coerceAtMost(paragraph.length)
        hits += TextHit(
            paragraphId = index,
            before = (if (start > 0) "…" else "") + paragraph.substring(start, at),
            match = paragraph.substring(at, at + needle.length),
            after = paragraph.substring(at + needle.length, end) +
                (if (end < paragraph.length) "…" else ""),
        )
    }
    return hits
}
```

**测试**：`BookSearchTest`：
空查询、无命中、大小写不敏感、前后文截断、同段只取第一处、`max` 上限。

### E2. 逐章扫描（P0）

`BookSearchService`（无状态，可在 ViewModel 内创建）：

```kotlin
class BookSearchService(private val contentStore: ContentStore) {
    suspend fun search(
        book: BookEntity,
        chapters: List<ChapterEntity>,
        query: String,
        preferTranslated: Boolean,
        limit: Int = 30,
    ): List<BookSearchHit> = withContext(Dispatchers.IO) { ... }
}
```

- 优先读 `readZh`；译文缺失或原文模式读 `readRaw`；
- 每章 `findHits(..., max = 3)`，总数到 `limit` 停止；
- 章节标题用 `titleZh ?: title ?: "第 N 话"`；
- 不把整本书读进内存：一次一章，命中即释放。

### E3. ViewModel 状态（P1）

```kotlin
private var searchJob: Job? = null
private val _searchResults = MutableStateFlow<List<BookSearchHit>>(emptyList())
val searchResults: StateFlow<List<BookSearchHit>>
private val _searching = MutableStateFlow(false)
val searching: StateFlow<Boolean>
val searchScope: String get() = if (_state.value.displayMode == "raw") "原文" else "译文"

fun searchBook(query: String) {
    searchJob?.cancel()
    if (query.isBlank()) {
        _searchResults.value = emptyList()
        return
    }
    searchJob = viewModelScope.launch {
        _searching.value = true
        val hits = BookSearchService(contentStore).search(
            book = bookEntity ?: return@launch,
            chapters = chapterList,
            query = query,
            preferTranslated = _state.value.displayMode != "raw",
        )
        _searchResults.value = hits
        _searching.value = false
    }
}
```

- 取消由 `searchJob` 控制；Sheet 关闭时调 `clearSearch()`；
- 防抖在 UI（300ms）做，ViewModel 不再加延迟。

### E4. UI（P1）

新增 `BookSearchSheet`：

- `OutlinedTextField` 自动聚焦；
- `LaunchedEffect(query) { delay(300); onSearch(query) }`；
- 结果行用 `AnnotatedString` 高亮 `match`；
- 点击结果回调 `onJump(hit)`；关闭时清空。

`ReaderRoute` 跳转：
- 同章 → `viewModel.jumpToAnchor(ReaderAnchor(hit.chapterIndex, hit.paragraphId, 0))`；
- 跨章 → `onOpenChapter(hit.chapterIndex)`。

**测试**：UI 不测；`BookSearchTest` 覆盖匹配与段落 ID。

### E5. 版本与文档

- `versionCode = 48`，`versionName = "1.4.1"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. `findHits` + `BookSearchTest`。
2. `BookSearchService`。
3. ViewModel 状态与 `searchBook`。
4. `BookSearchSheet` + 菜单项 + 跳转。
5. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥239，0 failures；lint 0 errors，warning ≤22；APK versionCode 48。

## 4. 风险

- 大章节（数万字）`Paragraphs.split` 会产生较多对象；单章处理可接受，未做流式。
- 搜索会读取最多几百个文件；在 IO 线程、逐章进行，用户取消即停止。
- 段落 ID 与阅读器分页的 anchor 同源（`Paragraphs.split`），但译文变化后 ID 可能漂移。
