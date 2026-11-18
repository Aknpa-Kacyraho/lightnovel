# Round 3 · 工程师视角升级指南（v1.1.1）

> 基线：1.1.0 / versionCode 39。测试预计 178 + 新增（空态 5、设置 3、菜单 5、任务 1）。
> 本轮不拆 `ReaderViewModel`（50KB+，行为风险高），只做可验证的自适应与清理。

## 1. 工程问题与方案

### E1. 排版宽度是硬计算，无法单测（P1）

`ReaderRoute.kt:479-484` 直接 `maxWidth - margin*2`。横屏限宽要改计算，
但 UI 里算完就没法回归。

**方案**：抽纯函数（`reader/ReaderViewport.kt`）：

```kotlin
internal const val READER_MAX_CONTENT_DP = 680
internal fun readerContentWidthDp(screenWidthDp: Float, marginDp: Float): Float =
    (minOf(screenWidthDp, READER_MAX_CONTENT_DP) - marginDp * 2f).coerceAtLeast(1f)
```

`BoxWithConstraints` 里用 `widthIn(max = READER_MAX_CONTENT_DP.dp)` + 该函数换算 px。
**测试**：`ReaderViewportTest` 覆盖手机、680、平板三种宽度与 margin 最小值。

### E2. 翻译字数提示没有统一口径（P1）

`ReaderRoute` 手上有 `state.chapterText`，但菜单在 `ReaderComponents`。
新增 `charCount: Int` 参数传递；格式化抽纯函数：

```kotlin
internal fun formatCharCount(count: Int): String? = when {
    count <= 0 -> null
    count < 1000 -> "约 ${count} 字"
    else -> "约 %.1f 千字".format(count / 1000f)
}
```

`readerMenuItems(...)` 增加 `charCount: Int = 0`，`TRANSLATE` 标签拼上括号。
**测试**：`ReaderMenuTest` 补 0 / 800 / 1200 三档。

### E3. 大字体换行（P1）

任务卡动作行、空态次级入口改 `FlowRow`：

```kotlin
@OptIn(ExperimentalLayoutApi::class)
FlowRow(
    modifier = Modifier.fillMaxWidth(),
    horizontalArrangement = Arrangement.End,
    verticalArrangement = Arrangement.spacedBy(4.dp),
) { ... }
```

空态次级入口 `horizontalArrangement = Arrangement.Center`。
不改按钮尺寸与主题。

### E4. 长章节提示（P2）

`ReaderRoute` 增加：

```kotlin
var showSlowPagination by remember { mutableStateOf(false) }
LaunchedEffect(state.loading, state.layout) {
    if (state.loading || state.layout == null) {
        delay(300)
        showSlowPagination = true
    } else {
        showSlowPagination = false
    }
}
```

注意 effect 取消时 `showSlowPagination` 可能残留，离开阅读器无影响；重新进入是新组合。
显示在 `CircularProgressIndicator` 下方。

### E5. 弃用 API（P2）

- `TabRow` → `PrimaryTabRow`（`ChapterListScreen.kt:382`、`StoryMemoryScreen.kt:159`）；
  先本地目视，若指示器压字则回退并记录。
- `ClickableText`（`ReaderRoute.kt:945`）**不本轮改**：点词依赖字符 offset，
  改 `LinkAnnotation` 需要重写命中映射，风险大于收益，Round 4 评估。
- `UseKtx` 12 条、依赖版本提示：不动。升级依赖需要单独回归，不混在体验版。

### E6. 版本与文档

- `versionCode = 40`，`versionName = "1.1.1"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`。
- `round-3/SELF-REVIEW.md`。

## 2. 实施顺序

1. `ReaderViewport` + 测试 + 横屏限宽。
2. 字数格式化 + 菜单参数 + 测试。
3. `FlowRow` 两处。
4. 长章节提示。
5. `TabRow` 替换与目视检查。
6. 版本、文档、全量验证、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥186，0 failures；lint 0 errors，warning ≤22；APK 可安装。

## 4. 风险

- `BoxWithConstraints` 内再加 `widthIn` 可能让 `HorizontalPager` 的高度测量变化；
  必须 `fillMaxHeight()`，否则翻页区域会塌缩。
- `FlowRow` 的 `Arrangement.End` 在换行后仍右对齐，符合现有按钮行视觉。
- 字数格式化用 `String.format` 需要 `Locale.US`，避免某些区域设置用逗号小数点。
- `PrimaryTabRow` 的 API 在 Material3 版本中可能仍标记 Experimental，需加
  `@OptIn(ExperimentalMaterial3Api::class)`（文件已有）。
