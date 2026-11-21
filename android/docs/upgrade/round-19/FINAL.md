# Round 19 · 统一升级指南（v1.7.0）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：先保证翻译动作有明确终点，再保证「重译本段」只改这一段。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 翻译异常卡在「翻译中」 | **采纳，P1** | 非取消异常落 failed + 可读原因 |
| U2 + D2 + E2 | 重译本段破坏排版 | **采纳，P1** | 按字符区间替换，保留原分隔符 |
| U3 + D3 + E3 | 不可重试错误空转 | **采纳，P2** | 尊重 `TranslationException.retryable` |

## 2. 实施清单

### 2.1 异常出口（P1）

- [ ] `TranslationService.translate` 增加 `catch (Exception)`：`NonCancellable` 写 `failed`，
      返回 `Failed("翻译异常：…", retryable = true)`。
- [ ] 保留 `CancellationException` 分支的 `markCancelled` + rethrow。
- [ ] 测试：client 抛 `IllegalStateException` → DB `failed`、无 zh 文件。

### 2.2 重译本段布局（P1）

- [ ] `retranslateParagraph` 用 `Paragraphs.startOffset` 定位并 `replaceRange`，
      只替换目标段文字。
- [ ] 回退分支按原文是否含空行选择 `\n` 或 `\n\n`。
- [ ] 测试：单换行三行章节重译第 1 段 → 仍 3 行、无空行、其余段不变。

### 2.3 不可重试错误（P2）

- [ ] `translateOne` 的 catch 增加 `if (!error.retryable) return null`。
- [ ] 测试：`retryable=false` 只调用一次 client。

### 2.4 版本与文档

- [ ] `versionCode = 56`，`versionName = "1.7.0"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改 prompt、模型参数、分块策略。
- 不改数据库结构与章节状态枚举。
- 不持久化失败原因（只在即时提示里展示）。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥274 tests，0 failures；新增异常/布局/重试用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 56 |
| 用户 | 异常不再卡住；重译一段不改排版；不可重试立即失败 |
| 发布 | 提交 + tag `v1.7.0` + 推送 |

## 5. 回滚

改动集中在 `TranslationService.kt`、`ChapterTranslator.kt` + 测试；无迁移。
`git revert` 单提交即可。
