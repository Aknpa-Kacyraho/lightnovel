# Round 23 · 工程师视角升级指南（v1.8.1）

> 基线：1.8.0 / versionCode 59；预计 302 tests。
> 本轮三个小修复：sidecar 版本字段、EPUB 注音、备份路径过滤。

## 1. 工程问题与方案

### E1. 单段重译覆盖整章版本字段（P1）

`TranslationService.retranslateParagraph` 的 sidecar：

```kotlin
old.copy(
    status = ...,
    contentSha256 = Hashes.sha256(newText),
    translationConfigHash = config.cacheKey(),      // ← 覆盖整章
    modelProvider = config.provider,
    modelId = config.model,
    promptVersion = config.promptVersion,
    glossaryRevision = config.glossaryRevision...,
    storyRevision = config.storyRevision...,
    glossaryHash = config.glossaryHash... ?: old.glossaryHash, // ← 覆盖整章
    ...
)
```

其他段落仍是旧术语/旧配置，但整章被标成新版本，`staleReasons` 不再提示。

**方案**：抽出内部纯函数，只更新内容相关字段；版本字段全部保留 `old`：

```kotlin
internal fun retranslatedParagraphSidecar(
    old: ChapterSidecar,
    newText: String,
    tokens: ChapterTokens,
    cost: ChapterCost,
    incomplete: List<Int>,
): ChapterSidecar = old.copy(
    status = if (incomplete.isEmpty()) "complete" else "partial",
    contentSha256 = Hashes.sha256(newText),
    translatedAt = Instant.now().toString(),
    tokens = tokens,
    cost = cost,
    incompleteParagraphs = incomplete,
    incompleteReason = if (incomplete.isEmpty()) null else old.incompleteReason,
)
```

`old.copy` 保留 `translationConfigHash/modelProvider/modelId/promptVersion/
glossaryRevision/storyRevision/glossaryHash`。`retranslateParagraph` 用该函数。

**测试**：新增 `ParagraphRetranslationSidecarTest`：
- old 带 `glossaryHash="old-g"`、`translationConfigHash="old-c"`；
- 构造新 tokens/cost/incomplete；
- 断言结果保留两个旧 hash、`status` 正确、`contentSha256` 更新。

### E2. EPUB 注音节点（P2）

`LocalTextParser.stripHtml` 直接 `replace(Regex("<[^>]+>"), "")`，
`<rt>`/`<rp>` 的文本会留在正文。

**方案**：先移除注音节点，再处理换行：

```kotlin
internal fun stripHtml(html: String): String {
    val withoutRuby = html
        .replace(Regex("""<rt\b[^>]*>.*?</rt>""", RUBY_OPTIONS), "")
        .replace(Regex("""<rp\b[^>]*>.*?</rp>""", RUBY_OPTIONS), "")
    val withBreaks = withoutRuby
        .replace(Regex("""<br\s*/?>""", RegexOption.IGNORE_CASE), "\n")
        ...
}
```

`RUBY_OPTIONS = setOf(IGNORE_CASE, DOT_MATCHES_ALL)`。`stripHtml` 改为 `internal` 以便测试。

**测试**：`LocalTextParserTest` 新增：
- `<ruby>漢字<rt>かんじ</rt></ruby>` → `漢字`；
- `<ruby>東京<rp>(</rp><rt>とうきょう</rt><rp>)</rp></ruby>` → `東京`。

### E3. 备份路径过滤（P2）

`BackupExporter.filesUnder` 只检查 `name.contains(".bak-")`，不检查目录。
`novels/book.bak-20260101/raw/0001.txt` 会被导出。

**方案**：抽纯函数：

```kotlin
internal fun isExportableRelativePath(rel: String): Boolean {
    val parts = rel.split('/')
    if (parts.any { it.contains(".bak-") }) return false
    if (rel.contains("/cache/")) return false
    val name = parts.lastOrNull().orEmpty()
    return !name.contains(".tmp-") &&
        !name.endsWith(".part") &&
        !name.endsWith(".restore-tmp")
}
```

`filesUnder` 用它替代现有内联过滤。

**测试**：`BackupFilesTest` 新增 4 条：
- `book.bak-20260101/raw/0001.txt` → false；
- `book/cache/x.json` → false；
- `book/raw/0001.txt` → true；
- `book/raw/0001.txt.tmp-123` → false。

### E4. 版本与文档

- `versionCode = 60`，`versionName = "1.8.1"`。
- 更新 `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。

## 2. 实施顺序

1. `retranslatedParagraphSidecar` + 测试；改 `retranslateParagraph`。
2. `stripHtml` 注音清理 + 测试。
3. `isExportableRelativePath` + 测试；改 `filesUnder`。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 302，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 60。

## 4. 风险

- 单段重译后整章仍显示过期，用户可能重复点整章重译；这是事实正确的提示。
- `<rt>` 可能包含有意义的注释（非注音）；移除后只保留基准汉字，符合轻小说正文预期。
- `.bak-*` 目录不再进入备份；用户若需要旧文件，只能从本地 `.bak` 目录手动取。
