# Round 2 · 工程师视角升级指南（v1.1.0）

> 基线：1.0.4 / versionCode 38；178 JVM tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。
> 本轮不引入新依赖、不改 Room schema、不改翻译管线。

## 1. 工程问题与方案

### E1. 空态逻辑散落在 Composable 里，无法回归（P1）

`LibraryScreen.kt:306-346` 用嵌套 `when` 决定标题、说明和按钮。
文案与「是否筛选 / 是否已移出」耦合，改文案容易改坏分支。

**方案**：抽纯函数（放 `feature/library/LibraryEmptyState.kt`）：

```kotlin
data class EmptyShelfCopy(
    val title: String,
    val message: String,
    val primary: EmptyAction,      // OPEN_DISCOVER / CLEAR_FILTERS
    val secondary: List<EmptyAction> = emptyList(),
)
enum class EmptyAction { OPEN_DISCOVER, IMPORT_BACKUP, IMPORT_DOCUMENT, CLEAR_FILTERS }

fun emptyShelfCopy(query: String, favoritesOnly: Boolean, removedOnly: Boolean, shelf: String?): EmptyShelfCopy
```

**测试**：`LibraryEmptyStateTest` 覆盖「已移出」「有搜索」「有收藏」「有书架筛选」「纯空」五种。

### E2. 设置页无法定位分组（P1）

`SettingsScreen` 是 `Column + verticalScroll`，没有可寻址的分组 id。

**方案**：

- `SettingsRoute` / `SettingsScreen` 增加 `focus: String?` 与 `onFocusConsumed: () -> Unit`；
- `LightnovelNavHost` 用 `remember { mutableStateOf<String?>(null) }` 保存待定位分组，
  书架备份提醒设置 `"backup"` 后切 Tab；
- 「数据」分组 `Modifier.onGloballyPositioned { dataTop = it.positionInParent().y.toInt() }`；
- `LaunchedEffect(focus)` 等待 `dataTop > 0`，`animateScrollTo((dataTop - 16).coerceAtLeast(0))`，
  高亮 2 秒后回调 `onFocusConsumed()`；
- `SettingsGroup` 增加 `modifier` 与 `highlighted`，用 `animateColorAsState` 淡出，
  不写死颜色。

**测试**：定位是 UI 行为，JVM 只测 `SettingsFocus.parse(raw): String?`（白名单
`backup`，其余 null），保证脏路由参数不会误滚动。

### E3. 阅读器菜单硬编码 13 项（P1）

`ReaderComponents.kt:405-501` 平铺 `DropdownMenuItem`，新增功能只能继续堆。

**方案**：定义为数据驱动列表（`ReaderMenu.kt`）：

```kotlin
internal enum class ReaderMenuGroup(val label: String) { READING("阅读"), TRANSLATION("翻译"), REFERENCE("资料"), WORLDLINE("世界线") }
internal data class ReaderMenuEntry(val group: ReaderMenuGroup, val label: String, val enabled: Boolean = true, val onClick: () -> Unit)
```

`TranslationMenu` 只负责渲染：组标题 + `HorizontalDivider` + 菜单项。
`onClick` 仍直接调用原回调，不加中间层状态。

**测试**：`ReaderMenuTest` 断言 4 组都存在、每组至少 1 项、原 13 个动作标签一个不少
（防止重构漏项）。

### E4. 任务统计与筛选是两套逻辑（P2）

`TaskCenterViewModel` 已提供 `setFilter`，统计数字来自 `state.failed/partial/translating`。
UI 只需把统计项变成可点击并复用 `setFilter`，不需要新状态。

**测试**：`TaskGroupingTest` 补一条：筛选 `FAILED` 时 `groups` 只含 failed 任务，
且 `total` 与 `groups.flatMap` 数量一致。

### E5. 版本与文档

- `versionCode = 39`，`versionName = "1.1.0"`。
- `CHANGELOG.md` 增 1.1.0 段。
- `04-final.md` §8.1 增 1.1.0。
- `PROGRESS.md` 更新状态。

## 2. 实施顺序

1. 空态纯函数 + 测试 + UI 接入。
2. 设置 `focus` 参数与滚动高亮。
3. 菜单数据化与分组渲染。
4. 任务统计点击。
5. 版本、文档。
6. 全量验证 + 构建 + 提交 + tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

通过标准：

- tests ≥178，0 failures；新增 `LibraryEmptyStateTest`、`ReaderMenuTest`；
- lint 0 errors，warning 数不高于 22；
- 不改动 `schemas/`、`MIGRATION_*`、备份格式；
- Debug APK 可安装。

## 4. 风险

- 设置滚动定位依赖首帧布局；若 `dataTop` 长时间为 0，用超时 1 秒兜底，绝不阻塞 UI。
- 菜单分组只改渲染顺序，不改任何业务回调；`ReaderMenuEntry` 的 `enabled` 必须
  与原条件一一对应（翻译需 `enabled`，润色需 `enabled && hasTranslation`）。
- 空态文案变化可能影响截图对比（无截图测试），人工核对 360dp。
