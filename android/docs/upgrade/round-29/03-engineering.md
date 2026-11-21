# Round 29 · 工程师视角升级指南（v1.9.2）

> 基线：1.9.1 / versionCode 65；316 JVM tests。
> 本轮只改阅读器纸色、警告条颜色与 Sheet 形状。

## 1. 工程问题与方案

### E1. 四套纸色（P1）

`ReaderTheme` 的当前值：

```kotlin
PAPER("paper", "纸白", 0xFFFAFAF7, 0xFF242424, 0xFF6B6B66, ...)
SEPIA("sepia", "米黄", 0xFFF5ECD9, 0xFF3A3226, 0xFF7A6A52, ...)
GREEN("green", "护眼", 0xFFEFF6E9, 0xFF081B16, 0xFF4F6B5D, ...)
NIGHT("night", "夜间", 0xFF121212, 0xFFBDBAB2, 0xFF8E8B84, ...)
```

改为：

```kotlin
PAPER  bg #F8F5EE  text #2A2824  secondary #6E675C
SEPIA  bg #F3E9D2  text #3A3226  secondary #7A6A52
GREEN  bg #EDF2E6  text #22302A  secondary #4F6B5D
NIGHT  bg #171614  text #B8B3A8  secondary #8F8A80
```

`AUTO` 的占位颜色同步成 PAPER 的值；`resolve(dark)` 逻辑不变。
`danger` 保持 `#B3261E`（夜间为 `#FFB4AB`）。

### E2. 警告条从纸色派生（P2）

`ReaderComponents.StaleBanner` 现在：

```kotlin
val background = if (theme == ReaderTheme.NIGHT) Color(0xFF3B2A17) else Color(0xFFFFF1DC)
val foreground = if (theme == ReaderTheme.NIGHT) Color(0xFFFFCC80) else Color(0xFF7A4A00)
```

改为：

```kotlin
val warning = if (theme == ReaderTheme.NIGHT) Color(0xFFD9A45B) else Color(0xFF8A5A00)
val background = lerp(
    theme.background,
    warning,
    if (theme == ReaderTheme.NIGHT) 0.16f else 0.12f,
)
val foreground = warning
```

- import `androidx.compose.ui.graphics.lerp`；
- 圆角改为 `MaterialTheme.shapes.small`；
- 文案与按钮不变。

### E3. 阅读器 Sheet 顶角（P2）

给以下 `ModalBottomSheet` 加：

```kotlin
shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
```

文件与位置：

- `ReaderComponents.kt`（章节信息）
- `ReaderMenuSheet.kt`
- `QuerySheet.kt`（两处）
- `TypographySheet.kt`
- `ParagraphSheet.kt`
- `BookmarkSheet.kt`
- `BookSearchSheet.kt`
- `GlossarySheet.kt`

没有 `RoundedCornerShape` import 的文件补
`import androidx.compose.foundation.shape.RoundedCornerShape`。

### E4. 测试与版本

- `ReaderThemeTest`（若已存在）补充四套纸色的亮度顺序：
  `PAPER/SEPIA/GREEN` 背景亮度 > `NIGHT`；`NIGHT` 背景不是纯黑。
- `versionCode = 66`，`versionName = "1.9.2"`。
- 更新 `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。

## 2. 实施顺序

1. `ReaderTheme` 颜色。
2. `StaleBanner` 派生色。
3. 阅读器 Sheet 顶角。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 316，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 66。

## 4. 风险

- 纸色变暖后，`StaleBanner` 的琥珀文字在纸白上对比约 6:1，仍达标；
- 夜间正文变暗一档，极低亮度下可能显得发灰；自检时确认次要文字仍可读；
- Sheet 顶角只改阅读器，其他页面仍是 28dp；后续可统一，但不属于本轮。
