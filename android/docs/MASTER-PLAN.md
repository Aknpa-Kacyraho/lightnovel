# 轻小说 App 集大成方案（v1 A′）

> 输入：`ADR-000-P0.md`、`research/legado-reader.md`、`research/novela-translation-reader.md`、
> `research/source-library.md`、`research/reader-ux.md`、`research/current-audit.md`。
> 参考代码只在 `.tmp/reference/` 只读研究，不直接复制。目标：私有自用、本地优先、能长期维护。

## 0. 一句话方向

**把“能读”做成“读得舒服”，把“能翻”做成“翻得可信”。**
v1 不追求功能数量，先把三条主线做扎实：

1. **阅读器**：段落 → 行 → 页的稳定模型，锚点进度，后台重排，多章窗口。
2. **翻译**：单章 DeepSeek 最小闭环，但对白数/引号/不可翻段/partial 与旧 Python 对齐。
3. **数据**：文件是内容真相、Room 是状态真相；导入/恢复有事务、可回滚、可备份。

## 1. 从参考实现吸收什么

| 来源 | 采用 | 明确不采用 |
| --- | --- | --- |
| Legado | 段落/行/页模型；章内锚点；三章窗口；LayoutConfig/ThemeConfig 分层；翻页控制器 seam | 全局 object；`ZhLayout` 继承 Layout；三份 View+截图 Bitmap；仿真/卷曲 |
| NoveLA | `text + textTranslated + textToDisplay` 段落模型；译文缺失回退原文；章级翻译状态；TTS 只留 seam | 后台 DownloadManager/队列/通知；三层翻译设置；ListView/词级高亮 |
| LNReader | `SourceAdapter` 纯函数契约；目录/正文分离；声明式设置 schema | 远程 JS 动态加载；插件市场；v1 多源搜索 |
| Wenku8x | 三层浮层 Chrome；左/中/右点击区；菜单开时点击只关层；目录高亮；章前预取；固定主题 | Widget 列表当分页数据；6 个 bool 菜单；改字号回章首；章节号当页号 |
| Mihon | 源身份/能力/备份边界；扩展失败原因要可见 | 漫画阅读器；扩展生态 |
| IReader | 源码未拿到，暂不纳入 | — |

## 2. 目标架构（单 `:app`，逻辑分包）

```
app/
  LightnovelApp.kt        Application + AppContainer（手写 DI）
  navigation/             NavHost + 路由
core/
  model/                  Book/Chapter/Reader*/Translation* 领域模型
  storage/                ContentStore、BookPaths、原子写、sidecar
data/
  db/                     Room entities/dao/migrations/repositories
  legacy/                 ArchiveSource/BackupImporter/CatalogAdapter（只在导入导出用）
  translation/            DeepSeekClient、ChapterTranslator、validators、cache
feature/
  library/                LibraryScreen/ViewModel
  chapters/               ChapterListScreen/ViewModel
  reader/                 ReaderRoute/Content/Chrome/Panel/ViewModel/engine
  settings/               SettingsScreen/ViewModel
  import/                 ImportScreen/ViewModel/Coordinator
```

**三条必须先抽的 seam**：

```kotlin
interface ContentStore {
    fun bookDir(bookId: String, storageDir: String): Path
    fun readRaw(bookId: String, idx: Int): String?
    fun readZh(bookId: String, idx: Int): String?
    fun readSidecar(bookId: String, idx: Int): ChapterMeta?
    fun writeZhAtomic(bookId: String, idx: Int, text: String)
    fun writeSidecar(bookId: String, idx: Int, meta: ChapterMeta)
    fun stageBackup(uri: Uri): Path       // SAF 输入边界
}

interface LibraryRepository {
    fun observeBooks(filter: ShelfFilter): Flow<List<BookSummary>>
    fun observeChapters(bookId: String): Flow<List<ChapterSummary>>
    suspend fun readState(bookId: String): ReadState
    suspend fun updateProgress(bookId: String, anchor: ReaderAnchor)
}

interface ChapterTranslator {
    suspend fun translate(chapter: ChapterContent, cfg: TranslationConfig,
                          onProgress: (ChunkProgress) -> Unit): TranslationOutcome
}
```

规则：
- `data.import` 只依赖 `ContentStore` + `LibraryRepository`，不再直接依赖 `data.catalog`。
- UI 只依赖 Repository/UseCase，不直接读 `java.nio.file`，不直接发 HTTP。
- catalog/aliases 只在 `data.legacy` 内部使用；Room 是运行时真相。

## 3. 阅读器引擎（v1 核心）

### 3.1 模型

```kotlin
data class ReaderChapter(val ref: ChapterRef, val title: String, val blocks: List<ReaderBlock>)
sealed interface ReaderBlock {
    data class Paragraph(val id: Int, val raw: String, val zh: String?, val state: BlockState) : ReaderBlock
    data class Image(val id: Int, val path: String) : ReaderBlock
}
data class ReaderAnchor(val chapterId: String, val paragraphId: Int, val charOffset: Int)
data class ReaderLine(val blockId: Int, val start: Int, val end: Int, val top: Int, val baseline: Int, val bottom: Int)
data class ReaderPage(val indexInChapter: Int, val lines: List<ReaderLine>,
                      val start: ReaderAnchor, val end: ReaderAnchor)
data class ReaderLayout(val pages: List<ReaderPage>, val layoutHash: String, val viewport: Viewport)
```

- **页号不是真相**：进度存 `ReaderAnchor`；页码由锚点反算。
- 段落是排版最小单位；后续日文隐藏/对照只是过滤/组合 block，不重建字符映射。
- `LayoutConfig`（字号/行距/段距/边距/字体/缩进）变化才重排；
  `ThemeConfig`（纸白/米黄/护眼/夜间）只重绘。

### 3.2 分页与渲染

- `Paginator` 接口：输入 `ReaderChapter + LayoutConfig + Viewport`，输出 `ReaderLayout`；
  在 `Dispatchers.Default` 单线程执行，UI 显示“重排中”，保留旧页直到新页就绪。
- 先实现 `MonoPaginator`：按段落建 `StaticLayout`，按行高累加切页；保留现有
  `StaticLayoutPaginator` 作为回归基线。
- 绘制用 `ReaderPageView` 绑定 `(layout, page, palette, header, footer)`，
  **按 `page.bottom` 二次裁剪**，页码/页眉画在页内，不再用独立 Text 盖正文。
- CJK 断行：API 33+ 先试 `LineBreakConfig(STRICT/PHRASE)`；低版本回退
  `BREAK_STRATEGY_HIGH_QUALITY`；用中日文 fixture 对比后再决定是否写纯函数断行器。
  **不直接移植 `ZhLayout`**。
- 重排恢复：字号/行距/旋转/译文完成后，按旧 `ReaderAnchor` 找新页并 `scrollToPage`
  （无动画），禁止回第 1 页。
- 多章：内存保留 prev/current/next 三章；距章末 ≤3 页或章首 ≤2 页预读/预排下一章；
  v1 翻页仍用 `HorizontalPager`，跨章时把新章 pages 追加到 page list。

### 3.3 Reader UI

三层，互不挤压：

```
ReaderScreen        // 系统栏/生命周期/常亮/沉浸
├─ ReaderContent    // HorizontalPager，永远占满
│  └─ ReaderPage    // 页眉 + 正文 + 页脚页码
├─ ReaderChrome     // 顶栏（返回/书名/章名）+ 底栏（目录/主题/排版/设置）
└─ ReaderPanel      // 目录/排版/主题详情，单开，贴底栏上方
```

- 点击区：左 30% 上一页、中 40% 开关菜单、右 30% 下一页；菜单开时点正文只关层。
- 返回优先级：Panel → Bars → 退出；保留预测式返回。
- 设置 v1：4 主题、字号 14–30、行距 1.3–2.2、段距 0–24、页边距三档、常亮、沉浸；
  竖滚/音量键/亮度/仿真/双页后置。
- 无障碍：Canvas 页容器必须补 `contentDescription`、`stateDescription` 和
  上一页/下一页/目录自定义动作；`fontScale` 参与分页 key。
- 页脚显示 `章内 x/y`；全书进度用章序/百分比，不要用页号冒充全书进度。

## 4. A′ 翻译管线（单章、无后台）

### 4.1 流程

```
选章 → 读取 raw → 拆段 → hasTranslatable 过滤
→ 按 6000 字/段落边界切块 → 顺序请求（单飞行）
→ 每块校验 → 失败重试 ≤3 / 二分（≤4）
→ 合并 → 残留假名统计 → 边车 → 正文原子写 → Room 状态/用量
```

- 模型默认 `deepseek-flash`（可配）；`max_tokens=32000`；`temperature=0.2`；
  连接 30s / 读 120s；不流式（A′）。
- key 只存 Keystore/EncryptedSharedPreferences；不进日志、不进备份。
- 章节翻译状态：`NONE → TRANSLATING(done/total) → DONE | PARTIAL | FAILED`。
- 退出/切章/手动停止取消 Job；已落库块保留；重进续译。
- 可见段优先可后置；A′ 先按块顺序，保证“整章可解释”。

### 4.2 必须复用的 Python 行为

| 行为 | 说明 |
| --- | --- |
| 不可翻段穿透 | 分隔线/纯符号/纯数字/颜文字不送模型、不计未译 |
| 对白数 | 原文引号对数 > 译文 → 重试并点名段；多行对白不能只译第一行 |
| 引号 | 只在数量与开/闭角色完全一致时换字形；结构不同整段不动 |
| 中文/回抄检测 | 假名比例阈值；去空白后与原文全等判回抄 |
| 编号/段落 | 编号必须齐全；缺号重试；连续失败二分 |
| 分块 | 云端 6000 字，段落边界，带上文尾巴 |
| partial | 失败块留原文，标 `partial` + `incomplete_paragraphs`；绝不冒充 complete |
| 边车 | 先写 sidecar 再换正文；hash 不匹配视为不可用 |
| 缓存 | 失败/缺号不缓存；key 含段范围 + 原文 sha + 配置 hash |
| 成本 | token in/out、估算 CNY；日志只记模型/段数/耗时/用量 |

### 4.3 数据落点

- `ContentStore`：`chapters/NNNN.txt`、`chapters/NNNN.meta.json`、
  `cache/chunks/...`；原子写。
- Room：`chapters.status/model/token_in/token_out/updated_at`；
  新增 `translation_runs`/`usage_ledger`（可选）记录本章状态/费用。
- 真相：**文件=内容，Room=状态**；Room 失败不回滚文件，下次启动按边车修复。
- 不自动预翻译；不后台翻译；A′ 的“翻译本章”只在阅读页手动触发。

## 5. 数据、导入、备份

### 5.1 真相归属

| 内容 | 真相 |
| --- | --- |
| 书架/进度/章节状态/用量 | Room |
| 原文/译文/边车/chunk cache | 书目录文件 |
| catalog/aliases/legacy | `legacy_json` + 导入结果 |
| 备份 zip / EPUB | SAF 外部文件 |

### 5.2 必补

- `LightnovelApp` + `AppContainer`：`filesDir/lightnovel-data`、Room、DataStore、OkHttp。
- Room v2：`progress_anchor`（block/char）、`chapter_state`、唯一 `(source, source_id)`；
  写 v1→v2 migration + migration test。
- `ImportCoordinator`：`inspect → preview → extract → commit → Room withTransaction`；
  staging 清理、容量预检、失败回滚。
- 恢复合并规则：进度取更靠后、收藏 OR、时间取新；不无脑覆盖。
- `ChapterPlanner` 读 `.meta.json` 的 `complete/partial`/hash，不再只看文件存在。
- `Exporter`：backup format 1 + `last_backup_at` + 首次导入强制导出 + 周期提醒；
  导出排除 key/日志/chunk cache 中的敏感内容。
- SAF：`content://` 先复制到 cache 或流式读 manifest；`BackupVerifier` 保留 verify-first。

## 6. 屏幕地图（v1）

| 路由 | 内容 |
| --- | --- |
| `library` | 书架：封面占位、中文标题、作者、进度、翻译状态；筛选；空态“导入备份” |
| `chapters/{bookId}` | 章列表：标题、raw/partial/complete/failed 徽标、最近阅读 |
| `reader/{bookId}/{idx}` | 分页阅读、页眉页脚、字号/主题/日文开关、翻译面板、章末导航 |
| `settings` | DeepSeek key/模型/端点/价格、阅读默认样式、备份导出、关于 |
| `import` | SAF 选 zip → 校验 → 预览（书/章/孤儿/冲突）→ 应用 → 结果 |
| `TaskSheet` | 当前章：分块 x/y、tokens、估算费用、失败原因/重试/取消 |

阅读页三态：`raw`（只有日文）、`translating`（日文 + 进度）、`zh/partial`
（译文；partial 段回填日文并标徽标）。

## 7. 源站扩展（不在 v1）

```kotlin
interface SourceAdapter {
    val id: String
    suspend fun search(query: String, page: Int): SourcePage
    suspend fun book(ref: SourceRef): SourceBook
    suspend fun chapters(ref: SourceRef): List<SourceChapterRef>
    suspend fun chapter(ref: SourceChapterRef): RawChapter
}
```

- v1：零适配器，只留 seam；不做多源搜索/插件市场/动态 JS/Cloudflare 绕过。
- v2：单源手动加书；目录/正文分离；源只填空白元数据；新章不自动翻译。
- v3：多源 + 更新；备份离线可恢复；类型化错误，不在适配器里碰 Room/翻译/UI。

## 8. 路线图

### Week 1（不需要手机）

- D1：`LightnovelApp`/`AppContainer`、数据根、DataStore、Room builder。
- D2：`ContentStore`/`BookPaths`/`ArchiveIndex`；`ImportCoordinator` 事务化。
- D3：Room v2（锚点、章节状态、唯一键）+ migration test；`LibraryRepository` Flow。
- D4：`LibraryScreen` + `ChapterListScreen` + Navigation；空态/筛选/徽标。
- D5：`ReaderViewModel` + 章节加载；后台分页；页脚预算；锚点保存/恢复；主题/字号。
- D6：阅读器引擎 v1（`ReaderBlock/Page/Anchor`，mono 先跑通）+ golden 测试。

### Week 2（不需要手机为主）

- D7：`DeepSeekClient` + Settings key + MockWebServer（401/429/5xx/超时/截断）。
- D8：校验层（不可翻段/对白数/引号/中文/回抄/编号/chunker）+ Python golden。
- D9：单章编排 + chunk cache + 边车 + 原子写 + Room 状态/成本。
- D10：阅读页翻译面板（进度/取消/重试/partial/费用）+ 译后锚点恢复。
- D11：导入 UI（SAF 预览/应用）；D12：Exporter/备份提醒。
- D13：真机冒烟（安装/冷启动/真实 19 本/SAF/120Hz/HyperOS）。
- D14：补迁移/事务/翻译测试、lint、release 配置评估。

## 9. 验收（v1/A′）

1. 导入真实备份后，书架/章列表正确；无孤儿/半本书；重复导入幂等。
2. 打开一章：分页、翻页、页码、目录、返回层级正常；字号/行距/旋转后回到同一段。
3. 点“翻译本章”：有进度/可取消/失败可重试；完成后就地刷新且不丢位置；
   对白数/引号/不可翻段/partial 全部正确；失败不落盘、不冒充已译。
4. 杀进程重进：阅读位置与翻译状态仍在；无 key 不阻塞阅读。
5. 备份导出 + 干净安装恢复；卸载前有明确提醒/备份入口。
6. 真机：冷启动 ≤1.5s（debug 已 666ms 中位）、翻页无卡顿、120Hz 手测通过。

## 10. 不做清单（v1）

TTS 实现、源站抓取/多源搜索、助手、finder、PC LAN、竖滚/仿真/卷曲、双页、
自定义字体/背景图、音量键/亮度/书签/批注、后台翻译/调度/通知、跨设备同步。

## 11. 三个最高风险

1. **分页模型太浅** → 双语/预取/TTS 返工。缓解：先落 `Block/Page/Anchor/Paginator`。
2. **Room 与文件双真相 + 导入无事务** → 半本书。缓解：`ImportCoordinator` +
   `withTransaction` + `reconcile` + 恢复合并规则。
3. **翻译契约漂移** → 假完整/备份不兼容。缓解：复用 `chapter-meta-v1` 字段与 Python
   golden；失败不写 complete、不缓存；UI 显示 partial。
