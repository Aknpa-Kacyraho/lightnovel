# Round 8 · 统一升级指南（v1.3.1）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：翻译首先要「不骗人」——过期状态可信、费用可判断、失败能自愈。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 单段重译仍报过期 | **采纳，P0** | 数据一致性 bug，一行补齐 + 测试 |
| U2 + D2 + E2 | 翻译前没有金额 | **采纳，P1** | 纯函数 + 菜单/确认文案，不伪造总额 |
| U3 + D3 + E3 | 失败只能手动重试 | **采纳，P1** | 仅可重试错误、每章一次 |
| U4 + D4 + E4 | 任务页 100 条截断 | **采纳，P2** | 上限 300，不加分页 |

## 2. 实施清单

### 2.1 单段重译（P0）

- [ ] `retranslateParagraph` 的 sidecar 补 `translationConfigHash`、`modelProvider`、
      `modelId`、`promptVersion`、`storyRevision`。
- [ ] `TranslationServiceTest` 断言重译后指纹等于当前配置。

### 2.2 费用预估（P1）

- [ ] 新增 `CostEstimator.kt`：`estimateTranslationCost(...)` + `formatCostRange(...)`。
- [ ] 新增 `CostEstimatorTest`（0 字、1000 字、0 价格、三档格式）。
- [ ] `readerMenuItems(..., costLabel)` 翻译项拼「约 ¥…」。
- [ ] 章节列表批量确认加「按每千字约 < ¥0.01 估算」。

### 2.3 队列自动重试（P1）

- [ ] `translateTarget` 返回 `TargetResult(success, retryable)`。
- [ ] `BookQueue.retriedTargets`；`shouldRetryAfterFailure(...)` 纯函数。
- [ ] 每章最多自动重试一次；`failed` 只在最终失败时 +1。
- [ ] `QueueRetryPolicyTest` 4 种组合。

### 2.4 任务页上限（P2）

- [ ] `observeActiveTasks` LIMIT 100 → 300。

### 2.5 版本与文档

- [ ] `versionCode = 45`，`versionName = "1.3.1"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不做预算上限/账本、不做模型自动切换、不做翻译质量评分。
- 不改费用币种与定价配置。
- 不改书库结构、不做彻底删除。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥220 tests，0 failures；新增费用/重试用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 45 |
| 用户 | 单段重译不误会话；确认框有金额；可重试失败自动再试 |
| 数据 | sidecar 指纹与配置一致；旧译文版本仍存档 |
| 发布 | 提交 + tag `v1.3.1` + 推送 |

## 5. 回滚

改动集中在 `TranslationService`、`ReadingTranslationCoordinator`、`ReaderMenu/Route`、
`ChapterListScreen` 与 3 个测试；无迁移、无备份变化。`git revert` 单提交即可。
