# Round 26 · 三视角自检（v1.8.4）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。无真机（`adb` 不可用）。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **313 tests / 0 failures / 0 errors / 1 skipped**（+2） |
| lint | **0 errors / 22 warnings**（无新增） |
| Debug 构建 | 成功，versionCode 63 / 1.8.4 |
| 数据 | 无 DB schema 变化 |

## 用户视角

**已改善**

1. 取消翻译/退出阅读器后，摘要、人物提取与知识抽取不再继续写入。
2. 切换搜索/离开发现页后，旧的卡片翻译请求会结束，不再继续等待与写缓存。
3. 取消世界线生成时，差异报告/知识抽取不会把取消当成普通失败继续保存。
4. 章节下载/搜索源请求的取消会正确向上传播。

**仍然存在**

- OkHttp 的同步请求发出后无法中途打断，取消只能阻止后续写入；
  当前请求仍可能占用几秒到几十秒。
- 章节下载 worker 与本地导入的 `runCatching` 仍会吞取消（P3，见审计结论）。
- 旧搜索的翻译请求虽然不再写 UI，但已发出的请求仍可能产生少量费用。

## 设计师视角

**一致**

- 没有新增/删除控件、文案或 loading。
- 取消/返回的交互不变；只是后台不再做用户没要求的事。
- 错误提示仍沿用现有文案。

**取舍**

- 没有为「已取消」增加单独提示：用户已经离开或用按钮表达了意图。
- 没有改任何加载指示的时长：失败/取消仍是静默结束。

## 工程师视角

**做对了**

- `runCatchingCancellable` 是 `suspend inline`，取消原样抛出，普通异常仍转成
  `Result.failure`；纯解析的 `runCatching` 不受影响。
- 替换点集中在挂起模型调用：`StoryMemoryService` 3 处、
  `MetadataTranslationService` 5 处、`WorldlineService.diffReport` 1 处、
  `KakuyomuSource.recommend` 2 处、`SyosetuSource.search/recommend` 2 处。
- `KnowledgeExtractionService` 的 catch 顺序修正后，取消不会被
  「知识抽取返回无法解析」吞掉。
- `CancellationTest` 覆盖取消透传与普通异常包装。

**风险与限制**

- `runCatchingCancellable` 只能阻止协程在挂起点之后继续；底层 OkHttp 请求
  仍会完成。要彻底中断需要改用可取消的异步客户端。
- 仍有少量 `runCatching` 包裹挂起调用（下载 worker、本地导入、
  `ReadingTranslationCoordinator.chapterFetcher`），属于 P3，未在本轮改动。
- 世界线/摘要的「取消后不写」依赖上层没有其他 fire-and-forget 协程；
  当前调用点都在可取消的 job 内。

**未验证**

- 真机上取消翻译后立即返回书架的时序。
- 取消世界线生成后的知识文件实际内容。
- 弱网下 OkHttp 请求完成前的延迟。

## 结论

Round 26 目标达成，可作为 1.8.4 发布。最终审计未再发现 P0/P1/P2
可复现问题；剩余项记录在 `PROGRESS.md` 的「审计结论」。
