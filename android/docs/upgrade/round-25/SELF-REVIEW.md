# Round 25 · 三视角自检（v1.8.3）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。无真机（`adb` 不可用）。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **311 tests / 0 failures / 0 errors / 1 skipped**（+3） |
| lint | **0 errors / 22 warnings**（无新增） |
| Debug 构建 | 成功，versionCode 62 / 1.8.3 |
| 数据 | 无 DB schema 变化 |

## 用户视角

**已改善**

1. 「进行中」等任意筛选下，点「重试全部失败」都会重试全部失败/未译全章节。
2. 快速连续搜索时，旧搜索的翻译请求不会提前关闭新搜索的加载提示。
3. 清空搜索后，旧翻译结果不再写回空列表。
4. 世界线重新生成保存失败时，旧知识恢复，正文与知识一致。

**仍然存在**

- `retryAllFailed` 受 DAO 查询上限 300 影响，超过 300 的失败任务需分批。
- 旧搜索的翻译请求仍会跑完（只是不写 UI、不关加载），仍消耗 API。
- 世界线恢复知识本身失败时，只能保留原始错误提示。

## 设计师视角

**一致**

- 没有新增/删除控件、文案或 loading。
- 批量重试确认框数字与动作范围一致。
- 搜索加载指示只反映当前搜索。

**取舍**

- 没有为「旧请求已丢弃」加提示：用户不需要知道。
- 没有为世界线失败增加额外确认框：沿用现有错误提示。

## 工程师视角

**做对了**

- `retryableRows` 是纯函数，只按 status + ignored 过滤，不接收当前筛选；
  `retryAllFailed` 从 DAO 获取完整快照。
- `translateCards` 的旧 token 分支只写 catalog 缓存，不碰 UI 状态；
  `clearSearch` 递增 token，使进行中的翻译失效。
- `regenerateLastChapter` 的保存失败/取消都会恢复旧知识，恢复用 `runCatching`
  包裹，不覆盖原始异常。

**风险与限制**

- `retryAllFailed` 的 `dao.observeActiveTasks().first()` 在事务外读取，
  确认框与实际任务之间可能有一小段延迟；最坏是多翻一章。
- `clearSearch` 递增 token 不会取消已经发出的模型请求；只能丢弃结果。
- `WorldlineService` 的 `oldKnowledge` 可能为 null（首次生成），保存失败时
  没有可恢复的旧知识，新知识可能残留。

**未验证**

- 真机上筛选切换后批量重试的实际入队。
- 快速搜索 A→B 的加载指示时序。
- 世界线保存失败的实际回滚（需要构造 IO 失败）。

## 结论

Round 25 目标达成，可作为 1.8.3 发布。下一轮做最终审计，
重点检查取消语义与剩余 P3；若没有新的 P0/P1/P2，则收敛。
