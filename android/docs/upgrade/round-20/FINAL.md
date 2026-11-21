# Round 20 · 统一升级指南（v1.7.1）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：用户按下的按钮优先；重复不是失败；暂停就是现在停。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 手动翻译被自动预译插队 | **采纳，P1** | `pickNextIndex(manual, auto)` 手动优先 |
| U2 + D2 + E2 | 重复任务计为失败 | **采纳，P2** | `skipped` + `TargetDisposition` |
| U3 + D3 + E3 | 暂停不取消当前请求 | **采纳，P2** | `pause` 总是取消 worker |

## 2. 实施清单

### 2.1 出队优先级（P1）

- [ ] 新增 `pickNextIndex(manual, auto)`，手动优先。
- [ ] `runWorker` 使用该函数选择目标。
- [ ] 测试：手动/自动/空三种情况。

### 2.2 结果归类（P2）

- [ ] `TargetResult` 增加 `skipped`；`register` 失败返回 `skipped = true`。
- [ ] 新增 `TargetDisposition` 与 `dispositionOf`。
- [ ] `runWorker` 对 `SKIPPED` 不更新完成/失败计数。
- [ ] 测试：四种归类 + 已重试过的可重试失败。

### 2.3 暂停（P2）

- [ ] `pause` 总是 `worker.cancel()`、`worker = null`、`runningIndex = null`。
- [ ] 保留 `finally` 的 `queue.worker === self` 保护。
- [ ] 自检说明：无法在 JVM 稳定模拟，依赖代码审查。

### 2.4 版本与文档

- [ ] `versionCode = 57`，`versionName = "1.7.1"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改自动预译章数与触发时机。
- 不改任务中心 UI、筛选与分组。
- 不做跨书队列。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥277 tests，0 failures；新增队列策略用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 57 |
| 用户 | 手动先跑；重复不计失败；暂停立即停 |
| 发布 | 提交 + tag `v1.7.1` + 推送 |

## 5. 回滚

改动集中在 `ReadingTranslationCoordinator.kt` + 新测试；无迁移。
`git revert` 单提交即可。
