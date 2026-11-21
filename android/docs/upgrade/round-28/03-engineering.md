# Round 28 · 工程师视角升级指南（v1.9.1）

> 基线：1.9.0 / versionCode 64。本轮只改 Compose 布局与样式，不动数据。

## 1. 工程问题与方案

### E1. 书架行去卡片化（P1）

`LibraryScreen.BookRow` 现在：

```kotlin
Card(
    colors = CardDefaults.cardColors(containerColor = surfaceContainerLow),
    border = BorderStroke(1.dp, outlineVariant.copy(alpha = 0.35f)),
) {
    Row(modifier = Modifier.padding(start = 12.dp, ...)) { ... }
}
```

`LazyColumn` 用 `contentPadding = 16.dp` + `spacedBy(10.dp)`。

**方案**：

```kotlin
Column(modifier = modifier.fillMaxWidth()) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(start = 16.dp, end = 4.dp, top = 12.dp, bottom = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        BookCover(... 48.dp x 72.dp ...)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) { title / meta / progress }
        menuButton
    }
    HorizontalDivider(
        modifier = Modifier.padding(start = 76.dp, end = 16.dp),
        thickness = 1.dp,
        color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.28f),
    )
}
```

- `LazyColumn(contentPadding = PaddingValues(vertical = 8.dp), verticalArrangement = spacedBy(0.dp))`；
- 进度改为自绘 2dp `Box`（两层，track 0.12 / fill 0.35），不用
  `LinearProgressIndicator`（Material3 默认 4dp 且有停靠点）；
- 行高约 96dp，触控目标仍 ≥44dp。

### E2. 封面统一 2:3（P2）

- `RecommendationCard`：`width(148.dp)` → `width(140.dp)`，
  封面 `height(188.dp)` → `height(210.dp)`。
- `SourceResultCard`：封面 `64×88` → `60×90`；内边距保持 12dp。
- `BookRow` 封面 `52×72` → `48×72`。
- `BookCover` 的形状已统一为 `MaterialTheme.shapes.small`。

### E3. 发现卡标签收敛（P2）

`SourceResultCard` 现在 `pairs.take(3)` 全部渲染。改为：

```kotlin
pairs.take(2).forEach { ... }
if (pairs.size > 2) {
    Text("+${pairs.size - 2}", style = labelSmall, color = onSurfaceVariant)
}
```

不加新 chip，避免横向溢出。

### E4. 设置分组去卡片（P2）

`SettingsGroup` 现在是一个 16dp 圆角 + 描边 Card。改为：

```kotlin
Column(modifier = modifier.fillMaxWidth()) {
    Text(
        title,
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(start = 2.dp, bottom = 8.dp),
    )
    val container by animateColorAsState(
        if (highlighted) MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.35f)
        else Color.Transparent,
        label = "settings-group-highlight",
    )
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(container, MaterialTheme.shapes.medium)
            .padding(if (highlighted) 12.dp else 0.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        content()
    }
}
```

- `SettingsScreen` 根 `Column(spacedBy(14.dp))` 不变；
- `ThemePreviewCard` 保留 Card（视觉选择器需要边界）；
- 删除 `SettingsGroup` 的 `CardDefaults`/`BorderStroke` 使用（若其他组件仍在用则保留 import）。

### E5. 版本与文档

- `versionCode = 65`，`versionName = "1.9.1"`。
- 更新 `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。

## 2. 实施顺序

1. 书架 `BookRow` + 列表间距 + 进度线。
2. 封面比例与发现卡标签。
3. 设置分组去卡片。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 316，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 65。

## 4. 风险

- 去卡片后，行与行之间只靠 1dp 线；深色主题下 0.28 可能太淡，
  自检时确认仍可辨。
- `SettingsGroup` 的 `highlighted` 背景只包内容，不包标题；
  滚动定位 `dataTop` 仍以组顶部为准，不受影响。
- 推荐卡变高会让横向列表整体变高，需确认不挤压下方内容。
