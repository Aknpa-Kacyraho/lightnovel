# Android 现状审计与 A′ v1 规划

- 审计日期：2026-10-28
- 范围：`android/` 全工程 + `docs/ADR-000-P0.md`、`docs/REFERENCE-NOTES.md`；
  旧 Python `lntrans` 只作为行为 oracle 对照，不作为运行时依赖。
- 约束：只读审计；未联网、未跑 adb、未改任何源码。文中“推断/未验证”均已标注。

## 0. 结论摘要

- 工程能支撑 A′，但当前是“P0 垂直切片”：没有 App 容器、Repository、导航、设置、
  数据根和翻译层；`MainActivity` 直接渲染 `SampleText`（`MainActivity.kt:25-29`）。
- 最该先补的不是页面，而是三条 seam：`ContentStore`（路径/原子写）、
  `LibraryRepository`（Room 事务/Flow）、`ChapterTranslator`（单章管线）。
- 阅读器当前把“分页、绘制、Compose 状态、示例数据”揉在一个文件里
  （`ReaderScreen.kt:87-145`），多章/预取/对照会迫使重写；应先抽 `Paginator` 端口。
- Room 是运行时真相，但导入的 4 次 upsert 没有事务（`BackupImportService.kt:108-111`），
  文件提交与 DB 写入也没有统一编排；这是数据风险第一优先。
- 翻译必须复用 Python 的“对白数、引号、不可翻段、partial、失败不落盘”语义；
  A′ 只砍调度/后台，不砍校验（见 §3）。
- 当前 `allowBackup=false`（`AndroidManifest.xml:7`），卸载必丢数据；ADR-007 的
  “首次导出 + 备份时间 + 提醒”尚未实现。

## 1. 模块/包结构

### 1.1 现状

| 包 | 主要文件 | 职责 | 问题 |
| --- | --- | --- | --- |
| `data/backup` | `BackupManifest.kt`、`BackupVerifier.kt`、`BackupArchive.kt` | 备份格式/校验/zip 读取 | 只接受 `Path`；无 `ArchiveSource` 抽象 |
| `data/catalog` | `CatalogAdapter.kt`、`CatalogModels.kt` | v5/legacy `library.json` 适配 | `legacyJson` 是重新序列化（`CatalogAdapter.kt:177`） |
| `data/import` | `ImportPlanner`、`ChapterPlanner`、`ReadStatePlanner`、`BackupExtractor`、`LibraryCommitter`、`BackupImportService` | 计划、解压、提交、写库 | zip 路径解析重复 3 处；无事务；无进度/取消 |
| `data/local` | `Entities.kt`、`LibraryDao.kt`、`LightnovelDatabase.kt` | Room | 无迁移、无外键、无 `Flow`、无 `withTransaction` |
| `reader` | `StaticLayoutPaginator`、`ReaderPageView`、`ReaderScreen`、`SampleText` | 分页与示例阅读页 | UI/引擎/数据耦合；整章单 layout；无章节模型 |
| `ui/theme` | `Theme.kt` | Material3 主题 | 无阅读主题/字号/纸张色 |

### 1.2 耦合点（按优先级）

1. `BackupImportService.plan()` 同时做校验、读 zip、解析 catalog、plan、read state
   （`BackupImportService.kt:33-56`），无法对 SAF/流式输入复用，也无法注入失败做测试。
2. `ImportPlanner.dirsFrom()` 自己解析 `novels/<dir>/...`（`ImportPlanner.kt:181-190`），
   `ChapterPlanner` 再解析一遍（`ChapterPlanner.kt:19-32`），`ImportPlanner` 又解析
   `source-` 前缀；应统一成 `ArchiveIndex`。
3. `LibraryCommitter` 直接使用 `java.nio.file` 与 `dataRoot/novels|legacy` 约定
   （`LibraryCommitter.kt:18-71`）；SAF 的 `content://` 无法直接变成 `Path`。
4. `data.import` 直接依赖 `data.catalog`（`ImportPlanner.kt:3-6`、
   `ReadStatePlanner.kt:3`）；catalog 是“迁移期适配器”，不应成为运行时依赖。
5. `ReaderScreen` 直接 `new TextPaint/StaticLayout`、直接持有分页结果和页码状态
   （`ReaderScreen.kt:92-145`），没有 `ViewModel`/`ReaderRepository` 可替换。
6. Room 实体直接暴露给 UI 的路径尚未建立；一旦页面直接吃 `BookEntity`，
   后续领域模型（章节状态、翻译任务）会污染 DB 层。

### 1.3 建议目标结构

单 `:app` 继续用，但先做**逻辑分包**；等翻译/阅读稳定后再拆 Gradle module。
推荐：`app/`（导航、DI、Application）、`core/model`、`core/storage`、`data/db`、
`data/legacy`、`data/translation`、`feature/library`、`feature/reader`、
`feature/import`、`feature/settings`、`feature/tasks`。

必须抽的接口（Kotlin 伪代码）：

```kotlin
// core/storage：所有路径/原子写只在这里出现
interface ContentStore {
    fun bookDir(bookId: String, storageDir: String): Path
    fun readRaw(bookId: String, idx: Int): String?
    fun readZh(bookId: String, idx: Int): String?
    fun writeZhAtomic(bookId: String, idx: Int, text: String)
    fun readSidecar(bookId: String, idx: Int): ChapterMeta?
    fun writeSidecar(bookId: String, idx: Int, meta: ChapterMeta)
    fun stageBackup(uri: Uri): Path   // SAF 输入边界，内部可复制/流式
}

// data/legacy
interface ArchiveSource { fun entries(): List<ArchiveEntry>; fun open(path: String): InputStream }
interface BackupImporter { suspend fun inspect(uri: Uri): ImportPreview
                           suspend fun apply(preview: ImportPreview, onProgress: (Int, Int) -> Unit): ImportResult }

// data/db
interface LibraryRepository {
    fun observeBooks(filter: ShelfFilter): Flow<List<BookSummary>>
    fun observeChapters(bookId: String): Flow<List<ChapterSummary>>
    suspend fun readState(bookId: String): ReadState
    suspend fun updateProgress(bookId: String, anchor: PageAnchor)
}

// reader
interface Paginator { suspend fun paginate(c: ChapterContent, s: ReaderStyle, v: Viewport): ChapterLayout }
interface ChapterSource { suspend fun load(ref: ChapterRef): ChapterContent; fun prefetch(ref: ChapterRef) }
```

原则：`data.import` 依赖 `core.storage` + `data.db`，不再依赖 `data.catalog`；
catalog 只在 `data.legacy` 内部使用；UI 只依赖 repository/use case。

## 2. 阅读器引擎

### 2.1 当前边界

- `StaticLayoutPaginator` 接收整章 `CharSequence`，自己 build `StaticLayout`，
  以 `BREAK_STRATEGY_SIMPLE` + 无 hyphenation 切页（`StaticLayoutPaginator.kt:36-43`）。
- `PageSlice` 同时存字符区间与像素 `top/bottom`（`:8-13`）；切页算法按行底累加
  （`:48-77`）。
- `ReaderPageView` 保存整章 `StaticLayout`，用 `-slice.top` 平移后整块绘制
  （`ReaderPageView.kt:18-26`）；每页共享同一 layout。
- `ReaderScreen` 在组合期 `remember` 中建 paint/layout/pages（`ReaderScreen.kt:98-111`），
  字号变化重建；页数变化只在当前页越界时回到第 0 页（`:116-120`）。
- 页码浮层直接盖在内容底部（`:138-145`），高度预算没有扣掉它，长段最后一行可能被挡。

### 2.2 问题与升级约束

1. **主线程分页**：长章（10 万字+）`StaticLayout` 构建与切页都在组合线程；A′ 必须
   移到单线程 `Dispatcher`，UI 显示“重排中”，保留锚点。
2. **整章单 layout**：无法按段隐藏日文/显示对照，因为字符区间与段落不是一一对应；
   翻译缺失段也无法局部回退。
3. **无锚点**：字号/宽度/主题变化后按页码恢复会跳到别处；必须按
   `(chapterIdx, blockIdx, charInBlock)` 恢复。
4. **无多章/预取**：`HorizontalPager` 只知道单章页数；章末没有“下一章”数据源。
5. **CJK 断行未定制**：API 36 的 `StaticLayout` 会做基础 CJK 断行，但行首/行尾禁则、
   连续标点压缩、日式引号悬挂未验证；ADR/REFERENCE-NOTES 已指出需补这一层
   （`ADR-000-P0.md:57`、`REFERENCE-NOTES.md:27`）。先做 `CjkBreakPolicy` 可插拔，
   用真实语料回归，不要直接抄 GPL 的 `ZhLayout`。
6. **绘制范围**：`ReaderPageView` 只按 view 高度裁剪，未按 `slice.bottom` 二次裁剪；
   最后一行超高时会溢到页脚。

### 2.3 目标模型与接口

```kotlin
data class ReaderStyle(
    val fontSizeSp: Float = 18f, val lineHeight: Float = 1.45f,
    val font: ReaderFont = Serif, val theme: ReaderTheme = Paper,
    val margin: InsetsDp = InsetsDp(16), val paragraphGapDp: Float = 8f,
    val showJapanese: Boolean = true, val translationMode: TranslationMode = Bilingual,
)

sealed interface Block {
    data class Para(val ja: String, val zh: String?) : Block
    data object Blank : Block
}
data class ChapterContent(val ref: ChapterRef, val title: String, val blocks: List<Block>)
data class PageAnchor(val block: Int, val charInBlock: Int)
data class TextLine(val start: Int, val end: Int, val top: Int, val baseline: Int, val bottom: Int)
data class TextPage(
    val chapter: ChapterRef, val pageInChapter: Int,
    val start: PageAnchor, val end: PageAnchor,
    val lines: List<TextLine>, val top: Int, val bottom: Int,
)
data class ChapterLayout(val pages: List<TextPage>, val styleHash: String, val viewport: Viewport)

interface Paginator {
    suspend fun paginate(content: ChapterContent, style: ReaderStyle, viewport: Viewport): ChapterLayout
}
interface ReaderEngine {                     // 多章窗口 + 预取
    fun window(current: ChapterRef, radius: Int = 1): Flow<ChapterContent>
    suspend fun pageAt(anchor: PageAnchor): Int
    suspend fun anchorOf(chapter: ChapterRef, page: Int): PageAnchor
}
```

### 2.4 升级路径

- **第 1 步（A′ 必须）**：把 `PageSlice` 换成 `TextPage`/`PageAnchor`；保持
  “整章单 layout”渲染 mono 模式，先解决主线程、锚点、页脚预算。
- **第 2 步（A′ 可选）**：双语模式改为“按 Block 排版、按行高累加”，每个 Block
  单独 layout；日文隐藏只是过滤 Block，不重建整章字符映射。
- **第 3 步（B）**：`ChapterWindow` 预取下一章（距章末 N 页触发），翻页跨章时把
  新章 pages 追加到 pager；`HorizontalPager` 的 `pageCount` 来自合并后的 page list。
- **重排**：`ReaderStyle` 变更加 150–300ms debounce；后台算完再原子替换 pages，
  用 anchor 定位；缓存 key = `(chapterId, styleHash, viewport)`，最多保留 2–3 章。
- **绘制**：`ReaderPageView` 改为 `bind(layoutHandle, page)`，增加 `slice.bottom`
  裁剪与页脚 inset；未来高亮/TTS 用 `TextLine` 坐标，不改分页核心。

## 3. A′ 翻译 pipeline

### 3.1 范围

只做“当前章 → 单次用户触发 → 分块请求 → 校验 → 边车 + 正文原子写 → 阅读页刷新”。
不做调度、队列、后台服务、自动翻译、预算刹车、多角色兜底/校对（ADR-002）。
但**函数级行为**必须与 Python 对齐，否则会出现“看着译完、实际漏对白”的假完成。

### 3.2 组件边界

```kotlin
interface TranslationClient { suspend fun complete(req: ChatRequest): ChatResult }
data class ChatRequest(val system: String, val user: String, val model: String,
                       val temperature: Double = 0.3, val maxTokens: Int = 32000)
data class ChatResult(val text: String, val tokensIn: Int, val tokensOut: Int, val model: String)

interface ChapterTranslator {
    suspend fun translate(chapter: ChapterContent, cfg: TranslationConfig,
                          onProgress: (ChunkProgress) -> Unit): TranslationOutcome
}
sealed interface TranslationOutcome {
    data class Complete(val text: String, val meta: ChapterMeta) : TranslationOutcome
    data class Partial(val text: String, val meta: ChapterMeta) : TranslationOutcome
    data class Failed(val reason: String, val retryable: Boolean) : TranslationOutcome
}
interface TranslationStore {                 // 只碰文件，不碰 Compose
    fun loadChunkCache(bookId: String, idx: Int, rawSha: String): ChunkCache?
    fun saveChunkCache(bookId: String, idx: Int, rawSha: String, cache: ChunkCache)
    fun loadSidecar(bookId: String, idx: Int): ChapterMeta?
    fun commit(bookId: String, idx: Int, text: String, meta: ChapterMeta)
}
```

- `DeepSeekClient`：OkHttp 已在依赖里（`app/build.gradle.kts:90`）；端点
  `https://api.deepseek.com/chat/completions`，默认模型 `deepseek-flash`。
  `max_tokens` 至少 32000（Python 实测思考也计入 completion，`lntrans.py:987-995`）。
- key 只存设置层（建议 EncryptedSharedPreferences/Keystore），不进日志、不进备份。
- 单章编排：`splitParagraphs → hasTranslatable 过滤 → 按 6000 字在段落边界切块 →
  顺序请求 → 每块校验 → 失败重试 ≤3 / 二分（深度 ≤4）→ 合并 → 去重 → 残留假名统计 →
  写边车 → 写正文 → Room 更新状态/用量`。
- 失败语义：逐段模式**分段失败不落盘、不缓存、不算已译**；整章模式可“收下以中文为主
  的一版 + 原文回填 + partial”，失败块不缓存（Python `:2218-2287`）。两种都不得冒充
  `complete`，reader 必须显示“未译全”。

### 3.3 必须复用的 Python 行为

| 行为 | Python 出处 | Kotlin 要求 | A′ |
| --- | --- | --- | --- |
| 不可翻段穿透：分隔线/纯符号/纯数字/颜文字不送模型、不计未译 | `lntrans.py:1405-1422`、`:1895-1899` | `hasTranslatable` 先过滤，命中段原样回填 | 必须 |
| 对白数兜底：原文开引号数 > 译文则重试，并点名段落 | `lntrans.py:1297-1319`、`:2064-2094` | 段落级 `dialogueCount`，整章模式数 `「『“` 总数 | 必须 |
| 引号只对齐不增删：序列一致才换字形，否则整段不动 | `lntrans.py:1280-1330`、`:2096-2100` | `alignQuotesWithSource(zh, ja)`，禁止“统一成「」” | 必须 |
| 中文检测 + 回抄检测：假名占比 ≥15% 或 ≥8 且 >5% 判非中文；去空白后与原文全等判回抄 | `lntrans.py:1239-1277`、`:2017-2039` | 同一阈值；回抄直接重试 | 必须 |
| 段落数/编号校验 + 重试 + 二分 | `lntrans.py:1879-2131` | 编号必须齐全；缺号重试，连续失败二分 | 必须 |
| DeepSeek 整章 6000 字上限、单次 32000 max_tokens | `lntrans.py:93-94`、`:987-995` | 段落边界切块；不要按 2400 本地模型上限 | 必须 |
| partial 语义：`status=partial` 时 `incomplete_paragraphs` 非空 | `lncontracts.py:128-174`、`contracts/chapter-meta-v1.schema.json` | 复用 schema 字段名，reader 可见 | 必须 |
| 边车先写、正文后替换；hash 不匹配视为不可用 | `lntrans.py:2307-2332`、`lncontracts.py:177-199` | `source_sha256`/`content_sha256` 必须校验 | 必须 |
| 失败/缺号不缓存、不冒充已译 | `lntrans.py:2218-2245` | chunk cache 只在完整时写 | 必须 |
| 块缓存 key 含段范围 + 原文 sha | `lntrans.py:2153-2165`、`:2189-2245` | `(a-b, rawSha)`，原文变更整章失效 | 必须 |
| 配置 hash：源 sha + provider/model + prompt 版本 + 术语/人物/风格修订 | `lncontracts.py:103-125` | 存边车；配置变只提示“可能过时”，不判不可读 | 建议 |
| 成本/用量：tokens in/out、估算 CNY；CJK 约 1 token/字 | `lnmodels.py:311-344` | UI 显示“估算 ¥x.xxxx / 实际 token” | 必须 |
| 翻译 prompt 的角色声音/引号/不漏译规则 | `lntrans.py:712-767`、`:912-929` | 先移植精简版，保留“每行对白都译” | 必须 |

### 3.4 与阅读器/数据库的边界

- `ChapterTranslator` 只返回 `TranslationOutcome`，不直接改 Compose 状态；
  ViewModel 收到 `Complete/Partial` 后刷新 `ChapterContent`（从 `ContentStore` 重读）。
- 写入顺序：`sidecar` → `正文` → `Room`（状态/token/cost/updatedAt）。
  Room 失败不回滚文件（文件是内容真相），下次启动以边车为准修复 Room。
- Reader 只观察 `LibraryRepository.observeChapter()`；不要在 Composable 里发请求。
- `books.legacy_json`/catalog 不参与翻译；术语/前情 A′ 暂不做，但 prompt 版本要写死，
  为 B 的角色卡/术语表留字段。

## 4. 数据/迁移/备份

### 4.1 真相归属（建议明确写进 ADR）

| 内容 | 真相 | 说明 |
| --- | --- | --- |
| 书架/阅读进度/章节状态/用量 | Room | 运行时查询与 UI 状态 |
| 章正文/原文/边车/chunk cache | 书目录文件 | 与 Python 备份格式互通；原子写 |
| catalog/aliases/legacy 状态 | `legacy_json` + 导入结果 | 只做导入/导出适配，不参与运行时 |
| 备份 zip / EPUB | SAF 外部文件 | 用户可见、可迁移；不含 key |

### 4.2 当前缺口

- **无 App 容器**：全工程没有 `Room.databaseBuilder`、`filesDir`、DataStore 使用
  （grep 无匹配）；`LightnovelDatabase` 只在测试里建（`LibraryDaoTest.kt:25-30`）。
- **无事务**：`BackupImportService.apply()` 四次独立 upsert（`:108-111`），
  中途崩溃会留下“有书无章节/有章节无状态”。改为 `withTransaction`，并加导入批次表。
- **无进度锚点**：`ReadStateEntity.progressIdx` 只有章号（`Entities.kt:35`）；
  需要 `progress_block`/`progress_char`/`progress_updated_at`，否则重排必丢位置。
- **章节状态太粗**：`ChapterPlanner` 只看文件存在，`zh` 存在即 `translated`
  （`ChapterPlanner.kt:43-48`）；不读 `.meta.json` 的 `complete/partial`/hash
  （ADR 未决 `ADR-000-P0.md:84`）。必须按边车派生 `ChapterState`。
- **标题/集数丢失**：`ChapterPlanner` 不读 `novels/<dir>/meta.json`，`title/titleZh`
  恒为 null（`BackupImportService.kt:97-98`）；`episodes` 只信 catalog。
  真实本地 2 本若不在 catalog，标题会退化成目录名（`ImportPlanner.kt:158-178`）。
- **legacy_json 非原文**：`rawJson = row.toString()`（`CatalogAdapter.kt:177`），
  未知字段语义保留但字节/键序/数字格式丢失；若要求“未知字段原样保留”，
  应在解析前保存原始对象字符串（或按 key 存原始片段）。
- **无唯一业务键**：只对 `slug` 唯一（`Entities.kt:8-11`）；同一 `(source, source_id)`
  以不同 `id` 再导入会生成重复书。建议加非空 `(source, source_id)` 唯一索引，
  local 书用 `local-<hash>` 兜底。
- **无迁移**：DB `version=1`（`LightnovelDatabase.kt:6-15`）、schema 已导出
  （`app/schemas/.../1.json`），但没有任何 `Migration`/迁移测试。A′ 加字段前先定
  v1→v2 迁移与回滚策略。
- **无导入编排**：`BackupExtractor` 解压到 staging、`LibraryCommitter` 搬目录，
  但生产代码没有“extract → commit → Room apply”的协调器；失败时 staging 不清理
  （`BackupExtractor.kt:16-65`）。需要 `ImportCoordinator` + 临时目录 GC。
- **合并策略缺失**：Room `upsert` 会用备份值覆盖本地进度/收藏（`:78-89`）；
  恢复应“取更新/取更大进度/收藏 OR”，并记录冲突，而不是无脑覆盖。
- **SAF 不可用**：`BackupVerifier`/`BackupExtractor` 只吃 `java.nio.file.Path`；
  `content://` 必须先复制到 cache（或改 `ZipInputStream` 顺序流 + 先读 manifest）。
  1GB 备份复制会翻倍占用，需容量预检与进度。ADR 的“verify-first”保留。
- **导出缺失**：ADR-006 的 `Exporter`（EPUB/backup/future-lan）尚未建；
  `lnbackup` 的 manifest format 1 可复用，但需 Kotlin 侧 writer + SAF `createDocument`。
  备份必须排除 API key、日志、chunk cache 中的敏感内容（如用户决定）。
- **卸载丢数据**：`allowBackup=false`（`AndroidManifest.xml:7`）意味着系统备份也不可用；
  ADR-007 的首次导入强制导出、`last_backup_at`、周期提醒都未实现。
- **归档位置**：`LibraryCommitter` 把 `data/`、`lnfinder/` 移到
  `legacy/<backupId>/`（`:60-70`），但 Android 上该目录在 app 私有区，用户不可见；
  导出时应单独列出“legacy 归档”。

## 5. UI 屏幕地图

### 5.1 现状

- 单 `MainActivity` → `ReaderScreen(title="轻小说", subtitle="分页示例",
  text=SampleText.long)`（`MainActivity.kt:15-32`）。
- 没有 Navigation、书架、导入、设置、任务页；Reader 只有 A-/A+ 与页码
  （`ReaderScreen.kt:57-85`、`:138-145`）。
- 依赖里没有 `navigation-compose`（`app/build.gradle.kts:71-107`）。

### 5.2 v1 最小屏幕集（4 路由 + 1 面板）

| 路由 | 内容 | 必做理由 |
| --- | --- | --- |
| `library` | 书架网格/列表：封面占位、中文标题、作者、进度、翻译状态；筛选 在读/想读/读完；空态“导入备份” | 用户入口 |
| `chapters/{bookId}` | 章列表：标题、`raw/partial/complete/failed` 徽标、最近阅读高亮 | 选章翻译必须 |
| `reader/{bookId}/{idx}` | 分页阅读、页码、字号/主题/日文开关、当前章翻译按钮/进度、章末上一章/下一章 | A′ 核心 |
| `settings` | DeepSeek key/模型/端点/价格、阅读默认样式、备份导出、关于 | key 与备份入口 |
| `import` | SAF 选择 zip → 校验进度 → 预览（书/章/孤儿/冲突）→ 确认 → 结果 | 迁移闭环 |
| `TaskSheet`（阅读页底部） | 当前章：分块 x/y、tokens、估算费用、失败原因/重试/取消 | A′ 不建后台任务页，先做面板 |

- 导航：`NavHost` + `Scaffold`；路由参数只用 `bookId`/`idx`，不传大对象。
- 状态：每屏一个 `ViewModel` + `StateFlow<UiState>`；一次性事件用 `Channel`。
- 设置项最小集：`apiKey`、`model=deepseek-flash`、`baseUrl`、`priceIn/priceOut`、
  `readerStyle`、`lastBackupAt`、`autoTranslate=false`（A′ 固定 false）。
- 阅读页明确三态：`raw`（只有日文）、`translating`（显示日文 + 进度）、
  `zh/partial`（显示译文；partial 段回填日文并标徽标）。

## 6. 性能/测试

### 6.1 已测事实与未测项

- 真机 Redmi Turbo 3：debug 冷启动 920/666/621ms，中位 666ms；无崩溃
  （`ADR-000-P0.md:76-79`、`adb-coldstart.log`）。这是 debug + 示例页，release/R8
  未配置（`app/build.gradle.kts:24-31`），不能当 v1 性能基线。
- 真实字体度量下页数随字号/宽度变化：36px/720×1200=10 页，72px=32 页，
  900×1200=14 页，360×1200=30 页（`PaginatorDeviceTest.kt:25-46`、
  `paginator-device-2.log`）。
- **120Hz 未测**：Compose instrumentation 在 HyperOS 被“Abort background activity
  starts”拦截（`ADR-000-P0.md:79`、`SkipOnMiuiRule.kt:9-25`）。
- **分页性能未测**：当前在组合线程建 `StaticLayout`（`ReaderScreen.kt:106-111`），
  长章必卡；需 Macrobenchmark/Perfetto 量化，不能只凭体感。
- **Robolectric 不模拟真实字体度量**（`ADR-000-P0.md:57`），只能测不变量，
  页数/断行 golden 必须在真机或 AOSP 模拟器。

### 6.2 HyperOS 限制（写进测试计划）

- instrumentation 启动 Activity 被拦；Compose UI 测试在 HyperOS 上只能 skip/手动。
- 后台活动/自启动/省电策略可能杀进程；A′ 不做后台翻译，正好规避。
- SAF 选择器、文件权限、卸载重装行为需真机演练；模拟器不能替代。
- 建议保留 `SkipOnMiuiRule`，另建 AOSP API 36 模拟器跑 UI/迁移；真机只跑
  安装、冷启动、分页、SAF、120Hz 手测。

### 6.3 测试金字塔

| 层 | 工具 | 覆盖 | 现状/要补 |
| --- | --- | --- | --- |
| JVM 单测（~65%） | JUnit4 + kotlinx-coroutines-test | catalog/planner/read state、翻译校验、chunker、边车契约、成本、分页数学（fake metrics） | 已有 catalog/import/verifier；缺翻译/边车/成本 |
| Robolectric（~20%） | Robolectric 4.15 + Room in-memory + MockWebServer | DAO/事务、迁移、Settings、ViewModel、导入编排、HTTP 错误映射 | 已有 DAO/分页；缺迁移/翻译 |
| 真机 instrumentation（~15%） | AndroidJUnit4 + Compose UI Test | StaticLayout golden、Reader 语义、SAF、迁移、冷启动 | 已有 Paginator；UI 被 HyperOS 拦 |
| 手动/基准 | Macrobenchmark、`dumpsys gfxinfo`、Perfetto | 冷启动、120Hz 翻页、长章内存、卸载重装 | 全缺 |

- 必加测试：`ChapterPlanner` 读边车 `partial`；`BackupImportService.apply` 事务回滚；
  DB v1→v2 migration；`QuoteAligner`/`DialogueGuard`/`ChineseDetector` 与 Python
  golden 对照；`DeepSeekClient` 429/5xx/超时/截断；`ContentStore` 原子写中断；
  `lastBackupAt` 提醒；SAF 导入 0 字节/超大/错误 zip。
- CI：`compileall` 不适用于 Android；需 Gradle `testDebugUnitTest` + `lintDebug`，
  instrumentation 用 AOSP emulator（可选、耗时长）。

## 7. 未来两周任务清单（按天/优先级）

优先级：P0 = A′ 闭环阻塞；P1 = 质量/可维护；P2 = 可延后。`[手机]` = 依赖真机。

| 天 | 任务 | 优先级 | 依赖 |
| --- | --- | --- | --- |
| D1 | 写 ADR-008：模块边界、数据根、真相归属、DB v2 草案；加 Application/AppContainer（手写 DI），接 `filesDir`/DataStore | P0 | 无 |
| D2 | `ContentStore` + `BookPaths`；把 `ChapterPlanner`/`ImportPlanner` 的路径解析收敛到 `ArchiveIndex`；`ImportCoordinator`（extract→commit→Room 事务） | P0 | 无 |
| D3 | DB v2：`progress_anchor`、`chapter_state`、`translation_task`/`usage_ledger`；写 Migration + migration test；`LibraryRepository`/Flow | P0 | 无 |
| D4 | `LibraryScreen` + `ChapterListScreen` 接真实 Room；空态/筛选/状态徽标；Navigation 骨架 | P0 | 无 |
| D5 | `ReaderViewModel` + 章节加载；字号/主题/日文开关；页脚预算；锚点保存/恢复；后台分页 | P0 | 无 |
| D6 | 阅读器引擎 v1：`Block/TextPage/PageAnchor`，mono 先跑通；双语按 Block；下一章预取（只读） | P1 | 无 |
| D7 | `DeepSeekClient`（OkHttp/serialization）+ Settings key 存储 + MockWebServer 测试；429/5xx/超时/截断 | P0 | 无（key 可后填） |
| D8 | 翻译校验层：`hasTranslatable`、`dialogueCount`、`alignQuotes`、`detectChinese`、`echo`、chunker；Python golden 对照 | P0 | 无 |
| D9 | 单章编排 + chunk cache + 边车（复用 `chapter-meta-v1` 字段）+ 原子写 + Room 状态/成本 | P0 | 无 |
| D10 | 阅读页翻译面板：进度/取消/失败重试/partial 徽标/费用；译完就地刷新 | P0 | 无 |
| D11 | 导入 UI：SAF 选择 → 校验 → 预览 → 应用 → 结果；staging 清理/容量预检 | P0 | `[手机]` SAF 实测 |
| D12 | 导出 v1：backup（兼容 `lnbackup` format 1）+ `last_backup_at` + 首次导入向导/卸载提醒 | P0 | `[手机]` 保存到下载目录 |
| D13 | 真机冒烟：安装、冷启动、19 本真实备份、长章分页、SAF、120Hz/HyperOS 手测；记录页数与帧时间 | P0 | `[手机]` |
| D14 | 回归：补迁移/事务/翻译测试；lint；release 配置（R8/arm64/签名）评估；更新 ADR 与本文 | P1 | `[手机]` 安装验证 |

- 可并行的无手机任务：D1–D10 大部分、D14 的单测/lint。
- 必须真机：D11 SAF、D12 下载目录、D13 全部、D14 安装。
- 真实 19 本备份 fixture 属于个人数据，**不要提交**；放 `.tmp/fixtures` 或
  `LN_TEST_FIXTURE_ZIP` 环境变量（现有 `RealFixtureTest.kt:16-23` 已按此约定）。

## 8. 三个最可能返工的设计风险

### 风险 1：分页模型太浅，双语/预取/标注会推倒重来

- 症状：UI 直接依赖 `PageSlice` 字符区间 + 单章 `StaticLayout`；一旦要“段落级日文隐藏/
  对照/TTS 高亮”，字符区间与段落对不上，只能重写。
- 缓解：现在就引入 `Block/TextPage/PageAnchor/Paginator`（§2.3），保留
  `StaticLayoutPaginator` 作为 `MonoPaginator` 实现；UI 只依赖 `ChapterLayout`；
  先写 3 个 golden 测试（纯中文、日文混排、长对白）锁页数与锚点。

### 风险 2：Room 与文件/边车双真相，导入无事务会“半本书”

- 症状：`LibraryCommitter` 已搬文件、`BackupImportService.apply` 四次 upsert 中途失败
  （`:108-111`），或恢复覆盖了更新的本地进度；下次启动书架/章节对不上。
- 缓解：明确“文件=内容真相、Room=查询/状态真相”；`ImportCoordinator` 用
  `withTransaction` + 导入批次表；恢复合并规则（进度取 max、收藏 OR、时间取新）；
  边车 hash 决定内容可用性；启动时做一次 `reconcile(Room, 文件)` 并只记日志/修复，
  不静默删。

### 风险 3：翻译契约漂移，产出“假完整”或与 Python 备份不兼容

- 症状：只做“段落数 + 中文”校验，漏掉“多行对白只译第一行”（Python 实测 152 段）；
  或边车字段/路径与 `chapters/NNNN.meta.json` 不一致，备份回 Python 后不可读。
- 缓解：直接复用 `chapter-meta-v1.schema.json` 与 `lncontracts` 的校验语义；
  把 §3.3 的校验做成独立纯函数并用 Python golden 对照；失败/缺号绝不写
  `complete`、绝不缓存；UI 必须显示 `partial`；A′ 先不做术语/前情，但保留
  `translation_config_hash`/`prompt_version` 字段，B 阶段可无缝扩展。

## 附：本次审计未做的事

- 未运行 Gradle/测试/adb；未修改源码、未新增依赖。
- 未验证真实 19 本备份、SAF、120Hz、R8/release；这些都在 §7 的真机任务里。
- 旧 Python 只读了翻译/边车相关函数，未审计调度/worker/备份 writer 的完整实现。
