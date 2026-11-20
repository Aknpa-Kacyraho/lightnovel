# Round 5 · 设计师视角升级指南（v1.2.1）

> 目标：深色模式从「能用」变成「耐看」。只调明度与容器混合，不动色相。

## 1. 设计问题

### D1. 深色的层级被拉平（P0）

Material 的深色规范默认次要文字很亮（`#CAC4D0` 级别），在手机上会把
「作者/进度/说明」推到与标题同一亮度带。8 套主题全部继承了这个倾向。

**方案**：8 套 dark 的 `onSurfaceVariant` 统一降低约 12% 明度：

| 主题 | 现在 | 调整后 |
| --- | --- | --- |
| 青灯 | `#C0C8C9` | `#A9B2B3` |
| 紫夜 | `#CAC4D3` | `#B4AEBE` |
| 樱纸 | `#D7C1C6` | `#C0ACB1` |
| 苔庭 | `#C5C7B8` | `#AEB0A2` |
| 琥珀 | `#D0C6B6` | `#B8AF9F` |
| 靛蓝 | `#C6C5D0` | `#AFAEB9` |
| 墨灰 | `#C6C7C5` | `#AFB0AE` |
| 枫烬 | `#D2C4BB` | `#BBADA4` |

目标对比度：对 `surface` **7.5–9.5:1**；`onSurface` 保持 ≥12:1。
浅色主题不动。

### D2. 标签容器像荧光贴纸（P1）

`toScheme` 的 dark 容器混合 `0.30`，在深色底上形成高饱和块。
标签出现频率高（书架、发现、大书库、详情），叠加后很吵。

**方案**：dark 容器混合 `0.30 → 0.24`；light 保持 `0.14`。
只影响 `secondaryContainer`、`tertiaryContainer`、`errorContainer`。

### D3. 卡片描边太亮（P1）

深色下每张卡都有一圈 `outlineVariant` 亮边。书架 20 本书就是 20 个框。

**方案**：
- 书架 `ContinueCard`、`BookRow`、任务 `TaskCard` 显式
  `containerColor = surfaceContainerLow`，描边 `outlineVariant.copy(alpha = 0.6f)`；
- 设置页的 `SettingsGroup` 是分组容器，保留现有完整描边（它是页面结构，不是列表项）；
- 详情页/发现页的 Card 不改（本来就没有描边）。

### D4. 不改的东西

- 8 套主题的 primary/secondary/tertiary 色相；
- 浅色主题；
- 状态色（`LnExtendedColors` 仍从主题派生）；
- 卡片圆角与间距。

## 2. 验收

- [ ] 8 套深色主题：`onSurfaceVariant` vs `surface` 在 7.5–9.5:1。
- [ ] `onSurface` vs `surface` ≥12:1。
- [ ] 深色标签容器肉眼可见变柔和，文字对比度仍 ≥4.5:1。
- [ ] 书架与任务卡不再有亮边框，卡片仍能与背景区分。
- [ ] 浅色模式截图与 1.2.0 一致（无变化）。
