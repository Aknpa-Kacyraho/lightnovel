# Ka小说家 0.8 改造最终方案

> 合并来源：`01-information-architecture.md`、`02-visual-system.md`、`03-product-engineering.md`、`review-round1.md`。
> 裁决原则：先解决用户看得到、摸得到的痛点；不为“架构正确”增加页面和返回栈；保留现有数据/备份/测试兼容；允许底层重构，但每一阶段可验证、可回退。
> 参考：`auto-novel` 只吸收信息层级、标签语义、继续阅读、简介折叠、设置分组等交互思想；不复制 GPL 代码、Vue/CSS/资产，不引入登录、Wenku、评论、论坛、远端同步。

## 0. 用户反馈与最终取舍

| 用户反馈 | 最终处理 |
| --- | --- |
| 标签颜色和主题对不上 | 统一 `LnTag`，四类标签全部从当前 `ColorScheme` 派生；禁止页面硬编码颜色。 |
| 简介和章节排在一起不美观 | 保留一个书籍详情路由，改为 Hero + 吸顶“简介 / 目录”双 Tab；两者不共享滚动流。 |
| 标签、作者不能点 | 类型/关键词/来源标签可点，作者可点；统一跳到发现搜索，传原始日文标签/作者名。状态标签不可点。 |
| 参考 auto-novel | 吸收“继续阅读优先、作者/标签可搜索、简介折叠、操作主次、设置分组、发现分节”；不复制代码。 |
| 外观太少、不喜欢现有三套 | 扩展到 8 套明显不同色相的主题，新装默认 `amber`；旧 `teal/lavender/sakura` id 继续可用。 |
| 功能杂乱、没有归类 | 发现升为底栏一级；书架降噪；设置改分组卡片；低频操作进 overflow/高级折叠；任务 Tab 保留。 |
| 高质量 App | 统一 token、空态/错误态、加载态、点击区、对比度、状态徽标；不靠堆功能。 |
| 先写 3 份文档、自查、合并再动手 | 已完成 01/02/03、第一轮交叉评审和本最终版；实施前再做一次最终文档审计。 |
| 允许底层重构 | 导航壳、主题系统、标签组件、详情页结构可重构；Room/备份/翻译管线不推倒重来。 |

## 1. 目标 / 非目标

### 目标

- 底栏：**书架 / 发现 / 任务 / 设置**。发现是独立一级入口，不再藏在书架右上角。
- 书籍详情：一个路由、两个 Tab；简介与目录彻底分开；继续阅读、收藏、下载、导出、源站入口有明确位置。
- 实体可点：作者、类型/关键词/来源标签可点；统一进入发现搜索；传原始日文值，显示中文译文。
- 视觉：8 套主题、统一标签/状态/来源徽标、统一卡片/间距/圆角；标签颜色随主题变化。
- 书架：最近阅读横栏、筛选、导入/备份收进 overflow；移除每行常驻收藏星。
- 发现：首屏只留一个搜索入口；“从链接添加”进 Sheet；加书后停留原页；单源失败不清空其他结果。
- 设置：外观/阅读/翻译/数据/关于分组；高级端点/模型折叠；暴露边距、段距、常亮等已有能力；危险操作确认。
- 数据前提：在线加书写入原始 `tags_json`；最近阅读兼容导入书缺失 `updated_at`；主题默认/回退改 `amber`。

### 非目标

- 不做“我的”新页面、设置子页、账号、云同步、Wenku、评论、论坛、后台翻译/通知。
- 本轮不拆“详情/目录”双路由；不做跨 Tab 多返回栈；不做平板双栏、动态取色、搜索历史、任务重试/取消/忽略。
- 不重写阅读器分页、翻译管线、导入/备份格式；不新增 Room 必填列。
- 不复制 GPL 代码；不把 auto-novel 的桌面侧栏/复杂筛选矩阵搬进手机。

## 2. 信息架构与导航

### 2.1 底栏（4 Tab）

| 顺序 | 名称 | 图标 | 职责 |
| --- | --- | --- | --- |
| 1 | 书架 | `ic_nav_library` | 最近阅读、全部书籍、本地搜索/筛选、导入入口。 |
| 2 | 发现 | 新增 `ic_nav_discover` | 搜索、周榜推荐、热门标签、链接加书、来源预览。 |
| 3 | 任务 | `ic_nav_tasks` | 翻译进行中/失败/未译全；保留现有入口。 |
| 4 | 设置 | `ic_nav_settings` | 外观/阅读/翻译/数据/关于；高级折叠。 |

- 不新建“我的”空壳；不删除任务 Tab。用户要求的是“发现升为一级”，不是“删除任务”。
- 书架顶栏不再放“发现”按钮；发现只从底栏进入。
- 详情/阅读器/任务/设置是否显示底栏：详情保留底栏（仍属浏览层）；阅读器隐藏；任务/设置为 Tab 根，显示。`showBottomBar` 用显式白名单：顶层四个 route + `chapters/{bookId}` + `discover?...`；详情页固定选中书架 Tab，避免“四个都不选中”。
- 详情路由从书架进入时书架 Tab 高亮；从发现进入时发现 Tab 高亮。实现上通过 `currentBackStackEntry` 的 `savedStateHandle["originTab"]` 传递来源，缺省为书架。
- 图标新增两个 vector drawable；底栏选中色用 `primary`，未选用 `onSurfaceVariant`。

### 2.2 路由

| 路由 | 入口 | 底栏 | 返回/状态 |
| --- | --- | --- | --- |
| `library` | 启动/底栏 | 显示 | 书架根；搜索/筛选保留。 |
| `discover?q={q}&mode={mode}` | 底栏/标签/作者 | 显示 | 同一发现目的地；`q/mode` 可选；清空 query 回推荐。 |
| `tasks` | 底栏 | 显示 | 任务根。 |
| `settings` | 底栏 | 显示 | 设置根。 |
| `chapters/{bookId}` | 书架/发现 | 显示 | 书籍详情 + 简介/目录 Tab；保留旧 `chapter-list-screen` tag。 |
| `reader/{bookId}/{idx}` | 继续阅读/目录/任务 | 隐藏 | 换章替换当前条目，不按章累积返回栈。 |

- 作者/标签点击：在当前栈 push `discover?q=...&mode=tag|author`；返回回到详情。跨 Tab 恢复来源栈是 P1，不在本轮做“魔法”。
- 动态参数用 `Uri.encode`；`q` 走 query 参数，避免作者名中的 `/`；`mode` 白名单。
- 发现加书成功不自动跳转；卡片原位变“已加入”，Snackbar 提供“查看”。
- 阅读器换章：`popUpTo(reader 目的地 id) { inclusive = true }` + `launchSingleTop`。

## 3. 书籍详情页

### 3.1 结构

```
TopAppBar：返回 / 书名 / 收藏 / 更多
Column
├─ 固定 Hero：封面、中文书名、日文书名、可点作者、来源/话数、主操作
├─ 继续阅读卡（有进度才显示）
├─ 固定 TabRow：简介 / 目录
├─ 简介 Tab：独立 LazyColumn（简介卡、标签卡、信息卡）
└─ 目录 Tab：独立 LazyColumn（目录工具 + 章节列表）
```

两个 Tab 必须是两个兄弟 `LazyColumn`，各自 `LazyListState`，不得共用一个 `LazyColumn`；否则切换 Tab 会继承对方的滚动位置，重新变成“简介和章节混在一起”。Hero 可随 Tab 内容一起滚动，但两个 Tab 的列表状态必须隔离。

### 3.2 交互

- **Hero**：文字封面（无封面字段）；书名最多 2 行；作者可点；来源徽标可点（跳发现按来源过滤，P1）；主按钮“继续阅读 第 X 章 / 开始阅读”。
- **继续阅读**：`progressIdx` 在 `1..chapters.size` 用它；0/null 用第 1 章；越界回退最后一章；无章节禁用。
- **收藏**：详情主操作星标；写 `read_state.favorite`；失败 Snackbar 回滚。
- **更多**：下载全部、导出 EPUB、打开源站；下载显示 X/Y 进度；单章失败不终止整本，结束汇总成功/失败。低频操作不占顶栏。
- **简介**：默认 6 行 + 渐隐 + “展开全部”；中文优先，缺失回落原文；空简介显示“暂无简介”并保留标签/信息。
- **标签**：`LnTag` FlowRow；中文译文优先，点击传原始日文标签；最多 10 个 + 展开；不再用 `/` 拼接纯文本。
- **目录**：搜索、正/倒序、状态筛选（全部/已译/未译/失败/缺文件）；当前章高亮；进入自动定位当前章，用户手动滚动后不再抢夺；行高 56dp，点击进阅读器。
- **默认 Tab**：有进度默认目录，无进度默认简介；用户手动切换后不再自动覆盖。
- **本地书**：显示“本地导入”；隐藏下载/源站；保留收藏、继续、导出、目录。
- **在线书**：显示平台徽标、话数、源站入口、翻译覆盖（P1）。
- **状态**：加载用骨架/局部进度；源站失败保留本地缓存信息并内联重试；目录空显示“源站可能变更/重新导入”。

## 4. 标签与主题

### 4.1 标签系统

新增 `LnTagKind`：`TYPE / KEYWORD / SOURCE / STATUS`；统一组件 `LnTag(kind, text, onClick?)`。

| 类型 | 容器 | 文字 | 可点 | 落点 |
| --- | --- | --- | --- | --- |
| 类型 | `secondaryContainer` | `onSecondaryContainer` | 是 | 发现 `mode=tag`，原始日文 |
| 关键词 | `surfaceVariant` | `onSurfaceVariant` | 是 | 同上 |
| 来源 | `surface` + outline | `onSurfaceVariant` | 是 | 发现按来源过滤（P1；本轮可只搜索） |
| 状态 | 状态色 12% + 状态色文字 | 同左 | 否 | 失败任务单独“重试” |

- 状态色：已译 `primary`、进行中 `secondary`、未译全 `tertiary`、失败/缺文件 `error`、生肉 `onSurfaceVariant`。
- 标签数据用 `TagRef(original, localized?)` 配对；只有 `tags.size == tagsZh.size` 时才按索引配对，否则整组只显示原文，禁止错位配对。译文缺失显示原文，点击仍传原文。`MetadataTranslationService` 的缓存继续保存两个数组，但 UI 必须先经过 `TagRef` 校验。
- `BrandFilterChip` 保留；新增 `LnTag`、`StatusBadge`、`BookCover`、`SectionHeader`。
- 业务页面禁止 `Color(0xFF...)`/`Color.Blue` 等硬编码；阅读器状态点也改从 `MaterialTheme.colorScheme` 取。

### 4.2 主题（8 套）

保留 `teal/lavender/sakura` id，新增 `matcha/amber/indigo/slate/ember`；新装默认 `amber`，未知/空 id 回退 `amber`。旧 id 用户会看到重画后的同 id 配色，这是有意变更。

| id | 名称 | 气质 |
| --- | --- | --- |
| `teal` | 青灯 | 冷青 + 铜色，清透纸感 |
| `lavender` | 紫夜 | 灰紫 + 苔绿，低饱和夜色 |
| `sakura` | 樱纸 | 绯粉 + 墨绿，柔和和纸 |
| `matcha` | 苔庭 | 苔绿 + 雾蓝，自然安静 |
| `amber` | 琥珀 | 琥珀 + 松绿，旧书暖光（默认） |
| `indigo` | 靛蓝 | 靛蓝 + 珊瑚，深夜强对比 |
| `slate` | 墨灰 | 石墨 + 铁锈，克制工具感 |
| `ember` | 枫烬 | 砖红 + 橄榄，戏剧性 |

- 每套 light/dark 必须成对定义 `primary/onPrimary/primaryContainer/onPrimaryContainer/secondary/onSecondary/secondaryContainer/onSecondaryContainer/tertiary/onTertiary/tertiaryContainer/onTertiaryContainer/background/onBackground/surface/onSurface/surfaceVariant/onSurfaceVariant/outline/outlineVariant/error/onError/errorContainer/onErrorContainer`。
- 容器色由主色与 surface 混合生成；`on*Container` 用主色/深色安全值；不用 Material 默认紫色 errorContainer。
- 主题选择器改为 2 列预览卡（色块 + `Aa` + 名称），不再一排 FilterChip；点击即应用。
- 深色模式本轮继续跟随系统；手动覆盖 P1。
- 新增 `ThemePaletteTest` 遍历 8×2，断言关键角色齐全、文本对比度 ≥ 4.5:1；更新 `AppThemeTest`（unknown→AMBER）与 `SettingsStoreTest`（默认 amber）。

## 5. 书架 / 发现 / 任务 / 设置

### 5.1 书架

- 顶栏：`书架` + 搜索 + overflow（导入备份）；移除发现按钮。
- 最近阅读：1–5 本横向卡，显示书名、第 X 章、进度；只显示 `progressIdx > 0`；无数据整段隐藏。
- 筛选：全部/在读/想读/读完/收藏；收藏在内存过滤；搜索标题/作者/标签（标签用 `tagsJson`）。
- 书籍行：封面、标题、作者、进度、本地/在线徽标；移除每行常驻收藏星；点击进详情。
- 备份提醒：仅“有书且从未备份”显示一条可关闭提示；不每次进书架都顶一条警告。
- 空态：无书 →“导入备份”+“去发现”；筛选空 →“清除筛选”；搜索空 →“清除关键词”。
- 导入：overflow + 空态；成功后留在书架并提示备份。

### 5.2 发现

- 首屏：`发现` 顶栏 + 一个搜索框 + “从链接添加”TextButton；不再常驻两组输入框。
- 推荐：横向卡片（封面/标题/作者/来源），最多 12 条；点击打开预览 Sheet；加入按钮在 Sheet 内。
- 热门标签：FlowRow，点击直接搜索；标签来自主题色。
- 搜索结果：纵向卡片（封面 72×96、标题、作者可点、来源、简介 2 行、最多 3 个标签 + `+N`、加入按钮）；整卡点击预览。
- 链接加书：`ModalBottomSheet` 单输入框 + 粘贴 + 示例；支持 Kakuyomu / ncode / 数字 ID；错误就地提示，不关闭。
- 加书：成功停留原页，卡片/预览变“已加入”，Snackbar “查看”；不再自动跳转。
- 状态：首次骨架、搜索中旧结果 + 顶部进度、单源失败只替换该源、全失败可重试、无结果给建议、翻译中不阻塞。
- 搜索/翻译竞态：`requestId` 或查询 token；迟到结果不覆盖新查询。

### 5.3 任务

- 本轮保留现有任务列表与空态；不新增重试/取消/忽略、按书分组、失败角标。
- 任务页增加顶部状态摘要（进行中/失败/未译全）和返回设置/底栏行为；不把已完成成功任务当长期归档。
- 后续 P1 再上按书分组、重试、忽略。

### 5.4 设置

- 一页 5 组卡片：外观、阅读、翻译、数据、关于；不建设置子页。
- 外观：8 套主题预览网格；跟随系统。
- 阅读：阅读纸色（纸白/米黄/护眼/夜间）、字号/行距/边距/段距滑杆、字体/显示模式/翻页模式分段按钮、常亮开关。暴露现有 ViewModel 已有但 UI 缺失的项。
- 翻译：Key 状态、Key 输入、模型、保存；Base URL 收进“高级设置”折叠区。
- 数据：上次备份、导出备份、缓存大小/清理（AlertDialog 确认“只清缓存，不删书/进度/Key”）。
- 关于：应用名、版本、本地优先说明、源站说明；不放登录/Wenku/论坛。
- 危险操作二次确认；取消不执行。

## 6. 数据与工程

### 6.1 数据前提

| 变更 | 内容 | 迁移 |
| --- | --- | --- |
| `tags_json` | `DirectLibraryService` / `OnlineBookService` 加书写入原始标签 JSON；`BookTags` 容错解析；详情/搜索/本地书复用；`BackupExporter` 增可选 `tags` 字段，`BackupImportService` / `CatalogAdapter` 读取；旧在线书首次打开详情回填 | 零迁移，备份只加可选字段 |
| 导入 `updated_at` | `BackupExporter` 增可选 `updated_at`；`ReadStatePlanner`/`BackupImportService` 读取并写入；旧备份缺失时用导入时间兜底；最近阅读排序 `updatedAt ?: openedAt ?: finishedAt ?: createdAt ?: importNow` | 零迁移，备份只加可选字段 |
| 主题默认 | `AppSettings.appTheme`、`LightnovelTheme` 默认、`SettingsUiState` 默认改 `amber`；fallback amber | 设置兼容 |
| 收藏 | 详情写 `read_state.favorite`；书架收藏筛选内存过滤 | 零迁移 |
| 下载 | 逐章结果汇总，单章失败不终止整本；复用 `DirectLibraryService.ensureChapter` | 零迁移 |

- P0 不新增 Room 列、不改 `format=1` 必填字段；P1 的 `last_read_at/error_message/task_ignored_at` 必须 `MIGRATION_2_3` + 测试。
- `MetadataTranslationService` 的 `tagsZh` 与原始 `tags` 通过 `TagRef` 配对；不保证等长时缺失回落原文。

### 6.2 文件影响

| 模块 | 文件 |
| --- | --- |
| 导航 | `navigation/LightnovelNavHost.kt`；新增 `res/drawable/ic_nav_discover.xml`、`ic_nav_me.xml`（若最终用 4 Tab 则不需要 me） |
| 主题 | `ui/theme/Theme.kt`；新增 `ui/theme/LnColors.kt`（`LnExtendedColors`、`ThemePreview`） |
| 组件 | `ui/components/BrandChips.kt`、新增 `BookCover.kt`、`SectionHeader.kt` |
| 详情 | `feature/chapters/ChapterListScreen.kt`、`ChapterListViewModel.kt`（重写为 Hero + 双 Tab） |
| 发现 | `feature/discover/DiscoverScreen.kt`、`DiscoverViewModel.kt` |
| 书架 | `feature/library/LibraryScreen.kt`、`LibraryViewModel.kt` |
| 设置 | `feature/settings/SettingsScreen.kt`、`SettingsViewModel.kt` |
| 数据 | `data/source/DirectLibraryService.kt`、`data/online/OnlineBookService.kt`、新增 `data/local/BookTags.kt`、`data/export/BackupExporter.kt`、`data/import/BackupImportService.kt`、`data/import/ReadStatePlanner.kt`、`data/catalog/CatalogAdapter.kt`、`core/settings/SettingsStore.kt` |
| 测试 | `AppThemeTest`、`SettingsStoreTest`、`MetadataTranslationServiceTest`、新增 `ThemePaletteTest`、`TagRefTest`、`ContinueTargetTest`、`BookTagsTest`、`RouteArgsTest`、`BottomBarTest`、`BackupCompatibilityTest`；修 `MainActivityTest` / `ReaderScreenTest` 的“轻小说”断言 |

### 6.3 实施顺序

1. **数据/主题地基**：`BookTags`、`tags_json` 写入、主题 8 套 + `LnExtendedColors`、测试更新。
2. **导航壳**：4 Tab、发现一级、移除书架发现按钮、阅读器换章替换。
3. **详情双 Tab**：Hero、继续阅读、收藏、简介/目录、目录搜索/排序/筛选。
4. **发现降噪**：单搜索、链接 Sheet、加书停留、预览 Sheet、标签/作者点击。
5. **书架/设置**：最近阅读、筛选、设置分组、主题网格、滑杆、高级折叠。
6. **收尾**：Snackbar/错误态、空态、无障碍、真机冒烟、全量测试/lint。

## 7. 验收

- [ ] 底栏为书架/发现/任务/设置；发现 1 击可达；书架无发现按钮。
- [ ] 详情为 Hero + 继续阅读 + 收藏 + 简介/目录双 Tab；简介与目录不共享滚动流。
- [ ] 作者/标签可点；点击进入发现搜索；返回详情；状态标签不可点。
- [ ] 发现首屏只有一个搜索入口；链接加书在 Sheet；加书后停留；单源失败保留其他结果。
- [ ] 书架有最近阅读、收藏筛选；行内无收藏星；导入/备份收进 overflow。
- [ ] 设置 5 组；主题 8 套预览卡；字号/行距/边距/段距/常亮可达；高级端点折叠；清缓存确认。
- [ ] 8 套主题浅/深色标签/状态/正文对比度通过；业务页面无硬编码颜色。
- [ ] 最近阅读不漏导入书；`tags_json` 对在线书/本地书可解析；主题默认/回退 amber。
- [ ] 现有 72 tests 全绿（更新允许的断言后）；新增主题/标签/继续阅读测试全绿；`lintDebug` 无新增 error。
- [ ] 真机：4 Tab、详情 Tab、标签/作者跳转、加书、最近阅读、8 主题切换、深色、返回栈无异常。


## 8. 实施补充（2026-10-31）

- 当前构建：`0.9.0`（versionCode 23）。
- 任务中心已按书分组，支持状态筛选（全部/失败/未译全/进行中）；失败/未译全可带 `retry=true` 进入阅读器自动重试。
- 从标签/作者进入发现搜索时，搜索页提供返回箭头；仍保留当前栈 push 语义，完整多 Tab 栈恢复未做。
- 新增 `TaskGroupingTest`、`BookTagsTest`、`ThemePaletteTest`、`TranslationProvidersTest`、`TranslationCalibratorTest`、`StoryMemoryStoreTest`、`TranslationPromptsTest`、`StoryMemoryServiceTest`、`KnowledgeStoreTest`、`KnowledgeExtractionServiceTest`、`KnowledgeQueryServiceTest`、`EntityHighlighterTest`、`WorldlineStoreTest`、`WorldlineServiceTest`、`BranchKnowledgeExtractorTest`、`WorldlineContextBuilderTest`；当前 123 tests / 0 failures / 1 skipped。
- 翻译设置支持 OpenAI 兼容供应商预设与自定义端点；首次保存自动校准 batch/sakura 协议和安全块大小，结果按端点+模型缓存，可手动重测。
- 故事记忆按书存 `story.json`：术语/人物卡/梗概/风格/经验；翻译只注入本段相关记忆，自动生成章节梗概；「本书设定」可编辑与扫描人物/检查译名；阅读器支持「润色本章」。
- 事实级知识库按书存 `knowledge.json`：Entity/Fact/Relation/VoiceFact/Secret，带原文 quote 与锚点；翻译后增量抽取；阅读器查询模式支持正文下划线、点词卡片、章节出处和「资料更新中」状态。
- 完整世界线：从指定章分叉、用户介入角色行动；plan → Writer → Validator → 分支知识抽取 → branchCursor/branchExtractedThrough；CharacterView 只含分叉前已知 + 分支实际经历，Writer 永不看 reveal_content；对照型生成差异报告。
- 真机回归因测试机断开暂未重新安装 alpha.2；alpha.1 已完成 4 Tab/详情双 Tab/主题/发现/标签搜索的截图验证。

- 参考官方 Novelia 客户端：发现页增加最近搜索、来源筛选；结果行改为紧凑行（封面/标题/作者/话数/更新时间/标签/加入）。只借鉴信息层级，不复制 GPL 代码。

- 本地导入：库顶部“更多”与空态加入 TXT / EPUB；TXT 按章标题分章，EPUB 按 OPF/spine 抽正文；中文文本写入译文轨，日文文本保留原文轨。
- 主题模式：外观页可选跟随系统/浅色/深色，与 8 套主题独立。
- 成为小说家吧：`api.syosetu.com` 不可达时自动回退 `yomou.syosetu.com` 搜索与周榜 HTML，直连章节页仍可用。

- 导航：每个 Tab 使用独立 NavHost + saveable state；详情、搜索、阅读器在各自 Tab 栈内，切 Tab 后可恢复。
- 后台下载：WorkManager 按书入队，逐章缓存、已有章节跳过、中断后可续。
- 任务取消：全局 TranslationTaskRegistry 记录运行中任务；任务页取消会终止对应 Job 并回写状态。
- 高级筛选：发现结果支持来源、连载状态、字数区间；支持保存当前搜索组合。
- 元数据：先请求书名/简介/标签并立即刷新，章节标题后续并行补全，减少首屏等待。

- 任务忽略：任务页可忽略失败/未译全任务，忽略键持久化在本机。
