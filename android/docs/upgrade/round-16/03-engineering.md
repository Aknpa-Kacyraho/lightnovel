# Round 16 · 工程师视角升级指南（v1.6.0）

> 基线：1.5.2 / versionCode 52；264 JVM tests。本轮修「行号 ↔ 段号」混用。
> 这是真实数据语义 bug：`progress_block` 是段号，滚动模式却写行号。

## 1. 工程问题与方案

### E1. 抽取行/段映射（P0）

当前 `paragraphIndexForScrollLine` 是 `ReaderViewModel` 的私有方法，
没有反向映射，也无法测试。

**方案**：新增 `feature/reader/ReaderScrollMapping.kt`：

```kotlin
internal fun paragraphIndexForLine(
    paragraphs: List<ReaderParagraph>,
    displayMode: String,
    line: Int,
): Int

internal fun lineForParagraph(
    paragraphs: List<ReaderParagraph>,
    displayMode: String,
    paragraphIndex: Int,
): Int
```

- 行数按段落显示文本的 `split("\n").size` 累加，段间 +1（与现有实现一致）；
- `lineForParagraph` 返回该段起始行，越界钳制；
- 空段落列表返回 0。

**测试**：`ReaderScrollMappingTest`：单段多行、多段、bilingual、空列表、
越界行、往返（段→行→段）。

### E2. 写进度存段号（P0）

`onScrollParagraphChanged(paragraphId)` 当前把 `safe`（行号）直接写进
`progress_block`。

**方案**：

```kotlin
_state.value = _state.value.copy(scrollParagraph = safe, pageIndex = 0)
val state = _state.value
repository.updateProgress(
    bookId,
    ReaderAnchor(
        chapterIndex = chapterIndex,
        paragraphId = paragraphIndexForLine(state.paragraphs, state.displayMode, safe),
        charOffset = 0,
    ),
)
```

- `scrollParagraph` 仍存行号；
- DB 存段号。

### E3. 恢复时把段号换算成行号（P0）

`load()` 中：

```kotlin
scrollParagraph = restore?.paragraphId ?: 0,
```

改为：

```kotlin
scrollParagraph = if (_state.value.readerMode == "scroll") {
    restore?.let {
        lineForParagraph(_state.value.paragraphs, _state.value.displayMode, it.paragraphId)
    } ?: 0
} else {
    restore?.paragraphId ?: 0
},
```

注意 `_state.value.paragraphs` 必须在赋值前已更新（当前代码先 copy 再设置？检查顺序，
必要时用局部 `readerChapter` 计算）。

### E4. 书签与翻译锚点（P0）

`addBookmark()` 与 `translateChapter()` 的滚动分支：

```kotlin
ReaderAnchor(chapterIndex, currentParagraphIndex(), 0)
```

`currentParagraphIndex()` 已做行→段映射（翻页模式取当前页 startAnchor）。
这样预览、跳转、DB 都是段号。

### E5. 滚动列表响应跳转（P1）

`ReaderScreen` 的滚动分支加：

```kotlin
LaunchedEffect(state.scrollParagraph) {
    if (state.scrollParagraph in blocks.indices &&
        listState.firstVisibleItemIndex != state.scrollParagraph
    ) {
        listState.scrollToItem(state.scrollParagraph)
    }
}
```

- 只对滚动模式生效（该 composable 本身只在滚动分支）；
- 等值不滚，避免与用户滚动打架；
- 不新增动画。

### E6. 版本与文档

- `versionCode = 53`，`versionName = "1.6.0"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. `ReaderScrollMapping` + 测试。
2. ViewModel 写进度/恢复/书签/翻译锚点。
3. 滚动列表 effect。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥264，0 failures；lint 0 errors，warning ≤22；APK versionCode 53。

## 4. 风险

- 已有用户的 `progress_block` 里可能存了行号；修复后首次恢复会按行号当段号，
  可能偏几段。无法区分旧数据，接受一次性偏差。
- 映射函数依赖 `paragraphs` 与 `chapterBlocks` 的一致性（同一 displayMode）；
  切换语言模式后行数变化，映射会重新计算。
- 滚动列表的 effect 与 `onScrollParagraphChanged` 可能互相触发；等值检查避免循环。
