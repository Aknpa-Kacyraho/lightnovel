# 第一轮交叉自查：IA / 视觉 / 工程三份方案

> 审查方式：只读 `01-information-architecture.md`、`02-visual-system.md`、`03-product-engineering.md`，并抽查指定 Android 源码与测试；未构建、未安装、未改代码。
> 基线核对：`0.7.2-p1`、Room v2、`@Test` 共 72 个；Android instrumentation 另有 3 个测试，不计入 72。

## 结论摘要

1. 三份文档方向一致，但不能直接合并：底栏、详情页、主题回退、P0 边界存在硬冲突。
2. 底栏应保留“任务”，本轮做 **书架 / 发现 / 任务 / 设置 4 Tab**；“我的”只承载设置会变成空壳，建议延后。
3. 详情页本轮采用 **详情内“简介 / 目录”双 Tab**，不拆两个路由；用户痛点是“简介和章节混排”，不是“少一个页面”。
4. 新装默认与未知回退都用 **amber**；旧 `teal/lavender/sakura` 继续可读；但必须同时改 `AppThemeTest` 与 `SettingsStoreTest`。
5. 03 的 P0 实际是“全量重构”：Me、设置子页、任务控制台、搜索历史、8 套主题、跨 Tab 栈同时上，不可交付；本轮应砍到 5 条主线。
6. 标签概念一致，但组件 API 不一致：需要一个 `LnTag(kind, onClick)`；02 的“详情标签只读”与 01/03 的“可点”冲突，应拒绝只读。
7. 跨 Tab 恢复来源栈技术上可行，但当前扁平 `NavHost` 做不到；本轮用“当前栈 push 搜索页”，跨 Tab 保留栈放 P1。
8. Room v2 在 P0 可零迁移；P1 的 `last_read_at/error_message/task_ignored_at` 必须 v3。备份只允许加可选字段，不能改 `format=1` 的必填契约。
9. 真实风险不是“方案不美”，而是 **导入路径丢掉 `updated_at`、`tags_json` 从未写入、`SettingsStore` 默认仍是 teal**；这三个前提不修，最近阅读/标签/新默认主题都会假落地。

## 1. 代码基线抽查（只列会推翻方案的前提）

| 事实 | 证据 | 对方案的影响 |
| --- | --- | --- |
| 底栏当前是书架/任务/设置；“发现”是书架右上角按钮 | `LightnovelNavHost.kt:38-42, 97-99`；`LibraryScreen.kt:98` | 01/03 的“发现一级化”前提成立。 |
| 从发现打开书会 `popUpTo("discover"){inclusive=true}`，销毁发现结果 | `LightnovelNavHost.kt:116-126` | 01/03 指出的上下文丢失成立。 |
| 详情与目录共用同一个 `LazyColumn`；作者是 Text，标签是 `joinToString(" / ")` | `ChapterListScreen.kt:157-233` | 02 的“简介/章节混排”诊断成立。 |
| `tags_json` 在加书、在线书、备份导入三处都写 `null`，全仓没有读取/解析 | `DirectLibraryService.kt:46`；`OnlineBookService.kt:48`；`BackupImportService.kt:88` | “标签可点”不能只改 UI；必须先写入并解析，且覆盖导入书。 |
| 设置页实际没有渲染边距、段距、常亮；Novelia 登录也不在 UI | `SettingsScreen.kt:92-117` 的 3 个参数未被使用；`SettingsViewModel.kt:225-247` | 01/03 的“能力不可达”成立；但“我的/子页”不是唯一解法。 |
| 任务页是单层列表，最多 100 条；没有重试/取消/忽略字段 | `TaskCenterScreen.kt:45-92`；`LibraryDao.kt:112-129` | 03 的“任务控制台”需要新字段与执行器，不能算小改。 |
| 主题仅 3 套；`fromId(unknown)` 回退 TEAL；`AppSettings.appTheme` 默认 teal | `Theme.kt:10-22`；`SettingsStore.kt:15,62` | 02 的 amber 默认/回退与现状、测试都冲突。 |
| `SettingsStoreTest` 断言默认主题为 `"teal"` | `SettingsStoreTest.kt:22` | 03 只提 `AppThemeTest`，漏了这个会红的测试。 |
| `MainActivityTest`、`ReaderScreenTest` 仍找“轻小说”；当前书架标题是“Ka小说家” | `MainActivityTest.kt:22`；`ReaderScreenTest.kt:26`；`LibraryScreen.kt:96` | 两个 instrumentation 测试现在就是红的；不是 72 个单测的一部分。 |
| 最近阅读拟用 `read_state.updated_at`，但导入路径没有写入它 | `LibraryRepository.kt:97-125`；`BackupImportService.kt:95-108` | 导入书的 `progress_idx>0` 但 `updated_at=null`，最近阅读会漏。 |
| 本地搜索只过滤标题/作者，不过滤标签 | `LibraryRepository.kt:40-67` | 01 说“搜标题/作者/标签”，03 说“只过滤标题/作者”，二者矛盾。 |
| 阅读器换章只 `launchSingleTop`，不替换当前条目 | `LightnovelNavHost.kt:157-161` | 01/03 的“返回栈不按章累积”目前未实现。 |
| Room v2、`MIGRATION_1_2` 存在；备份 `format=1` | `LightnovelDatabase.kt:8-37`；`BackupExporter.kt:73-92` | P0 只做查询/写现有列可零迁移；P1 加字段必须 v3。 |

结论：三份文档的**现状诊断大体准确**，但有四个前提没对齐：`tags_json` 没有写入、导入没有 `updated_at`、`SettingsStore` 默认不是 amber、本地搜索不搜标签。

## 2. 硬冲突与裁决

| 冲突 | 01 | 02 | 03 | 本轮裁决 |
| --- | --- | --- | --- | --- |
| 底栏数量 | 书架/发现/我的 3 Tab | 未明确，但书架仍保留“发现”图标 | 3 Tab，任务/设置归“我的” | **4 Tab：书架/发现/任务/设置** |
| 详情结构 | 详情/目录双路由 | 详情内“目录/简介”双 Tab | 双路由，明确不引入 `detailTab` | **采用 02 双 Tab；P1 再评估拆路由** |
| 新装默认/未知回退 | 未定义 | 默认 amber，未知回退 amber | 默认 amber，但 P0 保留 teal fallback 守测试 | **默认与回退都 amber，更新测试** |
| 详情标签 | 可点 | 只读版本 `onClick=null` | 可点 | **拒绝 02 只读；类型/关键词可点** |
| 来源预览 | 独立路由 | 底部 Sheet | 独立路由 | **P0 Sheet；路由 P1** |
| 设置分组 | 6 组（含高级） | 5 组卡片 | 6 组 | **P0 一页 5 组 + 高级折叠；不建子页** |
| P0 范围 | 5 项，但每项很大 | P0 含 8 主题、详情、书架；发现为 P1 | 把 01 的书架/目录 P1 提前到 P0 | **以本文第 7 节重划 P0，03 的“以本文件为准”不成立** |
| 搜索历史 | P2 | 未提 | P1，且称“需求明确提前” | **P1，不进本轮** |
| 最近阅读 | P1（用 `updatedAt`） | 未提 | P0 | **P0 只读横栏；不做 `last_read_at`** |
| 标签上限 | 详情 8 个 + 更多 | 详情 10 个 + 展开；卡片 3 个 | 结果 3 个；详情全部 | **详情 8 个 + 展开；卡片 3 个 + N** |
| 书架筛选 | 全部/在读/想读/读完/收藏 5 个 | 4 个（无收藏） | 5 个 | **P0 先做 4 个；收藏筛选 P1，行需可横滚** |
| 书架“发现”按钮 | 移除 | 保留 | 移除 | **移除；02 此处应改写** |
| 深色模式控制 | 跟随系统 P2 | 三段按钮 | P1 | **P0 仅跟随系统；手动覆盖 P1** |

## 3. 决策一：底栏用 4 Tab，保留任务

用户原话是“发现可以搬到下面来和下边栏一起是大类”，这是**增加发现**，不是“删除任务”。01/03 把任务移进“我的”属于额外产品决策，收益不明确，成本却很高。

- **推荐顺序：书架 / 发现 / 任务 / 设置。** 四个都是两字标签，符合 Material 底栏 3–5 项；任务保持现有 1 击可达，设置保留 `settings-screen` 根 tag。
- **不新建“我的”空壳。** “我的”若只有设置，用户会期待账号、数据、关于等更多内容；实际没有账号体系，页面会显得空。等“我的”有备份/任务/缓存状态卡时再改名，属于 P1。
- **任务 Tab 不是死 Tab。** 当前就有该入口，空队列已有解释文案；保留它比“移除后新增 Me 页面 + 状态卡 + 失败角标”风险低得多。
- **拒绝 02 §8 的“书架顶栏再放一个发现 IconButton”**：既然发现已是一级 Tab，顶栏再放入口会制造双重入口与状态歧义。
- 若产品最终坚持 3 Tab，前置条件必须是：Me 页面已有状态卡与分组入口、任务 1 击可达、失败角标可用；本轮不满足，不能做。

## 4. 决策二：详情内双 Tab，不拆双路由

用户痛点是“简介和章节排在一起”，02 的双 Tab 已经直接解决；01/03 的详情/目录双路由解决的是“页面职责”，不是用户当前最痛的点。

- **本轮保留一个路由 `chapters/{bookId}`**，把现有 `ChapterListScreen` 改成：Hero/继续阅读/收藏 → 吸顶 Tab（简介 / 目录）→ 对应内容。保留 `chapter-list-screen` 根 tag，现有测试与深链不动。
- **返回栈成本更低**：详情 → 阅读器 → 返回详情；目录是详情内 Tab，不增加“详情 → 目录 → 阅读器 → 返回目录 → 返回详情”的层级，也不需要为目录单独定义底栏隐藏规则。
- **状态恢复成本更低**：一个 ViewModel、一个 `selectedTab`（`rememberSaveable`）；两个 Tab 各自持有 `LazyListState`，按 `bookId` 保存。双路由则要两个 ViewModel、两套 SavedStateHandle、两个滚动状态。
- **实现约束**：简介 Tab 与目录 Tab 用两个兄弟 `LazyColumn`（或一个列表但 Tab 内容切换时重建状态），不要把目录塞进 `Column.verticalScroll`，也不要让简介和章节目录共享同一条滚动流；否则又回到混排。
- **默认 Tab**：有进度默认目录，无进度默认简介；这条 02 规则合理，保留。
- **目录工具延后**：章节搜索、正倒序、状态筛选、当前章自动定位列为 P1；本轮目录只做“分组/当前章高亮/点击阅读”。等目录复杂度上来、或平板双栏需要时，再提升为独立路由。
- **合并动作**：改写 01 §书籍详情/路由表、03 §3.2/§4.2/§4.3；删除 `library/book/{bookId}/chapters`、`BookDetailViewModel` 的 P0 身份，保留为 P1 备选。

## 5. 决策三：amber 默认、amber 回退、旧 id 兼容

- **新安装默认 `amber`**；`AppSettings.appTheme` 默认值、`LightnovelTheme` 默认参数、`SettingsScreen` 初始化都必须一起改，否则只改 `AppTheme.fromId` 不会生效。
- **旧设置兼容按 id，不按颜色**：已有 `teal/lavender/sakura` 字符串继续生效；02 会重画这三套色板，因此老用户会看到同一 id 的新配色，合并文档应明确这是有意变更。
- **未知/空 id 回退 `amber`**：产品默认色与回退色保持一致，避免“新装 amber、损坏设置变 teal”的割裂。
- **拒绝 03 的“P0 保留 teal fallback 以守 72 tests”**。72 tests 是门槛，不是不可改的契约；更新断言后仍可 72/72 全绿。保留 teal fallback 会让 02 的默认策略名存实亡。
- **P0 只上 5 套：teal / lavender / sakura / amber / indigo**；matcha / slate / ember 放 P1。8 套 × light/dark × 全部 Material 角色是 16 套 scheme，02 只列了 10 个关键色，剩余 `on*Container`、`surfaceContainer*`、`errorContainer` 都要补齐并跑对比度，风险不应压进本轮。
- **必须更新的测试**：`AppThemeTest`（`unknown→AMBER`，并遍历 8 个 id）、`SettingsStoreTest`（默认 `amber`）、新增 `ThemePaletteTest`（每套浅/深色的文本与描边对比度）。如果保留 8 套，则测试必须覆盖 8×2，不能只测 3 套。
- **布局也要改**：`SettingsScreen.kt:141-149` 现在是 `AppTheme.entries` 的一行 `Row`；3 套尚可，5 套开始拥挤，8 套必然溢出。P0 改成 2 列网格或可横滚行，不能只加 enum 条目。

## 6. 标签、作者与跨 Tab

### 6.1 组件与数据模型

- 02 的 `LnExtendedColors` 与 03 的四类标签**概念一致**：类型、关键词、状态、来源；状态映射也一致（已译 primary、进行中 secondary、未译全 tertiary、失败/缺文件 error、生肉 onSurfaceVariant）。
- 但 API 不一致：02 的 `TagChip` 只描述“关键词标签”，类型标签没有对应组件；03 又把 `TagChip` 当成所有标签。合并为一个 `LnTag(kind = TYPE|KEYWORD|STATUS|SOURCE, onClick)`，`StatusBadge` 单独保留，`SourceBadge` 是 `LnTag` 的来源变体。
- **不要用 `tagsZh.ifEmpty { tags }` 的下标配对**：`MetadataTranslationService` 返回的 `tagsZh` 不保证与原始 `tags` 等长/同序；当前 `DiscoverScreen.kt:304-307` 已经用 index 取原始标签，存在错配。应引入 `TagRef(original, localized?)`，或持久化 `[{original, zh}]`；UI 只消费配对后的列表。
- `tags_json` 必须同时覆盖：在线加书、在线书刷新、备份导入、本地/遗留书；读取容错空数组，缺失时用本地化文本兜底搜索。否则“标签可点”只对本次新加的书生效。

### 6.2 是否所有标签都能点

不。建议明确矩阵：

| 类型 | 可点 | 落点 |
| --- | --- | --- |
| 类型标签 | 是 | 发现搜索 `mode=tag`，传原始日文标签 |
| 关键词标签 | 是 | 同上 |
| 来源标签 | 是 | 发现页带 provider 过滤；没有 query 时进入该来源浏览/推荐 |
| 状态标签 | 否 | 仅失败任务可点“重试”，不是搜索入口 |
| 作者 | 是 | 发现搜索 `mode=author`，传原始作者名 |

拒绝 02 §5“详情页标签用只读 TagChip”：这与 01/03 的 P0-3 直接冲突，也让用户无法从详情顺标签找书。

### 6.3 跨 Tab 返回栈现实吗

技术上可行，但不是本轮成本。当前是扁平 `NavHost` + `route == 顶层字符串` 判断底栏；要实现“书架详情 → 发现搜索 → 返回只回发现 → 再点书架恢复详情”，需要每个 Tab 一个嵌套图、`saveState/restoreState`、按层级判断选中态，并逐一测返回路径。

- **P0**：从详情/卡片点标签或作者，在当前栈 push 一个 `discover/search` 路由；返回回到详情，发现 Tab 自己的搜索仍独立。这样“标签能点、上下文不丢”，但不做跨 Tab 栈魔术。
- **P1**：再上嵌套图与跨 Tab 恢复；届时补 `BottomBarTest` 与真实 `NavHost` 测试。
- **作者搜索要诚实**：Syosetu 不保证作者索引；作者模式应保留关键词结果并提示“该源可能未按作者索引”，不要假装精确过滤。来源标签的“空 query”落点当前未定义，合并文档必须补，否则该入口不可实现。

## 7. P0 范围：砍到本轮可交付

03 把 01 的 P1 书架/目录提前到 P0，同时保留 Me、设置子页、任务控制台、8 主题、搜索历史，范围已经超过一次可验证交付。建议本轮只保留以下 5 条主线：

| 本轮保留（P0） | 具体边界 | 验收 |
| --- | --- | --- |
| A. 4 Tab 导航 | 书架/发现/任务/设置；移除书架发现按钮；底栏显隐规则；阅读器换章替换条目 | 4 Tab 1 击可达；发现不再清空来源；返回栈逐路径正确 |
| B. 详情双 Tab | 一个 `chapters/{bookId}` 路由；Hero + 继续阅读 + 收藏 + 简介/目录 Tab；保留旧 tag | 简介与章节不同滚动流；本地/在线能力差异正确 |
| C. 发现降噪 | 单搜索框 + 链接 Sheet；加书不跳转；单源失败保留其他结果；标签/作者在当前栈搜索 | 首屏不再两组表单；加书停留；部分失败可重试 |
| D. 5 套主题 + 标签 | teal/lavender/sakura/amber/indigo；amber 默认/回退；`LnTag`/`StatusBadge`；详情/发现/书架统一取色 | 换主题无硬编码色；标签同义同色；对比度测试通过 |
| E. 书架/设置最小修复 | 只读最近阅读横栏；移除行内收藏星前先给详情收藏；设置一页分组 + 高级折叠；暴露边距/段距/常亮 | 最近阅读不漏导入书；设置不再有“ViewModel 有、UI 没有”的项 |

**必须砍到 P1/P2 的项：**

- “我的”新页面、备份/任务/缓存状态卡、失败角标、设置 6 个子页：**P1**；本轮保留“设置”Tab。
- 任务控制台（按书分组、重试、取消、忽略、精确跳章）：**P1**；本轮只保留现有任务列表与空态。
- 搜索历史、作者精确匹配、结果过滤增强、加载更多：**P1/P2**；不阻塞搜索与加书。
- 详情/目录双路由、`BookDetailViewModel` 拆分、目录搜索/排序/筛选：**P1**；本轮双 Tab 已解决混排。
- 8 套主题中的 matcha/slate/ember、主题预览 4 列、平板双栏、动态取色：**P1/P2**。
- 发现首页/搜索页/来源预览三路由拆分：**P1**；本轮单页 + 预览 Sheet，先修复加书上下文。
- 跨 Tab 保存来源栈、来源预览独立路由、深链：**P1/P2**。
- 书架收藏筛选/排序/书架标记、备份提醒 7 天持久化、批量选择、EPUB/TXT 导入、下载管理：**P1/P2**。
- `LnTokens` 全套动效/圆角/内容宽度 token：可保留 `LnExtendedColors` 与最小 spacing；动效 token 延后，不要为 120ms/220ms 建抽象。

**本轮必须先修的数据前提**：`tags_json` 写入与解析、导入 `updated_at` 回填或最近阅读兜底、`SettingsStore` 默认 amber。否则 D/E 两条主线会“UI 有了、数据不对”。

## 8. 与 72 tests、Room v2、备份的冲突

- **72 个 `@Test` 计数准确**。但“全绿”不等于“断言不改”：`AppThemeTest` 与 `SettingsStoreTest` 都锁定了 teal 默认，必须显式更新；否则 02 的 amber 策略无法落地。
- **`AppThemeTest`**：改为 `unknown→AMBER`；保留 `teal/lavender/sakura` 显式 id；新增 8 个 id 的 `fromId` 断言。不要只新增用例而保留旧断言。
- **`SettingsStoreTest`**：默认主题改 `amber`；再断言显式保存 `sakura` 仍生效，证明旧 id 兼容。
- **`MetadataTranslationServiceTest`**：只要不改变 `BookEntity` 构造契约、不把 `tagsJson` 设为必填，就应保持通过；若 `translateBook` 开始写 `tagsJson`，补一条“原文标签保留、译文不覆盖原文”的断言。
- **`P0SmokeTest`**：纯算术，不受影响；不要拿它当导航/主题覆盖。
- **Android instrumentation**：`MainActivityTest`/`ReaderScreenTest` 找“轻小说”而当前标题是“Ka小说家”，现在已红；本轮必须改为查找 `library-screen` 或“Ka小说家”。这不是 72 个单测，但会阻塞 `connectedDebugAndroidTest`。
- **Room v2**：P0 只加 DAO 查询、写现有 `tags_json`、内存排序/内存过滤，可零迁移；不要为了“最近阅读”新增 `last_read_at`。P1 的 `last_read_at/error_message/task_ignored_at` 必须 `MIGRATION_2_3` + `Migration2To3Test` + 导出 schema 3，不能 destructive fallback。
- **备份**：`format=1` 只能加可选字段；`tracking/favorites` 等既有键不能改名；缺 `last_read_at` 时回退 `updated_at`；新增字段必须做旧备份导入与 round-trip 测试。01 的“不重写备份格式”和 03 的“P1 加可选字段”并不矛盾，但合并文档要写成“仅向后兼容的增量”。
- **测试 tag**：保留 `library-screen`、`chapter-list-screen`、`settings-screen`、`reader-screen`；采用双 Tab 也保留 `chapter-list-screen`，不要因为改名让现有测试全部失效。
- **导入路径**：`BackupImportService` 当前没有给 `ReadStateEntity.updatedAt` 赋值。P0 若上“最近阅读”，必须补导入时间或按 `openedAt/finishedAt/createdAt` 兜底；否则测试造的数据和真实 19 本备份都会漏。

## 9. 用户 10 条反馈覆盖

> 三份文档没有附用户 10 条原话。以下按 02 §2 的现状诊断、01/03 反复引用的条目，加上用户本轮明确的“发现搬到底栏”整理为 10 条口径；若原话不同，合并前必须把原话贴回文档，否则无法证明 100% 覆盖。

| # | 反馈口径 | 覆盖 | 缺口 / 结论 |
| --- | --- | --- | --- |
| 1 | 发现搬到底栏，作为大类 | ✅/⚠️ | 01/03 做对，但改成 3 Tab 并删任务属于过度解读；02 还留书架发现按钮。 |
| 2 | 主题只有 3 套、不喜欢 | ✅/⚠️ | 02 给 8 套，03 默认/回退又冲突；本轮建议 5 套，amber 默认。 |
| 3 | 标签颜色不跟主题 | ✅/⚠️ | `LnExtendedColors` 方向对；类型/来源仍取 ColorScheme，02 详情只读与 01/03 可点冲突。 |
| 4 | 简介和章节排在一起 | ✅ | 02 双 Tab 直接解决；01/03 双路由也能解决但成本更高。 |
| 5 | 界面杂乱、功能没归类 | ⚠️ | 发现/设置/任务都有方案，但 P0 同时做太多，容易从“杂乱”变成“半成品”。 |
| 6 | 当前任务 Tab 怎么处理 | ❌ | 01/03 未征求用户就移除任务 Tab；建议保留，设置不改成空壳“我的”。 |
| 7 | 详情页动作/继续阅读 | ✅ | 三份都覆盖；双 Tab 下仍需保留“继续阅读”主按钮与收藏。 |
| 8 | 书架难用、每行收藏星、最近阅读 | ⚠️ | 最近阅读 P0 只有 sidebar 查询；导入丢 `updated_at`，且 01 P1 / 03 P0 冲突。 |
| 9 | 发现两组输入框、加书自动跳转 | ✅ | 三份一致；单搜索 + 链接 Sheet + 停留原页，必须做。 |
| 10 | 设置长滚动、部分设置不可达 | ✅ | 代码确认边距/段距/常亮没有 UI；P0 一页分组并暴露这些项，子页延后。 |

## 10. 最终合并决策表

| 条目 | 决策 | 合并动作 |
| --- | --- | --- |
| 3 Tab + 我的 | **拒绝** | 改为 4 Tab：书架/发现/任务/设置；Me 放 P1。 |
| 详情/目录双路由 | **改写** | P0 采用 02 双 Tab；路由拆分、BookDetailViewModel 放 P1。 |
| 02 详情只读标签 | **拒绝** | 类型/关键词/来源可点；状态标签不可点。 |
| 02 书架保留发现按钮 | **拒绝** | 删除；发现只从底栏进入。 |
| 8 套主题同时上 | **改写** | P0 5 套；matcha/slate/ember 放 P1；全量对比度测试。 |
| unknown→teal fallback | **拒绝** | unknown/空值→amber；更新 `AppThemeTest`、`SettingsStoreTest`。 |
| `LnExtendedColors` | **采用** | 保留四类标签 + 状态映射；补类型标签组件。 |
| `TagChip` 一统所有标签 | **改写** | 统一 `LnTag(kind, onClick)`；`StatusBadge` 独立。 |
| `tags_json` 写原始标签 | **采用** | 但必须补导入/本地/遗留书与解析；不能只改加书。 |
| 跨 Tab 搜索返回栈 | **改写** | P0 当前栈 push；P1 嵌套图 + saveState。 |
| 来源预览独立路由 | **改写** | P0 底部 Sheet；P1 路由/深链。 |
| Me/设置子页 | **拒绝（P0）** | P1 再做；P0 一页分组 + 高级折叠。 |
| 任务控制台 | **改写** | P0 只保留列表/空态；分组、重试、取消、忽略 P1。 |
| 搜索历史 | **改写** | P2/P1；不进本轮 P0。 |
| 最近阅读 | **采用（限量）** | P0 只读横栏，用 `updated_at`，补导入兜底；`last_read_at` P1。 |
| 归档/README 的 P0 优先级 | **改写** | 以本文第 7 节为准；03 §6 的“以本文件为准”删除。 |
| Room v2 零迁移 | **采用** | P0 只查询/写现有列；P1 v3 + MigrationTest。 |
| 备份 format=1 | **采用（增量）** | 只加可选字段；旧备份回退 `updated_at`；round-trip 测试。 |

## 合并清单：必须 / 应该 / 可选 / 拒绝

**必须（P0，缺一不可）**

- 4 Tab 书架/发现/任务/设置；移除书架发现按钮；发现不再销毁来源；阅读器换章替换条目。
- 单路由详情 + “简介/目录”双 Tab；继续阅读、收藏、目录入口；保留旧 `chapter-list-screen` tag。
- 发现单搜索框 + 链接 Sheet + 加书停留 + 部分源失败保留其他结果；标签/作者当前栈可点。
- 5 套主题 + amber 默认/回退 + `LnExtendedColors` + `LnTag/StatusBadge`；更新 `AppThemeTest`、`SettingsStoreTest`。
- 只读最近阅读横栏 + 设置一页分组 + 暴露边距/段距/常亮；`tags_json` 写入/解析与导入 `updated_at` 兜底。
- 修 `MainActivityTest`/`ReaderScreenTest` 的“轻小说”断言；新增 `ThemePaletteTest`、`RouteArgsTest`、`BottomBarTest`。

**应该（P1，P0 后立刻做）**

- 详情/目录双路由、目录搜索/排序/筛选、`BookDetailViewModel` 拆分。
- Me 页面、设置子页、任务控制台、搜索历史、跨 Tab 保存来源栈。
- 书架收藏筛选/排序/书架标记、7 天备份提醒、单源重试、结果过滤。
- 8 套主题补齐、深色手动覆盖、平板双栏、发现来源浏览。

**可选（P2）**

- 动态取色、后台下载任务、EPUB/TXT 导入、批量管理、深链/分享/引导、完整阅读历史/书签/批注、Novelia 遗留清理。
- 动效/圆角/内容宽度全套 token、骨架屏与 840dp 宽屏细节。

**拒绝**

- 3 Tab 删任务、Me 只承载设置、02 的详情只读标签、02 的书架发现按钮。
- 用 teal fallback 守旧测试、P0 同时上 8 套主题、P0 新建设置子页/任务控制台/搜索历史。
- 在 P0 改动 Room 必填列或备份必填字段；用 `popUpTo(discover){inclusive=true}`；用 `tagsZh` 下标强行配对原始标签。
