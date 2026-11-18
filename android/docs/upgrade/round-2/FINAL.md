# Round 2 · 统一升级指南（v1.1.0）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：让第一次用的人不迷路，让常用动作少一步；不新增页面、不换视觉语言。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 空态三入口、无主次 | **采纳，P0** | 唯一一个「第一次打开就困惑」的问题；同时可抽纯函数测试 |
| U2 + D2 + E2 | 备份提醒不能直达数据分组 | **采纳，P1** | 一个状态 + 一次滚动，无导航重构 |
| U3 + D3 + E3 | 阅读器菜单 13 项平铺 | **采纳，P1** | 只改渲染顺序，业务回调不动，风险可控 |
| U4 + D4 + E4 | 任务统计不可点 | **采纳，P2** | 复用已有 `setFilter`，零新状态 |
| U5 | 翻译入口费用不清 | **推迟到 Round 3** | 涉及翻译管线文案与费用模型，不与 UI 混合 |

## 2. 实施清单

### 2.1 空态两条路径（P0）

- [x] 新增 `feature/library/LibraryEmptyState.kt`：`EmptyShelfCopy` / `EmptyAction` / `emptyShelfCopy(...)`。
- [x] 空态改为：标题「还没有书」；两行说明「第一次用？去发现…」「有旧备份？先导入备份…」；
      唯一实心按钮「去发现」；次级一行「导入备份 · 导入 TXT / EPUB」。
- [x] 有搜索/收藏/书架/已移出筛选时保持「清除筛选」，不套用新空态。
- [x] 新增 `LibraryEmptyStateTest` 覆盖五种分支。

### 2.2 备份提醒直达「数据」（P1）

- [x] `LightnovelNavHost` 增加 `settingsFocus` 状态；书架备份提醒设 `"backup"` 后切 Tab。
- [x] `SettingsRoute` / `SettingsScreen` 接收 `focus`、`onFocusConsumed`。
- [x] 「数据」分组 `onGloballyPositioned` 记录位置；`LaunchedEffect` 滚动 + 2 秒高亮。
- [x] `SettingsGroup` 支持 `highlighted`，用 `animateColorAsState`，不写死颜色。
- [x] 手动进入设置不滚动、不残留高亮。
- [x] 新增 `SettingsFocusTest`（白名单解析）。

### 2.3 阅读器菜单分组（P1）

- [x] 新增 `feature/reader/ReaderMenu.kt`：4 组（阅读 / 翻译 / 资料 / 世界线）+ 13 个原动作。
- [x] `TranslationMenu` 按组渲染：组标题 `bodySmall`、`onSurfaceVariant`、`HorizontalDivider`。
- [x] 每个 `enabled` 与原实现一一对应；顺序只在组内调整。
- [x] 新增 `ReaderMenuTest` 断言组数与标签集合。

### 2.4 任务统计可点（P2）

- [x] 失败 / 未译全 / 进行中统计项可点，调用 `setFilter`。
- [x] 当前筛选对应项有选中态（`primary` + `primaryContainer`），未选中 `onSurfaceVariant`。
- [x] `TaskGroupingTest` 补筛选一致性断言。

### 2.5 版本与文档

- [x] `versionCode = 39`，`versionName = "1.1.0"`。
- [x] `CHANGELOG.md`、`04-final.md` §8.1、`PROGRESS.md`、`README.md` 同步。
- [x] 本目录 `SELF-REVIEW.md`。

## 3. 非目标

- 不做新手引导页、设置目录页、菜单 Sheet 化。
- 不改底栏、导航、Room schema、备份格式、翻译管线。
- 不新增依赖、不新增图标、不新增颜色 token。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥178 tests，0 failures；新增两个纯函数测试文件 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功 |
| 用户 | 空态首屏两条路径；备份提醒一次点击见「导出备份」 |
| 设计 | 菜单 4 组、3 条分隔线；统计选中态清楚；360dp 不截断 |
| 发布 | 提交 + tag `v1.1.0` + 推送 |

## 5. 回滚

全部改动集中在 6 个 Kotlin 文件 + 3 个测试 + 文档，无数据迁移；
`git revert` 单提交即可恢复 1.0.4 行为。
