# 阅读器 UX 研究：wenku8x / IReader

> 只读研究，未运行 Flutter、未联网。路径相对仓库根；`wenku8x` 指 `.tmp/reference/wenku8x`。
> IReader：`.tmp/reference/ireader-tmp` 为空；`.tmp/reference/ireader` 只有 `.git`、无工作树，
> `android/docs/REFERENCE-NOTES.md:15,91` 也记录了源码未拿到，故本篇以 wenku8x + 本项目现状为主。

## 0. 一句话结论

wenku8x 的**交互结构**值得学（中央点击出菜单、左右点击翻页、子面板贴在底栏上方、章前预取）；
它的**状态模型不要照搬**（Widget 列表当数据、进度语义错误、改字号丢位置、换主题不重绘）。
我们 v1 的目标应是：**一个稳定的 ReadingLocator + 一套可重排的排版参数 + 三层菜单**，而不是堆翻页动画。

## 1. 参考实现地图
### 页面与状态
- `lib/screen/reader/reader_screen.dart:51-88`：`Theme > Scaffold > Stack`；内容层 + 7 个浮层 + loading，
  所有菜单都是 Stack 兄弟，互不挤压正文。
- `lib/screen/reader/reader_provider.dart:36-62`：6 个 bool 表示菜单（top/bottom/catalog/theme/text/config + progress），
  `subMenusVisible`/`parentMenuVisible` 由 bool 组合推导——组合态多，容易出「两个面板同时开」。
- `reader_provider.dart:66-104`：`Reader` 持有 `cIndex/themeId/catalog/textStyle/pages/config`；
  `ReaderConfig` 一次塞进 8 种翻页/显示模式。
- `reader_provider.dart:108-113`：持久化只有 `cIndex + pIndex` 两个整数（`meta.json`）。
- `reader_provider.dart:217-254`：目录与章节文本各自落盘（`catalog.json`、`<cid>.txt`），文本按正则切段。
- `reader_provider.dart:256-294`：整章被一次性切成 `List<Widget>`；页内用 `ValueKey{cIndex,pIndex,allPages}`。
- `reader_provider.dart:300-335`：当页数 ≤4 或当前页 <3 / >末 3 页时，同时预取前后章；
  `:365-406` 预取结果 append/prepend，前插后 `jumpToPage(nextPages.length + pIndex)` 保持视觉位置。
- `reader_provider.dart:337-363`：启动恢复：把 meta 的 `pIndex` 反查页码，再 `jumpToPage`。
- `reader_provider.dart:408-447`：翻页结束写 meta；但进度滑块写入的是
  `currentIndex = currentChapterIndex`、`totalPages = 本章页数`（`:420-430`），**章节号被当成页号**。
- `reader_screen.dart:56-69` + `scroll_reader.dart:44-52`：`PageView` 关闭自带滚动
  （`NeverScrollableScrollPhysics`），改由 `Listener` 手动处理拖动/点击。
- `reader_provider.dart:489-568`：点击区 = 中间 1/3 开合菜单、右 1/3 下一页、左 1/3 上一页；
  菜单开着时，点正文只关菜单、不翻页（`:503-505`），子面板开着时只关子面板（`:491-500`）。
- `lib/screen/reader/custom_scroll.dart:3-18`：自定义弹簧，但全仓只有自引用，**未接线**。

### 菜单
- `menu_bars/menu_bottom.dart:31-146`：底栏 4 项（目录/主题/字号/设置），200ms 位移；
  高度测量后存进 state，供子面板贴底。
- `menu_bars/menu_catalog.dart:40-121`：目录从底栏上沿展开到顶部；打开时
  `scrollController.jumpTo(cIndex * 46.0)` 自动定位当前章；当前章高亮。
- `menu_bars/menu_top.dart:32-70`：顶栏只有返回、书名、刷新（空实现）。
- `menu_bars/progress_bar.dart:32-91`：进度条贴在底栏上方，滑块松手才 `jumpToPage`。
- 子面板统一 `AnimatedPositioned`（200ms）从底栏下方滑入；`menu_text` 字号 14-32、行距 1.3-2.5，
  松手才提交（`menu_text.dart:83-96,140-153`）；「系统字体/页边距」按钮是空实现（`:185-241`）。
- `menu_bars/menu_config.dart:54-109`：8 宫格翻页模式，其中「仿真翻页」显式 `notWork`；
  `fullScreen`/`keepScreenOn` 有开关（`:97-108`），但全仓找不到任何应用点（grep 仅声明与菜单）。

### 排版与主题

- `lib/utils/render.dart:18-24`：排版宽高 = `MediaQuery.size - padding - 系统 inset`；
  页边距 20，上 36 下 64，段距 20px；每章首页占 3 行标题区。
- `render.dart:47-183`：按 `TextPainter.computeLineMetrics()` 逐行累计高度切页；首行缩进 2 字；
  页尾若放不下就整页切断，最后 `:225-265` 每页叠书名/章名 + `x/y` 页码。
- `lib/utils/splitter.dart:214-356`：另一套更干净的 `PageConfig` 模型：
  页边距 24、字号 16、行高 1.6、段距 `fontSize + 2`、标题 `+3`、上下信息栏 12；
  `PageInfo/ParagraphInfo` 存的是「段落 + 坐标」，而不是 Widget（`:358-394`）。
- `lib/screen/reader/themes/{mulberry,spring,glacier,cherry,walnut}.dart:3-11`：5 套固定浅色配色，
  仅 `background/onBackground/surface/outline/primary`；**没有深色阅读主题**。
- 阅读主题与 App 深色模式解耦：`lib/main.dart:105-119` 用 `ThemeMode.system` 管全局，
  但 `ReaderScreen` 始终套 `reader.theme`，所以阅读页在系统深色下仍是浅色。

## 2. 值得学 / 不该照搬

| 判断 | 依据 |
| --- | --- |
| 学：菜单全部浮层，正文尺寸不随菜单变化 | `reader_screen.dart:51-88` 的 Stack 结构 |
| 学：菜单开着时首次点击只关闭、不翻页 | `reader_provider.dart:489-506` |
| 学：子面板单开、贴在底栏上方、点另一项直接切换 | `menu_bottom.dart:48-132` |
| 学：目录自动定位当前章、当前章高亮 | `menu_catalog.dart:28-33,94-102` |
| 学：章前预取 + 前插后保持页码 | `reader_provider.dart:383-406` |
| 学：切页参数集中成 PageConfig，便于重排 | `splitter.dart:214-356` |
| 不学：`List<Widget>` 当分页数据 | `reader_provider.dart:66-73,256-294`，无法做纯函数重排/测试 |
| 不学：6 个 bool 描述菜单 | `reader_provider.dart:36-62`，应有显式 `ChromeState` |
| 不学：改字号=`refresh()` 回章首 | `reader_provider.dart:624-626` + `:575-591`（pIndex 写 0） |
| 不学：换主题只改 themeId | `reader_provider.dart:616-618`；页面文本色在切页时已固化（`:256-294`），从代码看不会重绘 |
| 不学：进度滑块混用章节号/页号 | `reader_provider.dart:420-430` |
| 不学：声明了 fullScreen/keepScreenOn 却没有应用 | `reader_provider.dart:94-104`，`menu_config.dart:97-108` |

## 3. v1 阅读页设计

### 3.1 布局（三层，互不挤压）
```
ReaderScreen                       // 只负责系统栏/生命周期
├─ ReaderContent                   // HorizontalPager，永远占满窗口
│  └─ ReaderPage                   // 页眉(章名) + 正文 + 页脚(页码)
├─ ReaderChrome                    // 顶栏 + 底栏 + 轻 scrim；浮层
│  ├─ ReaderTopBar                 // 返回 / 书名 / 章名
│  └─ ReaderBottomBar              // 目录 主题 排版 设置
└─ ReaderPanel                     // 目录 / 排版 / 主题详情，二选一
```

- **正文尺寸只由「窗口 - 固定安全 inset - 页边距」决定**，菜单开合不触发重排。
- 页眉/页脚画在页内（低对比、13sp 左右），页码形如 `12/37`；不再用独立 Text 盖在正文底部。
- 现有 `ReaderScreen.kt:57-85` 的标题行与 A-/A+ 常驻会吃掉阅读高度，应移除并收进排版面板。

### 3.2 状态模型（单一 UiState，Compose 友好）
```kotlin
data class ReadingLocator(val chapterId: String, val charOffset: Int)

data class ReaderSettings(
    val themeId: String = "paper",
    val fontSizeSp: Float = 18f,
    val lineHeight: Float = 1.7f,
    val paragraphSpacingDp: Float = 10f,
    val marginDp: Float = 20f,
    val keepScreenOn: Boolean = true,
    val immersive: Boolean = true,
)

data class ReaderUiState(
    val bookId: String,
    val chapters: List<ChapterRef>,
    val locator: ReadingLocator,
    val settings: ReaderSettings,
    val pagination: Pagination?,      // 由 textRevision + settings + 尺寸派生
    val pageIndex: Int,
    val chrome: ChromeState,          // Hidden | Bars | Panel(PanelKind)
    val load: LoadState,              // Loading | Ready | Error
)
```

- **唯一真相是 `ReadingLocator(chapterId, charOffset)`**，`pageIndex` 只是派生物。
  翻页停稳（400-800ms debounce）、`onStop`、退出时落盘；恢复时先分页，再二分查 `[start,end)`。
- 不要复用 `ReadStateEntity.progressIdx` 存页号：它是章索引（`Entities.kt:35`）。
  v1 用 DataStore 按 bookId 存 locator；v1.1 再加 Room 列并迁移。
- 设置变更只让 `paginationKey` 失效：在 Default 线程重排，保留 locator，跳到包含该 offset 的页；**不重新拉章节**。
- 分页输入固定为 `textRevision, widthPx, heightPx, fontSize, lineHeight, paragraphSpacing, margin, fontScale`；
  这些之外的任何状态都不应触发分页。
- 章节窗口：内存保留 prev/current/next 三章文本与页码表；当前页距章末 ≤3 页或距章首 ≤2 页时预取。
  若时间紧，v1 可先「单章 + 章末卡片」，但页列表仍要建模成 `PageRef(chapterId, pageIndex)`。

### 3.3 设置项（v1 只保留影响「读得舒服」的）
| 项 | 默认 | 范围/形式 | 理由 |
| --- | --- | --- | --- |
| 主题 | 纸白 | 纸白/米黄/护眼/夜间，4 套固定色 | 固定对比度，不跟动态取色漂移 |
| 字号 | 18sp | 14-30，步进 1 | 与 wenku8x 18/1.7 同档，上限更克制 |
| 行距 | 1.7 | 1.3-2.2，步进 0.1 | 中文长文 1.6-1.8 最稳 |
| 段距 | 10dp | 0-24，步进 2 | 用段距代替空行，重排可控 |
| 页边距 | 20dp | 紧凑 12 / 标准 20 / 宽松 28 | 预设比滑杆更少决策 |
| 常亮 | 开 | 开关 | 阅读页默认常亮，退出即恢复 |
| 沉浸 | 开 | 开关 | 隐藏状态栏，保留系统导航手势区 |
| 翻页 | 横滑 | 固定 | 竖滚放 v1.1 |

主题建议色（参考 wenku8x 但补夜间）：纸白 `#FAFAF7/#242424`、米黄 `#F5ECD9/#3A3226`、
护眼 `#EFF6E9/#081B16`（同 spring）、夜间 `#121212/#C8C5BE`。正文对比度目标 ≥7:1。

## 4. 手势与菜单层级
- **点击区**：左 30% 上一页、中 40% 开合菜单、右 30% 下一页；整页高度生效。
  比 wenku8x 的「中间 1/3 × 1/3」更大，但左右仍留 30% 防止误触。
- **滑动**：直接用 `HorizontalPager` 的滑动与吸附，`beyondViewportPageCount = 1`；
  不自定义物理/仿真。章节跳转用无动画定位。
- **菜单打开时**：点正文只关面板/菜单，不翻页；面板打开时禁用 pager 滑动。
- **返回优先级**：`Panel -> Bars -> 退出阅读页`（`BackHandler`）；不要拦截边缘侧滑，保留预测式返回。
- **菜单层级**：顶栏（返回/书名/章名）+ 底栏（目录/主题/排版/设置）；
  子面板永远单开，贴底栏上方；目录占满可用高度。`ChromeState` 用枚举，不用多个 bool。
- **进度**：v1 只做「本章页滑块 + 页码文字 + 目录」；全书进度用页脚百分比/章序展示。
  滑块拖动实时改页码标签，松手才落 locator。不要做错误的「章节号当页号」。
- **动画**：横滑 220-260ms ease-out；章间切换瞬时；不做卷曲/覆盖/仿真。
- **音量键、双击、长按、TTS**：v1 全部不做；音量键放 v1.1 且默认关闭（会破坏音量控制直觉）。

## 5. 无障碍、深色与系统
- **画布分页没有语义**：`ReaderPageView` 只是 `Canvas`，TalkBack 读不到内容。
  必须在页容器上加 `semantics { contentDescription = 页文本; stateDescription = "第 x 页，共 y 页";
  customActions = [上一页, 下一页, 目录] }`。这是 v1 必做，不是加分项。
- 尊重系统字体缩放（`fontScale` 参与分页 key），不硬编码 dp 字号；行距用倍数，保证一起放大。
- 夜间不用纯黑底纯白字（光晕），用 `#121212/#C8C5BE`；状态栏图标亮度跟随主题亮度。
- 常亮用 `FLAG_KEEP_SCREEN_ON` + 生命周期，不用 WakeLock；沉浸用 `WindowInsetsControllerCompat`，退出恢复。
- 方向 v1 跟随系统，不锁定；竖屏单栏在横屏下加宽页边距即可。双页/横屏双栏放 B。
- 屏幕亮度 v1 不覆盖系统；阅读器亮度滑杆放 v1.1（退出需恢复原值）。

## 6. 版本切分
| 版本 | 内容 |
| --- | --- |
| v1 | 三层浮层菜单、4 主题、字号/行距/段距/页边距、locator 进度、目录高亮与跳章、前后章预取、点击区+横滑、页内页码、返回层级、常亮、沉浸、深色、TalkBack 语义、加载/错误/空态 |
| v1.1 | 竖向滚动模式、音量键翻页（默认关）、全书进度拖动、阅读亮度、方向锁定、章末「下一章」卡片、书签 |
| B | 卷曲/仿真翻页、自动翻页、双页/横屏、自定义字体导入、背景图/纹理、手势自定义、跨端同步、批注/分享、双语对照、环境光自适应 |

**明确不做（v1）**：仿真/卷曲动画、TTS 实现、音量键、亮度覆盖、护眼滤色、背景图、自定义字体、
自动滚动、双页、手势重映射、动态取色阅读主题、书签/批注、跨设备同步、按页单独设置。

## 7. 对现有 ReaderScreen / ReaderPageView 的改造清单

**P0（不做就不算「读得舒服」）**

1. `ReaderScreen.kt:39-148` 拆成 `ReaderRoute/ReaderContent/ReaderChrome/ReaderPanel`；
   删除常驻标题行与 A-/A+（`:57-85`），改为页内页眉页脚；保留 `reader-screen`/`reader-pager` tag。
2. 引入 `ReaderViewModel + ReaderUiState + ReadingLocator`；把 `fontSizeSp` 从
   `rememberSaveable`（`:46`）迁到 DataStore 设置；停稳/`onStop` 持久化 locator。
3. `ReaderScreen.kt:98-120`：把分页改为 `produceState`/`LaunchedEffect(paginationKey)`，
   在 Default 线程重排；重排后按 charOffset 回到原页，不再因字号变化回到第 1 页
   （对照 wenku8x `reader_provider.dart:624-626`）。
4. `StaticLayoutPaginator.kt:48-77`：`PageSlice` 增加 `chapterId/startChar/endChar`；
   用 `SpannableStringBuilder + LeadingMarginSpan` 做首行缩进，`setLineSpacing(extra, multiplier)` 做段距；
   补「重排后 offset 仍落在同一页」单测。
5. 章节仓库：从 `ChapterEntity.rawPath/zhPath`（`Entities.kt:50-61`）读取章节文本，
   维护 prev/current/next 窗口，距边缘 2-3 页预取，跳章取消旧任务；暴露 Loading/Error/End。
6. `ReaderPageView.kt:12-25`：改为绑定 `PageRender(layout, slice, palette, header, footer)`；
   主题/页眉页脚变化必须 `invalidate()`；不要在 View 外再用独立 Text 盖页码（现 `ReaderScreen.kt:138-145` 会压住正文）。
7. 菜单：新增 `ChromeState` 枚举 + `BackHandler`；实现点击区、面板单开、菜单开时禁翻页、
   点击正文只关层；菜单开合不改变正文尺寸。参考 `reader_provider.dart:489-506`、`reader_screen.dart:51-88`。
8. 主题：建 `ReaderPalette(background/content/secondary/accent/isDark)` 4 套；正文色只从这里取，
   不再用 `MaterialTheme.colorScheme.onBackground`（现 `:48`），换主题立即重绘。
9. 进度与目录：`pageIndex` 由 locator 派生；目录高亮当前章并自动滚动（参考 `menu_catalog.dart:28-33`）；
   跳章 offset=0、无动画；页脚显示 `章内 x/y`。
10. 无障碍：给页容器加语义与自定义动作；验证 TalkBack 能读当前页并翻页；系统 fontScale 参与分页。

**P1（紧随 v1）**

11. 排版设置面板：主题 chips + 字号/行距/段距滑杆 + 页边距三档；拖动只更新预览，150ms debounce 后重排。
12. 常亮/沉浸：Activity 生命周期内开关，退出恢复；状态栏图标颜色跟随主题。
13. 测试更新：`ReaderScreenTest.kt:24-29` 目前断言 `轻小说/分页示例`，改造后应断言页眉/页码/菜单；
    新增分页 offset、点击区、返回层级、设置持久化的 Robolectric/Compose 测试。
14. 竖滚模式（v1.1）预留 `PageMode`，但 v1 只实现 Horizontal。

**P2（B 阶段）** 音量键、TTS 入口、书签、全书进度拖动、方向锁定、阅读亮度。

## 8. 验收（v1）

字号 18→24→14 往返、旋转/分屏后都停在原段落；切主题无白闪；章末翻页直达下一章第 1 页；
菜单开合正文不跳；返回严格「面板→菜单→退出」；TalkBack 可逐页朗读；冷启动可读 <1s。
