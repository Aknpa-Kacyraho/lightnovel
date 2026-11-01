# 从成熟项目学到的设计（前辈知识，别再闭门造车）

> 用户说：「能利用前辈们的知识是你最大的优势，不要闭门造车」。
> 这份文档记录**我实际读过源码并采纳**的设计，注明出处，避免以后重复踩坑。

---

## 一、Kavita（★11.8k，C#，跨平台阅读服务器）

源码：`github.com/Kareadita/Kavita`（`develop` 分支）

### 1. 进度模型 `AppUserProgress`

```csharp
public class AppUserProgress {
    public int PagesRead { get; set; }
    public int VolumeId / SeriesId / LibraryId / ChapterId { get; set; }
    /// For Book Reader, represents the nearest passed anchor on the screen
    /// that can be used to resume scroll point on next load
    public string? BookScrollId { get; set; }
    public DateTime LastModified / LastModifiedUtc { get; set; }
    /// Total times the underlying Chapter has been fully read
    public int TotalReads { get; set; } = 0;
}
```

**学到的**：

* 进度存**章节 + 滚动锚点**，不只是"读到第几章"。长篇一章几千字，
  回到章首和回到原处体验差别很大 → 我们加了 `scroll`。
* `TotalReads` 支持"重看次数"（小说场景没什么用，我们没做）。
* `LastModified` / `LastModifiedUtc` **分开存**。我们用本地时间字符串，
  够用（单机个人使用），但知道这是权衡。

### 2. 「想读」是**独立表**，不是状态枚举

```csharp
public class AppUserWantToRead {   // 只有 SeriesId + AppUserId
    public required int SeriesId { get; set; }
}
```

**学到的（重要）**：Kavita 没有把「想读/在读/已读/弃文」做成一个字段。
它把 **阅读进度**（AppUserProgress）与 **想读列表**（WantToRead）分开，
"是否已读"由进度**推导**。

→ 印证了我们的做法：`tracking` 与 `favorites` 是两个正交维度，
而不是一个互斥的状态机字段。

### 3. 阅读会话 `AppUserReadingSession`

```csharp
public class AppUserReadingSession {
    public DateTime StartTime / StartTimeUtc { get; set; }
    public DateTime? EndTime / EndTimeUtc { get; set; }
    public bool IsActive { get; set; }
    /// True if the session was generated and not from progress events
    public bool IsGenerated { get; set; }
    public IList<AppUserReadingSessionActivityData> ActivityData { get; set; }
}
```

**学到的**：它记录**每次阅读的起止时间**（还区分"真实阅读"与"手动标记已读"），
从而能算每日时长、连续天数。我们只存"最后读到的章节 + 时间"，
算不出这些统计 → 加了 `history.jsonl`（每次进度的追加日志）。

### 4. 它的 `ReadStatus` 在 Plus 模块里没有独立枚举

`ScrobbleReadStatus`（外部同步用）等都在可选模块；
核心库**用进度推导状态**。说明"用数据推导"比"维护一个状态字段"更不容易不一致。

---

## 一·补、auto-novel 的 translator（本项目自身的上游）

源码：`github.com/auto-novel/auto-novel` → `packages/translator/src/`
（`web_search` 在本会话不可用时，靠 GitHub API 直接读源码最有效）

### 1. `SegmentQueue` —— 高水位线背压（`segment/segment_queue.ts`）

```ts
private _enqueuedCount = 0;          // 在途（排队+翻译中）分片总数
async enqueueAll(segments) {
  await this._enqueueLock.use(async () => {       // 入队锁，防交错
    await this.waitUntilBelowHighWaterMark(signal); // 水位满了就等
    this._enqueue(segments);
  });
}
ack(next?: Segment) {                // 消费者完成一个分片
  if (next) { /* 把后续分片插到队首，保持顺序 */ }
  else { this._enqueuedCount--; this._tryResolveHw(); }
}
```

**学到的**：控制的是**在途总数**而不是"一次生成多少"，生产者会被背压挂起；
`ack(next)` 支持"重试分片插队首"，保证顺序不被打乱。
（我们逐段串行 + 信号量，规模小得多，没有照搬队列；但背压思路记下了。）

### 2. `detectChinese` —— 校验译文真的是中文（`utils.ts`）

```ts
export const detectChinese = (text: string) => {
  // 统计中文/假名/英文占比
  return pZh > 0.75 || (pZh > pJp && pZh > pEn * 2 && pJp < 0.1);
};
```

**学到的（很重要）**：只校验"行数是否相等"**不够**——模型可能把日文原文
原样抄回来，行数完全正确但根本没翻。必须再加**语言检测**。
→ 我们实现了 `detect_chinese()`，并写进 `robust_translate_paras()` 的校验。

### 3. 二分降级（`translator/openai-translator.ts`）

```ts
if (failBecauseLineNumberNotMatch === 3 && lines.length > 1) {
  return this.binaryTranslate(lines, context, signal);   // 拆两半递归
}
```

**学到的**：长段/对话密集的内容最容易对齐失败，**整段硬重试成功率低**；
把它拆成两半分别翻再拼起来，成功率高得多。
→ 我们实现了按段落二分（`depth < 4` 防无限递归）。

### 4. `Semaphore`（`utils.ts`）

```ts
async use<T>(fn) { await this.acquire(); try { return await fn(); }
                   finally { this.release(); } }
```

→ 我们实现了 `Semaphore` + `_GLOBAL_SEM = Semaphore(3)`，把在途 LLM 请求压住。

### 5. 已采纳清单

| 来源 | 采纳的做法 | 落地位置 |
|---|---|---|
| `detectChinese` | 译后语言校验，防止抄回原文 | `detect_chinese()` |
| 二分降级 | 连续 3 次对齐失败就拆半递归 | `robust_translate_paras()` |
| `Semaphore` | 限制在途请求数 | `_GLOBAL_SEM` |
| 高水位背压 | （思路记录；我们规模不需要队列） | — |

**测试陷阱（自己也踩了）**：用桩模拟 LLM 时，桩必须**从 prompt 里读实际编号**
再回显。二分后右半段编号是 `#3/#4` 而不是 `#1/#2`，硬写 `#1` 起会永远对不上，
表现为"二分总是失败"，其实是测试桩错了。

## 一·补二、LightNovelReader（★2242，Kotlin/Compose，中文轻小说阅读器）

仓库：`github.com/dmzz-yyhyy/LightNovelReader`（`dev/1.3` 分支）
**这是最贴近我们场景的参考**：多数据源轻小说阅读器，带 epub 导出、
自定义背景、本地书架、更新提醒、AI 翻译。

### 1. `UserReadingData` —— **双轨章节进度**（本轮采纳，价值最高）

```kotlin
val currentChapterReadingProgressMap: Map<String, Float> = mapOf()
val maxChapterReadingProgressMap: Map<String, Float> = mapOf()

fun copyWithUpdatedChapterReadingProgress(chapterId, progress) {
    val maxProgress = progress.coerceAtLeast(this.maxChapterReadingProgressMap[chapterId] ?: 0f)
    // current 跟着实际位置走；max 只前进
}
```

**为什么这个设计对**：只存一个"最远位置"是错的——用户往回翻一点再退出，
下次会被送到**最远处**，而不是他真正停下的地方。
两者用途不同：

* `current` → **续读位置**（我下次从这里开始）
* `max` → **进度百分比**（这本书我读了多少）

→ 我们已采纳成 `progress.scroll` / `progress.max_scroll`，
并用 `max_scroll` 算书架上的「已读 N%」。

### 2. `Bookshelf` —— 书架是一等对象，排序是**持久设置**

```kotlin
data class Bookshelf(
    val name: String, val sortType: BookshelfSortType = Default,
    val sortReversed: Boolean = false, val autoCache: Boolean = false,
    val systemUpdateReminder: Boolean = false,
    val allBookIds: List<String>, val pinnedBookIds: List<String>,
    val updatedBookIds: List<String>)

enum class BookshelfSortType(val key: String) {
    Default("default"), Latest("latest"), Name("name"), WordCount("word_count") }
```

**学到的**：

* 允许**多个书架**（分组），不止一个"我的书架"。
* **排序方式、是否自动缓存、是否系统通知更新**都是**每书架的可持久化设置**，
  不是写死的。（我们目前排序固定，是个已知短板。）
* **「有新章节」是书架里的一个 id 列表**（`updatedBookIds`），
  不是每本书上散落的布尔值。

### 3. `BookshelfBookItem` —— 卡片没有"状态"字段

```kotlin
data class BookshelfBookItem(
    val id: String, val bookshelfBookMetadata: BookshelfBookMetadata?,
    val bookInformation: BookInformation, val lastUpdatedChapterTitle: String?)
```

只有书籍信息 + **最新更新章节标题**，**没有** `status: 在读/弃文/读完`。

→ **第三次印证**同一个结论（Kavita / calibre-web / Komga / LightNovelReader）：
成熟阅读器的卡片围绕**「内容 + 进度 + 更新」**，而不是让用户维护状态标签。
我们的四态 shelf 是产品选择（跟着中文网文 App 的习惯），但要记住
**核心信息是进度和更新**，不是状态徽标。

### 4. 其他值得记的

* `lastReadChapterTitle` 存在阅读数据里 —— 书架不用反查章节表就能显示
  "读到第几章 标题"。我们现在是 `progress.chapter` 数字，标题要查 meta。
* `totalReadTime`（秒）、`lastReadTime` —— 用于统计和排序。
  我们有 `history.jsonl`，能算，但没存累计秒数。
* Track A 的多数据源探索接口含 `ExploreBooksRow` / `ExploreDisplayBook`
  —— 和我们「推荐位」是同一类东西。

## 二、calibre-web（★18.4k）与 Komga（★6.8k）

* **calibre-web**：书架靠 Calibre 数据库 + 各平台的 Kobo sync 状态。
  它的"已读"也是从阅读位置推导，没有独立的书架状态字段。
* **Komga**：只有 **ReadList**（收藏夹/书单）+ 每本书的 **read progress**，
  同样没有"在读/弃文"这种用户级状态。

**共同结论**：主流阅读服务器都用
**「进度（事实）」+「列表/收藏（意图）」** 两个维度，
而不是让用户维护一个状态机。我们本轮把这一点对齐了。

---

## 一·补三、作品详情页：一个合格的轻小说站该回答什么

参考（`web_search` 现在可用，可直接搜中文/日文资料）：

* [Reikai 的 novel-details 设计文档](https://github.com/unseensnick/Reikai/blob/main/docs/dev/plans/novel-details.md)
  —— 同样做"轻小说发现+阅读"的开源项目，有专门的作品页设计计划
* [NovelUpdates](https://zhuanlan.zhihu.com/p/73514847) —— 英文圈最主要的中文网文索引站
* Kobo/Amazon 等电子书店的**商品页规范**：书的商品页必须让读者在
  30 秒内判断"要不要读"
* 日文侧的通行结构：カクヨム作品页 = あらすじ（简介）+ 目次（目录）+
  タグ（标签）+ 各種統計，**这四块缺一不可**

### 结论：作品页要回答五个问题

| 读者的疑问 | 页面上必须有 |
|---|---|
| 这书讲什么？ | **简介**（あらすじ） |
| 什么类型、写给谁？ | **标签** + 分类（genre） |
| 多长、完结没、口碑如何？ | 话数 · 字数 · 积分 · 连载状态 · 更新日期 |
| 我读到哪了？ | 阅读进度 + **目录**（章 / 话标题） |
| 下一步做什么？ | 加入书架 / 继续阅读 / 去源站 |

**用户报的 bug 正是违反第 1、2、4 条**：书库的书点进去没反应，
没有任何可判断的信息，等于"只给你一个标题让你决定要不要读"。

### 数据从哪来（kakuyomu 实测）

| 字段 | 位置 |
|---|---|
| 简介 | **`<meta property="og:description">`** —— kakyomu 把あらすじ放这里（Apollo 的 `Work` 实体里**没有**简介） |
| 目录 | `__NEXT_DATA__` 的 Apollo：`Chapter`(章) + `TableOfContentsChapter`(章的 episodeUnions) + `Episode`(話标题/日期) |
| 标签 / 类型 / 话数 / 字数 / 积分 | 搜索结果页的 Apollo 已有，此前就抓到了 |

**注意**：`extract_work_page()` 的形参原本叫 `html`，**遮蔽了 `html` 模块**
（`import html`）导致 `html.unescape()` 报 `'str' has no attribute 'unescape'`。
现在参数名是 `page`。教训：参数名别和模块名撞。

## 三、已采纳进本项目的 4 条

| 来源 | 采纳的做法 | 落地位置 |
|---|---|---|
| Kavita `BookScrollId` | 进度存滚动位置，回到上次的位置而不只是章首 | `progress.scroll` + 阅读页恢复 |
| Kavita `AppUserProgress` | 章级进度 + 时间戳 | `data/books/<slug>.json` 已有 |
| Kavita `WantToRead` 独立表 | 「想读」与「收藏」正交 | `tracking` + `favorites` |
| Kavita `ReadingSession` | 追加阅读日志，可算连续天数/时长 | `data/history.jsonl` + 书架统计 |

## 四、没有采纳的（记录原因）

| 设计 | 为什么不采纳 |
|---|---|
| `TotalReads` 重看次数 | 小说重看极少，收益低 |
| 分页 `PagesRead` | 我们是章节 + 滚动，不按页 |
| `ReadingSessionActivityData` 细粒度活动 | 需要活跃心跳，个人使用过重 |
| `IsGenerated` 标记 | 它用于区分"真实阅读/手动标记"，我们场景简单 |

---

## 五、方法论（下次该怎么做）

1. **先找同类成熟项目读源码**，不要自己拍脑袋。GitHub API 在本环境可用
   （`/repos/{owner}/{repo}/git/trees/{branch}?recursive=1` 列文件，
   `raw.githubusercontent.com` 取文件）。
2. 特别注意它们**怎么划分概念边界**（这比具体字段更有价值）。
3. 记录**采纳与不采纳的理由**，否则以后会反复纠结同一件事。
4. 搜索引擎不可靠时（本环境 Mojeek 时好时坏、DuckDuckGo 不通），
   **直接定位仓库读代码**比搜索更有效。
