# Round 3 · 三视角自检（v1.1.1）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。无真机（`adb` 不可用）。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **199 tests / 0 failures / 0 errors / 1 skipped**（+7：视口 5、字数 2） |
| lint | **0 errors / 22 warnings**（与 1.1.0 持平） |
| 编译警告 | `TabRow` 弃用消失；`ClickableText` 仍在（本轮明确不改） |
| Debug 构建 | `:app:testDebugUnitTest :app:lintDebug :app:assembleDebug` 成功 |
| 版本 | `versionName 1.1.1` / `versionCode 40` |
| 数据 | 无 schema/迁移/备份格式变化 |

## 用户视角

**已改善**

1. 平板/横屏正文最大宽度 680dp 并居中，长行不再横跨整块屏幕；手机竖屏宽度不变。
2. 系统字体放大后，任务卡四个动作、书架空态两个次级入口会换行，不再挤成一行。
3. 阅读器「翻译本章」显示「（约 N 字）」或「（约 X.X 千字）」，0 字不显示。
4. 超大章首次打开超过 300ms 显示「正在排版长章节…」。

**仍然存在**

- 滚动模式的正文没有 680dp 限宽（只改了翻页模式）。
- 章节列表的批量翻译对话框没有统一显示「共 N 章」（详情页已有）。
- 导入完成摘要仍只有书籍数量（Round 4 候选）。

## 设计师视角

**一致**

- 680dp 只限制内容宽度，不改变字号、行距与上下留白；页码浮层仍在屏幕底部。
- `FlowRow` 行距 4dp、End/Center 对齐与原 `Row` 一致；按钮样式未改。
- 字数提示是菜单项文案的一部分，不加 badge、不加颜色。
- `PrimaryTabRow` 与原 `TabRow` 共用 Material3 主题色，未新增样式。

**取舍**

- 空态次级入口去掉了「·」分隔符，改用按钮间距；换行时不会出现孤立的点。
- 排版提示不做百分比：无法准确估算，假进度比没有更糟。

## 工程师视角

**做对了**

- `readerContentWidthDp(...)` 是纯函数，5 个边界（手机 / 680 / 平板 / 零边距 / 极端边距）
  都有断言；`ReaderRoute` 只负责换算 px。
- `formatCharCount(...)` 固定 `Locale.US`，避免区域设置把小数点点成逗号。
- `FlowRow` 只改布局容器，按钮点击、语义、回调全部不变。
- `showSlowPagination` 由 `LaunchedEffect(state.loading, state.layout)` 驱动，
  排版完成会立即复位；effect 取消不会写入 UI。

**风险与限制**

- `HorizontalPager` 的 `widthIn(max=680dp).fillMaxHeight().align(Center)` 依赖
  `BoxWithConstraints` 的 BoxScope；已在编译期验证，但未在平板真机目视确认居中。
- `PrimaryTabRow` 的指示器与标签同宽，视觉与旧 `TabRow` 略有差异；无真机截图，
  若用户反馈「指示器压字」需回退。
- 字数取 `state.chapterText.length`，显示译文时是译文字数，与原文略有差异；
  作为量级提示可接受。

**未验证**

- 1.5x / 最大字体下的实际换行与触控目标。
- 横屏、分屏、平板上的 680dp 居中效果。
- 长章节 300ms 阈值的实际体感（无超大章 fixture）。

## 结论

Round 3 目标达成，可作为 1.1.1 发布。滚动模式限宽、导入摘要列为 Round 4 候选。
