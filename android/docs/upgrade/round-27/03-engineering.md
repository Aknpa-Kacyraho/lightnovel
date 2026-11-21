# Round 27 · 工程师视角升级指南（v1.9.0）

> 基线：1.8.4 / versionCode 63；313 JVM tests。
> 本轮只建立 token 并替换硬编码，不改布局与数据。

## 1. 工程问题与方案

### E1. 主题没有注入 Typography / Shapes（P1）

`LightnovelTheme` 目前只传 `colorScheme`：

```kotlin
MaterialTheme(
    colorScheme = colors,
    content = content,
)
```

全 App 因此使用 Material3 默认排版与默认圆角；各页面又各自硬编码
`RoundedCornerShape(6/8/9/10/12/14/16/50)`，没有统一来源。

### E2. 新增 `LnTypography`（P1）

`ui/theme/LnTypography.kt`：

```kotlin
val LnTypography = Typography(
    titleLarge = TextStyle(
        fontSize = 20.sp,
        lineHeight = 28.sp,
        fontWeight = FontWeight.SemiBold,
        letterSpacing = 0.sp,
    ),
    titleMedium = TextStyle(16.sp, 24.sp, FontWeight.Medium),
    titleSmall = TextStyle(14.sp, 20.sp, FontWeight.Medium),
    bodyLarge = TextStyle(16.sp, 26.sp, FontWeight.Normal),
    bodyMedium = TextStyle(14.sp, 22.sp, FontWeight.Normal),
    bodySmall = TextStyle(13.sp, 20.sp, FontWeight.Normal),
    labelLarge = TextStyle(13.sp, 18.sp, FontWeight.Medium),
    labelMedium = TextStyle(12.sp, 16.sp, FontWeight.Medium),
    labelSmall = TextStyle(11.sp, 15.sp, FontWeight.Normal),
)
```

未覆盖的角色沿用 Material3 默认；`letterSpacing` 统一 0。

### E3. 新增 `LnShapes`（P1）

`ui/theme/LnShapes.kt`：

```kotlin
val LnShapes = Shapes(
    extraSmall = RoundedCornerShape(4.dp),
    small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(12.dp),
    large = RoundedCornerShape(16.dp),
    extraLarge = RoundedCornerShape(20.dp),
)
```

`LightnovelTheme` 注入：

```kotlin
MaterialTheme(
    colorScheme = colors,
    typography = LnTypography,
    shapes = LnShapes,
    content = content,
)
```

### E4. 替换硬编码圆角（P1）

| 文件 | 现状 | 改为 |
| --- | --- | --- |
| `BookCover.kt` | 12dp | `MaterialTheme.shapes.small` |
| `BrandChips.kt` FilterChip | 9dp | `MaterialTheme.shapes.small` |
| `BrandChips.kt` LnTag | 8dp | 6dp（标签专用） |
| `BrandChips.kt` StatusBadge | 6dp | `MaterialTheme.shapes.extraSmall` |
| `SettingsScreen.kt` 分组卡 | 16dp | `MaterialTheme.shapes.medium` |
| `SettingsScreen.kt` 主题卡 | 12dp | `MaterialTheme.shapes.medium` |
| `ChapterListScreen.kt` 卡片 | 16dp | `MaterialTheme.shapes.medium` |
| `QuerySheet.kt` 14/12/8 | 混合 | `medium` / `small` |
| `ReaderRoute.kt` 提示条 | 10dp | `MaterialTheme.shapes.small` |

### E5. 降低描边（P2）

- `LibraryScreen` 的 `ContinueCard` / `BookRow`：
  `outlineVariant.copy(alpha = 0.6f)` → `0.35f`。
- `SettingsScreen` 的 `SettingsGroup`：`outlineVariant` → `.copy(alpha = 0.5f)`。
- `ChapterListScreen` 中同类卡片同步降到 0.35f。
- 不新增阴影；`Card` 默认 elevation 保持 0。

### E6. 测试与版本

- 新增 `ThemeTokensTest`（纯 JVM）：
  - `LnTypography.bodyLarge.fontSize == 16.sp`、`lineHeight == 26.sp`；
  - `LnTypography.titleLarge.fontWeight == FontWeight.SemiBold`；
  - `LnShapes.small` 的 `topStart` 为 8dp（通过 `CornerSize` 比较）。
- `versionCode = 64`，`versionName = "1.9.0"`。
- 更新 `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。

## 2. 实施顺序

1. `LnTypography` / `LnShapes` + 注入 + 测试。
2. 替换硬编码圆角。
3. 降低描边。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 316，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 64。

## 4. 风险

- 全局 Typography 会改变所有页面的文字高度，个别固定高度行（如 56dp 目录行）
  需要确认不裁切；本轮只改字号/行高，56dp 仍能容纳 20sp 行高。
- `LnShapes` 不改变 Material3 `Button` 的胶囊形状（Button 默认 `full`）；
  本轮不动按钮，避免大面积视觉跳变。
- 标签 6dp 是唯一不落在五档上的例外，注释说明。
