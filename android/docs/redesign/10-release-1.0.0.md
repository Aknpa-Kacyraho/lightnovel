# 1.0.0 阅读翻译窗口与整页滚动

日期：2026-11-04

## 问题

- 加入书架后只有生肉，没有明显的主动翻译入口。
- 发现页搜索区和作品详情页 Hero/目录固定，只有下半屏列表能滚，内容显示少。
- 直接全本自动翻译会浪费钱；跳章时被跳过的章节也没有翻译策略。

## 实现

### 阅读翻译窗口

- `AppSettings` 新增：
  - `autoTranslateWhileReading` 默认开。
  - `translateAheadChapters` 默认 3（可 0/1/3/5/10）。
  - `translateBackfillChapters` 默认 5（可 0/2/5/10）。
- 打开阅读器时：当前章未翻译则先翻译当前章；完成后预译后面 X 章。
- 跳到后面章节时，回补当前章之前最多 N 章；超过 N 的中间章节不自动烧钱，可在任务页或设置调整。
- 新增 `ReadingTranslationPlanner`（纯函数）和 `ReadingTranslationCoordinator`（应用级 IO 队列）：
  - 同章任务去重，不改变阅读进度；
  - 逐章保存，失败/取消保留已有译文；
  - 删除书架时取消该书任务。
- 作品详情页「更多 → 翻译当前章」提供手动入口；阅读器原有「翻译本章」保留。

### 整页滚动

- 发现页：搜索框、最近搜索、保存搜索、错误、筛选和搜索结果全部放进同一个 `LazyColumn`，顶部随内容滚走。
- 作品详情：Hero、TabRow、简介/目录头、章节列表放进同一个 `LazyColumn`；不再固定 Hero/Tab 只滚下半屏。
- 章节行补水平内边距，搜索结果卡片补水平内边距，避免贴边。

## 验证

- `164 JVM tests / 0 failures / 1 skipped`
- lint `0 errors`
- `assembleDebug` 通过，真机覆盖安装
- 新增 `ReadingTranslationPlannerTest`：超前、回补、翻译边界、上限。
- 真实模型验证沿用 0.9.10：DeepSeek 短档 1375 字、续写 1981/1726 字、重写 2200 字；本轮不重复跑完整长线。
