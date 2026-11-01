# 源站适配与书库边界研究（LNReader / Mihon）

> 只读研究，不引入参考代码（LNReader MIT、Mihon Apache-2.0；仍按 `REFERENCE-NOTES.md` 的约定重写思路，不复制实现）。
> 参考树：`.tmp/reference/lnreader`、`.tmp/reference/mihon`。本文所有行号以当前本地快照为准。

## 0. 结论

1. **书库真相必须在本地**：源站只提供“元数据 + 目录 + 正文”三件事，不能拥有主键、阅读状态或翻译状态。
2. **适配器是纯函数边界**：输入站内引用，输出 DTO；不碰 Room、不碰翻译、不碰 UI、不做全局缓存。
3. **更新 = 目录差异，不是正文变化**：用稳定章节 key 做 diff；消失的章节标记而不是删除，阅读状态按“章节号/标题”尽量继承。
4. **v1 一个适配器都不要写**，只保留 `source/source_id` 字段和未来 seam；v2 单源手动加书；v3 才做多源注册与自动更新。
5. **动态加载/插件市场/Cloudflare 绕过明确不做**：安全、版权、稳定性和维护成本都不划算。

## 1. 关键文件坐标

| 主题 | 路径 | 关键行 |
| --- | --- | --- |
| LNReader 插件契约 | `lnreader/src/plugins/types/index.ts` | `ChapterItem` 56-63；`SourceNovel` 77-85；`Plugin` 118-131；设置 schema 39-47 |
| LNReader 动态加载 | `lnreader/src/plugins/pluginManager.ts` | 白名单依赖 31-43；`Function` 执行 58-64；安装/版本 126-159；仓库拉取 178-195；懒加载 205-222；重载 243-266 |
| LNReader 调用边界 | `lnreader/src/services/plugin/fetch.ts` | `fetchNovel` 20-30；`fetchChapter` 32-39；`resolveUrl` 71-91 |
| LNReader 书库写入口 | `lnreader/src/database/queries/NovelQueries.ts` | 加书 171-252；缓存书 275-288；恢复（会联网）293-351；备份恢复 481-562 |
| LNReader 表结构 | `lnreader/src/database/schema/{novel,chapter}.ts` | `(path, pluginId)` 唯一 novel.ts 32；`(novelId, path)` 唯一 chapter.ts 31 |
| LNReader 章节目录合并 | `lnreader/src/database/queries/ChapterQueries.ts` | `insertChapters` upsert 49-120 |
| LNReader 更新调度 | `lnreader/src/services/updates/{index,LibraryUpdateQueries}.ts` | 按源分组/并发 3 index.ts 24-39、137-157；目录 diff 与下载 LibraryUpdateQueries.ts 80-159；分页目录 211-250 |
| LNReader 更新候选 | `lnreader/src/database/queries/LibraryQueries.ts` | 分类与 smart update 条件 22-32、93-137 |
| LNReader 备份 | `lnreader/src/services/backup/{types,fileSections,options}.ts` | 分区 3-23；插件/下载目录单独打包 12-31；章节 ID 重映射 54-95 |
| Mihon 源接口 | `mihon/source-api/.../source/{Source,CatalogueSource,SourceFactory}.kt` | `Source` 14-106；`getMangaUpdate` 81-86；`CatalogueSource` 14-47；`SourceFactory` 6-12 |
| Mihon HTTP 适配基类 | `mihon/source-api/.../source/online/HttpSource.kt` | `baseUrl` 38；`versionId` 57；ID 生成 69、98-102；相对 URL 429-463 |
| Mihon 源 DTO | `mihon/source-api/.../source/model/{SManga,SChapter,UpdateStrategy}.kt` | `SManga` 8-41；`SChapter` 8-31；`UpdateStrategy` 10-23 |
| Mihon 源注册 | `mihon/domain/.../source/service/SourceManager.kt` | `getOrStub` 8-21；领域 `Source` 3-25 |
| Mihon 扩展模型 | `mihon/domain/.../extension/model/Extension.kt` | `Loaded/NotLoaded` 82-140；拒绝原因 121-139 |
| Mihon 扩展加载 | `mihon/app/.../extension/ExtensionManager.kt` | 签名信任说明 46-52；重载触发 96-116 |
| Mihon 更新合并 | `mihon/app/.../mihon/domain/source/interactor/UpdateMangaFromRemote.kt` | 拉取与同步 66-79；元数据合并策略 89-145 |
| Mihon 章节同步 | `mihon/app/.../eu/kanade/domain/chapter/interactor/SyncChaptersWithSource.kt` | 按 url 去重 67-74；新增/更新 106-147；消失章节 149-154；阅读状态继承 171-220；原子写 223-227 |
| Mihon 书库更新 | `mihon/app/.../data/library/LibraryUpdateWorker.kt` | 跳过规则 192-226；按源分组、并发 5 251-267；单本更新 281-313 |
| Mihon 书库模型 | `mihon/domain/.../library/model/LibraryManga.kt` | 6-25 |
| Mihon 备份 | `mihon/app/.../data/backup/create/{BackupOptions,BackupCreator}.kt` | 分区开关 6-32；gzip+protobuf 88-116；自动备份保留 4 份 168-175；恢复原子性 `RestoreRepository.kt` 7-13 |

## 2. LNReader 提炼

### 2.1 契约

- 插件 = `popularNovels / searchNovels / parseNovel / parseChapter` 四个纯函数（types 118-131）。
- 目录与正文分离：`parseNovel` 只返回 `chapters: ChapterItem[]`，正文按 `chapterPath` 单独取（types 77-85、56-63）。这正好对应我们的“先目录、后按需正文”。
- 设置是声明式 schema（Text/Switch/Select/CheckboxGroup，39-47），由插件自己声明、宿主渲染。
- `PluginItem` 带 `url`（远程代码地址）、`version`、`hasUpdate`（97-109）——这就是“插件市场”的根，也是我们不做的部分。

### 2.2 动态加载与错误边界

- 插件代码是远程 JS，`Function('require','module', ...)` 直接执行（58-64），仅靠白名单 `require`（31-43）限制依赖。
- 安装即下载并写 `index.js`，版本号比较后覆盖（126-159）；仓库 JSON 聚合去重（178-195）。
- 初始化/加载失败被吞成 `undefined`（85-87、219-221），上层只看到“未知插件”。
- **教训**：`fetchChapter` 在插件缺失时返回错误字符串当正文（fetch.ts 32-39），会把失败渲染成内容。我们必须改成抛类型化错误。
- **教训**：`restoreLibrary` 恢复时先 `fetchNovel` 联网（NovelQueries 293-296），离线恢复不可用；与 ADR-004 的 verify-first、纯本地恢复冲突。

### 2.3 书库 / 章节 / 更新

- `Novel` 以 `(path, pluginId)` 唯一（novel.ts 32），计数（总章/已读/已下载）是冗余列（24-29），便于书架排序。
- `Chapter` 以 `(novelId, path)` 唯一（chapter.ts 31）；`position` 保存源站顺序，`chapterNumber` 可空、缺失时用 `index+1` 兜底（ChapterQueries 78-80）。
- 目录 upsert 只在字段真的变化时更新（ChapterQueries 98-117），避免每次刷新都改 `updatedTime`。
- 不在书库的 `inLibrary=false` 行是“浏览缓存”，可整批删除（NovelQueries 275-288）——书库与缓存有明确分界。
- 更新按源串行、源间并发 3（updates/index.ts 24、137-165），每本 sleep 1s；只更新目录与元数据，正文另行下载。
- 更新候选在 SQL 层过滤分类与“已完结/未开始/有未读”策略（LibraryQueries 22-32、93-137）。

### 2.4 备份

- 备份是分区 ZIP：数据、插件、下载文件、小说文件（backup/types 3-23；fileSections 12-31），恢复时把章节 ID 重新映射到新库 ID（54-95）。
- 教训：备份里混入插件代码/下载缓存会让包变大且不可信；我们只备份本地真相 + 阅读状态 + 翻译产物清单。

## 3. Mihon 提炼（只看边界）

- 源接口刻意收窄：身份（`id/name/lang`）+ 能力（popular/latest/search）+ 一次合并更新 `getMangaUpdate(manga, chapters, fetchDetails, fetchChapters)` + 正文页（Source 14-106）。**目录和元数据一次请求返回**，减少往返。
- 源 ID 由 `name/lang/versionId` 的 MD5 生成（HttpSource 57、69、98-102）；站点完全改版、URL 不兼容时递增 `versionId`，等价于新源，旧书进入 stub 而不是错乱。
- 站内 URL 只存相对路径（429-463），域名迁移不影响书库。
- 领域层不依赖具体源：`SourceManager.getOrStub` 保证“源被卸载/失效”时书库仍可打开（SourceManager 8-21），只是不能更新。
- 扩展是独立 APK，必须签名且被信任才加载（ExtensionManager 46-52）；加载失败有明确原因（Extension 121-139：未信任/内容警告/未签名/lib 不兼容/损坏/实例化异常）。**这是“可诊断失败”，比 LNReader 吞异常好。**
- 更新合并：先拉远程，再 `SyncChaptersWithSource`；按相对 URL 去重、匹配；元数据“不覆盖用户改名/自定义封面”有显式策略（UpdateMangaFromRemote 100-140）。
- 章节消失不直接删库：`updateFromRemote(removedIds=...)` 交给仓储处理（SyncChapters 223-227）；阅读/书签可按章节号继承到重编号的新章节（171-220）。
- 书库更新按源分组、源内串行、信号量 5（LibraryUpdateWorker 251-267）；`ONLY_FETCH_ONCE`、已完结、有未读、未开始、未到发布窗口都可跳过（192-226）。
- 备份是 gzip + protobuf 的单流文件，自动备份只留 4 份（BackupCreator 88-116、168-175）；恢复是“整批成功或整批失败”的事务（RestoreRepository 7-13）。
- 备份可选包含扩展商店/源设置，但“私有设置”默认关闭（BackupOptions 6-17、88-94）——源设置可能含 Cookie，绝不能默认外带。

## 4. 我们的 SourceAdapter 设计

### 4.1 接口（Kotlin 伪代码）

```kotlin
interface SourceAdapter {
    val sourceId: String          // "kakuyomu" / "syosetu"，稳定、永不复用
    val schemaVersion: Int        // URL/解析不兼容时 +1，旧书转 stub
    val name: String
    val capabilities: Set<Capability> // DETAIL, TOC, BODY, SEARCH, LATEST

    suspend fun fetchBook(ref: SourceRef): SourceBook
    suspend fun listChapters(ref: SourceRef, cursor: String? = null): ChapterPage
    suspend fun fetchChapter(ref: SourceRef, chapter: SourceChapterRef): RawChapter

    // 不支持就抛 UnsupportedCapability，禁止返回空列表伪装成功
    suspend fun search(query: String, cursor: String? = null): List<SourceBookBrief> =
        throw UnsupportedCapability(sourceId, Capability.SEARCH)
}

data class SourceRef(val sourceId: String, val key: String) // key = 站内相对路径/ID，不含域名
data class SourceBook(val ref: SourceRef, val title: String, val author: String?,
                      val coverUrl: String?, val status: BookStatus, val tags: List<String>)
data class SourceChapterRef(val key: String, val title: String,
                            val number: Double?, val publishedAt: Instant?)
data class ChapterPage(val chapters: List<SourceChapterRef>, val nextCursor: String?)
data class RawChapter(val ref: SourceChapterRef, val title: String,
                      val paragraphs: List<String>, val fetchedAt: Instant,
                      val contentHash: String)
```

约束：

- 输入输出只有 DTO；**适配器内不得出现 Room Entity、Compose State、翻译模型**。
- HTTP 客户端、UA、超时、重试、限速由宿主注入/统一策略层负责；适配器只描述“请求什么、怎么解析”。
- 错误类型化：`NotFound / RateLimited / AuthRequired / ParseChanged / SourceUnavailable`。`ParseChanged` 要能触发“适配器需更新”的 UI 提示。
- 设置沿用 LNReader 思路但收窄：`Text/Switch/Select`，按 `sourceId` 持久化；Cookie 等敏感项单独加密存储且默认不进备份。
- 适配器随 APK 编译发布，**不做远程下载**；选择器修复跟随版本更新。

### 4.2 分层

```
UI (Compose) ── LibraryViewModel ── LibraryRepository (Room，唯一真相)
                                      │
                    ┌─────────────────┼──────────────────┐
              SourceRegistry      TranslationQueue     BackupService
                    │                                      │
              SourceAdapter ── FetchPolicy(限速/重试/熔断)  └─ 只读本地表
```

- `SourceRegistry` 只回答“当前编译进了哪些适配器”，v1 可以为空。
- `TranslationQueue` 只消费 `RawChapter.paragraphs`，不 import 任何 source 包。
- `BackupService` 只遍历本地表与文件，不调用 `SourceAdapter`（离线可恢复）。

## 5. 书库 / 章节 / 更新 / 备份的数据边界

| 数据 | 归属 | 关键约束 |
| --- | --- | --- |
| 书目身份 | 本地 | `id` 逻辑主键；`(source, source_id)` 唯一；`source_schema_version` 记录适配器版本；`source_key` 存站内相对路径 |
| 元数据 | 本地可编辑 | 源只填空白字段；用户改过的 `title_zh/tags/cover` 不被刷新覆盖 |
| 章节 | 本地 | `(book_id, idx)` 排序；另存 `source_chapter_key` 用于 diff；本地导入书该字段为空 |
| 正文 | 本地文件 | `raw` 与 `zh` 分离；`content_hash` 判断源正文是否真的变化；源永远不读翻译文件 |
| 阅读状态 | 本地独占 | 进度/书签/已读永不上传源站；章节重编号时按 `number/title` 尽量继承 |
| 更新记录 | 本地 | “目录发生新增/改名”才记一条；`limit` 控制展示量（Mihon `GetUpdates` 15 行取 500） |
| 备份 | 本地真相 | 含书、章、阅读状态、翻译清单、源注册表（id/name/schemaVersion）；不含抓取临时态与源缓存目录；格式版本 + sha256，verify-first |

更新算法（v2/v3 固定）：

1. `listChapters` 取全量或增量目录；
2. 以 `source_chapter_key` 匹配；新增插入、字段变化更新；
3. 源站不再返回的章节标 `missing_at`，不删正文/阅读状态；
4. 新章节默认不自动翻译；翻译是用户动作或独立队列；
5. 整轮更新按源分组，源内串行，源间并发上限（建议 2-3），失败记录原因但不阻断其它源。

## 6. v1 明确不做

| 不做 | 原因 |
| --- | --- |
| 多源搜索/聚合 | 需要能力协商、结果归一化、去重与排序；v1 没有源，做了也是空壳 |
| 插件市场 / 远程插件 | 远程代码执行 + 签名信任 + 供应链，等于自建应用商店；LNReader 的 `Function` 白名单不是安全沙箱 |
| 扩展动态加载（Dex/JS） | Android 上无法可靠隔离；Play 政策、崩溃归因、版本兼容都会失控 |
| Cloudflare/反爬绕过 | 违反站点条款、随时失效、把维护成本转成军备竞赛；还会让“解析失败”无法与“被封”区分 |
| 自动追更 / 后台抓取 | 依赖源稳定与调度，v1 先把导入/阅读/单章翻译闭环做扎实 |
| 源站账号/Cookie 同步 | 隐私与凭据风险；真要支持也走本地加密 + 默认不备份 |

理由统一到一点：**v1 的差异化是“本地书库 + 单章翻译”，不是“又一个聚合阅读器”**。抓取能力越晚接入，接口越容易被真实需求校准。

## 7. 分阶段方案

### v1（当前）：零适配器，只留 seam

- 保留并校验 `books.source / source_id`，新增（可为空）`source_schema_version / source_key` 字段。
- 导入、阅读、单章翻译、备份全部只依赖 Room 与本地文件。
- 不写 `SourceAdapter` 实现、不加网络权限之外的东西、不做源设置页。
- 验收：离线全流程可用；备份恢复不触网；未知 `source` 不影响打开书。

### v2（最小单源）：一个站，手动加书

- 先选一个站（Kakuyomu 或 成为小说家吧），实现 `DETAIL + TOC + BODY`，`SEARCH` 可暂不支持。
- 入口只有“粘贴作品 URL 加书”；不自动追更、不后台抓取。
- 抓取失败类型化提示；解析变更用固定 HTML fixture 回归（录制快照，测试不联网）。
- 设置只留 UA/请求间隔/是否下载封面；域名与相对路径规则按 Mihon 的做法固化。
- 验收：加书 → 目录 → 取一章 → 进翻译队列 → 阅读；源站挂掉不影响已有书。

### v3（完整）：多源 + 更新 + 备份元数据

- `SourceRegistry` 注册 2-3 个编译内置适配器；能力协商决定 UI（无 SEARCH 就不显示搜索框）。
- WorkManager 周期更新（网络/充电约束），按源限速与并发上限；更新结果进“更新”页。
- 章节 diff 用 `source_chapter_key`，消失章节软删除；阅读状态继承。
- 备份加入源注册表与每本源设置（敏感项显式 opt-in），恢复后源缺失则书转 `stub` 状态可读不可更。
- 可选：只读搜索（单源内），仍不做跨源聚合与插件市场。
- 验收：卸载某源/源站改版后，书库仍可打开、可读已缓存章节、错误可诊断。

## 8. 风险

| 风险 | 表现 | 缓解 |
| --- | --- | --- |
| 反爬 / Cloudflare | 403、挑战页、IP 封禁 | 不绕过；限速、退避、明确提示；必要时放弃该源 |
| HTML 结构漂移 | 解析突然为空/错位 | 契约测试 + fixture；`ParseChanged` 错误；适配器随版本修复 |
| 版权 / 站点条款 | 下架、投诉、分发风险 | 仅个人自用、不内置内容、不提供绕过；保留来源与删除通道 |
| 章节 ID 漂移 | 重复章节、进度丢失 | 相对 URL 作为 key；软删除；按章节号继承阅读状态 |
| 源站消失 | 书打不开 | stub 源 + 本地缓存优先；备份保留本地正文 |
| 翻译成本失控 | 自动追更触发全量翻译 | 新章不自动翻译；预算/并发/单章确认 |
| 远程代码/供应链 | 恶意插件 | 不做动态加载；适配器编译进 APK 并签名 |
| 测试不可复现 | 联网测试随机失败 | 全部用录制 HTML/JSON fixture；真机只做冒烟 |

## 9. 落地清单（按顺序）

1. 数据层加 `source_schema_version`、`source_chapter_key`、`missing_at`（可空，v1 不填）。
2. 定义 DTO 与错误类型（纯 Kotlin，无 Android 依赖），先只写测试。
3. v2 选源后，用 fixture 写 `listChapters`/`fetchChapter` 契约测试，再实现解析。
4. 翻译队列只接收 `RawChapter`；加一条架构测试禁止 `source` 包 import `data.local`/`ui`。
5. 更新与备份各自独立验收：更新失败不影响阅读；恢复全程不联网。
