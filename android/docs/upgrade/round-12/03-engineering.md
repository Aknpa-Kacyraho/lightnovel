# Round 12 · 工程师视角升级指南（v1.4.2）

> 基线：1.4.1 / versionCode 48。本轮 UI 为主，核心是「拖动只更新本地值，
> 结束时才触发分页」与「进度 ↔ 页码」纯函数。

## 1. 工程问题与方案

### E1. 排版设置入口（P0）

已有 ViewModel setter：`setFontSize`、`setLineHeight`、`setReaderMargin`、
`setParagraphSpacing`，都会 `persistSettings()`。

**方案**：新增菜单项 `TYPOGRAPHY`（阅读组），打开 `TypographySheet`：

```kotlin
@Composable
fun TypographySheet(
    fontSizeSp: Float,
    lineHeight: Float,
    marginDp: Float,
    paragraphSpacing: Float,
    theme: ReaderTheme,
    onFontSizeChange: (Float) -> Unit,
    onLineHeightChange: (Float) -> Unit,
    onMarginChange: (Float) -> Unit,
    onParagraphSpacingChange: (Float) -> Unit,
    onReset: () -> Unit,
    onDismiss: () -> Unit,
)
```

- 每个滑块 `remember` 本地值，`onValueChangeFinished` 再回调；
- 「恢复默认」直接回调 `onReset`（ViewModel 写 18/1.7/16/8）。

### E2. 位置保持（P1）

`setFontSize` 等只改状态，分页由 `onViewportChanged` 的 key 触发。
当前 `anchorToRestore` 只在显式设置时使用；字号变化时没有设置锚点。

**方案**：在 ViewModel 加：

```kotlin
private fun captureAnchorForRepagination() {
    if (anchorToRestore == null) {
        anchorToRestore = currentAnchor()
    }
}
```

在 `setFontSize/setLineHeight/setReaderMargin/setParagraphSpacing` 开头调用；
分页完成后 `anchorToRestore` 会被清空。连续调整四项时，第一次捕获的锚点会在
第一次分页后失效；后续调整会用当前页重新捕获，行为一致。

### E3. 进度 ↔ 页码（P1）

底栏拖动需要纯函数：

```kotlin
internal fun progressToPage(progress: Float, pageCount: Int): Int {
    if (pageCount <= 0) return 0
    return (progress.coerceIn(0f, 1f) * (pageCount - 1)).roundToInt()
        .coerceIn(0, pageCount - 1)
}

internal fun pageToProgress(pageIndex: Int, pageCount: Int): Float {
    if (pageCount <= 1) return 0f
    return (pageIndex.toFloat() / (pageCount - 1)).coerceIn(0f, 1f)
}
```

**测试**：`ReaderProgressTest` 补 0 页、1 页、首末、往返。

### E4. 底栏拖动（P1）

`ReaderBottomBar` 增加 `pageIndex: Int`、`pageCount: Int`、`onSeekPage: (Int) -> Unit`：

- 翻页模式：用 `Canvas`/`Box` 画轨道 + thumb，加 `pointerInput` 拖动；
  或直接用 `Slider` 并自定义 colors/thumb（更省事）。
- 拖动中 `var dragProgress by remember`；松手 `onSeekPage(progressToPage(...))`；
- 顶部浮层显示「第 x / y 页」（`labelSmall`），拖动时可见；
- 滚动模式不传 `onSeekPage`，保持原细线。

**实现选择**：用 `Slider` + `Modifier.height(20.dp)`，`thumb = { Box(8.dp 圆点) }`，
`track = { ... }` 自定义 2dp 轨道。避免手写 pointerInput。

### E5. 版本与文档

- `versionCode = 49`，`versionName = "1.4.2"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. `progressToPage` / `pageToProgress` + 测试。
2. ViewModel 锚点捕获。
3. `TypographySheet` + 菜单项。
4. 底栏 Slider + 页码浮层。
5. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥239，0 failures；lint 0 errors，warning ≤22；APK versionCode 49。

## 4. 风险

- `Slider` 默认 thumb 较大；必须用 8dp 自定义 thumb，否则底栏变高。
- 拖动触发 `onPageChanged` 会写进度；只在松手时调用，避免每帧写 DB。
- 滚动模式与分页模式的页码语义不同，本轮只让翻页模式可拖。
