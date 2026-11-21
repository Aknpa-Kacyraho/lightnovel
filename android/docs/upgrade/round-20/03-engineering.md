# Round 20 · 工程师视角升级指南（v1.7.1）

> 基线：1.7.0 / versionCode 56；预计 277 JVM tests。
> 本轮只动 `ReadingTranslationCoordinator` 的出队、归类与暂停，不碰翻译内容。

## 1. 工程问题与方案

### E1. 自动目标压过手动目标（P1）

`runWorker` 现状：

```kotlin
queue.autoTargets.firstOrNull() ?: queue.manualTargets.firstOrNull()
```

`request()` 每次滚动都会清空并重建 `autoTargets`，而 `manualTargets` 只在
`enqueue()` 时追加。结果：只要自动计划非空，手动队列永远排在后面。

**方案**：抽出纯函数并反转优先级：

```kotlin
internal fun pickNextIndex(
    manual: Collection<Int>,
    auto: Collection<Int>,
): Int? = manual.firstOrNull() ?: auto.firstOrNull()
```

`runWorker` 改为 `pickNextIndex(queue.manualTargets, queue.autoTargets)`。
自动预译不会丢：手动队列清空后继续。

**测试**：`TranslationQueuePolicyTest`：
- 手动 `[30]` + 自动 `[12, 13]` → `30`；
- 手动空 → `12`；
- 两者都空 → `null`。

### E2. 重复任务被计为失败（P2）

`translateTarget` 中：

```kotlin
if (!taskRegistry.register(book.id, index, child)) {
    child.cancel()
    return@coroutineScope null
}
...
null -> TargetResult(false)
```

`runWorker` 把 `success=false` 且不可重试的目标 `failed++`。

**方案**：`TargetResult` 增加 `skipped`，`register` 失败返回
`TargetResult(success = false, skipped = true)`；归类改成纯函数：

```kotlin
internal enum class TargetDisposition { COMPLETED, RETRY, FAILED, SKIPPED }

internal fun dispositionOf(
    success: Boolean,
    skipped: Boolean,
    retryable: Boolean,
    alreadyRetried: Boolean,
): TargetDisposition = when {
    success -> TargetDisposition.COMPLETED
    skipped -> TargetDisposition.SKIPPED
    retryable && !alreadyRetried -> TargetDisposition.RETRY
    else -> TargetDisposition.FAILED
}
```

`runWorker` 按结果更新计数：`SKIPPED` 不动 `completed`/`failed`。

**测试**：四种结果各一条；`alreadyRetried=true` 的可重试失败归 `FAILED`。

### E3. 暂停不取消当前请求（P2）

`pause` 现状：

```kotlin
queue.paused = true
if (queue.runningIndex == null) {
    queue.worker?.cancel()
    queue.worker = null
}
```

正在跑的章节不会被取消，UI 却立即显示暂停。

**方案**：无论是否在跑都取消：

```kotlin
queue.paused = true
queue.worker?.cancel()
queue.worker = null
queue.runningIndex = null
publishLocked()
```

- `translate()` 内部会 `markCancelled`，已写入的段落缓存保留；
- `resume()` 重新 `ensureWorkerLocked`；
- 旧 worker 的 `finally` 因 `queue.worker !== self` 不会重复清理或重启。

**测试**：行为依赖真实协程调度，JVM 不做集成断言；在自检中说明，
并用代码审查确认 `finally` 的 `worker === self` 保护仍然成立。

### E4. 版本与文档

- `versionCode = 57`，`versionName = "1.7.1"`。
- 更新 `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`。
- 指南与自检写入 `android/docs/upgrade/round-20/`。

## 2. 实施顺序

1. `pickNextIndex` / `dispositionOf` + 测试。
2. `runWorker` 接入新优先级与归类。
3. `pause` 立即取消。
4. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥ 277，0 failures；lint 0 errors / ≤22 warnings；
APK versionCode 57。

## 4. 风险

- 手动优先意味着「翻译全书」期间自动预译暂停；这是预期，手动队列本身已覆盖后续章。
- 暂停取消当前章会产生 `partial` 状态（已译段落保留），恢复后只补缺失段。
- `pause` 在锁内调用 `cancel()` 只标记取消，不会阻塞等待；worker 的清理在 `finally` 中完成。
