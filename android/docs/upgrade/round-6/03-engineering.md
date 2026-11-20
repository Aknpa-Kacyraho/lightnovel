# Round 6 · 工程师视角升级指南（v1.2.2）

> 基线：1.2.1 / versionCode 42。本轮动阅读器手势与两条进度线，业务零改动。
> 手势是高风险区：单击/滑动/查询点词必须互斥，先写清楚判定顺序再改。

## 1. 工程问题与方案

### E1. 单击没有统一出口（P1）

`ReaderPageView.handleTap` 只在点中实体时回调；普通点击被吞掉。
沉浸切换需要一个新的 `onCenterTap`，但必须保留查询模式的优先级。

**方案**：

```kotlin
var onEntityClick: ((String) -> Unit)? = null
var onCenterTap: (() -> Unit)? = null

private fun handleTap(event: MotionEvent) {
    if (onEntityClick != null) {
        val id = entityAt(event.x, event.y) ?: return   // 查询模式：只处理词条
        onEntityClick?.invoke(id)
        return
    }
    onCenterTap?.invoke()
}
```

- 查询模式开着时，点击空白不切换沉浸（避免「想点词却把界面藏了」）；
- 普通模式点击任何空白 → 切换沉浸；
- `ACTION_UP` 且 `!moved` 才走到这里，横向滑动仍由 Pager 处理。

`ReaderRoute` 的 `AndroidView.update` 里设置：
`view.onCenterTap = { immersive = !immersive }`。

**测试**：手势依赖 Android View，无 JVM 测试；靠 lint（`ClickableViewAccessibility` 已清零）
与真机验证，自检如实记录。

### E2. 进度计算散落在 UI（P1）

底栏页码用字符串拼，继续阅读卡用 `progressIdx` 直接算。

**方案**：新增纯函数（`feature/reader/ReaderProgress.kt`）：

```kotlin
internal fun readerChapterProgress(
    scrollMode: Boolean,
    pageIndex: Int,
    pageCount: Int,
    scrollParagraph: Int,
    blockCount: Int,
): Float

internal fun shelfProgress(progressIdx: Int, episodes: Int): Float
```

- 都返回 0..1；
- 0 页 / 0 段 / 0 话返回 0；
- `pageIndex + 1` / `scrollParagraph + 1` 表示「已到当前页/段」。

**测试**：`ReaderProgressTest` 覆盖翻页首末、滚动首末、0 值、越界。

### E3. 底栏与卡片加线（P2）

- `ReaderBottomBar` 增加 `progress: Float` 参数，在 Row 上方渲染
  `LinearProgressIndicator(progress = { progress })`，`Modifier.fillMaxWidth().height(2.dp)`，
  `color = textColor.copy(alpha = 0.28f)`，`trackColor = Color.Transparent`；
- `ContinueCard` 在「第 N 话」下方加同尺寸进度线，`color = primary.copy(alpha = 0.45f)`；
- 两处都不改字号、间距（只加 2dp + 4dp padding）。

### E4. 首次沉浸提示（P2）

`ReaderRoute`：

```kotlin
var showImmersiveHint by remember { mutableStateOf(false) }
LaunchedEffect(immersive) {
    if (!immersive) { showImmersiveHint = false; return@LaunchedEffect }
    showImmersiveHint = true
    delay(3_000)
    showImmersiveHint = false
}
```

`LaunchedEffect` 以 `immersive` 为 key：每次进入沉浸都会提示一次（同一章内重复进入也算），
符合「第一次进入时出现」的宽松解释；若嫌频繁，可在后续用 `rememberSaveable` 记录本章已提示。

显示位置：沉浸态底部「退出沉浸」按钮上方，`labelSmall` + `secondaryColor`。

### E5. 版本与文档

- `versionCode = 43`，`versionName = "1.2.2"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. `ReaderProgress` + 测试。
2. `ReaderPageView` 点击回调 + `ReaderRoute` 接线。
3. 底栏进度线 + 沉浸提示。
4. 继续阅读卡进度线。
5. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥199，0 failures；lint 0 errors，warning ≤22；APK versionCode 43。

## 4. 风险

- 单击切换沉浸可能与「点正文复制/选词」未来功能冲突；当前没有选词，先占用手势。
- 进度线使用 `LinearProgressIndicator`，在夜间纸色下 0.28 alpha 可能太淡；
  真机确认，必要时提高到 0.35（不改结构）。
- `ContinueCard` 的 `episodes` 可能为 0，必须走 `shelfProgress` 的 0 分支。
