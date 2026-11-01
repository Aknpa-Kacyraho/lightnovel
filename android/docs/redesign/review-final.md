# 最终方案审计（04-final.md）

> 审查对象：`04-final.md`，并对照 01/02/03、`review-round1.md`、指定 Android 源码与测试。
> 基线核实：`@Test` 共 72 个；Room `version = 2`；备份 `format = 1`；本机未构建、未安装、未改代码。
> 结论：**不能按 04 原样动手。** 用户六项明确要求没有硬冲突，但 04 同时把“数据前提、4 Tab、详情双 Tab、发现重做、书架最近阅读、设置重做、8 套主题”压进一次交付，且存在 5 处会直接推翻验收的技术缺口。
> 正确顺序：**先改文档硬伤，再砍到 5 条主线；砍完可动手，原样不可交付。**
> 最高优先级：最近阅读的备份兜底、`tags_json` 端到端、详情双 Tab 的滚动隔离、`TagRef` 配对契约、导航底栏/参数规则。
> 建议本轮主题只上 5 套（teal/lavender/sakura/amber/indigo）；matcha/slate/ember 单独一批，不与详情/发现/设置同批验收。
> 判断依据以源码行为为准，不以三份设计文档的自我声明为准。

## 1. 用户明确要求逐条对照

| 用户要求 | 04 的处理 | 判定 |
| --- | --- | --- |
| 发现放到底栏 | 4 Tab：书架/发现/任务/设置；移除书架右上角发现按钮 | 满足。 |
| 标签、作者可点 | 类型/关键词/来源标签 + 作者可点；状态标签不可点 | 基本满足；来源标签的 P0 落点仍未定义（见 §4.4）。 |
| 简介/目录分开 | 一个详情路由，Hero 下“简介 / 目录”双 Tab，不共享滚动流 | 方向满足；04 的结构图仍是单个 `LazyColumn`，实现会共享滚动（见 §3.7）。 |
| 更多配色 | 8 套主题，新装默认 `amber`，旧 id 保留 | 满足；但 8×2 套 scheme 与一次交付冲突（见 §2）。 |
| 功能分组 | 设置一页 5 组卡片，高级折叠；不建“我的”空壳 | 满足；需保留“任务”Tab，不改成“我的”。 |
| 保留任务 | 明确保留任务 Tab，不删除 | 满足；任务摘要可延后，当前列表已可用。 |

结论：**没有和用户要求正面冲突的条目。** 真正的风险是“看起来都做了，但数据、滚动、返回栈不对”，以及范围过大导致半成品。

允许保留的取舍：详情用“一个路由 + 两个 Tab”是 `review-round1` 的裁决，只要两个 Tab 真正独立滚动，就不算违背“简介/目录分开”；用户要“更多配色”，没有指定必须 8 套，5 套明显不同色相已解决“只有三套”；任务 Tab 保留、暂不做重试/取消/忽略，符合“保留任务”；“不建我的”是合理取舍，设置仍是一级 Tab。

## 2. 一次交付是否装得下

04 不是“一个改造”，而是六个可独立发货的工程包：

1. 数据地基：`BookTags`、`tags_json` 写入/解析、备份导入导出、`updated_at` 兜底、默认主题。
2. 导航壳：4 Tab、发现一级、底栏显隐、阅读器换章替换、参数编码。
3. 详情重写：Hero、继续阅读、收藏、双 Tab、目录搜索/排序/筛选/自动定位、下载/导出。
4. 发现重写：单搜索、链接 Sheet、推荐横向卡、预览 Sheet、加书停留、单源失败、竞态。
5. 书架：最近阅读、5 个筛选、排序、移除收藏星、overflow、空态、备份提醒。
6. 设置与主题：5 组卡片、滑杆、8 套主题、主题网格、高级折叠、危险确认。

按 04 §6.3 的六阶段顺序，任何一阶段回归都会拖住后面；“8 套主题 + 详情目录工具 + 发现卡片重排”都不属于最小闭环。**建议拆成两个可验收批次**，而不是一张大票。

为什么这六包不能同批：数据前提会阻塞所有 UI，先做 UI 只能得到假数据；16 套 scheme 需要逐套对比度校验与设置页网格适配；目录搜索/排序/筛选需要 1000 章夹具和独立滚动恢复测试；发现竞态需要网络假源、旧结果保留、单源失败三类测试；设置滑杆要验证 ViewModel 早已存在但 UI 缺失的参数能真正写回；现有 72 个测试之外还要新增至少 6 类测试，一次改完会让失败定位成本成倍上升。

### 2.1 最小可交付子集（建议作为 0.8.0-alpha.1）

| 主线 | 本轮保留 | 明确移出本轮 |
| --- | --- | --- |
| A 数据前提 | `BookTags`；在线加书写原始 `tags_json`；备份导出/导入可选 `tags_json`/`updated_at`；旧在线书首次打开详情回填；amber 默认/回退 | 非必要的历史书批量重抓 |
| B 导航 | 书架/发现/任务/设置 4 Tab；发现一级；详情底栏规则；阅读器换章替换 | 跨 Tab 嵌套栈、Me 页面、深链 |
| C 详情 | 一个 `chapters/{bookId}` 路由；Hero、继续阅读、收藏；简介/目录双 Tab 且各自独立滚动 | 目录搜索/排序/筛选/自动定位；下载结果汇总可留下，但不扩成任务系统 |
| D 发现 | 单搜索框；链接加书 Sheet；加书停留；单源失败保留其他结果；作者/标签在当前栈 push 搜索 | 推荐横卡重排、预览 Sheet 视觉重做、搜索历史、来源筛选 |
| E 书架/设置 | 最近阅读只读横栏；移除行内收藏星；导入/备份 overflow；设置 5 组；边距/段距/常亮可达；2 列主题卡 | 7 天备份提醒持久化、任务摘要；收藏筛选可先内存实现但不扩 DAO |
| F 主题 | 5 套：teal/lavender/sakura/amber/indigo；amber 默认/回退；对比度测试 5×2 | matcha/slate/ember；8×2 全量、动态取色、平板列数 |

这样仍能直接回应用户的六个痛点，但把“视觉重做”和“目录工具”从交付门槛里拿掉。如果坚持 8 套主题，应单独开一批，只改 `Theme.kt` + palette 测试 + 设置网格，不混入详情/发现。

### 2.2 两批发布的建议边界

| 批次 | 内容 | 必须通过的验收 |
| --- | --- | --- |
| alpha.1 | A+B+C（核心）+D（降噪）+E（最小）+5 套主题 | 4 Tab、详情双 Tab、加书停留、最近阅读、5 主题切换、72+新增测试 |
| alpha.2 | 目录搜索/排序/筛选、8 套主题、推荐区重排、任务摘要、搜索结果过滤 | 8×2 对比度、目录 1000 章定位、任务空态/摘要、真实备份 round-trip |

不砍范围的后果：详情可能先上双 Tab、目录工具来不及做；后 3 套主题只换主色，标签/状态色仍像另一套 App；发现页同时改搜索/推荐/预览/加书停留，任何竞态失败都会让“加书后停留”不可信；设置页值能改但不持久；数据前提未先验收时，最近阅读横栏会在真实导入库上直接漏书。

## 3. 技术前提核验

### 3.1 `tags_json` 写入/解析：只完成一半

- `DirectLibraryService.kt:46` 仍写 `tagsJson = null`，加书时没有把 `detail.book.tags` 序列化。
- `OnlineBookService.kt:48` 也写 `null`；这条是 Novelia 遗留路径，但不改会让“所有在线书”这句话不成立。
- `BackupImportService.kt:88` 仍写 `tagsJson = null`，导入时即使备份里有标签也会丢。
- `BackupExporter.libraryJson`（约 114–140 行）只写 `id/slug/source/source_id/title/title_zh/author`，不写 tags。
- `CatalogAdapter.normalize` 与 `CatalogItem` 没有 tags 字段，备份 catalog 也没有标签入口。
- 结论：仅改加书路径，导入书、旧在线书、旧本地书仍然没有标签。必须补加书写入、详情首次回填、备份可选字段、catalog/import 解析、`BookTagsTest` 与 `BackupCompatibilityTest`。

### 3.2 最近阅读导入兜底：当前不成立

- `BackupExporter.bookStateJson`（约 156–183 行）不写 `updated_at`。
- `BackupExporter.libraryJson` 不写 `added_at`，所以导入后 `createdAt` 也经常为空。
- `ReadStatePlanner.kt:65–83` 只读 `opened`、`finished`、`progress`，不读 `updated_at`。
- `BackupImportService.kt:99–109` 构造 `ReadStateEntity` 时不赋 `updatedAt`。
- `openedAt/finishedAt` 在正常阅读路径也没有写入（`LibraryRepository`、`DirectLibraryService`、`ReaderViewModel` 均只写进度/更新时间）。
- 结论：对当前 App 导出的备份，`openedAt/finishedAt` 通常也为空，于是 04 的 `updatedAt ?: openedAt ?: finishedAt ?: createdAt` 会得到 `null ?: null ?: null ?: null`。
- 必须补：备份 `data/books/*.json` 增可选 `updated_at`；`ReadStatePlanner`/`PlannedReadState` 读取；导入时写入；旧备份缺失时允许 `Instant.now()` 或明确的“导入时间”兜底，并在验收中写清。

### 3.3 主题默认/回退测试：方案正确，文件清单漏项

- `AppThemeTest.kt:8–12` 仍断言 unknown→TEAL；`SettingsStoreTest.kt:22–24` 仍断言默认 `"teal"`。
- `SettingsStore.kt:15` 的 `AppSettings.appTheme` 默认 `teal`；`SettingsStore.kt:62` 读取默认也是 `teal`。
- `SettingsUiState` 的 `appTheme` 默认 `teal`；`LightnovelTheme` 默认参数仍是 `AppTheme.TEAL.id`。
- 结论：必须四处同改，不能只改 `AppTheme.fromId`。04 的测试清单写了 `AppThemeTest`/`SettingsStoreTest`，但 §6.2 文件表漏了 `SettingsStore.kt`；实施时容易只改测试不改数据源。

### 3.4 `TagRef` 配对：规则不可实现

- `MetadataTranslationService` 的 `tagsZh` 只是模型返回的字符串数组。
- 输入 `MetaInput.tags` 与输出 `MetaOutput.tagsZh` 没有“等长、同序”的硬契约。
- 04 禁止“用 `tagsZh` 下标强行配对原始标签”，却没有给替代算法。
- 当前 `DiscoverScreen.kt:304–307` 已经用 index 取原始标签，存在错配风险。
- 必须二选一：明确“仅 `tags.size == tagsZh.size` 时按索引配对；否则只显示原文”；或让 `MetadataTranslationService` 返回 `List<TagRef(original, localized?)>`，并在缓存 schema 中保存成对数据。
- 无论哪种，都要用 `TagRefTest` 覆盖等长、不等长、空译文、重复标签。

### 3.5 导航 `q/mode` 编码：可行，但文档不完整

- 路由若写成 `discover?q={q}&mode={mode}`，`q/mode` 必须是 `nullable = true` 且有 `defaultValue`，否则 `discover` 根路由不匹配。
- `q` 必须 `Uri.encode`；读取端只解码一次；`mode` 只接受 `keyword/tag/author` 白名单。
- 04 只写了原则，没有参数声明、`NavType`、`SavedStateHandle` 与测试。
- `showBottomBar = route.substringBefore("?")` 只能识别 `discover`，不会把 `chapters/{bookId}` 算进去。
- 详情页若显示底栏，还要定义“当前选中哪个 Tab”；平铺 NavHost 没有来源 Tab 信息，容易四个都不选中。必须补 `RouteArgsTest`、`BottomBarTest`。

### 3.6 阅读器换章 `popUpTo`：可行，但需明确 pattern

- 当前 `LightnovelNavHost.kt:157–161` 只有 `launchSingleTop`，不会替换当前条目。
- 04 的 `popUpTo(reader 目的地 id) { inclusive = true }` 方向正确。
- 实施时应使用 `popUpTo("reader/{bookId}/{idx}") { inclusive = true }`，不要用带实际参数的字符串做 pattern。
- 要区分“从详情/任务首次打开”和“阅读器内换章”；前者不应误 pop 掉详情。
- 需要返回栈测试：详情→阅读器→换 3 章→返回，应回到详情而非第 1 章。

### 3.7 详情双 Tab：文档自相矛盾

- 04 §3.1 画的是一个 `LazyColumn`：Hero、继续阅读、`stickyHeader`、简介/目录内容。
- 04 §0/§1 又说“简介与目录不共享滚动流”。
- 一个 `LazyColumn` 只有一个 `LazyListState`，切 Tab 会继承滚动位置。
- 若在同一个列表里切内容，简介会停在目录滚动过的位置，目录自动定位也会把简介带走。
- 必须改成两个兄弟 `LazyColumn`（各自 `LazyListState`），或固定 TabRow + 两个列表；并分别按 `bookId` 保存滚动位置。这一条不是“实现细节”，而是用户能直接看到的“简介/目录混在一起”的复发点。

### 3.8 72 tests / Room v2 / 备份 `format=1`

- 实测 72 个 `@Test`，数字成立；Room `version = 2`，`MIGRATION_1_2` 存在；04 的 P0 零迁移成立。
- 备份 `format = 1`；04 说“不改必填字段”成立，但若为 tags/updated_at 加可选字段，必须同步 exporter、importer、planner 与 round-trip 测试。
- 现有 `BackupExporterTest` 断言 `data/` 条目数为 3；加可选字段时不要新增文件，只改 JSON 内容，避免无谓破坏。
- `Migration2To3Test` 属于 P1，不在本轮；不要为了“最近阅读”提前加 `last_read_at`。

## 4. 文档遗漏、冲突与验收缺口

### 4.1 文件影响表缺项

04 §6.2 至少漏掉：`core/settings/SettingsStore.kt`（两处默认值）、`data/repository/LibraryRepository.kt`（标签搜索/收藏/最近阅读入口）、`data/export/BackupExporter.kt`（tags/updated_at 可选导出）、`data/import/BackupImportService.kt` 与 `ReadStatePlanner.kt`（解析/写入）、`data/catalog/CatalogAdapter.kt` 与 `CatalogModels.kt`（tags 解析）、`data/translation/MetadataTranslationService.kt`（TagRef 契约）、`feature/tasks/TaskCenterScreen.kt`（若保留摘要）、`feature/reader/ReaderComponents.kt`（`44–50` 行仍有 6 个硬编码状态色）、`data/source` 的源站 URL 纯函数（无 `SourceUrlTest`，当前也无对应 UI）。

### 4.2 测试清单缺项

04 §6.2 只列了 `AppThemeTest`、`SettingsStoreTest`、`ThemePaletteTest`、`TagRefTest`、`ContinueTargetTest`、`BookTagsTest` 和 `MainActivityTest` 修正，至少还缺：`ReaderScreenTest`（当前同样查找“轻小说”，不改会继续红）、`RouteArgsTest`（中文/空格/`/`/`?`/`#`/`%`/`&`/emoji）、`BottomBarTest`（4 Tab、详情、`discover?q=` 选中态）、`BackupCompatibilityTest`（旧备份缺字段仍可导入、新备份 round-trip）、`MetadataTranslationServiceTest`（原始标签不被译文覆盖）、`LibraryDaoQueryTest`/`LibraryFilterTest`（组合过滤与空结果）、`SourceUrlTest`（若保留“打开源站”）。

### 4.3 验收缺口

- 04 §7 写“8 套主题浅/深色……对比度通过”，但 02 只给了每套 10 个关键色；其余 `on*Container`、`surfaceContainer*`、`errorContainer` 需要明确是“手写”还是“从主色生成”。两种写法不能混着验收。
- 验收没有覆盖“旧在线书没有 tags”和“导入书没有 updated_at”这两个最可能被真实数据击穿的情况。
- 验收没有覆盖 `TagRef` 等长/不等长两种结果，也没有覆盖作者/标签返回详情后的底栏选中态。
- 验收写“现有 72 tests 全绿（更新允许的断言后）”，但未列出 `MainActivityTest`/`ReaderScreenTest` 两个仪器测试的修正，实际 `connectedDebugAndroidTest` 会红。
- 建议补：旧在线书打开详情后 tags 非空；19 本导入书 progress>0 出现在最近阅读；旧备份缺字段仍可导入；双 Tab 各自 `firstVisibleItemIndex` 独立；作者/标签返回详情底栏选中明确；`q` 特殊字符只编码/解码一次；阅读器换 10 章返回仍回详情；5 套主题对比度与 unknown→amber 通过。

### 4.4 内部不一致

1. **底栏显示规则**：§2.1 说详情保留底栏，但 `showBottomBar = route.substringBefore("?")` 不会把 `chapters/{bookId}` 算进去（当前 `LightnovelNavHost.kt:49` 只匹配顶层）。必须显式加入详情路由白名单，并定义详情页 4 个 Tab 的选中态。
2. **详情 Tab 滚动**：结构图是单 `LazyColumn`，却承诺“不共享滚动流”；见 §3.7。
3. **Tab 顺序**：04 §3.1 写“简介 / 目录”，02 §6 写“目录 / 简介”；默认又有进度进目录。顺序不是功能错误，但必须在文档里统一。
4. **来源标签**：04 §4.1 表格写“来源可点”，落点却写“P1；本轮可只搜索”。把“Kakuyomu”当关键词搜索不是用户预期；本轮要么不显示可点态，要么实现 provider 过滤。
5. **历史文档**：01/03 仍写“我的/3 Tab”和详情/目录双路由；04 改 4 Tab + 双 Tab 是正确的，但必须在 04 开头声明 01 的 `me/*`、03 的 `BookDetailViewModel`/`ChapterCatalogViewModel` 不再作为 P0 依据。

## 5. 五个最可能翻车的点与规避

| # | 翻车点 | 具体表现 | 规避 |
| --- | --- | --- | --- |
| 1 | 数据前提假落地 | 新加的书有标签，导入的 19 本没有；最近阅读横栏漏掉导入书；`updated_at` 永远空 | 先做 `BackupExporter` 可选 `tags`/`updated_at` + `ReadStatePlanner` 解析 + `BackupImportService` 写入；旧在线书首次打开详情回填 tags；用真实 v2 库/19 本备份做 round-trip；`BookTagsTest` + `BackupCompatibilityTest`。 |
| 2 | 详情双 Tab 共享滚动 | 切到简介仍停在目录的滚动位置；目录“自动定位当前章”把简介也跟着滚走 | 两个兄弟 `LazyColumn`，各自 `LazyListState` 按 `bookId` 保存；只在目录列表做当前章定位；写 UI 测试断言两个 Tab 的 `firstVisibleItemIndex` 独立。 |
| 3 | 导航参数/返回栈 | `discover?q=` 打不开、中文/`/` 被截断；详情没有底栏；阅读器换 10 章返回 10 次 | 集中 `AppDestinations`；`q` 用 `nullable`/`defaultValue` + `Uri.encode`；`showBottomBar` 显式白名单（顶层 + `chapters/{bookId}` + `discover?...`）；阅读器用 `popUpTo("reader/{bookId}/{idx}"){inclusive=true}`；`RouteArgsTest` + `BottomBarTest` + 真实 NavHost 返回路径测试。 |
| 4 | 标签配对错位 | `tagsZh` 与 `tags` 不等长时把“转生”译名配到“ざまぁ”原文，点击搜索到错误标签 | 明确契约：仅 `tags.size == tagsZh.size` 时按索引配对；否则只显示原文、不显示译文；或让 `MetadataTranslationService` 返回 `List<TagRef>`；`TagRefTest` 覆盖等长、不等长、空译文。 |
| 5 | 8 套主题与设置网格 | 16 套 scheme 对比度不达标；8 个卡片把设置页撑爆；默认/回退在三处不一致 | 本轮只上 5 套并统一从 `AppTheme` 派生；2 列网格在 360dp 实测；`AppThemeTest` unknown→AMBER、`SettingsStoreTest` 默认 amber、`ThemePaletteTest` 5×2（若坚持 8 套则 8×2）；业务页面禁用字面色值。 |

另外四个中风险：`source` 标签“可点但只搜索”会制造空结果错觉；`TaskCenterScreen` 摘要若只统计 `observeActiveTasks` 的 `LIMIT 100`，任务多时数字会偏小；书架空态与备份提醒同时出现时不要提示“去备份”；5 个筛选 Chip 在 360dp 可能溢出，必须横向滚动或换 FlowRow；详情底栏显示但四个 Tab 都不选中会被当成 Bug。

## 6. 最终结论

- **可以动手吗：不能按 04 原样动手。**
- **必须先改文档：是。** 至少修正 04 §3.7 双 Tab 单列表结构、04 §2.1 底栏白名单、04 §6.1 备份/导入链路、04 §6.2 文件/测试清单、04 §4.1 来源标签落点。
- **必须砍范围：是。** 以 §2.1 的 5 条主线作为 alpha.1；把 8 套主题中的 3 套、目录搜索/排序/筛选、推荐卡重排、搜索历史、任务摘要、跨 Tab 状态栈移到后续批次。
- **动手门槛**：数据 round-trip 测试先绿；双 Tab 滚动测试先绿；4 Tab/详情底栏/阅读器返回栈测试先绿；72 个旧测试（更新 `AppThemeTest`/`SettingsStoreTest` 后）与新增测试全绿；真机 19 本备份导入后最近阅读与标签抽查通过。
- **不满足以上门槛时的建议**：只发“数据前提 + 4 Tab + 详情双 Tab + 发现降噪 + 书架/设置最小修复”，主题只上 5 套；不要把 8 套主题当作本轮卖点。

建议实施顺序（每步单独可回退）：(1) `BookTags` + `tags_json` + 备份可选字段 + 默认主题 + 测试，先不碰 UI；(2) 4 Tab 导航壳 + 详情底栏白名单 + 阅读器 `popUpTo` + 导航测试；(3) 详情 Hero/继续阅读/收藏/双 Tab，目录只做列表与当前章高亮；(4) 发现单搜索/链接 Sheet/加书停留/单源失败/标签作者入口；(5) 书架最近阅读/收藏星移除/overflow，设置 5 组与已有参数暴露；(6) 5 套主题与 2 列网格，真机 19 本备份冒烟；(7) 全量测试、`lintDebug`、真机返回栈检查，通过后再排 alpha.2。

> 本审计只读源码与文档，未运行 Gradle、未安装 APK、未修改任何业务代码。
