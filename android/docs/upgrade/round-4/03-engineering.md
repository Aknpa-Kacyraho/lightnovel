# Round 4 · 工程师视角升级指南（v1.2.0）

> 基线：1.1.1 / versionCode 40；199 JVM tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。
> 本轮不改翻译管线、不改 Room、不新增依赖。

## 1. 工程问题与方案

### E1. 纸色是「用户选择」与「实际显示」混在一起（P0）

`ReaderViewModel.kt:201` 把 `settings.readerTheme` 直接放进 `state.theme`，
`ReaderRoute.kt:255` 直接 `ReaderTheme.fromId(state.theme)` 当显示主题。
要支持「跟随系统」，必须把**偏好**与**解析结果**分开。

**方案**：

```kotlin
enum class ReaderTheme(...) {
    AUTO("auto", "跟随系统", PaperColor, ...),   // 占位色，不会被直接渲染
    PAPER, SEPIA, GREEN, NIGHT;

    fun resolve(dark: Boolean): ReaderTheme =
        if (this != AUTO) this else if (dark) NIGHT else PAPER
}
```

- `ReaderRoute`：`val readerTheme = ReaderTheme.fromId(state.theme).resolve(isSystemInDarkTheme())`；
- `state.theme` 始终保存用户偏好（可能是 `auto`），
  `persistSettings()` 回写 `current.theme`，不会把解析结果写回去；
- 所有 Sheet / 字段色 / 状态栏图标都用解析后的 `readerTheme`，不直接读 `state.theme`。

**测试**：`ReaderThemeTest`：
`auto + dark → NIGHT`、`auto + light → PAPER`、`paper + dark → PAPER`、
`night + light → NIGHT`、未知 id → PAPER。

### E2. 默认值变更不能回写老用户（P0）

`SettingsStore` 默认 `readerTheme = "paper"`，改为 `"auto"` 只影响**没有该键**的安装。
`SettingsStore.update` 会写全量字段，因此解析只在读取时发生，不回写。

**测试**：`SettingsStoreTest` 补一条：空 prefs → `readerTheme == "auto"`；
显式存 `paper` → 读回 `paper`。

### E3. 横幅可见性没有回归（P0）

`TranslationStatusBanner` 的分支在 Composable 内，`title == null` 才 return，
但「未翻译」总是有 title。

**方案**：抽纯函数（`feature/reader/ReaderBanner.kt`）：

```kotlin
internal fun shouldShowTranslationBanner(
    status: TranslationStatus,
    hasTranslation: Boolean,
    running: Boolean,
    hasTask: Boolean,
    hasError: Boolean,
    hasMessage: Boolean,
    queueActive: Boolean,
    queuePaused: Boolean,
    queueError: Boolean,
): Boolean
```

「未译全/失败」仍显示；「未翻译且没有任何进行中/错误/队列」返回 false。
Composable 在计算 title 前调用它，false 直接 return。

**测试**：`ReaderBannerTest` 覆盖 5 种：未翻译安静、未翻译但运行中、
失败、预译暂停、有一次性消息。

### E4. 夜间对比度没有守护（P1）

夜间的正文/次要文字色是常量，改一次就可能跌破可读阈值。

**方案**：新增 `ReaderContrast.kt` 纯函数：

```kotlin
internal fun contrastRatio(foreground: Long, background: Long): Double
```

按 WCAG 相对亮度计算（`Color.luminance()` 可用，但为可测性用 Long 色值）。
`ReaderThemeTest` 断言：
- `NIGHT.text` vs `NIGHT.background` ≥ 7.0；
- `NIGHT.secondary` vs `NIGHT.background` ≥ 3.0（次要文字下限）；
- `PAPER` / `SEPIA` / `GREEN` 正文 ≥ 7.0。

### E5. 版本与文档

- `versionCode = 41`，`versionName = "1.2.0"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、本目录 `SELF-REVIEW.md`。

## 2. 实施顺序

1. `ReaderTheme` 增加 `AUTO` + `resolve` + 测试。
2. `ReaderRoute` 解析 + 默认值 + `SettingsStoreTest`。
3. 夜间正文调色 + 对比度测试。
4. 横幅纯函数 + 接入 + 测试。
5. 版本、文档、全量验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥199，0 failures；lint 0 errors，warning ≤22；APK 可安装。

## 4. 风险

- `ReaderTheme.entries` 现在包含 `AUTO`：设置页会多一项（预期）；
  阅读器「切换纸色」循环会先到 `AUTO`（预期）；`entries` 上任何假设「全部可直接渲染」
  的代码都要改用解析后的主题。
- `isSystemInDarkTheme()` 在阅读器内是 Compose 状态，系统切换时会重组并重新解析；
  `DisposableEffect(readerTheme)` 会恢复/设置状态栏图标，需确认不会闪烁。
- 夜间正文调色影响所有引用块、术语下划线；测试只覆盖主文本，视觉需真机确认（无 adb）。
