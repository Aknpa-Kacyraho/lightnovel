# Round 26 · 统一升级指南（v1.8.4）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：取消必须传播；挂起调用的失败不能把取消当成普通错误。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E2 | 取消翻译后仍写摘要/人物 | **采纳，P1** | `runCatchingCancellable` 替换 |
| U2 + D2 + E2 | 切搜索后旧翻译继续 | **采纳，P2** | 同上 |
| U3 + D3 + E2 + E3 | 取消世界线/知识提取仍写半成品 | **采纳，P2** | 替换 + catch 顺序 |

## 2. 实施清单

### 2.1 工具函数（P1）

- [ ] 新增 `core/util/Cancellation.kt`：`runCatchingCancellable`。
- [ ] `CancellationTest` 覆盖取消透传与普通异常包装。

### 2.2 替换挂起调用（P1）

- [ ] `StoryMemoryService` 3 处。
- [ ] `MetadataTranslationService` 5 处。
- [ ] `WorldlineService.diffReport` 1 处。
- [ ] `KakuyomuSource.recommend` 2 处、`SyosetuSource.search/recommend`。

### 2.3 知识提取 catch（P2）

- [ ] `KnowledgeExtractionService` 在 `catch (Exception)` 前加
      `catch (CancellationException) { throw }`。

### 2.4 版本与文档

- [ ] `versionCode = 63`，`versionName = "1.8.4"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改网络层、超时、重试次数。
- 不改模型 prompt 与 UI。
- 不替换纯解析的 `runCatching`。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥313 tests，0 failures；新增取消透传用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 63 |
| 用户 | 取消后不再写摘要/人物/知识；旧搜索请求结束 |
| 发布 | 提交 + tag `v1.8.4` + 推送 |

## 5. 回滚

改动集中在新增工具函数与 6 个调用文件 + 测试；无 DB 迁移。
`git revert` 单提交即可。
