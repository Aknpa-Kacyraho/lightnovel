# Round 5 · 统一升级指南（v1.2.1）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：深色模式只调「明度与容器」，不改色相；所有调整必须有对比度断言。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 深色次要文字过亮、无回归 | **采纳，P0** | 8 套统一降亮，测试锁 7–10:1 |
| U2 + D2 + E2 | 标签容器偏艳 | **采纳，P1** | 混合 0.30→0.24，抽常量 |
| U3 + D3 + E3 | 卡片亮边框 | **采纳，P1** | 三处统一容器与 0.6 alpha 描边 |
| U4 | 继续阅读卡无进度 | **推迟到 Round 6** | 与阅读进度一起做 |

## 2. 实施清单

### 2.1 深色可读性（P0）

- [ ] `Theme.kt`：8 套 dark 的 `onSurfaceVariant` 按设计表调整。
- [ ] 新增 `ThemeContrastTest`：8 套 dark 的次要文字 7.0–10.0:1、主文字 ≥12:1、
      标签文字 vs `surfaceVariant` ≥4.5:1。
- [ ] 浅色主题不动。

### 2.2 容器混合（P1）

- [ ] `toScheme` 抽 `DARK_CONTAINER_MIX = 0.24f`、`LIGHT_CONTAINER_MIX = 0.14f`。
- [ ] `secondaryContainer` / `tertiaryContainer` / `errorContainer` 共用。

### 2.3 卡片层级（P1）

- [ ] `BookRow`、`ContinueCard`、`TaskCard` 显式
      `containerColor = surfaceContainerLow`，描边 `outlineVariant.copy(alpha = 0.6f)`。
- [ ] `SettingsGroup` 保留原描边（分组容器）。

### 2.4 版本与文档

- [ ] `versionCode = 42`，`versionName = "1.2.1"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改浅色主题、不改 8 套主题色相、不新增主题。
- 不改布局、间距、圆角、状态色派生逻辑。
- 不做护眼模式/定时切换。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥199 tests，0 failures；新增 `ThemeContrastTest` |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 42 |
| 用户 | 深色下次要文字不抢眼；标签不发光；卡片无亮框 |
| 设计 | 对比度区间达标；浅色无变化 |
| 发布 | 提交 + tag `v1.2.1` + 推送 |

## 5. 回滚

改动集中在 `Theme.kt` + 3 个列表 Card + 1 个测试；无数据迁移、无逻辑变化。
`git revert` 单提交即可。
