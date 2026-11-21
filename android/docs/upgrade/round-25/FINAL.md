# Round 25 · 统一升级指南（v1.8.3）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：批量动作与文案同范围；加载状态属于最新请求；失败回滚到操作前。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 筛选下批量重试无效 | **采纳，P2** | `retryableRows` 取全部任务 |
| U2 + D2 + E2 | 旧翻译请求提前关加载 | **采纳，P2** | 旧 token 不碰 `metadataLoading`；清空搜索递增 token |
| U3 + D3 + E3 | 世界线保存失败留脏知识 | **采纳，P2** | 保存失败恢复旧知识 |

## 2. 实施清单

### 2.1 批量重试范围（P2）

- [ ] 新增 `retryableRows(tasks, ignoredKeys)` 纯函数。
- [ ] `retryAllFailed` 从 `dao.observeActiveTasks().first()` 取任务。
- [ ] `TaskCenterRetryTest` 覆盖状态过滤、ignored、与筛选无关。

### 2.2 搜索加载状态（P2）

- [ ] `translateCards` 旧 token 分支不修改 `metadataLoading`。
- [ ] `clearSearch()` 增加 `searchToken++`。
- [ ] 自检说明：ViewModel 路径暂无稳定 JVM 测试。

### 2.3 世界线回滚（P2）

- [ ] `regenerateLastChapter` 保存失败/取消时恢复旧知识。
- [ ] 恢复用 `runCatching`，不覆盖原始错误。
- [ ] 自检说明：需要真实 store + 模型。

### 2.4 版本与文档

- [ ] `versionCode = 62`，`versionName = "1.8.3"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改任务中心筛选/分组 UI。
- 不改发现页搜索源与元数据翻译服务。
- 不改世界线 prompt、校验与生成参数。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥311 tests，0 failures；新增批量重试用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 62 |
| 用户 | 任何筛选下都能批量重试；加载状态正确；世界线失败回滚 |
| 发布 | 提交 + tag `v1.8.3` + 推送 |

## 5. 回滚

改动集中在 `TaskCenterViewModel.kt`、`DiscoverViewModel.kt`、`WorldlineService.kt` + 测试；
无 DB 迁移。`git revert` 单提交即可。
