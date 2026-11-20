# Round 13 · 工程师视角升级指南（v1.5.0）

> 基线：1.4.2 / versionCode 49；258 JVM tests / 0 failures / 1 skipped。
> 本轮改系统栏、模式行与菜单项，不动分页/翻译/书签。

## 1. 工程问题与方案

### E1. 系统栏隐藏与恢复（P0）

`ReaderRoute` 已有 `DisposableEffect(readerTheme)` 设置状态栏图标明暗，但没有
显示/隐藏控制。

**方案**：新增独立 effect，避免与纸色 effect 抢控制器：

```kotlin
DisposableEffect(immersive) {
    val activity = view.context as? Activity
    val controller = activity?.let { WindowCompat.getInsetsController(it.window, view) }
    if (immersive) {
        controller?.systemBarsBehavior =
            WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        controller?.hide(WindowInsetsCompat.Type.systemBars())
    } else {
        controller?.show(WindowInsetsCompat.Type.systemBars())
    }
    onDispose {
        if (immersive) controller?.show(WindowInsetsCompat.Type.systemBars())
    }
}
```

- `onDispose` 只在 `immersive == true` 时 show，避免退出时多一次无意义调用；
- 不改变 `DisposableEffect(readerTheme)` 的图标颜色逻辑；
- 注意 Activity 可能为 null（预览），全部空安全。

**测试**：系统栏行为无 JVM 测试；靠 lint + 真机，自检如实记录。

### E2. 模式行移除滚动/翻页（P1）

`ReaderRoute` 的模式行删除「滚动/翻页」`TextButton`；阅读器菜单新增
`ReaderMenuAction.TOGGLE_READER_MODE`，文案：

```kotlin
if (_state.value.readerMode == "scroll") "滚动模式" else "翻页模式"
```

点击调用 `onReaderModeChange(if (scroll) "page" else "scroll")`。

**注意**：查询模式的 `◀ ▶` 仍保留在模式行（仅 `queryMode && readerMode != "scroll"`）。

### E3. 移除字号 ±（P1）

`ReaderMenuAction.FONT_DECREASE/FONT_INCREASE` 删除；`ReaderMenuTest` 的
动作集合与数量同步（18 → 17）。

`setFontSize` 仍保留（排版 Sheet 使用）。

### E4. 沉浸底部间距（P2）

沉浸态的 Column 已有 `padding(bottom = ...)`？当前提示 + 按钮在 Column 内。
系统栏隐藏后 `navigationBarsPadding` 变 0；加固定 `padding(bottom = 12.dp)`
到沉浸 Row/Column，保证不贴边。

### E5. 版本与文档

- `versionCode = 50`，`versionName = "1.5.0"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. 系统栏 effect + 沉浸底部间距。
2. 模式行删除滚动/翻页；菜单加模式切换。
3. 菜单删除字号 ±；更新 ReaderMenuTest。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥258，0 failures；lint 0 errors，warning ≤22；APK versionCode 50。

## 4. 风险

- 系统栏隐藏/显示与 `statusBarsPadding` 有动画；快速进出沉浸可能出现短暂跳动。
- `onDispose` 恢复系统栏依赖 Activity 仍存在；返回书架时 Activity 不变，安全。
- 移除字号 ± 后，老用户可能找不到字号；排版 Sheet 已在菜单顶部，可发现性可接受。
