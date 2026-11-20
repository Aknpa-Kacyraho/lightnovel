# Round 15 · 工程师视角升级指南（v1.5.2）

> 基线：1.5.1 / versionCode 51。本轮是 UI 容器调整，业务回调不动。
> 书架先做（低风险），阅读器 Sheet 后做（涉及渲染层）。

## 1. 工程问题与方案

### E1. 书架书架下拉（P1）

`LibraryScreen` 的筛选行删除「全部/在读/想读/读完」四个 chip，替换为：

```kotlin
var shelfMenuOpen by remember { mutableStateOf(false) }
Box {
    BrandFilterChip(
        selected = true,
        onClick = { shelfMenuOpen = true },
        label = { Text("书架：${shelfLabel(state.shelf) ?: "全部"}") },
    )
    DropdownMenu(...) {
        listOf<Pair<String?, String>>(
            null to "全部",
            "reading" to "在读",
            "want" to "想读",
            "finished" to "读完",
        ).forEach { (value, label) ->
            DropdownMenuItem(
                text = { Text((if (state.shelf == value) "✓ " else "") + label) },
                onClick = {
                    shelfMenuOpen = false
                    onShelfChange(value)
                    onFavoritesOnlyChange(false)
                    onRemovedOnlyChange(false)
                },
            )
        }
    }
}
```

注意：现有「全部」chip 会同时清 favorites/removedOnly；下拉里的「全部」等价。
`setShelf` 在 ViewModel 已清 `removedOnly`，但不清 favorites；UI 显式清，保持旧行为。

**测试**：筛选逻辑不变，无需新测试；`LibraryEmptyStateTest` 已覆盖空态。

### E2. 阅读器菜单 Sheet（P1）

新增 `ReaderMenuSheet.kt`：

```kotlin
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReaderMenuSheet(
    items: List<ReaderMenuItem>,
    theme: ReaderTheme,
    onDismiss: () -> Unit,
    onSelect: (ReaderMenuItem) -> Unit,
)
```

- `ModalBottomSheet` + `LazyColumn`，最大高度 70%；
- 组标题：遍历 items，组变化时插入标题 + `HorizontalDivider`；
- 项：`DropdownMenuItem` 风格（用 `Row + clickable` 或 Material `ListItem`），
  `enabled` 决定 alpha 与点击；
- 点击：`onSelect(item)`，由调用方关闭 Sheet 并执行 when。

`TranslationMenu`：
- 移除 `DropdownMenu` 与 `expanded` 逻辑，改为 `var sheetOpen`；
- 「更多」按钮 → `sheetOpen = true`；
- `ReaderMenuSheet(items, theme, onDismiss = { sheetOpen = false }) { item -> form(...) }`；
- `when (item.action)` 的现有分支保持不变，抽成局部函数 `handle(item)`。

**注意**：`TranslationMenu` 目前没有 `theme` 参数，只有 `textColor`。
Sheet 需要纸色背景：加 `theme: ReaderTheme` 参数（ReaderTopBar 已有 `textColor`，
可传 `readerTheme` 或新增参数）。最小改动：给 `ReaderTopBar`/`TranslationMenu`
加 `theme: ReaderTheme`。

### E3. 测试

- `ReaderMenuTest` 仍只测数据（16/15 项），不受容器影响；
- 书架下拉无纯函数，人工与现有 `LibraryEmptyStateTest` 覆盖。

### E4. 版本与文档

- `versionCode = 52`，`versionName = "1.5.2"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. 书架筛选下拉 + 文案。
2. `ReaderMenuSheet` + `TranslationMenu` 接入。
3. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥258，0 failures；lint 0 errors，warning ≤22；APK versionCode 52。

## 4. 风险

- 书架下拉「全部」与旧「全部」chip 的清空行为必须一致，避免筛选残留。
- 菜单 Sheet 的 `LazyColumn` 需要稳定 key（用 action.name），否则滚动跳动。
- `TranslationMenu` 的 `when` 分支多，抽局部函数时逐项对照，避免漏项。
