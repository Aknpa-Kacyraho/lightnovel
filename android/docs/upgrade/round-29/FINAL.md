# Round 29 · 统一升级指南（v1.9.2）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：纸色要像纸，夜间要像夜；提示层不能比正文更亮。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 夜间黑硬、正文刺眼 | **采纳，P1** | 暖灰黑 + 降一档正文 |
| U2 + D1 + E1 | 纸白冷、护眼绿 | **采纳，P2** | 四套纸色重定 |
| U3 + D2 + E2 | 警告条亮橙突兀 | **采纳，P2** | 纸色 + 琥珀派生 |
| — + D3 + E3 | 阅读器 Sheet 28dp | **采纳，P2** | 统一 20dp |

## 2. 实施清单

### 2.1 纸色（P1）

- [ ] `ReaderTheme` 四套背景/正文/次要文字更新；`AUTO` 占位同步。
- [ ] `danger` 保持现有值。

### 2.2 警告条（P2）

- [ ] `StaleBanner` 用 `lerp(theme.background, warning, 0.16/0.12)`。
- [ ] 圆角 `MaterialTheme.shapes.small`。
- [ ] 文案/按钮不变。

### 2.3 Sheet（P2）

- [ ] 8 个阅读器 `ModalBottomSheet` 加 20dp 顶角。
- [ ] 补 `RoundedCornerShape` import。

### 2.4 版本与文档

- [ ] `versionCode = 66`，`versionName = "1.9.2"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改字号、行距、分页、警告触发条件。
- 不改其他页面 Sheet。
- 不新增纸色/主题。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥316 tests，0 failures |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 66 |
| 用户 | 夜间久读不刺眼；纸色像纸；警告条不抢正文 |
| 发布 | 提交 + tag `v1.9.2` + 推送 |

## 5. 回滚

改动集中在 `ReaderTheme.kt`、`ReaderComponents.kt`、8 个 Sheet 文件 + 测试；
无数据迁移。`git revert` 单提交即可。
