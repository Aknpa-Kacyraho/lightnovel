# Round 3 · 统一升级指南（v1.1.1）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：只做「极端条件下会被真实用户遇到」的问题；不为了技术洁癖重写阅读器。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E3 | 大字体下动作行截断 | **采纳，P1** | `FlowRow` 两处，零业务改动 |
| U2 + D2 + E1 | 横屏一行太长 | **采纳，P1** | 一个宽度上限 + 纯函数测试 |
| U3 + D3 + E2 | 翻译前没有规模提示 | **采纳，P1** | 只加字数，不改费用模型 |
| U4 + D4 + E4 | 长章节加载像卡死 | **采纳，P2** | 300ms 延迟文案，不造假进度 |
| D5 + E5 | `TabRow` 弃用 | **采纳（部分），P2** | 只替换 TabRow；`ClickableText` 风险高，推迟 |
| U5 | 导入结果摘要 | **推迟到 Round 4** | 需要迁移报告数据，不与自适应混合 |

## 2. 实施清单

### 2.1 横屏/平板阅读宽度（P1）

- [x] 新增 `reader/ReaderViewport.kt`：`READER_MAX_CONTENT_DP = 680`、`readerContentWidthDp(...)`。
- [x] `ReaderRoute` 翻页分支外层 `Box(contentAlignment = Center)` +
      `BoxWithConstraints(widthIn(max = 680.dp).fillMaxHeight())`。
- [x] 排版宽度用纯函数换算；手机竖屏行为不变。
- [x] 新增 `ReaderViewportTest`（手机 / 临界 680 / 平板 / 极小 margin）。

### 2.2 翻译字数提示（P1）

- [x] 新增 `formatCharCount(count)`（0 → null；<1000 → 约 N 字；≥1000 → 约 X.X 千字，
      `Locale.US`）。
- [x] `readerMenuItems(..., charCount: Int = 0)`：翻译项标签拼「（约 N 字）」。
- [x] `ReaderTopBar` / `TranslationMenu` 透传 `charCount`；
      `ReaderRoute` 传 `state.chapterText.length`。
- [x] `ReaderMenuTest` 补 0 / 800 / 1200 三档。

### 2.3 大字体换行（P1）

- [x] 任务卡动作行改 `FlowRow`（End 对齐，行距 4dp）。
- [x] 书架空态次级入口改 `FlowRow`（Center 对齐）。
- [x] 不改按钮尺寸、颜色、文案。

### 2.4 长章节排版提示（P2）

- [x] `ReaderRoute` 在 `layout == null` 超过 300ms 时显示「正在排版长章节…」。
- [x] 排版完成立即消失；不显示百分比。

### 2.5 TabRow 清理（P2）

- [x] `ChapterListScreen`、`StoryMemoryScreen` 的 `TabRow` → `PrimaryTabRow`（或
      `SecondaryTabRow`，以视觉效果为准）。
- [x] 若指示器压字或跳动明显，回退并在自检记录原因。

### 2.6 版本与文档

- [x] `versionCode = 40`，`versionName = "1.1.1"`。
- [x] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不拆 `ReaderViewModel`、不改分页算法、不改 `ClickableText` 点词。
- 不做双栏、仿真翻页、TTS 改造。
- 不升级依赖、不清理 `UseKtx`（避免与体验改动混在一起）。
- 不改翻译管线、备份格式、Room schema。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥186 tests，0 failures；新增 `ReaderViewportTest` |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功 |
| 用户 | 1.5x 字体不截断；横屏正文居中限宽；翻译菜单有字数；长章节有提示 |
| 设计 | 680dp 上限；FlowRow 行距 4dp；Tab 指示器正常 |
| 发布 | 提交 + tag `v1.1.1` + 推送 |

## 5. 回滚

改动集中在 6 个 Kotlin 文件 + 2 个测试 + 文档；无数据迁移、无 API 变化。
`git revert` 单提交即可恢复 1.1.0。
