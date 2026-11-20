# Round 14 · 工程师视角升级指南（v1.5.1）

> 基线：1.5.0 / versionCode 50。术语表是 UI + 纯函数；不改存储与翻译。
> 先抽出可测的过滤函数，再接 UI。

## 1. 工程问题与方案

### E1. 术语过滤（P0）

新增纯函数（`feature/memory/GlossaryFilter.kt`）：

```kotlin
internal fun filterGlossary(
    entries: List<GlossaryEntry>,
    query: String,
): List<GlossaryEntry> {
    val needle = query.trim()
    if (needle.isEmpty()) return entries
    return entries.filter { entry ->
        entry.source.contains(needle, ignoreCase = true) ||
            entry.target.contains(needle, ignoreCase = true) ||
            entry.aliases.any { it.contains(needle, ignoreCase = true) }
    }
}
```

**测试**：`GlossaryFilterTest`：空查询返回全部、原文命中、译名命中、别名命中、
大小写、空白查询、无命中。

### E2. TermsTab 状态（P0）

`TermsTab` 增加：

```kotlin
var query by rememberSaveable { mutableStateOf("") }
var pendingDelete by remember { mutableStateOf<GlossaryEntry?>(null) }
val visible = filterGlossary(state.memory.glossary, query)
val duplicate = state.memory.glossary.any {
    it.source.equals(source.trim(), ignoreCase = true)
}
```

- 列表渲染 `visible`；
- 搜索框放在说明与旧词库按钮之后、列表之前；
- 空态区分「还没有术语」与「没有匹配的术语」。

### E3. 覆盖提示（P1）

在保存按钮上方：

```kotlin
if (duplicate && source.isNotBlank()) {
    Text(
        "已存在同名术语，保存会覆盖译名。",
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.tertiary,
    )
}
```

保存逻辑不变（现有 `saveGlossary` 已按 source 覆盖）。

### E4. 删除确认（P1）

列表项「删除」改为 `pendingDelete = entry`；页面底部渲染 `AlertDialog`：
标题带 `source → target`，正文说明过期影响，「删除」用 error 色，
确认后调 `onDeleteGlossary(entry.id)`。

### E5. 版本与文档

- `versionCode = 51`，`versionName = "1.5.1"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. `GlossaryFilter` + 测试。
2. TermsTab 搜索、条数、空态。
3. 覆盖提示。
4. 删除确认对话框。
5. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥258，0 failures；lint 0 errors，warning ≤22；APK versionCode 51。

## 4. 风险

- `rememberSaveable` 的 query 在配置变化后保留，符合预期。
- 删除确认多一步，但术语删除会导致过期标记，值得。
- 过滤只做 UI，不改变 `state.memory.glossary` 本身。
