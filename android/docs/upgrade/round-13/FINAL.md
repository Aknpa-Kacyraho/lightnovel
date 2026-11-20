# Round 13 · 统一升级指南（v1.5.0）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：沉浸做成真全屏；常驻控件只留每天用的；菜单去掉重复入口。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 沉浸不隐藏系统栏 | **采纳，P0** | 一个 effect + onDispose 恢复 |
| U2 + D2 + E2 | 模式行常驻三个按钮 | **采纳，P1** | 滚动/翻页进菜单，显示当前模式 |
| U3 + D3 + E3 | 菜单字号 ± 与排版重复 | **采纳，P1** | 删两项，18 → 17 |
| U4 + D4 + E4 | 沉浸底部贴边 | **采纳，P2** | 固定 12dp 间距 |

## 2. 实施清单

### 2.1 真沉浸（P0）

- [ ] `DisposableEffect(immersive)`：进入 hide(systemBars)，退出 show；
- [ ] `systemBarsBehavior = BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE`；
- [ ] `onDispose` 恢复系统栏（仅沉浸时）；
- [ ] 沉浸提示/按钮底部固定 12dp。

### 2.2 模式行（P1）

- [ ] 删除模式行的「滚动/翻页」按钮；
- [ ] 菜单「阅读」组加「翻页模式 / 滚动模式」，点击切换；
- [ ] 查询模式 ◀ ▶ 保留。

### 2.3 菜单去重（P1）

- [ ] 删除 `FONT_DECREASE` / `FONT_INCREASE` 及菜单项；
- [ ] `ReaderMenuTest` 更新为 17 项；
- [ ] 字号仍由排版 Sheet 调整。

### 2.4 版本与文档

- [ ] `versionCode = 50`，`versionName = "1.5.0"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不做边缘点击翻页、自动隐藏、全屏手势。
- 不改分页、翻译、书签、搜索、排版 Sheet。
- 不改系统栏图标颜色逻辑。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥258 tests，0 failures；ReaderMenuTest 17 项 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 50 |
| 用户 | 沉浸真全屏、模式行更短、菜单不再重复 |
| 恢复 | 退出沉浸/离开阅读器系统栏恢复 |
| 发布 | 提交 + tag `v1.5.0` + 推送 |

## 5. 回滚

改动集中在 `ReaderRoute`、`ReaderMenu`、`ReaderComponents` 与测试；无迁移。
`git revert` 单提交即可。
