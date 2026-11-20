# Round 5 · 工程师视角升级指南（v1.2.1）

> 基线：1.2.0 / versionCode 41。本轮只改主题 token 与三个列表卡片，不动业务逻辑。
> 主题是全 App 输入，必须用断言守住对比度，避免「调好看」变成「调不可读」。

## 1. 工程问题与方案

### E1. 深色主题没有对比度回归（P0）

`Theme.kt` 的 8 套 dark Palette 是手写常量，改一个值没有测试会阻断。
深色下一次「降亮」很容易把次要文字降到 4.5:1 以下。

**方案**：新增 `ThemeContrastTest`（Robolectric，`@Config(sdk = [35])`）：

```kotlin
AppTheme.entries.forEach { theme ->
    val scheme = colorSchemeFor(theme, dark = true)
    val secondary = contrastRatio(scheme.onSurfaceVariant.toArgb(), scheme.surface.toArgb())
    val primary = contrastRatio(scheme.onSurface.toArgb(), scheme.surface.toArgb())
    assertTrue("$theme 次要文字 $secondary", secondary in 7.0..10.0)
    assertTrue("$theme 主文字 $primary", primary >= 12.0)
}
```

同时断言 `scheme.onSurfaceVariant` vs `scheme.surfaceVariant` ≥4.5（标签文字）。

### E2. 容器混合比例是魔法数（P1）

`toScheme` 里 `0.30f` 重复三次（secondary/tertiary/error）。

**方案**：抽常量：

```kotlin
private const val DARK_CONTAINER_MIX = 0.24f
private const val LIGHT_CONTAINER_MIX = 0.14f
```

三处共用，避免只改一处导致不一致。

### E3. 列表卡片的容器与描边不统一（P1）

`BookRow`、`ContinueCard`、`TaskCard` 都用默认 `Card`，描边由各自主题决定；
深色下描边偏亮。

**方案**：三处统一：

```kotlin
Card(
    colors = CardDefaults.cardColors(
        containerColor = MaterialTheme.colorScheme.surfaceContainerLow,
    ),
    border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.6f)),
)
```

`ContinueCard` 是横向小卡，也统一；`SettingsGroup` 不改。

### E4. 测试与依赖

- `ThemeContrastTest` 需要 `androidx.compose.ui.graphics.toArgb`，Robolectric 环境下可用；
- 复用 Round 4 的 `contrastRatio`（`feature.reader`），不重复实现；
- 不新增依赖。

### E5. 版本与文档

- `versionCode = 42`，`versionName = "1.2.1"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. `Theme.kt` 调整 8 套 dark `onSurfaceVariant`、容器混合常量。
2. `ThemeContrastTest`。
3. 三处卡片统一容器/描边。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥199，0 failures；lint 0 errors，warning ≤22；APK versionCode 42。

## 4. 风险

- `onSurfaceVariant` 也用于标签文字（`tagKeywordContent`）与 `tagSourceContent`，
  降亮后标签对比度可能接近 4.5:1；测试覆盖 `surfaceVariant` 组合。
- 卡片描边 0.6 alpha 在浅色下会更淡；浅色本来不刺眼，视觉需要真机确认（无 adb）。
- 主题改动影响所有页面，但不改变布局与业务；回滚只需还原 `Theme.kt` 与三处 Card。
