# Legado 阅读器研究：分页、断行、绘制与设置

> 只读研究本地快照，不引入参考代码。Legado 为 GPLv3；本文只提炼设计，不复制实现，避免许可污染。
> 快照：`.tmp/reference/legado-src`，commit `dfce153`。路径缩写：
> `READ = app/src/main/java/io/legado/app/ui/book/read`；
> `APP = app/src/main/java/io/legado/app`；行号均按本地快照。

## 0. 结论

1. **页不是整章字符串，而是“段落 → 行 → 页”的坐标模型**；Legado 每段单独排版，再按行高把行装进页，所以段距、首行缩进、图片、双栏、TTS 高亮能共用一套数据。
2. **阅读进度存“章内字符偏移”，不是页号**；换字号/换字体后页数变了，字符偏移仍能定位，再反算页号。这是最值得直接采用的设计。
3. **常驻“上一章 / 当前章 / 下一章”三章窗口**，翻到章末/章首时整体换窗，并异步预取 ±1 章；比把所有章节拼成一个大列表更省内存、边界更清楚。
4. **Legado 默认仍用 `StaticLayout`，`ZhLayout` 是可选开关**（`pref_config_read.xml:54`，默认 false）。不要因为“中文标点”就整段照搬 `ZhLayout`；优先用 Android 13+ 的 `LineBreakConfig` 严格/词组断行做对照测试。
5. **翻页动画是 delegate 插件，分页数据与动画解耦**；这个 seam 值得保留，但具体实现（三份 View + 截图 Bitmap + Scroller）不适合 Compose。
6. **设置项要分层**：v1 只做字号/行距/段距/页边距/主题/字体/缩进/标题/隐藏状态栏；双栏、底部对齐、全角对齐、自定义字体、背景图、E-Ink、卷帘动画全部后置。
7. **与 Compose 不兼容的核心不是 UI 控件，而是全局单例与可变坐标**：`ReadBook`、`ChapterProvider`、`ReadBookConfig` 都是 object；`TextPage/TextLine/TextChar` 在排版后被原地改写。Compose 应改为 ViewModel + 不可变页面快照 + 显式配置。
8. **A′ 的翻译阅读必须用“段落锚点”而不是绝对字符偏移**：原文与译文字数不同，重译/增量翻译都会使字符偏移漂移；章节内段落编号才是跨语言稳定键。

## 1. 关键文件坐标

| 主题 | 路径 | 关键行 |
| --- | --- | --- |
| 页/行/字模型 | `READ/page/entities/TextPage.kt`、`TextLine.kt`、`TextChar.kt` | TextPage 15-25、36-77、79-116、151-174；TextLine 8-27、43-48；TextChar 3-14 |
| 章节页集合 | `READ/page/entities/TextChapter.kt` | 5-13、19-21、35-46、69-78 |
| 章节排版 | `READ/page/provider/ChapterProvider.kt` | 104-201、203-266、271-393、398-529、534-609 |
| 中文断行 | `READ/page/provider/ZhLayout.kt` | 14-18、43-165、174-209、213-259 |
| 页工厂/跨章 | `READ/page/provider/TextPageFactory.kt`、`READ/page/api/PageFactory.kt`、`DataSource.kt` | Factory 10-20、36-130；PageFactory 3-26；DataSource 6-21 |
| 绘制 | `READ/page/ContentTextView.kt`、`PageView.kt` | Content 73-157、196-221、230-335、426-497；PageView 42-47、101-172、213-236 |
| 手势/页面容器 | `READ/page/ReadView.kt` | 47-49、159-234、275-379、384-427、480-519 |
| 翻页 delegate | `READ/page/delegate/*.kt` | PageDelegate 16-189；Horizontal 9-144；Slide 8-61；Scroll 9-115；Simulation 13-573；Cover 9-84；NoAnim 6-24 |
| 阅读设置 | `APP/help/ReadBookConfig.kt`、`READ/config/ReadStyleDialog.kt`、`MoreConfigDialog.kt`、`PaddingConfigDialog.kt` | Config 426-478、480-588；Style 130-200；More 97-131；Padding 42-121 |
| 阅读状态/章节/预取 | `APP/model/ReadBook.kt` | 30-64、140-200、227-279、344-388、419-451 |
| TTS | `APP/model/ReadAloud.kt`、`APP/service/BaseReadAloudService.kt`、`TTSReadAloudService.kt` | ReadAloud 15-47；Base 114-134、355-360；TTS 69-99、138-173 |
| Activity 集成 | `READ/ReadBookActivity.kt`、`ReadBookViewModel.kt` | Activity 178-192、652-681、727-780、1066-1088、1100-1124；ViewModel 41-100、224-237 |
| 正文清洗/分段 | `APP/help/ContentProcessor.kt` | 68-121、126-140 |
| 阅读偏好清单 | `app/src/main/res/xml/pref_config_read.xml` | 26、47、54、61、68、96 |

## 2. 分页数据模型

### 2.1 三层结构

- `TextPage`：`index/pageSize/chapterIndex/chapterSize`、`title`、`text`、`textLines`、`height`、`leftLineSize`。`text` 是页面所有行的拼接，段末补 `\n`，可直接给 TTS/无障碍/搜索用。
- `TextLine`：`text`、`textChars`、`lineTop/lineBase/lineBottom`、`isTitle/isReadAloud/isImage`。行高和基线是绝对像素坐标。
- `TextChar`：单个字符的 `charData` 与 `start/end` 像素横坐标；`ChapterProvider` 路径按码点拆分（保留 emoji），`TextPage.format()` 回退路径按 UTF-16 索引。另有 `selected/isImage/isSearchResult` 可变标记。
- `TextChapter`：`position/title/url/pages/chaptersSize`；`getReadLength(pageIndex)` 把页号换成“本章起始字符偏移”，`getPageIndexByCharIndex` 反向找页。后者是线性扫描，长章节应改前缀数组 + 二分。
### 2.2 排版流水线（`ChapterProvider`）

1. 先排标题（`titleMode != 2`）：按 `\n` 拆行，用 `titlePaint`；首章/纯标题章有垂直居中与 `titleTopSpacing` 特判（104-129、289-313）。
2. 正文按“段”传入（`contents: List<String>`，来自 `ContentProcessor.getContent` 111-121 的按 `\n` 清洗与缩进）。
3. 每段建一个 `StaticLayout` 或 `ZhLayout`（284-288）；逐行取 `getLineStart/getLineEnd/getLineWidth` 生成 `TextLine`。
4. 首行缩进与两端对齐是**手工 x 坐标**：`addCharsToLineFirst` 先放缩进字符再放剩余字（398-428）；中间行按剩余宽度均摊（433-473）；末行自然排列（478-511）；超出右边界时 `exceed` 把整行字符向左压（516-529）。
5. 纵向不采用 `StaticLayout` 的行高：`durY += textPaint.textHeight * lineSpacingExtra`（387-389），`textHeight = descent - ascent + leading`（`APP/utils/PaintExtensions.kt:5-6`）。所以行距是统一倍数，不受字形影响。
6. 段末加 `textHeight * paragraphSpacing / 10`（391）；默认 `lineSpacingExtra=12` 即 1.2 倍行高，`paragraphSpacing=2` 即 0.2 行。
7. 当前页放不下下一行时新建 `TextPage`，并写入上一页的 `text/height`（314-334）。整章结束后回填 `index/pageSize/chapterIndex/chapterSize/title`，再对每页做底部对齐（186-193）。
8. 双栏不是两个独立页：横屏/平板时 `visibleWidth = viewWidth/2 - 左右边距`，一个 `TextPage` 内用 `leftLineSize` 记住左栏行数（318-324、626-644）。
### 2.3 页工厂与跨章

- `TextPageFactory` 只暴露 `curPage/prevPage/nextPage/nextPlusPage` 与 `moveToNext/Prev`；`nextPlus` 供滚动模式一次画三页。
- 跨章逻辑在 `moveToNext/Prev`（36-60）：当前页是章末则 `moveToNextChapter`，章首则 `moveToPrevChapter`；`prevPage` 会取上一章最后一页（94-110）。
- `ReadBook` 维护 `prev/cur/nextTextChapter` 三章；`moveToNextChapter` 把 next 升为 cur、cur 降为 prev 并清空 next，再异步加载新 next（140-160）；反向同理（162-185）。
- 内容加载完成后只接受 `index ∈ [durChapterIndex-1, +1]` 的章节，避免快速翻页时旧请求覆盖新状态（344-380）。
### 2.4 可直接复用的部分

- **段落是可排版的最小单位**：一段一个 `StaticLayout`，行盒再装页。段距、首行缩进、逐段双语、段落级翻译状态都自然成立。
- **页只保存行盒与锚点**：`startAnchor/endAnchor = (chapterIdx, paragraphIdx, charOffset)`；不要保存“第几页”作为真相。
- **三章窗口**：当前章前后各留一章；翻页到边界只换窗口，不重建全书。
- **页面文本缓存**：每页 `text` 可直接给 TTS/搜索/无障碍；但结构化段落仍要保留，不能只留扁平字符串。
- **`getReadLength` 的思想**：页起点 = 前面所有页字符数之和；我们用前缀数组 + `lowerBound` 实现 O(log n)。

## 3. 中文/日文断行

### 3.1 `StaticLayout` 的断行

- `StaticLayout` 的实际断行由系统 `LineBreaker`/ICU 规则决定，受 `breakStrategy`、`hyphenationFrequency`、文本语言影响；它不是“只会按宽度硬切”。
- Android 13（API 33）起 `StaticLayout.Builder.setLineBreakConfig(LineBreakConfig)` 可显式指定：
  - `LINE_BREAK_STYLE_STRICT`：严格断行（标点禁则）；
  - `LINE_BREAK_WORD_STYLE_PHRASE`：按词组断行，适合日文；
  - `HYPHENATION_DISABLED`：关闭连字符。
- 我们 `minSdk 26`，需 `Build.VERSION.SDK_INT >= 33` 分支；低于 33 回退到 `BREAK_STRATEGY_HIGH_QUALITY` + 后处理或自研断行。**先做 A/B fixture 对比，再决定是否自研**，不要先入为主。
### 3.2 `ZhLayout` 做了什么

- 只计算“每行起点 + 行宽”，不计算纵向（`getLineTop/Descent` 返回 0，213-259）；它是给 `ChapterProvider` 当“断行器”用的，不是通用 Layout。
- 逐码点累加宽度（43-51；码点拆分见 `APP/utils/StringExtensions.kt:82-93`，能保留 emoji 代理对）。
- 溢出时按标点分类：
  - 前一字是“行末禁则”的开引号/开括号（`isPrePanc` 185-191）→ 把前一字一起下移（`BREAK_ONE_CHAR`，108-112）；
  - 当前字是“行首禁则”的收引号/收括号/句读（`isPostPanc` 174-183）→ 把当前字下移（同段）；
  - 连续禁则/可压缩标点 → `CPS_1/2/3`，把字符留在本行、`offset=0`，之后再靠 `ChapterProvider.exceed` 压缩字距（118-132、516-529）；
  - 无法处理时从当前位置向前找“既非行首禁则、前字也非行末禁则”的断点（82-100）。
- `inCompressible` 用“宽度小于一个汉字”判断可压缩（193-195）；`getPre/PostPancOffset` 预留但当前主流程未使用（197-209）。
### 3.3 差异与风险

- `ZhLayout` 按码点断行，**没有拉丁词/空格/连字符规则**；英文单词、数字、URL 可能被从中间切开。
- 没有 bidi、复杂脚本、字素簇（ZWJ emoji、组合符）处理；“一个码点”不等于“一个可见字符”。
- `CPS` 模式允许 `lineWidth > width`，依赖后续统一压缩；字距可能不均，且压缩后 `TextChar` 坐标与真实字形宽度不再一致。
- 它继承 `Layout` 却返回假的行高/方向/Tab 信息；除了 `ChapterProvider`，其他 Android 文本 API 不应消费它。这是**脆弱 seam**，不适合作为我们长期接口。
- Legado 自己默认 `useZhLayout=false`；说明 `StaticLayout` 在多数场景可接受，`ZhLayout` 是特定排版需求的补丁。
### 3.4 建议

- 日文原文优先 `LineBreakConfig` 的 `PHRASE`；中文译文优先 `STRICT`。用固定 fixture 验证：行首不出现 `、。，．！？）」』】》…ーぁぃぅぇぉっゃゅょ` 等，行末不出现 `（「『【〈《` 等。
- 若系统断行仍不满足，再实现**纯函数** `CjkLineBreaker(text, paint, width) -> List<LineSpec(start,end,width)>`；内部用码点/字素簇、禁则集合、可压缩标点策略，返回数据而非继承 `Layout`，便于单测和替换。
- 全角对齐/底部对齐先不做；它们会改写行盒坐标，和 Compose 的稳定布局/无障碍冲突，等阅读体验验证后再加。

## 4. 绘制与交互

### 4.1 页面绘制

- `PageView` 是 FrameLayout：正文 `ContentTextView` + 页眉/页脚（时间、电量、章节名、页码、总进度）；页眉页脚有 6 个可配置槽位（101-172），进度文案在 `setProgress`（229-236）。
- `ContentTextView` 自己画：`canvas.clipRect(visibleRect)` 后逐行逐字 `drawText`（73-157）；图片按字符矩形绘制；选中态画半透明矩形；搜索命中改文字颜色。
- 因为是逐字绘制，选择、TTS 高亮、全角对齐都能精确到字符；代价是 `TextChar` 数量和坐标维护成本高。
- 滚动模式在同一画布里画当前页 + 下一页 + 下下页，按 `pageOffset` 纵向偏移（82-102、196-221）；触摸命中要判断相对页（295-335）。
### 4.2 手势与选择

- `ReadView` 持有 prev/cur/next 三个 `PageView`（47-49）；所有触摸由它拦截（151-234）。
- 单击按 3×3 九宫格分区（107-117、384-415），动作可配：菜单/下一页/上一页/下一章/上一章/TTS 上段/下段（417-427）。
- 长按选择用 `BreakIterator.getWordInstance` 做词边界扩展（275-379）；选择范围用 `(relativePage,line,char)` 三元组表示，支持跨页；选中文本按行拼接（426-497）。
- 选择状态直接写在 `TextChar.selected` 上，取消时全量清空（413-424）；这不是 Compose 的状态模型。
### 4.3 翻页 delegate

| 实现 | 做法 | 评价 |
| --- | --- | --- |
| `PageDelegate` | `Scroller` 驱动触摸点，`scroll()` 每帧更新；模板方法定义 `onAnimStart/onDraw/onAnimStop` | seam 清晰，可借鉴接口划分 |
| `HorizontalPageDelegate` | 三种 Bitmap 截图，按方向平移 | 截图有内存/回收/时机问题 |
| `SlidePageDelegate` | 平移当前页与上一/下一页 Bitmap | 最接近 Compose pager |
| `CoverPageDelegate` | 覆盖 + 阴影 | 可选 |
| `SimulationPageDelegate` | 贝塞尔曲线卷页 + 渐变阴影 + 矩阵翻转（13-573） | 代码量大、性能/兼容性风险高 |
| `ScrollPageDelegate` | 垂直滚动 + `VelocityTracker` 惯性（9-115） | 与分页模型不同，v1 不做 |
| `NoAnimPageDelegate` | 直接换页 | 最简单 |

**可复用**：把“下一页/上一页/是否可翻/章边界”抽成控制器接口；动画只是它的一个实现。**不建议**照搬三个 View + Bitmap + Scroller；Compose 用 `HorizontalPager` + `Animatable`/`pointerInput` 即可。
### 4.4 Compose 映射

- 页面渲染：用 `Modifier.drawBehind { drawIntoCanvas { it.nativeCanvas ... } }` 画每页的段落切片；或保留一个 `AndroidView` 包装 `StaticLayout.draw`。不要为每页创建一个 `View`。
- 翻页：`HorizontalPager`；`beyondViewportPageCount = 1`；`key = page.startAnchor.stableKey`，不要用页号（换字号后页号会变）。
- 重排后恢复：重新分页完成后，找到包含旧锚点的页，`scrollToPage`（不要 `animateScrollToPage`），避免“重排后回到第一页”。
- 轻点：`detectTapGestures` + 左/右/中三分区；九宫格配置后置。
- 选择：v1 不做；后续用 `Layout.getOffsetForHorizontal` / `getPrimaryHorizontal` 做命中，不要维护逐字可变标记。

## 5. 阅读设置

`ReadBookConfig.Config` 默认值（426-478）与 v1 取舍：

| 设置 | Legado 默认/说明 | v1 |
| --- | --- | --- |
| 字号 `textSize` | 20sp | 要；18-24sp |
| 行距 `lineSpacingExtra` | 12 → 1.2 倍行高 | 要；1.2-1.8 |
| 段距 `paragraphSpacing` | 2 → 0.2 行 | 要；0-1 行 |
| 字距 `letterSpacing` | 0.1f | 可要；默认 0 |
| 首行缩进 `paragraphIndent` | `"　　"` | 要；开关/1-2 字 |
| 页边距 | 左右 16dp、上下 6dp | 要；左右/上下两组 |
| 字体 `textFont` | 空=系统字体；支持文件/URI | 要系统 serif/sans；自定义字体后置 |
| 字重 `textBold` | 0 正常/1 粗/2 细 | 可要；正常/粗 |
| 标题 `titleMode/titleSize/...` | 0 正常/1 居中/2 不显示 | 要标题字号/是否显示；居中后置 |
| 主题/背景 | 日/夜/E-Ink 三套颜色；可图片 | 要日/夜/护眼；图片/E-Ink 后置 |
| 页眉/页脚 | 6 槽位、独立 padding、分隔线 | 后置；v1 仅章节名 + 页码 |
| 双栏 `doublePageHorizontal` | 横屏/平板，左栏行数 | 后置 |
| 全角对齐/底部对齐 | 默认 true | 后置；先自然排版 |
| 翻页动画 `pageAnim` | 0 覆盖/1 滑动/2 仿真/3 滚动 | v1 只用 pager 滑动；仿真/滚动后置 |
| 简繁转换 | `ChineseUtils.t2s/s2t` | 日文源不需要；中文译文可由 prompt 控制，后置 |
| 5 套样式 + 分享布局 | `configList`、`shareLayout` | 后置；v1 单套全局配置，后续按书覆盖 |
| 状态栏/导航栏隐藏 | 有 | 要；沉浸阅读 |
| 音量键翻页/亮度/自动翻页/休眠 | 有 | 后置 |

**配置建模建议**：分成 `LayoutConfig`（影响分页：字号/行距/段距/缩进/字体/边距/标题）与 `ThemeConfig`（只影响颜色/背景：文字色/背景色/主题）。只有 `LayoutConfig` 变化才重新分页；`ThemeConfig` 变化只重组。用一个稳定 `layoutHash` 做页缓存键。

## 6. 朗读、进度、章节与预取

### 6.1 进度

- 真相是 `ReadBook.durChapterIndex + durChapterPos`，`durChapterPos` 是**章内字符偏移**；`setPageIndex` 用 `getReadLength(index)` 把页号换成字符偏移（196-200），`durPageIndex` 再反算（227-232）。
- 翻页、跳页、换章、`onPause` 都会 `saveRead()`（419-432）；`onPause` 里还停自动翻页/备份（178-192）。A′ 应改为：页稳定后 debounce 500ms 保存 + `ON_STOP` 立即保存，避免每次重组写库。
- 进度百分比：章进度 + 章内页进度，接近末尾但非真正最后一页时压到 99.9%，避免“100% 但还有一页”（151-165）。这个细节值得保留。
- **A′ 注意**：`durChapterPos` 只在同一文本版本内可靠；原文/译文切换、重译后长度变化，必须用段落锚点重算。

### 6.2 章节切换与预取

- 换章：`moveToNextChapter` 把 `durChapterPos=0`，窗口前移；`moveToPrevChapter(toLast=true)` 用上一章 `lastReadLength`（最后一页起点）落位（140-185）。
- 预取：当前页变化后 `preDownload()` 预下载 `+2..+preDownloadNum` 与 `-2..-5` 章，每章间隔 1s（437-451）；同时三章窗口保证翻页不白屏。
- A′ 的“预取”不需要联网：靠近章末时提前读取/排版下一章原文文件即可；**不要自动预翻译**（成本与 ADR-002 冲突）。

### 6.3 TTS

- `BaseReadAloudService` 把“当前页到章末”的页面文本按 `\n` 拆成段落列表；可选“按页朗读”（114-134）。
- 播放用系统 `TextToSpeech`，`QUEUE_ADD` 逐段入队；`onStart/onDone/onRangeStart` 推进 `readAloudNumber`（章内字符偏移），跨页时 `ReadBook.moveToNextPage()`（TTS 138-173）。
- 高亮不按字符，而是把“当前段所在行区间”标 `isReadAloud`；`TextPage.upPageAloudSpan` 从段首向前找到上一段末行、向后找到本段末行（125-149）；Activity 收到 `TTS_PROGRESS` 后重绘（1066-1088）。
- 后台播放用前台 Service + MediaSession + 音频焦点 + 通知（Base 32-360）；v1 不做。若要快速验证，可先做前台 Activity 内的 `TextToSpeech`，但不要把它当最终架构。
- 为 TTS 留 seam：页面/段落模型要能按“段落索引 + 字符区间”定位；不要只存扁平页文本。

## 7. 不建议照搬的部分

| 部分 | 原因 | 我们的做法 |
| --- | --- | --- |
| `ReadBook`/`ChapterProvider` 全局 object + Activity callback | 多窗口/多本书/测试隔离都困难；静态 `viewWidth/contentPaint` 隐式状态 | ViewModel + Repository + 显式 `LayoutConfig` |
| `TextPage/TextLine/TextChar` 排版后原地改坐标 | Compose 需要不可变快照；重组期间改坐标会闪烁/竞态 | 不可变 `ReaderPage`，重排生成新对象 |
| 逐字符 `TextChar` 坐标 | 只有全角对齐/压缩时才必要；长章内存与命中成本高 | 行盒 + `StaticLayout` 的 `getPrimaryHorizontal` |
| `ZhLayout` 继承 `Layout` | 假行高/假方向，API 脆弱；拉丁词会被切 | 纯断行函数或 `LineBreakConfig` |
| 三份 `PageView` + 截图 Bitmap + `Scroller` | 内存、回收、首帧抖动；与 Compose 手势冲突 | `HorizontalPager` + `drawBehind` |
| 仿真卷页/滚动模式 | 代码量大，和 pager 的测量/无障碍模型冲突 | v1 不做；需要时单独模式 |
| 九宫格点击/音量键/亮度/自动翻页/休眠 | 配置面过大，v1 验证不了 | 左/右/中三分区；其余后置 |
| 5 套样式 + 分享布局 + 自定义字体/背景图/E-Ink | 组合爆炸，先验证核心阅读体验 | 单套全局 + 后续按书覆盖 |
| `ContentProcessor` 隐式替换/去重/简繁/重分段 | 隐藏变换让“原文/译文/进度”不可解释 | 显式 `TextSource` 管线；翻译产物带 hash/状态 |
| EventBus + 全局可变状态 | 事件顺序不可测；Compose 应用 Flow/StateFlow | 单向数据流 |
| 章内绝对字符偏移作为跨语言进度 | 原文/译文字数不同，重译即漂移 | 段落锚点 + 同版本内字符偏移 |
| 双栏/底部对齐/全角对齐 | 需要改行盒坐标；与分页/选择/无障碍耦合 | v1 自然排版；验证后再加 |

## 8. P0-4b（阅读器 UI）改造清单

按优先级排序；每项都能独立验收。

**P0（先做，形成可用阅读器）**

1. **数据模型**：`ReaderChapter(bookId, idx, title, blocks, textVersion)`；`ReaderBlock.Paragraph(id, raw, zh?, state)` / `Image`（先留接口）；`ReaderLine(paragraphId, charStart, charEnd, top, baseline, bottom, isParagraphEnd)`；`ReaderPage(indexInChapter, lines, startAnchor, endAnchor)`；`ReaderAnchor(chapterIdx, paragraphIdx, charOffset)`。**页号不是真相**。
2. **排版器**：按段落建 `StaticLayout`（后续可换断行器），输出行盒；支持段距、首行缩进、标题；提供 `Paginator` 接口 + 可注入 `TextMeasurer`，让 JVM 单测不依赖真实字体。
3. **配置拆分**：`LayoutConfig`（字号/行距/段距/边距/字体/缩进/标题）+ `ThemeConfig`（日/夜/护眼）；计算 `layoutHash`；只有 `LayoutConfig` 变化才重排。
4. **屏幕骨架**：`ReaderScreen` 接 `ReaderViewModel`；`HorizontalPager` 每页用 `drawBehind` 画 `ReaderPage`；页码/章名/进度；`key` 用 `startAnchor`。
5. **重排与恢复**：字号/行距/旋转/翻译完成后重排，按旧锚点找到新页并 `scrollToPage`；禁止“重排回第一页”。修复现有 `LaunchedEffect(pages.size)` 在页数变化时可能把位置推到 0 的行为（`ReaderScreen.kt:116-120`）。
6. **进度**：页稳定后 debounce 保存 `ReaderAnchor` 到 Room；`ON_STOP` 立即保存；冷启动按锚点恢复；跨章前后翻。
7. **章节切换**：章末下一页自动进下一章、章首上一页进上一章最后一页；`ModalBottomSheet` 章节目录；靠近章末预读/预排下一章。
8. **菜单与 v1 设置**：顶栏（返回/书名/章名/翻译状态）；底栏（目录、进度滑杆、字号、主题、行距/段距/边距、显示原文/译文）；沉浸状态栏。
9. **测试**：纯逻辑测试覆盖段落拆分、锚点换算、页边界、章边界、空段/超长段/emoji/代理对；真机 instrumentation 验证字号/宽度/旋转重排与恢复。

**P1（P0 稳定后）**

10. **断行质量**：先接 API 33 `LineBreakConfig(STRICT/PHRASE)`，用中日文 fixture 对比；仍不足再实现纯函数禁则断行器。不要直接移植 `ZhLayout`。
11. **双语/对照**：段落级 `ZH_ONLY / RAW_ONLY / BILINGUAL`；译文段落缺失时回退原文并标记；这是 A′ 的延伸，不是 P0 前置。
12. **选择/复制/词典**：用 `Layout` 命中 API + `BreakIterator`；v1 先不做。
13. **TTS**：前台 Service + MediaSession；按段落队列、段落高亮、跨页自动翻页。
14. **图片/插图**：`ReaderBlock.Image` 参与行盒；EPUB 插图后再做。
15. **双栏/底部对齐/仿真/滚动**：单独立项，不混进 pager 主路径。

## 9. A′（单章翻译阅读）改造清单

按顺序落地：

1. **文本来源解析**：`ChapterTextResolver` 读取 `ChapterEntity.rawPath/zhPath/status`（导入期 `translated/raw` 与 sidecar `complete/partial` 先归一）；只有 `zh + sidecar` 校验通过（`status=complete`、`source_sha256` 与 raw 文件 hash 一致）才用译文；`partial` 用“译文 + 未完成段落回退原文”；否则原文。绝不把失败当正文。
2. **段落模型**：按 `\n\n`/空行拆段，保留空段作为间距；译文与原文按段落索引对齐；记录 `incompleteParagraphs`。若段落数不一致，关闭逐段对照，只显示整章译文并提示。
3. **阅读页**：`ReaderBlock.Paragraph(raw, zh?, displayMode)`；`ZH_ONLY/RAW_ONLY` 整章切换是 v1 必做（ADR-005 的“日文隐藏/显示”），逐段双语可后置。
4. **翻译入口**：阅读页显示“未翻译 / 翻译中 / 已翻译 / 部分完成”；按钮“翻译本章”触发 A′ 单章任务；显示进度与失败原因；已翻译时提供“重新翻译”二次确认与费用提示。
5. **完成后刷新**：任务成功→Room 状态/文件更新→`ReaderViewModel` 重新加载文本→按段落锚点重排→恢复到同一段；不要回第一页。
6. **锚点策略**：持久化 `(bookId, chapterIdx, paragraphIdx, charOffsetInParagraph, textKind)`；跨 `textKind` 切换时用段落索引 + 段内比例近似；**不要**直接复用绝对字符偏移。
7. **缓存/预取**：内存缓存 `(chapterIdx, textHash, layoutHash)` 的页列表；进入章节时只读当前章；靠近章末预读下一章原文并排版；翻译只在用户点击时发生。
8. **失败与降级**：翻译失败/超时/校验失败时保留原文可读；不自动重试整章；显示可诊断错误；不覆盖已有完整译文（写 `.bak` 或版本化）。
9. **验收**：原文可读→点翻译→进度→完成后自动刷新且位置不丢→原文/译文切换→杀进程重进仍在同一段→备份恢复后译文状态正确。

## 10. 验收与风险

- **分页 golden**：固定日文/中文 fixture，断言页数、每页首尾字符、行首禁则；字体变化只影响页数，不改变锚点语义。
- **重排恢复**：字号 +2、行距 +0.2、横竖屏、译文完成，四种情况都恢复到同一段落/近似位置。
- **边界**：空章、只有标题、超长无标点段、连续标点、emoji/代理对、CRLF、全角空格、图片段落。
- **性能**：10k 字章节目录下分页耗时、内存、翻页帧时间；真机为主，Robolectric 不模拟真实字体度量（ADR-005 已记录）。
- **风险**：`StaticLayout` 在不同厂商字体/系统版本上的断行差异；`LineBreakConfig` 仅 API 33+；翻译文本长度变化导致页数波动；Compose pager 页数变化时的锚点恢复；GPL 代码只可读不可抄。
