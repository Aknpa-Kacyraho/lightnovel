# Round 15 · 三视角自检（v1.5.2）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。无真机（`adb` 不可用）。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **264 tests / 0 failures / 0 errors / 1 skipped**（无净增，容器改动） |
| lint | **0 errors / 22 warnings**（无新增） |
| Debug 构建 | 成功，versionCode 52 / 1.5.2 |
| 数据 | 无 schema 变化 |

过程中修正一处可见性错误：`ReaderMenuSheet` 参数使用 internal 的 `ReaderMenuItem`，
函数需为 `internal`；已改。

## 用户视角

**已改善**

1. 书架筛选行从 7 个控件减到 4 个：书架下拉、收藏、已移出、排序。
2. 书架下拉显示当前状态（「书架：在读」），切换时清收藏/已移出，与旧「全部」一致。
3. 阅读器「更多」改为底部 Sheet，组标题完整、可滚动、点击一项立即关闭。
4. 16 项功能与顺序不变，禁用条件不变。

**仍然存在**

- 书架下拉多一次点击（原来点 chip 直接切换）。
- 阅读器 Sheet 最大 70% 高，16 项仍需滚动；分组标题比 DropdownMenu 更清楚。
- 设置页仍长（本轮明确不做）。

## 设计师视角

**一致**

- 书架下拉与排序 chip 同一 `BrandFilterChip` 样式，当前项打勾。
- 阅读器 Sheet 用纸色背景与正文色，组标题 `labelMedium`、项 `bodyLarge`。
- 禁用项 alpha 0.5，与旧菜单一致。
- 没有新增图标、颜色或圆角。

**取舍**

- 书架没有把「收藏/已移出」也收进下拉：它们是独立布尔维度，保留一键切换。
- 阅读器 Sheet 没有做拖拽展开到全屏：70% 足够覆盖 16 项。

## 工程师视角

**做对了**

- 书架下拉切换时显式清 `favoritesOnly/removedOnly`，行为与旧「全部」一致。
- `ReaderMenuSheet` 只接收数据与回调，`when` 集中在一处，新增项仍只改 `ReaderMenu`。
- Sheet 用 `Column + verticalScroll`，避免 LazyColumn key 问题。
- `ReaderMenuTest` 仍测 16/15 项，容器变化不影响数据断言。

**风险与限制**

- `TranslationMenu` 的 `backgroundColor` 需要调用方传入；漏传会退回 App 主题色。
- `ReaderMenuSheet` 的 `fillMaxHeight(0.7f)` 在横屏下可能过矮，未真机确认。
- 书架下拉的「全部」与旧「全部」chip 语义一致，但用户可能仍习惯直接点 chip。

**未验证**

- 真机上 Sheet 的滚动与点击手感。
- 书架下拉在小屏/横屏的展开方向。
- 1.5x 字体下菜单项两行时的行高。

## 结论

Round 15 目标达成，可作为 1.5.2 发布。本批三轮（1.5.0–1.5.2）完成
「真沉浸 → 术语表可管理 → 长菜单与筛选收敛」。
