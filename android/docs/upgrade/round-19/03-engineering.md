# Round 19 · 工程师视角升级指南（v1.7.0）

> 基线：1.6.2 / versionCode 55；274 JVM tests。
> 本轮修「状态机漏出口」与「写回破坏原文布局」两个数据路径 bug。

## 1. 工程问题与方案

### E1. `translate()` 只处理了取消，没处理异常（P1）

`TranslationService.translate` 的现状：

```kotlin
val outcome = try {
    translator.translate(...)
} catch (error: CancellationException) {
    withContext(NonCancellable) { markCancelled(book, chapterIndex) }
    throw error
}
```

`ChapterTranslator` 只 catch `TranslationException`；`store.save` 的 IO 异常、
`dao.updateChapterTranslation` 的 SQLite 异常、解析越界等都会向上传播。
此时 DB 里已经是 `translating`，没有任何路径把它改回 `failed`。

**方案**：

```kotlin
val outcome = try {
    translator.translate(...)
} catch (error: CancellationException) {
    withContext(NonCancellable) { markCancelled(book, chapterIndex) }
    throw error
} catch (error: Exception) {
    withContext(NonCancellable) {
        dao.updateChapterTranslation(
            bookId = book.id,
            idx = chapterIndex,
            status = "failed",
            model = settings.deepSeekModel,
            tokenIn = 0,
            tokenOut = 0,
            updatedAt = Instant.now().toString(),
        )
    }
    return TranslationOutcome.Failed(
        "翻译异常：${error.message?.take(120) ?: "未知错误"}",
        retryable = true,
    )
}
```

- 放在现有的 `catch (CancellationException)` 之后，保证取消语义不变；
- 用 `NonCancellable` 写状态，避免清理动作被同一次取消带走；
- 不吞 `Error`（`OutOfMemoryError` 等），只 catch `Exception`。

**测试**：`TranslationServiceTest` 新增用例：fake client 抛
`IllegalStateException`，断言 `outcome is Failed`、`dao` 状态为 `failed`、
`store.readZh` 为 null。

### E2. `retranslateParagraph` 用固定 `\n\n` 写回（P1）

现状：

```kotlin
val newParagraphs = zhParagraphs.toMutableList().apply { this[paragraphIndex] = result.text }
val newText = newParagraphs.joinToString("\n\n")
```

`ChapterTranslator.translateBatch` 的输出是 `paragraphs.joinToString("\n")`；
单换行章节被单段重译后变成空行分隔，`chapterBlocks`（`split("\n")`）多出空行。

**方案**：按原文的字符区间替换，不动其它字符：

```kotlin
val oldParagraph = zhParagraphs[paragraphIndex]
val start = Paragraphs.startOffset(zh, paragraphIndex)
val newText = if (start >= 0 && zh.startsWith(oldParagraph, start)) {
    zh.replaceRange(start, start + oldParagraph.length, result.text)
} else {
    // 回退：沿用旧行为，但按原文是否含空行选择分隔符
    val separator = if (Regex("""\n[ \t]*\n""").containsMatchIn(raw)) "\n\n" else "\n"
    newParagraphs.joinToString(separator)
}
```

- `Paragraphs.startOffset` 已存在，按段号定位并处理重复文本；
- 只替换段落文字，分隔符原样保留；
- 回退分支保证极端情况下仍能写回。

**测试**：在 `TranslationServiceTest` 新增用例：原文/译文均为单换行
`a\nb\nc`，重译第 1 段，断言写回文本仍为 3 行、不含 `\n\n`，且第 2/3 段未变。

### E3. `translateOne` 对不可重试错误仍重试（P2）

现状：

```kotlin
repeat(2) {
    try { ... } catch (_: TranslationException) { /* retry once */ }
    delay(400)
}
```

**方案**：

```kotlin
} catch (error: TranslationException) {
    if (!error.retryable) return null
}
```

保留一次可重试错误的重试；不可重试立即返回 `null`，由调用方提示失败。

**测试**：fake client 记录调用次数，抛 `retryable = false`，
断言只调用 1 次且返回 `Failed`。

### E4. 版本与文档

- `versionCode = 56`，`versionName = "1.7.0"`。
- 更新 `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。
- 指南与自检写入 `android/docs/upgrade/round-19/`。

## 2. 实施顺序

1. `translate()` 异常兜底 + 测试。
2. `retranslateParagraph` 区间替换 + 测试。
3. `translateOne` 尊重 `retryable`。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 274，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 56。

## 4. 风险

- 异常兜底会捕获 `store.save` 失败；此时缓存文件可能写了一半，但 `FileTranslationStore`
  本身就是临时文件 + 原子移动，最坏是旧缓存，不影响正确性。
- 区间替换依赖 `Paragraphs.startOffset` 与实际译文一致；不一致时回退到按分隔符 join。
- 新增 catch 不会改变 `TranslationException` 的重试路径（它在 `ChapterTranslator` 内被消化）。
