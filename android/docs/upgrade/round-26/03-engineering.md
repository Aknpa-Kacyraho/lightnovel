# Round 26 · 工程师视角升级指南（v1.8.4）

> 基线：1.8.3 / versionCode 62；311 JVM tests。
> 本轮修一类系统性问题：`runCatching` 与 `catch (Exception)` 吞掉
> `CancellationException`，导致取消后继续请求/写入。

## 1. 工程问题与方案

### E1. 统一的「可取消 runCatching」（P1）

Kotlin 的 `runCatching` 会捕获所有 `Throwable`，包括
`kotlinx.coroutines.CancellationException`。在挂起调用外层使用它，
协程取消会被转成 `Result.failure`，流程继续执行。

新增 `core/util/Cancellation.kt`：

```kotlin
package com.kacyraho.lightnovel.core.util

import kotlinx.coroutines.CancellationException

suspend inline fun <T> runCatchingCancellable(
    crossinline block: suspend () -> T,
): Result<T> = try {
    Result.success(block())
} catch (error: CancellationException) {
    throw error
} catch (error: Exception) {
    Result.failure(error)
}
```

**测试**：`CancellationTest`：
- 抛 `CancellationException` → 原样抛出；
- 抛普通异常 → `Result.failure`。

### E2. 替换挂起调用处的 `runCatching`（P1）

只替换**包裹挂起调用**的位置；包裹纯解析（`json.decodeFromString`）的
`runCatching` 保持不动。

- `StoryMemoryService`：`generateSummary` / `extractCharacters` / `scanNames`
  的 `client.complete` 三处。
- `MetadataTranslationService`：`translateBook` / `translateTitles` /
  `translateBook` 另一分支 / `translateCards` / `translateTitles` 变体
  共 5 处 `client.complete`。
- `WorldlineService.diffReport`：`completeWithRetry` 一处。
- `KakuyomuSource.recommend`：`discoverPage` 与 `fetch` 两处。
- `SyosetuSource.search` / `recommend`：`runCatching` 包裹挂起请求的位置。

### E3. `KnowledgeExtractionService` 的 catch 顺序（P2）

现状：

```kotlin
try { ... } catch (error: TranslationException) {
    return Result.failure(error)
} catch (error: Exception) {
    return Result.failure(IllegalStateException("知识抽取返回无法解析：..."))
}
```

`CancellationException` 会被第二个 catch 吞掉。加：

```kotlin
} catch (error: CancellationException) {
    throw error
} catch (error: Exception) {
    ...
}
```

`merge` 之后的 `runCatching { merge(...) }` 包裹的是非挂起逻辑，
保持不动（`seedGlossary` 也是非挂起）。

### E4. 版本与文档

- `versionCode = 63`，`versionName = "1.8.4"`。
- 更新 `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。

## 2. 实施顺序

1. `runCatchingCancellable` + 测试。
2. 替换各模块的挂起调用。
3. `KnowledgeExtractionService` catch 顺序。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 313，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 63。

## 4. 风险

- OkHttp 的同步请求无法中途打断；取消只能让协程在请求返回后不再继续，
  当前请求仍可能占用几秒。
- 替换范围只限挂起调用；纯解析的 `runCatching` 保持不变，避免行为变化。
- `runCatchingCancellable` 是 `inline`，调用处不会新增 lambda 分配。
