# Round 16 · 统一升级指南（v1.6.0）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：只修真实的数据语义 bug，不重构阅读器。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E2 + E3 | 跨模式进度错位 | **采纳，P0** | `progress_block` 统一段号 + 双向映射 |
| U2 + D2 + E4 | 滚动书签位置错 | **采纳，P0** | 书签/翻译锚点用 `currentParagraphIndex()` |
| U3 + D3 + E5 | 滚动跳转不滚动 | **采纳，P1** | `LaunchedEffect` + 等值检查 |

## 2. 实施清单

### 2.1 映射纯函数（P0）

- [ ] 新增 `ReaderScrollMapping.kt`：`paragraphIndexForLine` / `lineForParagraph`。
- [ ] `ReaderScrollMappingTest`：单段多行、多段、bilingual、空、越界、往返。

### 2.2 进度写读（P0）

- [ ] `onScrollParagraphChanged` 写 DB 时映射为段号；`scrollParagraph` 仍存行号。
- [ ] `load()` 恢复时把段号换算成起始行号（仅滚动模式）。
- [ ] 旧数据一次性偏差在接受范围内（自检注明）。

### 2.3 书签与翻译（P0）

- [ ] `addBookmark()` 滚动分支用 `currentParagraphIndex()`。
- [ ] `translateChapter()` 的恢复锚点同样用段号。
- [ ] 预览、跳转、DB 三处一致。

### 2.4 滚动响应（P1）

- [ ] `ReaderScreen` 滚动分支加 `LaunchedEffect(state.scrollParagraph)`；
- [ ] 索引不同才 `scrollToItem`，无动画。

### 2.5 版本与文档

- [ ] `versionCode = 53`，`versionName = "1.6.0"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不重写分页/滚动渲染、不改数据库结构、不改书签/搜索 UI。
- 不做旧数据迁移（无法区分行号/段号）。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥264 tests，0 failures；新增映射用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 53 |
| 用户 | 跨模式进度一致、滚动书签正确、跳转会滚动 |
| 发布 | 提交 + tag `v1.6.0` + 推送 |

## 5. 回滚

改动集中在 `ReaderScrollMapping`、`ReaderViewModel`、`ReaderRoute` + 测试；无迁移。
`git revert` 单提交即可。
