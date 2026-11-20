# Round 11 · 统一升级指南（v1.4.1）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：搜索先保证「能搜到、能定位、不卡」，不追求正则/模糊/跨书。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1–E3 | 没有书内搜索 | **采纳，P0** | 纯函数 + 逐章 IO，可测 |
| U2 + D4 | 结果要能定位 | **采纳，P1** | 同章段落 ID 跳转，跨章到章首 |
| U3 | 搜索不能卡 | **采纳，P1** | IO + 每章 3 条 + 总 30 + 取消 |
| U4 | 范围要清楚 | **采纳，P2** | 顶部「搜索范围：译文/原文」 |

## 2. 实施清单

### 2.1 匹配（P0）

- [ ] 新增 `BookSearch.kt`：`TextHit`、`findHits(text, query, max)`。
- [ ] `BookSearchTest`：空查询、无命中、大小写、截断、每段一条、上限。

### 2.2 扫描（P0）

- [ ] `BookSearchService.search(...)`：逐章读 zh/raw，每章 3 条，总数 30。
- [ ] 译文缺失自动回退原文；不整本入内存。

### 2.3 ViewModel（P1）

- [ ] `searchResults` / `searching` / `searchScope`。
- [ ] `searchBook(query)` 取消旧任务；`clearSearch()`。
- [ ] 跳转复用 `jumpToAnchor` / `onOpenChapter`。

### 2.4 UI（P1）

- [ ] 菜单「资料」组加「搜索本书」。
- [ ] `BookSearchSheet`：输入框、300ms 防抖、结果片段、高亮关键词、空态、搜索中。
- [ ] 点击结果关闭 Sheet 并跳转。

### 2.5 版本与文档

- [ ] `versionCode = 48`，`versionName = "1.4.1"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不做正则、模糊匹配、拼音搜索、跨书搜索。
- 不做搜索历史/持久化。
- 不建全文索引。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥239 tests，0 failures；新增 BookSearchTest |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 48 |
| 用户 | 搜得到、看得到上下文、跳得到段落 |
| 性能 | 输入防抖、可取消、结果上限 30 |
| 发布 | 提交 + tag `v1.4.1` + 推送 |

## 5. 回滚

纯新增文件 + 菜单一项 + ViewModel 方法；`git revert` 单提交即可，无数据迁移。
