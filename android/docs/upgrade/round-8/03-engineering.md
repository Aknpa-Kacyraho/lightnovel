# Round 8 · 工程师视角升级指南（v1.3.1）

> 基线：1.3.0 / versionCode 44。本轮改翻译数据一致性与队列重试，不碰书库与 UI 结构。
> 费用预估必须是纯函数，避免在 UI 里散落 token 换算。

## 1. 工程问题与方案

### E1. 单段重译的 sidecar 指纹不完整（P0）

`TranslationService.retranslateParagraph` 的 `old.copy(...)` 只更新了
`contentSha256/translatedAt/tokens/cost/incompleteParagraphs/glossaryRevision`，
漏了 `translationConfigHash`、`modelProvider`、`modelId`、`promptVersion`、`storyRevision`。

**方案**：补齐为与 `polishChapter` 相同的字段集：

```kotlin
val sidecar = old.copy(
    ...,
    translationConfigHash = config.cacheKey(),
    modelProvider = config.provider,
    modelId = config.model,
    promptVersion = config.promptVersion,
    storyRevision = config.storyRevision.takeIf { it.isNotBlank() },
)
```

**测试**：`TranslationServiceTest` 加一条：配置变化后单段重译，断言 sidecar 的
`translationConfigHash == config.cacheKey()` 且 `modelId` 为新模型。

### E2. 费用预估（P1）

新增 `feature/reader/CostEstimator.kt`：

```kotlin
data class CostRange(val minCny: Double, val maxCny: Double)

internal fun estimateTranslationCost(
    charCount: Int,
    priceInCnyPerMillion: Double,
    priceOutCnyPerMillion: Double,
): CostRange
```

token 经验值（日文→中文）：

- 输入：`chars * 0.6 ~ 0.9`；
- 输出：`chars * 0.9 ~ 1.3`；
- 金额 = tokens / 1e6 × 单价；
- `charCount <= 0` 或单价 <=0 → 0。

格式化：

```kotlin
internal fun formatCostRange(range: CostRange): String
```

- 上限 < 0.01 → `"< ¥0.01"`；
- 否则 `"¥%.2f–%.2f"`（两位小数，`Locale.US`）。

**测试**：`CostEstimatorTest` 覆盖 0 字、1000 字、价格 0、格式化三档。

**接入**：
- `readerMenuItems(..., costLabel: String? = null)`：翻译项标签拼 `（$costLabel）`；
- `ReaderRoute` 用 `state.chapterText.length` 与 `state` 当前价格计算；
- 章节列表批量确认文案加一行「按每千字约 < ¥0.01 估算，实际以 token 计费」，
  不伪造总额（raw 未下载时无法知道字数）。

### E3. 队列对可重试失败再试一次（P1）

`translateTarget` 目前返回 `Boolean`，丢失 `TranslationOutcome.Failed.retryable`。

**方案**：

```kotlin
private data class TargetResult(val success: Boolean, val retryable: Boolean = false)
```

- `Failed -> TargetResult(false, outcome.retryable)`；
- `null`（被注册表拒绝）→ `TargetResult(false, false)`。

`BookQueue` 加 `retriedTargets: MutableSet<Int>`；`runWorker`：

```kotlin
if (!result.success && shouldRetryAfterFailure(target, queue.retriedTargets, result.retryable)) {
    queue.retriedTargets += target
    queue.manualTargets += target      // 排到队尾
} else {
    if (result.success) queue.completed++ else queue.failed++
}
```

纯函数（可测）：

```kotlin
internal fun shouldRetryAfterFailure(index: Int, retried: Set<Int>, retryable: Boolean): Boolean =
    retryable && index !in retried
```

`stop()` 清空 `retriedTargets`；`enqueue` 手动重试也要清掉该章的 retried 标记，
否则用户手动重试后不再自动重试（可接受，但显式清更直观）。

**测试**：`QueueRetryPolicyTest` 4 种组合。

### E4. 任务页上限（P2）

`LibraryDao.observeActiveTasks` 的 `LIMIT 100` → `LIMIT 300`。
DAO 测试可断言 `LIMIT` 行为太麻烦，跳过；在自检中说明。

### E5. 版本与文档

- `versionCode = 45`，`versionName = "1.3.1"`。
- `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 2. 实施顺序

1. 单段重译 sidecar + 测试。
2. CostEstimator + 格式化 + 测试。
3. 队列重试 + 纯函数 + 测试。
4. 任务页 300。
5. 菜单/确认文案接入。
6. 版本、文档、验证、构建、提交、tag。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

标准：tests ≥220，0 failures；lint 0 errors，warning ≤22；APK versionCode 45。

## 4. 风险

- 自动重试会增加一次 API 调用；只对 `retryable` 失败执行，且每章最多一次。
- 费用是估算，文案必须写「约」；不要用 `estimated` 之外的精度承诺。
- `readerMenuItems` 新参数有默认值，现有测试不需改；但标签变长，需检查菜单宽度。
