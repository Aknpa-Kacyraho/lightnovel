# Round 28 · 统一升级指南（v1.9.1）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：书架是书单，不是卡片墙；封面要像书；设置靠标题分组。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 书架卡片海 | **采纳，P1** | `BookRow` 去卡片 + 细线 |
| U2 + D2 + E2/E3 | 封面比例不像书 | **采纳，P2** | 统一 2:3，标签收敛 |
| U3 + D3 + E4 | 设置七连卡片 | **采纳，P2** | 分组标题 + 无卡片内容 |

## 2. 实施清单

### 2.1 书架（P1）

- [ ] `BookRow` 删除 `Card`，改为 `Column + Row + HorizontalDivider`。
- [ ] 封面 48×72；标题 `titleMedium`；meta `bodySmall`。
- [ ] 进度改 2dp 自绘线（track 0.12 / fill 0.35）。
- [ ] `LazyColumn` 水平 padding 0、垂直 8、`spacedBy(0)`。

### 2.2 封面与发现（P2）

- [ ] 推荐卡 140×210；结果卡封面 60×90。
- [ ] 结果卡标签最多 2 个 + `+N` 文本。
- [ ] 检查横向推荐列表高度变化。

### 2.3 设置（P2）

- [ ] `SettingsGroup` 去 Card；标题 `labelLarge` primary；内容透明底。
- [ ] `highlighted` 用 `primaryContainer` 0.35 的圆角底，只包内容。
- [ ] `ThemePreviewCard` 保留卡片。

### 2.4 版本与文档

- [ ] `versionCode = 65`，`versionName = "1.9.1"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改导航、数据、交互逻辑。
- 不改主题配色与阅读器纸色。
- 不新增图片封面加载。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥316 tests，0 failures |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 65 |
| 用户 | 书架像书单；封面 2:3；设置不像仪表盘 |
| 发布 | 提交 + tag `v1.9.1` + 推送 |

## 5. 回滚

改动集中在 `LibraryScreen`、`DiscoverScreen`、`SettingsScreen`；无数据迁移。
`git revert` 单提交即可。
