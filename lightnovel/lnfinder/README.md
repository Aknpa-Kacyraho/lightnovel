# novelia（轻小说机翻机器人）取数方式分析 + 自建发现工具

分析对象：<https://n.novelia.cc/>（用户常看的轻小说机翻站）
分析时间：2026-10-15
环境：容器网络 + 一台已连接的 Android 手机（Xiaomi / Android 16）

---

## 一、结论速览

| 问题 | 结论 |
|---|---|
| 站点是什么 | 「轻小说机翻机器人」。抓日文网文源站 → 机器翻译 → 提供中文阅读/下载 |
| 内容从哪来 | Kakuyomu、成为小说家吧(syosetu)、Novelup、Hameln、Pixiv、Alphapolis 六站 |
| 本机能否直连 | **不能**。对 `n.novelia.cc` 的 TLS 握手被 SNI 级阻断（见下） |
| 它自己怎么解决的 | 客户端内置 **ECH（加密 ClientHello）** 传输层，外加 `book.xkvi.top` 反代镜像 |
| 怎么拿它的数据 | 官方开放 REST API（`n.novelia.cc/api`），但同样被阻断 |
| 本体是否开源 | **是**：`auto-novel/auto-novel`（GPL-3.0），采集/机翻/检索全部可读 |
| 它靠什么发现好书 | 自建 Elasticsearch + 公开检索语法（`标签$` 精确匹配、`-标签$` 排除、`>N` 章节数） |
| 我最终怎么做 | **绕开它，直接打上游源站**——数据更原始、含全部标签、无阻断 |

---

## 二、站点架构（证书透明度日志 + 子域探测）

```
n.novelia.cc      小说阅读前端（React SPA）+ /api REST 接口
auth.novelia.cc   统一身份认证（/api/v1/auth/login）
forum.novelia.cc  论坛（帖子/评论/收藏，/api/v1/*）
nav.novelia.cc    导航页（列出「小说」「论坛」入口）
monitor.novelia.cc Grafana 监控
books / book / status / www / api .novelia.cc  → 525（配置了证书但源站不可达）
```

全部走 Cloudflare（`104.21.92.192` / `172.67.197.88`）。

### 阻断证据

```
$ curl -4 https://n.novelia.cc/
curl: (35) Recv failure: Connection reset by peer

$ openssl s_client -connect 172.67.197.88:443 -servername n.novelia.cc
CONNECTED(00000003)
write:errno=104          ← ClientHello 带该 SNI 后被切断
---
SSL handshake has read 0 bytes and written 314 bytes    ← 服务端没回过任何字节

$ openssl s_client -connect 172.67.197.88:443 -noservername
sslv3 alert handshake failure (SSL alert number 40)     ← 无 SNI 时 Cloudflare 正常拒绝
```

对比：`cloudflare.com`、`github.com`、`baidu.com`、`example.com` 全部 200，
`kakuyomu.jp` 200 —— 所以是**针对该域名的黑名单阻断**，不是网络不通。

`auth.novelia.cc` 等子域**没有被阻断**（能拿到 405/200），说明规则是按域名精确匹配。

---

## 三、它用什么方式获取轻小说情报

### 3.1 内容源（来自第三方客户端源码）

`nobYoQ/novelia`（面向轻小说机翻机器人的第三方安卓客户端）中：

```kotlin
// app/src/main/java/cc/novelia/app/data/catalog/Providers.kt
val providers = linkedMapOf(
  "kakuyomu" to "Kakuyomu", "syosetu" to "成为小说家吧", "novelup" to "Novelup",
  "hameln" to "Hameln", "pixiv" to "Pixiv", "alphapolis" to "Alphapolis")
```

即：**不做原创内容，只做「抓取 + 机翻 + 聚合」**。

### 3.2 发现/检索 API（这就是它的「推荐」机制）

```kotlin
// app/src/main/java/cc/novelia/app/data/network/NoveliaApi.kt
suspend fun webList(page, query, provider, type, level, translate, sort)
    = get<Page<WebOutline>>("novel", mapOf(
        "page" to "$page", "pageSize" to "20", "query" to query,
        "provider" to provider.ifBlank { providers.keys.joinToString(",") },
        "type" to "$type", "level" to "$level",
        "translate" to "$translate", "sort" to "$sort"))

suspend fun wenkuList(page, query, level) = get<Page<WenkuOutline>>("wenku", ...)
```

`/api/novel` 参数含义：`query` 关键词 / `provider` 源站 / `type` 分类 /
`level` 翻译质量档 / `translate` 是否有译文 / `sort` 排序。

**关键点：它没有「猜你喜欢」算法，发现入口就是标签 + 关键词检索。**
「轻小说消息」也不在它那里 —— 它只是把上游更新过来。

### 3.3 它怎么绕过阻断（ECH）

```kotlin
// app/src/main/java/cc/novelia/app/data/network/EchTransport.kt
private val engine = EchNativeEngine(applicationContext)   // 原生 ECH 引擎
private val httpClient = ... .addInterceptor(EchInterceptor(engine, { state.value }))
// 另设 diagnosticEchClient / diagnosticDirectClient 做「ECH vs 直连」对照探测
```

`EchNativeEngine` + `EchInterceptor`：**把 TLS 的 SNI 加密进 ClientHello（ECH）**，
中间设备看不到域名就无法按域名切断。

第三方工具 `mj3622/NoveliaReminder` 的 FAQ 也印证了这一点：
「状态码 104 错误：通常是由于**国内网络环境无法访问**轻小说机翻网导致，请使用代理」。

### 3.4 更新提醒的现成做法

`mj3622/NoveliaReminder`（Python）的思路值得直接借鉴：

```
POST https://auth.novelia.cc/api/v1/auth/login        → 拿 token
GET  https://n.novelia.cc/api/user/favored-wenku/default   → 收藏的文库
GET  https://n.novelia.cc/api/user/favored-web/default     → 收藏的网文
对比上一轮的 favorite_books.json → 有新章节就推送（邮件/飞书 webhook）
cron: 0 */12 * * * python3 main.py
```

**「收藏即订阅」** —— 它的消息来源其实是用户自己的收藏夹。

---

## 四、源码级确认（auto-novel/auto-novel 就是本体）

这份分析原本是从第三方安卓客户端反推的。后来确认了**本体开源仓库**：

* `auto-novel/auto-novel`，description 直接写着「轻小说机翻网站」，
  `homepage: https://n.novelia.cc`，GPL-3.0，TypeScript + Kotlin，1.2k star。
* 仓库结构：`packages/crawler`（采集）、`packages/translator`（机翻）、
  `server/`（Kotlin 后端）、`web/`（前端）、`daemon/`、`deploy/`。

### 采集层：一个源站一个适配器

`packages/crawler/src/web/` 下正是那六个源站：
`kakuyomu.ts` / `syosetu.ts` / `novelup.ts` / `hameln.ts` / `pixiv.ts` / `alphapolis.ts`，
外加 `amazon/`（用于文库版的书籍/卷信息）。

统一接口（`packages/crawler/src/web/types.ts`）：

```ts
export interface WebNovelProvider<GetRankOptionsT = Record<string, string>> {
  readonly id: string;
  getRank(options: GetRankOptionsT): Promise<Page<WebNovelListItem>>;  // 榜单发现
  getMetadata(novelId: string): Promise<WebNovelMetadata>;             // 详情+标签
  getChapter(novelId: string, chapterId: string): Promise<WebNovelChapter>;
}
```

**「轻小说消息」的正式来源就是 `getRank()`。** Kakuyomu 适配器里：

```ts
// packages/crawler/src/web/kakuyomu.ts
const RANGE_IDS  = { 每日:'daily', 每周:'weekly', 每月:'monthly', 每年:'yearly', 总计:'entire' };
const GENRE_IDS  = { 综合:'all', 异世界幻想:'fantasy', 现代幻想:'action', 科幻:'sf',
                     恋爱:'love_story', 浪漫喜剧:'romance', 现代戏剧:'drama', 恐怖:'horror',
                     推理:'mystery', 散文·纪实:'nonfiction', 历史:'history', ... };
const STATUS_IDS = { 全部:'all', 短篇:'short', 长篇:'long' };

await fetchDocument(this.client,
  `https://kakuyomu.jp/rankings/${genreId}/${rangeId}?work_variation=${statusId}`);
// 关键词：root.find('span.widget-workCard-tags > a')
```

`getMetadata()` 走 `https://kakuyomu.jp/works/{id}` 的 `#__NEXT_DATA__` →
`props.pageProps.__APOLLO_STATE__` → `apollo['Work:'+novelId]`，
取 `tagLabels`（即标签）、`totalReviewPoint`、`totalCharacterCount`、
`serialStatus`、`tableOfContentsV2`。

> 也就是说：auto-novel 的**适配器接口**只把「榜单」当发现入口（`getRank`），
> 它的「检索」是自建 ES，不是从源站借的。
>
> ⚠️ 但这不等于源站没有检索——实测 **Kakuyomu 站点本身就有 `/search`**：
> `/search?q=`（关键词）、`/search?genre_name={slug}`（流派）、`order=weekly_ranking`（排序）；
> 榜单页 `/rankings/{genre}/{range}?work_variation=` 单页约 **110 本**
> （2026-10 实测；`lnlib.kakuyomu_ranking` / `kakuyomu_search(genre=, order=)` 即走这两条）。

### 服务端检索：它真正的推荐引擎

`server/src/main/kotlin/api/RouteWebNovel.kt` + `infra/web/datasource/WebNovelEsDataSource.kt`
显示：机翻站把每个源站的元数据（含 `keywords`）**索引进 Elasticsearch**，
然后用自己的查询语法检索。这才是它「发现好书」的真正机制，而且语法是公开的：

| 语法 | 含义 |
|---|---|
| `关键词`（空格分隔） | 在 `titleJp`/`titleZh`/`authors`/`attentions`/`keywords` 里 AND 匹配 |
| `标签$` | **精确匹配** `keywords`（或 attentions）中的该标签 |
| `-标签$` | 排除该标签 |
| `>200` / `<100` | 按章节数（`tocSize`）筛选 |

排序参数 `sort`：**`0` = 按更新（默认）**、`1` = 按点击、`2` = 相关性。
筛选参数：`provider`（源站）、`type`（1 连载/2 完结/3 短篇）、
`level`（1 一般向 / 2 R18）、`translate`（1 GPT3 / 2 Sakura）。

另一条入口是 `GET /api/novel/rank/{providerId}`（缓存 2 小时），
把源站 `getRank()` 再返给前端。

**所以「怎么及时获得轻小说消息」的标准答案是：**
它没有推送，只有「按更新时间排序」的检索 —— 想追新就盯
`/api/novel?sort=0` + 你关心的 `provider`，想精确找口味就用 `标签$` 语法。

---

## 五、我采用的方案：直接打上游

缺陷：`n.novelia.cc` 被阻断 → 但它的**上游源站大多能直连**，
且上游数据更完整（Kakuyomu 的搜索接口直接返回 `tagLabels` 数组）。

```
Kakuyomu 搜索页  https://kakuyomu.jp/search?q=<日文标签>
  → HTML 内 <script id="__NEXT_DATA__"> 的 Apollo 状态
  → Work 实体：title / genre / tagLabels / author / totalReviewPoint
               / publicEpisodeCount / totalCharacterCount
               / publishedAt / lastEpisodePublishedAt / serialStatus
```

实测一次请求返回 20 部作品，全部带标签。于是可以按标签组合精准找书。

> 注意：`/tags/<标签>` 页面是 SSR，**没有** `__NEXT_DATA__`；
> `__schema` 内省被 Apollo 关闭（`INTROSPECTION_DISABLED`）。
> 用 `/search?q=` 这条路径，它是唯一同时给出「候选 + 完整标签」的入口。

成为小说家吧的官方 API `api.syosetu.com/novelapi/api/` 已在 `lnlib.py` 中实现
（`order=weekly|new|hyoka`、`genre=101`），但在本网络环境不通，作备用。

---

## 六、交付物

| 文件 | 说明 |
|---|---|
| `lnfind.py` | CLI：`profile` / `learn` / `recommend` / `new` / `author` / `interesting` |
| `lnlib.py` | 采集库（Kakuyomu + syosetu 官方 API） |
| `taste_profile.json` | 偏好画像（标签权重、黑名单、下限） |
| `reports/` | Markdown 推荐报告 |
| `.dsh/skills/lnfinder/SKILL.md` | 固化成 skill，以后一句话就能用 |

设计要点：**用标签组合打分，而不是用人气排序** ——
这正是「通用 AI 只推名著」的反面。热度只做温和封顶加成（`min(评价点/5000, 2)`），
避免又变成排行榜复读；同时有「命中标签数下限」和负标签黑名单过滤噪音。

---

## 七、给站长的现实建议

想在**不折腾网络**的前提下及时收到「轻小说消息」，最省事的两条路：

0. **追新的官方姿势**：`GET /api/novel?sort=0&provider=<源站>`（`sort=0` 即按更新时间），
   或 `GET /api/novel/rank/{providerId}`（榜单，缓存 2 小时）。
   想精确找口味就用 `标签$` 语法，例如
   `query=〈想要的标签〉$ -〈想避开的标签〉$` 表示「含 A 且不含 B」。
   注意这些接口本身也被 SNI 阻断，所以要配合下面第 1 条用；
1. 用带 **ECH** 的官方/第三方客户端（它能自己穿透 SNI 阻断）；
2. 在网站上把想看的书加进**收藏**，再用 `NoveliaReminder` 那种
   「登录 → 拉收藏列表 → 对比上次 → 推送」的脚本定时跑。

如果只是想要「有好书看」而不在乎机翻站，直接用本工具打上游源站更稳，
而且能看到源站全部标签——比机翻站的二次聚合更早、更全。
