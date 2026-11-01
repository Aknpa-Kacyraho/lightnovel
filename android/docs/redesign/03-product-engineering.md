# Ka小说家：功能体验与工程落地方案

> 基线：Android `0.7.2-p1`、Compose 单 Activity + Navigation Compose、Room v2、现有 72 个单元测试（`@Test` 计数）。
> 依赖：`01-information-architecture.md`（3 Tab、详情/目录双路由）、`02-visual-system.md`（8 套主题、`LnExtendedColors`、标签语义）。本文负责把 IA 与视觉方案落成工程约束。
> 约束：本地优先，直连 Kakuyomu / 成为小说家吧；不引入登录、Wenku、远端同步、评论、论坛或自建服务器。
> 参考：`auto-novel` 仅作交互与信息架构研究（GPL，代码不复制）；本文基于静态读码，未运行构建、测试或安装。

## 0. 目标 / 非目标

### 目标

- 作者、标签、来源成为可点实体；从详情/卡片切到发现搜索，切回书架仍保留来源 Tab 的详情与滚动。
- 书籍详情与章节目录拆成两个独立页面：详情只负责“决定读不读/从哪读”，目录只负责“选章”。
- 书架首屏回答“接着读什么”，提供最近阅读、收藏筛选、排序、导入与备份提醒；不再每行挂一颗收藏星。
- 发现升为底栏一级（书架/发现/我的 3 Tab）；链接加书、搜索、来源预览各有明确位置，加书后不打断浏览。
- “我的”承接任务、备份、缓存与设置分组；高级项折叠，危险操作确认。
- 按 02 落地 8 套主题与主题派生标签色，解决“只有 3 套且标签不跟主题”。
- 允许底层重构，但每一步有可测状态、回滚点和旧测试门槛。

### 非目标

- 不做账号、收藏云同步、Wenku、评论、论坛、远端推荐服务；不新增登录墙。
- 不在本阶段重写阅读器分页引擎、翻译管线、Room 导入/备份格式；不做后台翻译/通知。
- 不为“看起来功能多”新增非必要页面；任务/设置不占底栏。
- 不复制 GPL 代码、Vue 模板、CSS 或文案；只吸收交互模式。
- 本次只交付方案文档，不修改源码。

## 1. 读码结论

| 区域 | 现状（关键位置） | 直接问题 |
| --- | --- | --- |
| 导航 | 底栏只有书架/任务/设置，发现是书架右上角按钮（`LightnovelNavHost.kt:38-49`、`LibraryScreen.kt:98`） | 发现被当成书架附属；任务/设置占一级；`discover` 打开书时 `popUpTo("discover"){inclusive=true}` 销毁结果页（`LightnovelNavHost.kt:120-124`） |
| 详情/目录 | 书籍头、简介、标签与章节共用一个 `LazyColumn`（`ChapterListScreen.kt:167-176`） | 长简介和长目录互相挤压；详情无法独立演进，目录没有排序/筛选空间 |
| 实体 | 作者是普通 `Text`，标签是 `joinToString`（`ChapterListScreen.kt:196-217`） | 作者/标签不可点；翻译标签与原始标签没有成对模型 |
| 书架 | 固定 `ORDER BY b.title`；每行常驻收藏星；无最近阅读/收藏筛选/排序（`LibraryDao.kt:32-53`、`LibraryScreen.kt:281-287`） | 找不到“接着读”；视觉噪音大；收藏不能当筛选 |
| 发现 | 搜索、链接输入、推荐、结果全在一页；加书后自动跳转（`DiscoverScreen.kt:102-143, 64-69`） | 一屏两组表单；浏览上下文丢失；无来源筛选/单源重试/搜索历史 |
| 任务/设置 | 任务平铺最多 100 条；设置是一整条长滚动；Novelia 登录状态仍在 VM（`LibraryDao.kt:112-129`、`SettingsViewModel.kt:42-47`） | 任务像日志；设置难找；常规路径存在遗留服务死代码 |
| 主题/数据 | `AppTheme` 仅 3 套；无 `last_read_at`；加书写入 `tags_json=null`（`Theme.kt:10-22`、`DirectLibraryService.kt:37-52`） | 主题少、标签不跟主题；最近阅读/离线标签缺数据 |

## 2. 功能清单

### P0（本次必须做）

| 功能 | 用户价值 | 交互 / 数据依赖 | 失败与空态 |
| --- | --- | --- | --- |
| 作者可点 | 从一本书找到同作者作品 | 详情/卡片/来源预览的作者是独立点击区；切到发现 Tab 打开 `discover/search?mode=author`；传原始日文名；依赖 `BookEntity.author`/`SourceBook.author` | 源站无作者索引时保留关键词结果并提示；无结果显示“换关键词/换源” |
| 标签可点 | 顺着题材找同类 | `TagChip` 传**原始日文标签**；展示用 `tagsZh`；依赖 `SourceBook.tags`、`BookEntity.tagsJson` | 标签缺失不渲染；译文缺失显示原文；空结果保留当前筛选 |
| 详情/目录分离 | 先看简介再决定读，目录不被打断 | `library/book/{bookId}` 与 `library/book/{bookId}/chapters` 两个独立路由；详情不含章节长列表，目录不含 hero/标签 | 目录为空显示“源站可能变更/重新导入”；详情加载失败保留本地缓存信息 |
| 继续阅读 | 一次点击回到上次位置 | 详情主按钮；用 `progressIdx` + `progressBlock` 解析；0/null→第一章，越界→最后一章 | 无目录禁用；目标章缺文件时进阅读器拉取并显示重试 |
| 收藏 | 把“喜欢”变成可筛选状态 | 详情主操作星标；书架用“收藏”筛选 Chip，不再每行挂星；写入 `read_state.favorite` | 写入失败回滚并 Snackbar；收藏空态提示“取消筛选” |
| 下载全部 | 离线可读整本 | 详情 overflow；逐章缓存并保留已完成章节；进度 X/N；依赖 `DirectLibraryService.ensureChapter` | 单章失败不终止全本，结束汇总“成功 X/失败 Y”；可重试失败项 |
| 导出 EPUB | 备份到其他阅读器 | 详情 overflow；SAF `CreateDocument`；导出前检查章节/正文 | 无章节/正文禁用；失败显示具体原因，不静默 |
| 源站打开 | 看原站更新/作者页 | 由 `source + sourceId` 生成规范 URL，`ACTION_VIEW`；本地书隐藏 | 无浏览器提示；不支持 novel18 时明确说明 |
| 目录工具 | 1000 章也能定位 | 目录页：章节搜索、正/倒序、状态筛选、上次读到；滚动/搜索/排序按 `bookId` 保存 | 筛选/搜索无结果显示“清除条件”；上次章被删回退第一章 |
| 书架最近阅读 | 打开 App 就知道读什么 | 顶部 1–5 本横向卡；P0 用 `read_state.updated_at` 排序；只显示 `progressIdx > 0` | 无最近阅读整段隐藏；进度异常回退第一章 |
| 书架收藏筛选/排序 | 找书更快 | 筛选：全部/在读/想读/读完/收藏；排序：最近阅读/最近添加/标题/作者；组合生效 | 组合无结果显示“清除筛选”；空值按添加时间兜底 |
| 书架导入/空态 | 首次使用有明确下一步 | 顶栏 overflow + 空态提供 SAF 备份 zip 导入；显示阶段进度；成功后建议导出备份 | 导入失败保留原库；筛选空不误导去导入；无书给“导入/去发现” |
| 发现底部一级 | 符合“逛书”心智 | 底栏 3 项：书架/发现/我的；发现是第 2 项，任务/设置归“我的” | 无网络保留标签与链接加书入口；推荐区显示重试 |
| 发现搜索/结果过滤 | 减少重复输入 | 单实例搜索页；来源筛选（全部/成为小说家/Kakuyomu）；旧结果保留到新结果返回 | 区分“无结果/部分源失败/全部失败”；单源可重试 |
| 链接加书 Sheet | 降低首页噪音 | 发现 overflow/空态打开底部 Sheet；支持 Kakuyomu/ncode 链接与数字 ID；识别后加入 | 重复书提示“已在书架”；错误就地提示，不关闭 Sheet |
| 翻译状态/重试 | 结果先可读，译名后到 | 原文先出，卡片角落“翻译中”；失败回落原文并提供重试；无 Key 不显示进度 | 迟到结果不得覆盖新查询；无 Key 给设置入口 |
| 我的入口/任务状态 | 任务、备份、设置 1 击可达 | 第 3 Tab“我的”：备份/任务/缓存状态卡 + 失败角标；任务页 `me/tasks` | 空队列不制造死 Tab；P0 统计 failed/partial，P1 再加忽略过滤 |
| 设置分组/危险确认 | 找得到、不会误操作 | `me/settings/{group}`：阅读/外观/翻译/数据/关于/高级；高级默认折叠；清缓存/恢复备份确认 | 清缓存说明“不删书/进度/Key”；取消不执行 |
| 8 套主题 + 标签跟随 | 解决“只有三套且不喜欢” | 保留 teal/lavender/sakura，新增 matcha/amber/indigo/slate/ember；标签从 `LnExtendedColors` 取色 | 未知主题回退按 4.5 的兼容策略；浅/深色都测对比度 |
| 返回栈/状态保存 | 不丢搜索、不丢位置 | 跨 Tab 跳转保留来源栈；详情/目录滚动按 `bookId` 保存；阅读器换章替换条目 | 进程重建恢复 Tab/滚动/query；一次性事件不重放 |

### P1（值得做，不阻塞 P0）

| 功能 | 用户价值 | 交互 / 数据依赖 | 失败与空态 |
| --- | --- | --- | --- |
| 搜索历史 | 少打重复关键词 | 发现首页/搜索页显示最近 8–12 条；独立 DataStore；按 `(mode, normalizedQuery)` 去重；01 列为 P2，本次需求明确提前到 P1 | 历史为空显示热门标签；清空需确认；损坏 JSON 回退空 |
| 作者精确匹配 | 不被同名结果淹没 | 搜索页开关“只看该作者”；按归一化作者名过滤 | 0 条精确匹配保留关键词结果并提示，不假装源站支持作者索引 |
| 搜索加载更多 | 一次看更多候选 | 列表底部按钮；Kakuyomu 用 page，Syosetu 用现有 limit；保留旧结果 | 失败保留旧结果并可重试；到底显示“没有更多” |
| 结果过滤增强 | 只看未加入或已加入的作品 | 加入状态（全部/未加入/已加入）、排序（相关/更新）；本地 `findBySource` 判定 | 组合无结果显示“清除过滤”；已加入卡显示“打开” |
| 结果标签折叠 | 降低卡片高度 | 卡片最多 3 个标签 + “更多”；详情页全部显示 | 无标签不占位；翻译缺失显示原文 |
| 备份提醒 | 降低丢库风险 | 仅“有书且从未备份”时显示；关闭后 7 天不再出现；DataStore 字段 | 导出取消不改时间；有备份后不再常驻 |
| 最近阅读精度 | 收藏操作不污染最近排序 | P1 增加 `read_state.last_read_at`，只在 `updateProgress` 写；`setFavorite` 不写 | 旧数据回退 `updated_at`；迁移回填 `progress_idx>0` |
| 任务控制台 | 失败可处理、可停止 | `me/tasks` 按书分组；失败/未译全可重试；进行中可取消；忽略写 `task_ignored_at` | 重试中禁用；忽略可撤销；无进度字段不伪造百分比 |
| 书架标记 | 想读/在读/读完可管理 | 详情 overflow 或行尾菜单设置 `shelf`；首次进阅读器可自动“在读” | 未设置显示“未分类”；完成不自动猜 |
| 动态取色/浅深色 | 更贴个人设备 | Android 12+“跟随壁纸”；浅色/深色手动覆盖；复用 Material3 scheme | 不可用时隐藏；回退 8 套之一 |
| EPUB/TXT 本地导入 | 把手里的文件也放进书架 | 独立 SAF 导入，先解析元数据/章节；不混用备份格式 | 编码错误/DRM/空章节拒绝，不产生半本书 |
| 下载管理 | 控制存储空间 | 按书显示已下载章数/占用；单章下载、只删正文缓存 | 缺文件标记；删除失败保留原状 |
| 无障碍/字号 | 大字号/读屏可用 | TalkBack 自定义动作、字体缩放参与分页 key、44dp 点击区 | 文本 fallback；无障碍开关不导致崩溃 |

### P2（以后做）

| 功能 | 用户价值 | 交互 / 数据依赖 | 失败与空态 |
| --- | --- | --- | --- |
| 榜单/标签/作者页 | 从结果继续深挖 | `discover/rank`、标签落地页、作者页；来源分页 | 无结果给来源说明；分页失败保留已加载 |
| 宽屏双栏 | 平板/横屏更高效 | 详情左、目录右；`WindowSizeClass`；手机路径不变 | 宽屏不重复请求；小屏不启用 |
| 后台下载任务 | 下载可暂停/续传 | 可恢复任务进入 `me/tasks`；需要新表/迁移 | 失败保留已缓存章；任务中心可见 |
| 批量管理 | 一次整理多本 | 多选收藏/移动书架/删除下载 | 部分失败列清单；成功项不回滚 |
| 深链/分享/引导 | 外部打开与首次使用 | `ka://book/{id}`、分享进度、可跳过引导 | 无来源栈时返回书架；不支持链接给提示 |
| 阅读历史/书签/批注/全书搜索 | 回看轨迹、标记重点 | 新增 `reading_events`/`bookmarks` 表；按书/时间查询 | 空记录给下一步；搜索无结果给清除条件 |
| 自定义主题/背景/字体 | 更强个性化 | 扩展 `LnExtendedColors`；对比度校验 | 对比度不足回退安全色 |
| 遗留清理 | 去掉 Novelia/远端收藏/历史导入 | 评估删除 `data/online/*` 与设置依赖 | 备份/导入不受影响；常规 UI 无登录 |

## 3. 关键体验设计

### 3.1 作者/标签点击：跨 Tab 搜索、返回栈、历史与恢复

- **目标页**：统一进 `discover/search?q={q}&mode={tag|author|keyword}`，是发现图内的单实例搜索页。底栏仍显示“发现”选中；搜索页自己有返回箭头。
- **跨 Tab 规则**：从详情/搜索结果/来源预览点作者或标签，是“切到发现并搜索”，不是从详情 push 搜索页。书架 Tab 的详情与滚动保留在它自己的返回栈里；搜索返回只回发现上一屏，不弹回详情；再点书架，恢复原详情位置（01 §导航规则 3）。
- **查询语义**：标签传原始日文标签，`tagsZh` 只负责显示；作者传原始作者名。Kakuyomu 对含空格/全角空格的词加引号；Syosetu 保留规范化空格走 `word`。`SourceQueryPlanner` 按 provider 返回 query，测试中文、空格、斜杠、引号、`&`。
- **作者诚实处理**：Syosetu 不保证作者索引。作者模式发送短语查询，结果按归一化作者名优先排序但不硬过滤；0 条完全匹配时保留关键词结果并提示“该源可能未按作者索引”。
- **搜索历史**：P1 本地 `SearchHistoryStore`（独立 DataStore，JSON，schemaVersion=1），去重、NFKC、折叠空白、最多 12 条；记录 `lastUsedAt`。提交搜索和点作者/标签都写入；单条删除/全部清空；不写账号或 URL token。
- **状态恢复**：搜索页的 `q/mode/provider` 进 `SavedStateHandle`；输入草稿 `rememberSaveable`；结果列表位置 saveable。进程死亡后恢复 query/筛选并重搜一次，不持久化大结果列表。
- **编码**：动态值统一 `Uri.encode`；`q` 走 query 参数，不用 path，避免作者名中的 `/`；`mode` 做白名单校验。读取端不再二次 `Uri.decode`，用导航测试确认只解码一次。

### 3.2 书籍详情页 / 章节目录页：两个独立页面

01 已定“手机端不使用详情内目录 Tab”，因此这里**不引入 `detailTab` 状态**：详情和目录是两个路由、两个 ViewModel、两套滚动状态，从根上消除“详情里套目录”的嵌套滚动与状态耦合。

- **详情页**（`library/book/{bookId}`）：Hero 文字封面、中/日文书名、作者（可点）、来源徽标（可点→发现按来源筛选）、话数；主操作“继续阅读 第 X 章/开始阅读”、收藏星标；overflow 放缓存全部/导出 EPUB/打开源站/标记书架（P1）。上次读到卡（进度 + 第 X 章 + 第 N 段 + 更新时间）；简介默认 6 行 + 展开；翻译覆盖/来源信息；目录入口“目录 · 共 X 章 + 查看全部”。详情不渲染完整章节列表。
- **目录页**（`library/book/{bookId}/chapters`）：返回、书名/章数、章节搜索、正序/倒序、状态筛选（全部/已译/未译/失败/缺文件）、上次读到卡；进入自动滚到当前章，用户手动滚动后不再抢夺位置；行只做“打开阅读”，不重复简介/标签/下载大按钮。
- **继续阅读解析**：`progressIdx` 在 `1..size` 用它；`0/null` 用第 1 章；大于目录长度回退最后一章并提示；目录为空禁用。`progressBlock/char` 仅在 `progressIdx == 目标章` 时交给阅读器恢复。
- **下载全部**：复用 `DirectLibraryService` 的缓存判断，抽成 `DownloadAllUseCase`，返回 `done/failed` 列表；单章失败不终止整本，已有缓存跳过；详情显示线性进度和“X/Y”，失败可重试。当前 `ChapterListViewModel.downloadAll()` 与 service 的 `downloadAll()` 重复，合并为一处。
- **导出/源站/错误**：导出用现有 `EpubExporter`，成功 Snackbar；失败必须显示（当前 `ChapterListViewModel` 的 `message/error` 未被 UI 展示）。源站 URL 由纯函数生成：`kakuyomu.jp/works/{sourceId}`、`ncode.syosetu.com/{sourceId.lowercase()}/`；`ActivityNotFoundException` 显式提示。
- **状态分组**：已译=`complete/translated`；未译=`online/raw/translating`；失败=`failed`；缺文件=`missing`；`partial` 单独“未译全”，不混入已译。
- **空/异常**：目录空显示“源站可能变更/重新导入”+重试；详情源站失败显示本地缓存信息并内联重试，不整页清空。

### 3.3 书架

- **首屏顺序**：未备份提醒（仅“有书且从未备份”，可关闭 7 天）→ 最近阅读横栏（1–5 本）→ 搜索/筛选/排序 → 书列表。无最近阅读时整栏不渲染。
- **最近阅读**：P0 用 `read_state.updated_at`，P1 加 `last_read_at` 避免收藏操作污染排序；只显示 `progress_idx > 0` 且未隐藏。P0 收藏会更新 `updated_at`，可能短暂改变最近排序，P1 修复；卡片显示书名、第 X 章、进度；点击直接进阅读器。
- **筛选/排序**：筛选 Chip：全部/在读/想读/读完/收藏；排序菜单：最近阅读（默认）/最近添加/标题/作者。收藏筛选走 DAO 参数；搜索仍只过滤本地标题/作者，不做在线发现。
- **降噪**：移除每行常驻收藏星；收藏/标记书架/隐藏放详情或行尾 overflow（P2 长按多选）。行样式：文字封面、书名、作者（可点）、进度、本地/在线徽标。
- **导入/备份**：导入仍是备份 zip；先校验 manifest 并显示书/章/冲突摘要，确认后应用，失败保留原库；完成提示“已导入 X 本/Y 章，建议导出一次备份”。备份提醒只在“有书且 `lastBackupAt == null`”时出现；关闭后 7 天不再提示；不承诺卸载前自动备份。
- **空态**：全空 →“还没有书”+导入主按钮+“去发现”；筛选空→“清除筛选”；搜索空→“清除关键词”；导入中显示进度。不要用“去导入”误导已筛选用户。
- **阅读历史入口**：P0/P1 不单独设“历史”页；最近阅读由进度时间派生，已覆盖“接着读”。完整历史需要事件表，放 P2，避免为入口造第二份状态。

### 3.4 发现

- **首页**：顶栏“发现”+一个搜索入口+overflow（从链接添加）；内容：本周推荐（按来源分组，6–8 条/组，带来源徽标）→ 热门标签（FlowRow，10–12 个）→ 来源浏览（P2）。不把两个来源的推荐混成无来源 12 条。
- **搜索页**：单实例；一个输入框 + 来源筛选 + 结果计数；提交后保留旧结果并在顶部显示线性进度，首次加载才用骨架屏；旧请求 token 不覆盖新查询。
- **结果卡**：中文标题（缺失显示日文）、可点作者、可点来源徽标（→发现按该来源筛选）、话数、两行简介、最多 3 个标签 + 更多；主按钮“加入书架/已在书架”，次按钮“详情”进来源预览；整卡点击也进预览，避免按钮与卡片语义冲突。
- **链接加书**：发现 overflow/空态打开底部 Sheet，单输入框 + 粘贴 + 支持格式示例；识别 Kakuyomu/ncode 链接或数字 ID；错误就地提示，不关闭 Sheet。**加书成功停留原页**，卡片变“已在书架”，Snackbar“已加入书架 · 查看”；用户主动点“查看”才进书架详情（修复当前自动跳转丢上下文）。
- **状态**：首次加载 3 张骨架卡；搜索中旧结果 + 顶部进度；部分源失败只替换该源状态；全部失败给重试/链接加书；无结果给关键词建议/清除筛选；翻译中卡片角落小标签，原文可见；加书成功原位状态 + Snackbar。
- **搜索历史**：P1；按 3.1，空历史显示热门标签；不阻塞 P0 的搜索与加书。
- **加书后的导航**：不要 `popUpTo(discover){inclusive=true}`；来源预览/搜索页保留；书架详情由用户“查看”进入。

### 3.5 “我的”、设置与主题

- **我的**：顶部应用名/版本/“本地优先”；状态卡：备份（上次时间/从未备份）、翻译任务（进行中/失败数）、缓存（大小）；分组入口：阅读/外观/翻译/数据/关于/高级。每行显示当前值摘要，点进 `me/settings/{group}` 再改。失败任务在“我的”显示角标，进行中数放状态卡。
- **设置分组**：阅读（字号/行距/段距/边距/字体/常亮/默认译文/翻页）；外观（8 套主题 + 跟随系统/浅色/深色）；翻译（服务是否配置/模型/Key 状态/测试连接）；数据（导出/导入/上次备份/缓存）；关于（版本/源站说明/许可/隐私）；高级（Base URL/原始模型参数/诊断/遗留服务，带风险说明）。高级默认折叠。
- **隐藏项**：Novelia 登录/收藏/历史导入、Wenku、云同步、评论/论坛、缓存文件级信息、调试日志不进常规设置；`SettingsViewModel` 的账号状态从常规依赖移除。
- **危险操作**：清缓存确认“只清翻译缓存/旧版本，不删书、进度、Key”；恢复备份确认“会合并进度和收藏”；清空搜索历史确认。取消不执行。
- **主题**：按 02 的 8 套（`teal` 青灯、`lavender` 紫夜、`sakura` 樱纸、`matcha` 苔庭、`amber` 琥珀、`indigo` 靛蓝、`slate` 墨灰、`ember` 枫烬）；设置用 2 列色板预览卡，选中 2dp primary 描边 + check，点击即应用。
- **标签色**：不新增平行色表；使用 02 的 `LnExtendedColors`（`tagType*`/`tagKeyword*`/`tagStatus*`/`tagSource*`）从 `ColorScheme` 推导；同一原始标签跨页面同色，翻译只换文字；状态色按 02 映射（已译 primary、进行中 secondary、未译全 tertiary、失败/缺文件 error、生肉 onSurfaceVariant）。所有文本对比度 ≥4.5:1。

### 3.6 任务中心（我的 / 异常控制台）

- **定位**：只展示 `translating/failed/partial`，按书分组；`task_ignored_at` 非空隐藏。进行中显示状态，不伪造百分比（没有分块进度字段时只写“进行中”）。不展示阅读历史、收藏、推荐、成功归档。
- **P0 入口**：我的状态卡 + 失败角标可 1 击进 `me/tasks`；任务页空态解释“在阅读器翻译失败/未完成时出现”，给“去书架”。
- **P1 动作**：失败/未译全 →“继续翻译”（带 `retry=1` 打开阅读器并自动开始，复用阅读器进度/取消/错误）；进行中 →“查看”或“取消”；溢出“忽略”写 `task_ignored_at`，Snackbar 可撤销；成功翻译清空忽略。精确跳章用 `reader/{bookId}/{idx}`。
- **与阅读器联动**：不在任务页另起翻译执行器；`retry` 一次性参数由 `SavedStateHandle` 消费并清除，翻译单飞；返回任务页由 Room 状态刷新。
- **避免测试污染**：UI 测试优先无状态 Composable + 假状态；需要 Activity 的冒烟测试使用测试 `AppContainer`（内存 Room + 临时目录），不写生产 `filesDir`。启动的 `resetInterruptedTranslations` 应在任务首帧前完成或显示“正在恢复”，不能把上次进程/测试的 `translating` 当进行中。现有 `MainActivityTest` 仍找“轻小说”，而应用名已是“Ka小说家”，需同步修正。

## 4. 工程落地

### 4.1 数据模型、DAO、Repository

| 变更 | 内容 | 迁移/理由 |
| --- | --- | --- |
| `books.tags_json` | 加书/刷新详情时写原始标签 JSON，读取容错空数组 | 不加列；离线详情仍可点标签；当前写 null 是缺陷 |
| DAO `observeLibrary(shelf, favoriteOnly)` | `AND (:favoriteOnly=0 OR COALESCE(r.favorite,0)=1)` | 收藏筛选在查询层；不需要迁移 |
| DAO `observeRecent(limit)` | join `read_state`，`progress_idx>0`，P0 按 `updated_at DESC`，P1 切 `last_read_at` | 最近阅读横栏；与列表共用同一排序规则 |
| DAO `observeChapterStats(bookId)` | 总数/已译/生肉/失败计数 | 详情显示翻译覆盖，不必加载全部章节；无迁移 |
| Repository `ShelfFilter` | 增加 `favoriteOnly`、`sort: LibrarySort`（RECENT/ADDED/TITLE/AUTHOR） | 兼容旧构造（默认值）；排序比较器纯函数 |
| Repository 搜索参数 | `SearchKind` + `SearchRequest`；`SourceQueryPlanner` 按源生成 query | 作者/标签不再混在 `search(String)`；可测 |
| Repository 加书去重 | `findBySource(source, sourceId)`，已存在直接返回 | 避免重复网络与 upsert；支持“已在书架”状态 |
| Repository 继续阅读 | `resolveContinueTarget(progressIdx, chapters)` 纯函数 | 详情/书架/阅读器共用回退规则 |
| `SearchHistoryStore`（P1） | 独立 DataStore，JSON `[{mode,query,usedAt}]`，最多 12 条 | 无需 Room；纯逻辑可测；损坏回退空 |
| `ReadStateEntity.lastReadAt`（P1） | `last_read_at TEXT`；`updateProgress` 写，`setFavorite` 不写 | P1 Room v3；回填 `progress_idx>0` 的 `updated_at` |
| `ChapterEntity.errorMessage/taskIgnoredAt`（P1） | `error_message`、`task_ignored_at` | P1 Room v3；任务失败原因/忽略不篡改 status |

- **Room migration 结论**：按 01 的 P0 先用 `updated_at`、`tags_json` 与查询参数，**P0 不需要迁移**；P1 一旦采纳 `last_read_at/error_message/task_ignored_at`，必须新增 `MIGRATION_2_3`（只加列 + 回填 + schema 更新），绝不能只改实体不加迁移或 destructive fallback。
- **Backup**：`BackupExporter` 保持 `format=1`；P1 的 `last_read_at` 作为可选字段写入 `data/books/*.json`，并更新 `ReadStatePlanner` 解析；旧备份缺字段时回退 `updated_at`。`error_message/task_ignored_at` 可重建，可不入备份。
- **不为 UI 造重复状态**：收藏只读 `read_state.favorite`；最近阅读由查询派生；详情统计用 SQL 聚合；搜索历史只有 DataStore 一份；任务忽略只有 `task_ignored_at` 一份。不要把 `BookEntity` 复制成大 UI model 长期持有。

### 4.2 ViewModel 状态拆分

| ViewModel | 拥有的状态 | 不放进 |
| --- | --- | --- |
| `BookDetailViewModel` | `book`/`readState` Flow、`sourceDetail`、`actions`（收藏/下载/导出/源站）、`metadata` | 章节目录列表；目录搜索/排序；菜单展开 |
| `ChapterCatalogViewModel` | `chapters`、`query`、`sort`、`statusFilter`、`lastReadIdx`、`listError` | 详情 hero、收藏、下载 |
| `LibraryViewModel` | `books`（带 ShelfFilter）、`recent`、`import`、`backupReminder` | 单本书星标副本；菜单状态 |
| `DiscoverHomeViewModel` | `recommendations`、`sourceErrors`、`recentSearches`（P1）、`linkSheet` | 搜索结果；搜索页输入 |
| `DiscoverSearchViewModel` | `q/mode`、`providerFilter`、`results`、`addingId`、`metadataState`、`requestId` | 首页推荐；全局 loading |
| `MeViewModel` | 备份/任务/缓存摘要、失败角标、设置分组摘要 | 设置子页字段；任务行状态 |
| `TaskCenterViewModel` | `groups`、`counts`、`actionInFlight`、`message` | 每行独立布尔；翻译执行器 |
| `SettingsViewModel` | 按 `appearance/reader/translation/data` 拆子状态/Flow | 一个 30 字段的 `SettingsUiState` |

- **detail tab**：01 已定为双页面而非详情内 Tab，因此不引入 `detailTab`。若未来 01 改为详情内 Tab，`selectedTab` 也只放 `BookDetailViewModel` 的 SavedStateHandle，不放进目录列表；P2 宽屏双栏只加 `selectedSection`，不预造状态。
- **Tab/筛选/query**：目录 `sort/statusFilter/query`、搜索 `q/mode/provider` 进 `SavedStateHandle`；详情/目录滚动按 `bookId` 保存；进程重建可恢复。
- **menu state**：更多菜单、确认对话框、Sheet 展开是瞬态 UI，用 `rememberSaveable`/局部 `remember`，不放进 StateFlow。
- **一次性事件**：Snackbar/导航用 `Channel<UiMessage>` 或带 id 的 `SharedFlow`；不要用可重放的 `message` 字段。异步 metadata 只更新匹配 `requestId` 的结果；文件缓存写 `Dispatchers.IO`。

### 4.3 导航与参数编码

| 路由 | 入口 | 参数 | 底栏 | 返回栈/恢复 |
| --- | --- | --- | --- | --- |
| `library` | 启动/底栏 | — | 显示 | 搜索/筛选/排序/滚动保存 |
| `library/book/{bookId}` | 书架行、继续卡、发现“查看” | `bookId` | 显示 | 返回书架并保留滚动；详情滚动按书保存 |
| `library/book/{bookId}/chapters` | 详情“目录” | `bookId` | 隐藏 | 返回详情；目录滚动/搜索/排序按书保存 |
| `discover` | 底栏 | — | 显示 | 推荐/标签状态保留；根返回书架 |
| `discover/search` | 搜索框、标签、作者 | `q`、`mode=keyword/tag/author`、可选 `provider` | 显示 | 单实例；换词不压栈；返回发现上一屏 |
| `discover/source/{provider}/{id}` | 结果卡“详情” | `provider/id` | 显示 | 返回结果页；加书停留，Snackbar 查看 |
| `me` | 底栏 | — | 显示 | 状态卡/分组摘要；根返回书架 |
| `me/tasks` | 我的任务卡/角标 | 可选 `bookId` | 隐藏 | 返回我的；筛选保存 |
| `me/settings/{group}` | 我的分组行 | `group=reading/appearance/translation/data/about/advanced` | 隐藏 | 返回我的；未保存修改确认 |
| `reader/{bookId}/{idx}` | 继续阅读、目录、任务 | `bookId`、`idx` | 隐藏 | 换章替换当前条目；返回目录/任务/书架 |

- **底栏可见性**：浏览层（三个 Tab 根、发现搜索/来源预览、书籍详情）显示；专注层（目录/阅读器/任务/设置子页）隐藏。按目的地层级判断，不用 `route == 顶层字符串`。
- **编码**：动态值 `Uri.encode`；`NavType.StringType`（`idx` IntType）；`q` 走 query 参数；`mode/provider` 白名单；业务层不二次 `Uri.decode`。测试中文、半/全角空格、`/`、`?`、`#`、`%`、`&`、emoji。
- **返回栈**：跨 Tab 搜索返回只回发现上一屏；书架 Tab 恢复原详情/滚动；禁止 `popUpTo(discover){inclusive}`。阅读器上下章 `popUpTo("reader/{bookId}/{idx}"){inclusive=true}` 替换当前条目，不按章累积。
- **加书/来源**：加书成功停留原页，卡片“已在书架”+Snackbar；用户点“查看”才进 `library/book/{id}`。来源预览是独立路由，不做右侧抽屉。

### 4.4 Compose 性能

- **稳定 key/contentType**：书架 `book.id`；目录 `bookId/idx`；搜索结果 `provider/id`；任务 `bookId/idx`；标签 `original`。目录倒序 key 不变；不同行类型给 `contentType`。
- **避免嵌套滚动**：详情、目录、搜索各用一个 `LazyColumn`；筛选条用 `stickyHeader` 或列表外固定行；不把 `LazyColumn` 放进 `Column.verticalScroll`。标签用 `FlowRow` 或最多 3 个 + “更多”。
- **metadata 异步**：首帧先显示原文；VM scope + IO；按 key 合并，迟到请求丢弃；失败不阻塞加书/阅读；`MetadataTranslationService` 的缓存读写下沉 IO。
- **重组范围**：每行只收必要字段和稳定 lambda；筛选/排序在 VM 生成；搜索输入 250–300ms debounce；`derivedStateOf` 只用于滚动派生；不在组合期触发网络/排序。
- **主题/标签**：8 套主题与 `LnExtendedColors` 在 `LightnovelTheme` 一次性提供；TagChip 不硬编码颜色；深/浅色都测对比度。
- **可访问性**：TagChip `contentDescription` 含原文+译文；作者/标签点击区 ≥44dp；主题预览卡有选中语义；大字号参与分页 key。

### 4.5 兼容、升级与回滚

- **设置兼容**：新增主题 id 之外不改旧 key；旧 `teal/lavender/sakura` 继续生效；新安装默认 `amber`（02），但 `AppTheme.fromId(unknown)` 的 fallback 需与现有 `AppThemeTest` 对齐：测试要求 `TEAL`。**P0 保留 teal fallback 以守 72 tests；若产品坚持 02 的“unknown→amber”，必须显式更新该测试并接受契约变更，不能静默改。** 扩展 `AppTheme` 后所有 `when` 必须补分支，编译器负责抓漏。
- **数据库兼容**：P0 无迁移；P1 v2→v3 只加列/回填，保留 v1→v2；更新 `exportSchema` 并加 `MigrationTest`；绝不 destructive。迁移失败显示可恢复错误而不是清库。
- **备份兼容**：`format=1` 增加可选字段；旧备份可导入（缺失回退 `updated_at`）；新版备份被旧版读取时未知字段忽略；更新 round-trip 测试。
- **版本策略**：`0.8.0-alpha.1` 起；先内测真实 v2 库与 19 本备份；旧 `chapters` 路由/旧测试 tag 在迁移期保留，稳定后再清理。

## 5. auto-novel 参考：吸收与不采纳

| 参考文件 | 吸收的行为 | 明确不采纳 | 我们的落地 |
| --- | --- | --- | --- |
| `WebNovelActions.vue` | 有上次阅读就“继续阅读”，否则“开始阅读”；操作分主次 | FavoriteButton 的服务端收藏、编辑、文库 | 详情主按钮 `继续/开始`；收藏本地 Room；无 Wenku |
| `WebNovelMetadata.vue` | 作者可点、可搜索作者；标题可搜索；含空格查询加引号 | 登录 whoami、外链作者主页作为唯一入口 | 作者/标签切到发现搜索；原始日文查询；作者索引不足给提示 |
| `WebNovelTags.vue` | 标签即查询入口；关注标签排序；分数标签 | 服务端 `$` 查询语法、NovelTag 组件 | `TagChip` + 原始/中文配对；从 `LnExtendedColors` 取色 |
| `WebNovelIntroduction.vue` | 默认折叠、溢出才显示“展开全部” | Vue ResizeObserver/CSS mask 实现 | Compose `onTextLayout` 判断溢出；6 行折叠 |
| `NovelBottomTabs.vue` | 详情/目录/术语表分区思路；术语数量徽标 | 评论区、登录、键盘数字切换 | **不把目录塞回详情**；详情/目录双页面；术语表留阅读器 |
| `HomeView.vue` | 分节首页、快捷入口、“更多”、收藏区 | 公告、QQ/Telegram、论坛、文库、登录态 | 发现首页搜索/周榜/标签/链接 Sheet；书架最近阅读 |
| `WebNovelList.vue` | query 作为单一筛选来源；骨架/错误/空态分离 | 服务端分页/复杂筛选、whoami 分级 | query/mode 进导航；部分源失败保留其他结果；P1 加载更多 |
| `ReaderLayoutMobile.vue` | 底部菜单：上一章/详情/目录/设置/下一章 | 复制其点击区/抽屉布局代码 | 阅读器保留现有点击区；目录用底部 Sheet；详情回书架 |

> GPL 说明：以上只研究交互顺序、信息分组和空态处理，用 Kotlin/Compose 重新实现；不复制 Vue 模板、CSS、文案或函数体。

## 6. 实施顺序、回滚点与高风险

> 优先级以本文件为准：为回应“书架难用”，把 01 的 P1-1 书架降噪与 P1-2 目录工具提前到 P0；其余 IA 与 01/02 一致。

| 阶段 | 内容 | 验证 | 回滚点 |
| --- | --- | --- | --- |
| A 地基 | 纯函数、tags_json、收藏查询、排序、搜索参数、测试隔离；P0 不迁移 | 72 旧测试 + 新纯函数/DAO 测试 | 未发版前 revert；不触碰 Room 版本 |
| B 导航/IA | 3 Tab、我的、详情/目录双路由、底栏层级、返回栈、路由编码 | 路由单测 + `TestNavHostController` + 手工返回栈 | 保留旧 NavHost 提交与旧测试 tag |
| C 详情/目录 | 详情 hero/操作/进度/简介/目录入口；独立目录页与排序/筛选/搜索 | 详情/目录 UI 测试、空/错/本地/在线差异 | 旧 `ChapterListScreen` 保留到 C 验收 |
| D 书架/发现 | 最近阅读、收藏筛选/排序、导入/空态、发现分节、搜索、链接 Sheet、加书停留 | 排序/筛选/搜索竞态/加书幂等/Robolectric | 书架旧布局可回退；发现旧入口可由底栏回落 |
| E 我的/任务/主题 | 我的状态卡、设置子页、任务控制台、8 主题、标签色 | 主题对比度、危险确认、任务状态 | 旧主题 id 永久保留；任务只加 P1 字段 |
| F 收尾 | 性能、无障碍、备份演练、设备冒烟 | 全量测试 + lint + 真机 | 任一 P0 回归阻塞发布 |

**最高风险**

1. **跨 Tab 状态**：切到发现搜索后，来源详情/滚动必须保留；返回只回发现。必须用真实 NavHost 测，不靠纯函数。
2. **详情/目录双路由**：目录多一层返回、阅读器换章累积、底栏在错误页面显示。按层级推导底栏；逐路径手测。
3. **P1 Room v3**：升级后回滚旧 APK 打不开新库。只加列/回填、先备份、真实 v2 库演练；P0 不迁移。
4. **搜索/翻译竞态**：同词重搜、快速切作者标签、迟到 metadata 覆盖新结果。必须 `requestId` + 纯函数测试。
5. **下载/EPUB 失败语义**：`ensureChapter` 抛异常会中断整本；改逐章结果汇总，否则用户只看到“下载中”后整本失败。

## 7. 验收与测试清单

### 自动化测试

| 层 | 新增测试 | 覆盖点 |
| --- | --- | --- |
| 纯函数 | `ContinueTargetTest`、`RouteArgsTest`、`SourceQueryPlannerTest`、`TagToneTest`、`LibrarySorterTest`、`SearchHistoryCodecTest`、`ChapterFilterTest`、`TaskGroupingTest`、`SourceUrlTest` | 进度 0/越界/缺章；中文/空格/斜杠/`%`/`?`/emoji；作者/标签按源 query；标签配对/同色；最近排序空值；历史去重/损坏；筛选/分组/URL |
| Room/Robolectric | `LibraryDaoQueryTest`、`Migration2To3Test`（P1）、`BackupCompatibilityTest`、`CacheIsolationTest` | 收藏筛选；最近排序；忽略任务不出现；成功翻译清忽略；清缓存前后书/进度指纹不变；旧备份导入 |
| ViewModel | `DiscoverSearchRaceTest`、`ChapterDownloadTest`、`LibraryFilterTest`、`TaskRetryFlagTest` | 旧请求不覆盖新结果；翻译失败保留原文；单章失败不终止全本；重试参数只消费一次；筛选组合 |
| Compose/导航 | `BookDetailClickTest`、`CatalogFilterTest`、`BottomBarTest`、`MeScreenTest`、`TaskActionTest`、`ThemeSettingTest` | 作者/标签跨 Tab；详情/目录独立滚动；3 Tab 选中；我的状态卡；忽略/重试可点；8 主题切换不崩 |
| 手工 | 真实 v2→v3（P1）、19 本备份导入、断网搜索、下载中断、进程死亡恢复、深色/大字号 | 无白屏/无 500 类错误、无数据丢失、返回栈正确 |

- 现有 `MetadataTranslationServiceTest`、`AppThemeTest`、`P0SmokeTest` 必须保持全绿；`AppThemeTest` 的 `teal/lavender/sakura` 断言保留，只新增 8 主题与 palette 断言，不删旧 id。
- 主题映射专项：`ThemePaletteTest` 遍历 8 套浅/深色，断言 `LnExtendedColors` 四类标签色齐全、同标签稳定、文字对比度 ≥4.5:1；未知 id 按 4.5 的兼容策略验证。

### 验收口径

- [ ] 底栏为书架/发现/我的 3 项；发现 1 击可达；书架顶栏不再有发现按钮；任务/设置从“我的”1 击可达。
- [ ] 详情与目录是两个页面：详情无章节长列表，目录无 hero/标签/下载大按钮；返回不丢滚动。
- [ ] 作者、标签在详情/卡片/来源预览可点；切到发现搜索；返回只回发现；再点书架恢复原详情与滚动。
- [ ] 继续阅读在进度 0、正常、越界、缺章四种情况下都有确定行为；收藏/缓存/导出/源站位置正确。
- [ ] 书架有最近阅读、收藏筛选、排序、可关闭备份提醒；每行不再常驻收藏星；空态能给出下一步。
- [ ] 发现首页只有搜索入口 + 分节内容；链接加书在 Sheet；加书停留原页；单源失败不清空其他结果。
- [ ] 搜索/空态/全失败/翻译中都有下一步；无 Key 不阻塞；搜索历史（P1）可复用/清空。
- [ ] 我的有备份/任务/缓存状态卡与失败角标；设置分组/高级折叠生效；无登录/Wenku/论坛入口。
- [ ] 8 套主题与深色配对正常；同一标签跨页面同色，文字对比度 ≥4.5:1；未知主题回退兼容策略明确。
- [ ] 任务中心只显示进行中/失败/未译全且排除忽略；重试进阅读器；忽略可撤销；无测试遗留任务。
- [ ] 现有 72 个单元测试全绿；新增测试全绿；`lintDebug` 无新增 error；旧备份可导入。
- [ ] 真机冷启动/切换底栏/进出阅读器无 ANR、无重复返回、无错误底栏；卸载前备份提醒清楚。

### 执行命令（Windows，供实施阶段使用）

```powershell
.\gradlew.bat testDebugUnitTest
.\gradlew.bat testDebugUnitTest --tests "com.kacyraho.lightnovel.data.local.LibraryDaoQueryTest"
.\gradlew.bat lintDebug
.\gradlew.bat connectedDebugAndroidTest   # 有设备时；HyperOS 注意后台启动限制
```

> 本文是实施前的方案与验收契约；当前未修改任何代码、未构建、未安装。实施时以“现有 72 tests 不回归”为硬门槛，每个阶段先跑受影响测试，再跑全量。
