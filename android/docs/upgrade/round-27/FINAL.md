# Round 27 · 统一升级指南（v1.9.0）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：先统一尺度，再谈风格；不靠装饰制造「设计感」。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E2 | 字号行高各自为政 | **采纳，P1** | 注入 `LnTypography` |
| U2 + D2 + E4 | 圆角尺度混乱 | **采纳，P1** | 五档 `LnShapes` + 标签例外 |
| U3 + D3 + E5 | 描边过重 | **采纳，P2** | 0.35 / 0.5，无新增阴影 |

## 2. 实施清单

### 2.1 排版（P1）

- [ ] 新增 `ui/theme/LnTypography.kt`，覆盖 9 个常用角色。
- [ ] `LightnovelTheme` 注入 `typography = LnTypography`。
- [ ] `ThemeTokensTest` 断言正文字号/行高与标题字重。

### 2.2 形状（P1）

- [ ] 新增 `ui/theme/LnShapes.kt`（4/8/12/16/20）。
- [ ] `LightnovelTheme` 注入 `shapes = LnShapes`。
- [ ] 替换 `BookCover` / `BrandChips` / `SettingsScreen` / `ChapterListScreen` /
      `QuerySheet` / `ReaderRoute` 的硬编码圆角。

### 2.3 描边（P2）

- [ ] 书架列表卡 0.6 → 0.35。
- [ ] 设置分组卡 → 0.5。
- [ ] 章节列表同类卡 → 0.35。

### 2.4 版本与文档

- [ ] `versionCode = 64`，`versionName = "1.9.0"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改变信息架构、布局结构、交互。
- 不改主题配色、阅读器纸色。
- 不改按钮的胶囊形状；不改数据层。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥316 tests，0 failures；新增 token 测试 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 64 |
| 用户 | 排版节奏一致；圆角有规律；描边不抢正文 |
| 发布 | 提交 + tag `v1.9.0` + 推送 |

## 5. 回滚

改动集中在 `ui/theme`、6 个 UI 文件 + 测试；无数据迁移。
`git revert` 单提交即可。
