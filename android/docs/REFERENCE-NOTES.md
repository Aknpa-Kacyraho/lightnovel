# 参考实现笔记（私有研究）

> 目的：只读研究交互/架构，不直接复制代码。参考代码放在 `.tmp/reference/`（已 gitignore），
> 与 `android/` 工程隔离；私有自用不涉及分发，但混入 GPL 代码会让后续维护和许可边界变乱。

## 已拉到本地的仓库

| 目录 | 仓库 | commit | 许可 |
| --- | --- | --- | --- |
| `legado-src` | `TsaiYongChuan/legado`（原 `gedoor/legado` 主仓只剩公告） | `dfce153 优化` | GPLv3 |
| `lnreader` | `lnreader/lnreader` | `dc394e8` | MIT |
| `novela` | `HnDK0/NoveLA` | `6be06f3` | GPLv3 |
| `mihon` | `mihonapp/mihon` | `e588e04` | Apache-2.0 |
| `wenku8x` | `zsakvo/wenku8x` | `57c6312` | GPLv3 |
| IReader | `IReaderorg/IReader` | 下载未完成 | 待补 |

## 1. Legado：分页/排版最值得抄思路

关键文件：
- `app/.../page/entities/TextPage.kt`、`TextLine.kt`、`TextChar.kt`
- `app/.../page/provider/ChapterProvider.kt`、`TextPageFactory.kt`、`ZhLayout.kt`
- `app/.../page/delegate/{Horizontal,Slide,Scroll,Simulation}PageDelegate.kt`
- `app/.../page/PageView.kt`、`ContentTextView.kt`

值得学：
- **页不是一段字符串，而是 TextLine/TextChar 的坐标模型**：每行有 `lineTop/lineBase/lineBottom`，每个字有 `start/end` 像素坐标。这样换行、双栏、图片、TTS 高亮、仿真翻页都能共用一套页数据。
- **中文标点断行单独处理**：`ZhLayout.kt` 继承 `Layout`，处理“行首禁则/行尾禁则”，压缩连续标点；`StaticLayout` 对中文标点不符合中文习惯。我们现在的 `StaticLayoutPaginator` 是简单版，后续值得补这一层。
- **`ChapterProvider` 把标题/正文/图片/段距/缩进一起排版**，`TextPageFactory` 负责上一页/下一页/跨章；比我们“整章一个 StaticLayout + 字符区间”更完整。
- **翻页动画是 delegate 插件**：横向、滑动、滚动、仿真各自实现，页面数据不变。我们 P0 先 `HorizontalPager` 够用，后续加仿真/滚动不用重写分页核心。
- **阅读菜单/主题/字体/行距/段距/页边距/TTS 朗读**都在 `config/` 下，可对照我们的设置 schema。

## 2. NoveLA：翻译阅读/TTS 最值得抄产品形态

关键文件：
- `features/reader/.../domain/ReaderItem.kt`、`ReaderItemAdapter.kt`
- `features/reader/.../features/ReaderChaptersLoader.kt`
- `features/reader/.../features/ReaderLiveTranslation.kt`
- `features/reader/.../features/ReaderTextToSpeech.kt`
- `data/.../DownloadManager.kt`（`translateMode`、缓存/重试）
- `core/.../appPreferences/AppPreferences.kt`（阅读/翻译设置）

值得学：
- **段落级双语模型**：`ReaderItem.Text` 同时有 `text`、`textTranslated`、`textToDisplay`；适配器支持“只显示译文”“译文主/原文副（0.85 字号）”“原文/译文顺序切换”。这正好对应我们的“日文隐藏/对照”。
- **TTS 逐段高亮**：当前朗读项用 spans 标色；TTS 状态和阅读位置绑定。
- **在线翻译更适合按可见段落批量**：`ReaderLiveTranslation` 按可见/批次翻译，`DownloadManager` 在 `translateMode` 下只处理已缓存但未翻译的章节；对 A′ 的“单章最小闭环”有参考价值。
- **设置分层**：全局/插件/书籍三级翻译开关和 provider 解析，避免“开了翻译但没生效”的假状态。

## 3. LNReader：书源插件契约

关键文件：
- `src/plugins/types/index.ts`
- `src/services/plugin/fetch.ts`
- `src/plugins/pluginManager.ts`

值得学：
- 插件只暴露 `popularNovels / parseNovel / parseChapter / searchNovels` 等纯函数；UI/数据库/缓存不依赖具体站点。
- 章节列表用 `chapters: ChapterItem[]`，正文按 `chapterPath` 单独拉；适合“先目录、后按需取正文”。
- 插件可带 `pluginSettings`（Text/Switch/Select/CheckboxGroup），设置 schema 由插件声明。
- 我们 v1 不做源站聚合，但未来接 Kakuyomu/成为小说家吧时，可照这个边界设计 `SourceAdapter`，不要像旧 `lnserve` 那样把抓取/翻译/UI 揉在一起。

## 4. Wenku8x：Flutter 单源阅读器

关键文件：
- `lib/screen/reader/scroll_reader.dart`
- `lib/screen/reader/reader_provider.dart`
- `lib/screen/reader/menu_bars/*`
- `lib/screen/reader/themes/*`

值得学：
- `ReaderConfig` 把横向/纵向/仿真/音量键/全屏/常亮做成配置；主题是独立对象（纸/夜/纯黑等）。
- `ScrollReader` 在接近末尾时 `loadNext()` 预取下一章；我们的 A′/B 可以按“距章末 N 页/段预取”实现。
- 目录/主题/字号/进度是独立菜单栏，不塞进阅读页主体；我们的 `ReaderScreen` 现在只有 A-/A+ 和页码，后续可拆。

## 5. Mihon：扩展/书库模型，阅读器参考价值低

- 漫画为主，`reader` 的 page chrome/viewer 逻辑可看，但我们的文字分页和它不同。
- 扩展仓库、书库更新、备份/恢复的边界值得对照；v1 不做源站聚合，暂不深入。

## 对我们的直接映射

- **P0-4b 已有**：`HorizontalPager` + 整章 `StaticLayout` 按 `top/bottom` 裁剪 + A-/A+ + 页码。
- **下一步可加（不阻塞 A′）**：
  1. 把 `PageSlice` 升级成 `TextPage/TextLine` 级别，或至少补 CJK 标点断行（参考 `ZhLayout`）。
  2. 日文隐藏/对照：按 NoveLA 的 `text`/`textTranslated` 段落模型做，不要只做整章开关。
  3. 预取下一章：参考 Wenku8x 的“接近末尾 loadNext”，但翻译仍走 A′ 的单章闭环。
- **A′ 翻译**：优先参考 NoveLA 的 `ReaderLiveTranslation`/`DownloadManager` 的批量、缓存、状态机边界；不要照搬 GPL 代码。
- **未来书源**：参考 LNReader 的 `Plugin` 纯函数契约；v1 不实现。

## 待补

- IReader 仓库下载未完成（codeload 超时/zip 损坏），网络好时再拉；它是 Kotlin/Compose，优先级低于 Legado/NoveLA。
- 还没逐行读 Mihon/Wenku8x；先记录入口，等 A′/B 需要时再深入。
