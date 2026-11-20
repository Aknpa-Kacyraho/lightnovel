# Changelog

本项目从 `1.0.2` 起使用签名 Release。`main` 只维护 Android App；
旧 Web/Python 实现保存在远端 `archive/web`，不再参与构建与发布。

## 1.6.1 — 2026-11-20

### 修复

- 快速切换原文/译文/双语时，旧加载请求会被取消，最终内容与最后一次选择一致。
- 跨章书签/搜索结果会在目标章加载完成后自动定位到段落，不再只到章首。
- 连续添加书签时，新提示立即替换旧提示，不再排队延迟。

### 工程

- `ReaderViewModel` 增加 `loadJob`，`load()` 取消旧请求并在写状态前 `ensureActive()`。
- 新增 `PendingReaderJump`（内存一次性锚点），挂到 `AppContainer`；
  `ReaderRoute` 跨章写入、目标章加载后消费。
- 书签提示改用 `collectLatest`。
- 新增 `PendingReaderJumpTest`；`versionCode 54` / `versionName 1.6.1`。

## 1.6.0 — 2026-11-20

### 修复

- 滚动模式与翻页模式的阅读进度不再错位：滚动模式保存段号，恢复时换算成起始行号。
- 滚动模式添加书签使用当前段落（不再把行号当段号），预览与跳转正确。
- 滚动模式下点击书签/搜索结果，列表会滚动到目标行（已在目标行时不重复滚动）。

### 工程

- 新增 `ReaderScrollMapping.kt`：`paragraphIndexForLine` / `lineForParagraph` 纯函数。
- `ReaderViewModel` 的进度写入、恢复、书签与翻译锚点统一使用段号。
- `ReaderScrollMappingTest` 覆盖多段多行、bilingual、越界与往返。
- `versionCode 53` / `versionName 1.6.0`。

## 1.5.2 — 2026-11-20

### 用户可见

- 书架筛选行从 7 个控件减到 4 个：书架（全部/在读/想读/读完）、收藏、已移出、排序。
- 阅读器「更多」改为底部 Sheet：分组标题完整、内容可滚动、点击一项立即关闭。
- 功能与顺序不变，禁用条件不变。

### 工程

- `LibraryScreen` 用书架下拉替代三个状态 chip，切换时清收藏/已移除（与旧「全部」一致）。
- 新增 `ReaderMenuSheet`（ModalBottomSheet + 70% 高度），`TranslationMenu` 不再用 DropdownMenu。
- `ReaderTopBar`/`TranslationMenu` 增加 `backgroundColor` 以匹配纸色。
- `versionCode 52` / `versionName 1.5.2`。

## 1.5.1 — 2026-11-20

### 用户可见

- 「本书设定 → 术语」新增搜索：按原文、译名、别名过滤；显示「共 N 条 / N / 总数」。
- 输入已存在的原文时提示「已存在同名术语，保存会覆盖译名」。
- 删除术语前二次确认，说明「相关章节会标记过期，译名不再锁定」。

### 工程

- 新增 `filterGlossary(entries, query)` 纯函数与 `GlossaryFilterTest`。
- `TermsTab` 增加搜索状态、空态区分、覆盖提示与删除确认。
- `versionCode 51` / `versionName 1.5.1`。

## 1.5.0 — 2026-11-20

### 用户可见

- 沉浸阅读现在是真全屏：隐藏系统状态栏与导航栏，从屏幕边缘上滑可临时唤出。
- 阅读页常驻行只保留「语言」与「朗读」；滚动/翻页切换收进「更多 → 阅读」。
- 菜单移除重复的「字号减小/增大」，字号统一在「更多 → 排版」调整。
- 沉浸提示与退出按钮保留 12dp 底部间距，不贴屏幕边缘。

### 工程

- `DisposableEffect(immersive)` 控制 `WindowInsetsCompat.Type.systemBars()`，
  `onDispose` 恢复；系统栏图标颜色仍由纸色 effect 管理。
- `ReaderMenuAction` 移除 `FONT_DECREASE/FONT_INCREASE`，新增 `TOGGLE_READER_MODE`。
- `ReaderMenuTest` 更新为 16 项（无故事记忆时 15 项）。
- `versionCode 50` / `versionName 1.5.0`。

## 1.4.2 — 2026-11-20

### 用户可见

- 阅读器「更多 → 排版」：字号、行距、左右边距、段落间距四个滑块，即时生效。
- 「恢复默认」一键回到 18 / 1.7 / 16 / 8，并持久化。
- 翻页模式底栏进度可拖动：拖动时显示「第 x / y 页」，松手跳转。
- 调整排版时按当前页锚点恢复，尽量不丢阅读位置。

### 工程

- `ReaderProgress` 增加 `progressToPage` / `pageToProgress` 与测试。
- ViewModel 排版 setter 分页前捕获锚点；新增 `resetTypography()`。
- 新增 `TypographySheet`；`ReaderBottomBar` 增加可拖进度。
- `versionCode 49` / `versionName 1.4.2`。

## 1.4.1 — 2026-11-20

### 用户可见

- 阅读器「更多 → 资料」新增「搜索本书」：在当前书正文中搜索关键词。
- 结果包含章节、前后文与关键词高亮；同章点击定位到命中段落，跨章跳到目标章。
- 搜索范围随显示模式：译文模式搜译文、原文模式搜原文，缺失自动回退。
- 输入 300ms 防抖；每章最多 3 条、总数 30 条；关闭即取消。

### 工程

- 新增 `findHits(...)` 纯函数与 `BookSearchService`（逐章 IO，不整本入内存）。
- `ReaderViewModel` 增加 `searchResults/searching/searchBook/clearSearch`。
- 新增 `BookSearchSheet` 与 `BookSearchTest`。
- `versionCode 48` / `versionName 1.4.1`。

## 1.4.0 — 2026-11-20

### 用户可见

- 阅读器「更多」新增「添加书签」与「书签列表」：记录章节、段落、40 字预览。
- 同一段重复添加是幂等的；列表可跳转、可删除，空态给出添加路径。
- 同章书签点击直接回到原段落；跨章书签先跳到目标章（V1 限制）。

### 工程

- 数据库 v5：`bookmarks` 表 + `MIGRATION_4_5` + `schemas/5.json`。
- DAO/Repository 增加书签观察、upsert、删除、查询。
- `ReaderViewModel` 增加 `bookmarks`、`addBookmark`、`removeBookmark`、`jumpToAnchor`。
- 新增 `BookmarkSheet`、`relativeTime(...)` 与 `BookmarkTimeTest`。
- `versionCode 47` / `versionName 1.4.0`。

## 1.3.2 — 2026-11-20

### 用户可见

- 「已移出」视图新增「删除本地数据…」：二次确认后删除正文、译文、世界线、资料库与进度。
  在读/想读/读完视图不显示该入口。
- 删除前自动停止下载、翻译与预译队列；删除成功有 Snackbar，失败会提示原因。

### 工程

- `ContentStore.deleteBook(storageDir)` 递归删除 `novels/<storageDir>`，幂等且拒绝空目录名。
- DAO 增加 `deleteChapters/deleteReadState/deleteBook`；`LibraryRepository.deleteBook` 事务删除。
- `LibraryViewModel.messages` SharedFlow 驱动 Snackbar；`onBookRemoved` 停止预译队列。
- 新增 `ContentStoreTest.deleteBookRemovesOnlyThatDirectory`、`LibraryDaoTest.deleteBookRemovesChaptersAndReadState`。
- `versionCode 46` / `versionName 1.3.2`。

## 1.3.1 — 2026-11-20

### 用户可见

- 单段重译后会写入当前模型/提示词指纹，不再误报「译文过期」。
- 翻译章节确认框显示每千字费用区间（按当前模型价格估算，实际以 token 计费）。
- 阅读器「翻译本章」显示当前章字数与预估费用区间。
- 可重试的翻译失败（429 / 超时 / 503）会在队列里自动再试一次。
- 任务页最多显示 300 条（原 100 条），旧失败不再被挤出。

### 工程

- `retranslateParagraph` 的 sidecar 补齐 `translationConfigHash/modelProvider/modelId/promptVersion/storyRevision`。
- 新增 `CostEstimator`（`estimateTranslationCost` / `formatCostRange`）与测试。
- `ReadingTranslationCoordinator` 返回 `TargetResult(success, retryable)`；
  `shouldRetryAfterFailure(...)` 每章最多重试一次。
- `versionCode 45` / `versionName 1.3.1`。

## 1.3.0 — 2026-11-20

### 用户可见

- 本地 TXT / EPUB 重复导入不再新增一本书：按文件内容识别，已存在时提示
  「已在书架，没有重复添加」；曾移出的书会恢复到原位置，进度与译文保留。
- 书架新增排序：标题 / 最近阅读 / 最近添加，选择会记住。

### 工程

- 数据库 v4：`books.import_hash` + 唯一索引，新增 `MIGRATION_3_4`。
- 本地导入先算 SHA-256 再解析；`LocalDocumentImporter.Result(existing, restored)`。
- 新增 `LibrarySort` 与 `sortLibrary(...)` 纯函数；`SettingsStore.librarySort` 持久化。
- 新增 `LibrarySortTest`，补迁移、DAO 去重与默认排序测试。
- `versionCode 44` / `versionName 1.3.0`。

## 1.2.2 — 2026-11-20

### 用户可见

- 阅读时单击正文即可隐藏/显示顶栏与底栏；查询模式下点词优先，不会误触。
- 底栏新增 2dp 本章阅读进度线，翻页与滚动模式都随进度变化。
- 书架「继续阅读」卡补进度线，与列表卡信息一致。
- 第一次进入沉浸时提示「单击正文或点下方按钮退出沉浸」，3 秒后消失。

### 工程

- 新增 `readerChapterProgress(...)`、`shelfProgress(...)` 纯函数与 `ReaderProgressTest`。
- `ReaderPageView` 增加 `onCenterTap`；普通模式点击空白切换沉浸。
- `versionCode 43` / `versionName 1.2.2`。

## 1.2.1 — 2026-11-20

### 用户可见

- 深色模式下作者、进度、说明等次要文字整体调暗，主次更清楚，夜里不刺眼。
- 深色标签容器降低饱和度，题材/关键词/来源不再像荧光贴纸。
- 书架卡片与任务卡统一容器色，描边减淡，列表不再被一圈圈亮框包围。

### 工程

- 8 套深色主题的 `onSurfaceVariant` 与 `surfaceVariant` 同步调整，保持 7–10:1。
- 容器混合抽 `DARK_CONTAINER_MIX = 0.24f` / `LIGHT_CONTAINER_MIX = 0.14f`。
- 新增 `ThemeContrastTest`：8 套深色的次要文字、主文字、标签文字对比度。
- `versionCode 42` / `versionName 1.2.1`。

## 1.2.0 — 2026-11-20

### 用户可见

- 阅读纸色新增「跟随系统」，并作为新安装默认：系统深色时自动用夜间纸色，
  浅色时用纸白；已手动选过纸色的用户保持原选择。
- 未翻译章节不再常驻「本章还没翻译」横幅；只有翻译进行中、失败、预译队列
  运行/暂停/出错时才显示。
- 夜间纸色正文调暗为 `#BDBAB2`，长时间关灯阅读不再觉得字在发光。

### 工程

- `ReaderTheme` 增加 `AUTO` 与 `resolve(dark)`；渲染前统一解析，偏好与显示分离。
- 新增 `shouldShowTranslationBanner(...)`、`contrastRatio(...)` 纯函数。
- 新增 `ReaderThemeTest`、`ReaderBannerTest`，补 `SettingsStoreTest` 纸色默认值。
- `versionCode 41` / `versionName 1.2.0`。

## 1.1.1 — 2026-11-18

### 用户可见

- 平板与横屏阅读：正文最大宽度 680dp 并居中，长行不再横跨整块屏幕；手机竖屏不变。
- 系统字体放大时，任务卡动作行与书架空态入口自动换行，不再挤压或截断。
- 阅读器「翻译本章」显示当前章规模（约 N 字 / 约 X.X 千字），
  0 字或加载中不显示。
- 超大章节首次打开超过 300ms 时显示「正在排版长章节…」，不再像卡死。

### 工程

- 新增 `ReaderViewportTest`（手机 / 临界 680 / 平板 / 零边距 / 极端边距）。
- 排版宽度抽为 `readerContentWidthDp(...)`；字数格式化抽为 `formatCharCount(...)`，
  `ReaderMenuTest` 补 0 / 800 / 1200 三档。
- `TabRow` 替换为 `PrimaryTabRow`（章节列表、本书设定）。
- 任务卡动作行与空态入口改用 `FlowRow`。

### 版本

- `versionName = "1.1.1"`，`versionCode = 40`。

## 1.1.0 — 2026-11-18

### 用户可见

- 空书架改为两条明确路径：「第一次用 → 去发现」是唯一主按钮；
  「导入备份 / 导入 TXT / EPUB」降为次级入口，不再与主路径抢注意力。
- 书架备份提醒的「去设置」直达「数据」分组，并高亮 2 秒，不再要求用户自己滚动寻找。
- 阅读器「更多」菜单按「阅读 / 翻译 / 资料 / 世界线」四组排列；功能一个不少，查找更快。
- 任务页筛选标签直接显示数量（失败 3、未译全 2、进行中 1），点数字即筛选。

### 工程

- 新增 `LibraryEmptyStateTest`、`SettingsFocusTest`、`ReaderMenuTest`，
  覆盖空态分支、设置深链白名单、菜单分组与禁用条件。
- 空态文案与动作抽成 `emptyShelfCopy(...)` 纯函数；阅读器菜单抽成
  `readerMenuItems(...)`，渲染层不再硬编码 13 个菜单项。
- `TaskGroupingTest` 补筛选一致性断言。

### 版本

- `versionName = "1.1.0"`，`versionCode = 39`。

## 1.0.4 — 2026-11-18

### 用户可见

- 任务页「忽略」现在可撤销：忽略后出现 Snackbar，点「撤销」即恢复原任务，
  不再出现「点错就永远找不到」。
- 阅读器每页补页码无障碍描述（「第 x 页，共 y 页」），TalkBack 不再只读到一块空白画布。
- 备份提醒写清路径：去设置 → 数据 → 导出备份。

### 工程

- `ReaderPageView` 在未滑动点击时调用 `performClick()`，消除
  `ClickableViewAccessibility` lint 警告。
- 清理 `ObsoleteSdkInt`（合并 `mipmap-anydpi-v26`）与 3 处
  `AutoboxingStateCreation`（改用 `mutableIntStateOf` / `mutableFloatStateOf`）。
- 新增 `TaskIgnoreStoreTest`：写入、去重、清除、空值、损坏分隔符。
- 新增 `docs/upgrade/` 三轮升级档案与 `CHANGELOG.md`；补齐 `04-final.md` 的
  1.0.2–1.0.4 记录。

### 版本

- `versionName = "1.0.4"`，`versionCode = 38`。

## 1.0.3 — 2026-11-06

- 对齐 Android 版本号与签名发布流程。
- Web 归档分支修复首启、导入、书架、详情、设置与阅读器路径；`main` 不包含
  Web/Python 运行时。
- Android 侧无用户可见功能变化。

## 1.0.2 — 2026-11-05

- 首个签名 Release（versionCode 36）。
- Release 构建强制校验 `LIGHTNOVEL_RELEASE_*` 四项签名变量，缺少任意一项直接失败，
  不再悄悄产出未签名 APK。
- CI 增加签名 APK 校验与产物上传。

## 1.0.1 — 2026-11-04

- 阅读翻译队列按书合并，切换章节不再取消正在进行的任务。
- 阅读器状态条显示当前进度、后台预译、失败原因，可暂停/继续/停止。
- 详情页「更多 → 翻译章节…」支持当前章、后续 N 章、全书未译，带费用确认。
- 在线章节先拉正文再翻译；任务中心支持原地重试、重试全部失败、停止本书。
- 全部分块失败不再写成 partial 原文；缓存与实际译文不一致时自动重建。
- 书架移出只隐藏，保留离线正文、译文、世界线和阅读进度，可恢复、可撤销。

## 1.0.0 — 2026-11-04

- 阅读时自动翻译当前章并预译后续章节；跳章回补有限章节。
- 发现页与作品详情页改为整页滚动。
- 世界线、查询模式、故事记忆、备份导入导出沿用 0.9.x 能力。
