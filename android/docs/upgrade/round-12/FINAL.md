# Round 12 · 统一升级指南（v1.4.2）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：把「调排版」和「跳页」留在阅读界面，但不让它们破坏位置与性能。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + D2 + E1 | 阅读中不能调排版 | **采纳，P0** | 复用现有 setter，加 Sheet |
| U2 + D3 + E3 + E4 | 进度不能拖 | **采纳（翻页），P1** | 纯函数 + Slider，滚动模式不动 |
| U3 + D4 + E2 | 调排版丢位置 | **采纳，P1** | 分页前捕获锚点 |
| U4 | 恢复默认 | **采纳，P2** | 四项回默认并持久化 |

## 2. 实施清单

### 2.1 进度换算（P1）

- [ ] `ReaderProgress.kt` 加 `progressToPage` / `pageToProgress`。
- [ ] `ReaderProgressTest` 补 0 页、1 页、首末、往返。

### 2.2 位置保持（P1）

- [ ] ViewModel 加 `captureAnchorForRepagination()`，四个排版 setter 开头调用。
- [ ] 分页完成清空 `anchorToRestore`（已有）。

### 2.3 排版 Sheet（P0）

- [ ] `TypographySheet`：字号 / 行距 / 边距 / 段距四滑块 + 恢复默认。
- [ ] 滑块本地状态，`onValueChangeFinished` 才回调。
- [ ] 菜单「阅读」组加「排版」。

### 2.4 底栏拖动（P1）

- [ ] `ReaderBottomBar` 增加 `pageIndex/pageCount/onSeekPage`。
- [ ] 翻页模式用 `Slider`（2dp 轨道 + 8dp thumb + 20dp 高度）。
- [ ] 拖动显示「第 x / y 页」，松手 `onPageChanged`。
- [ ] 滚动模式保持原细线。

### 2.5 版本与文档

- [ ] `versionCode = 49`，`versionName = "1.4.2"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不做字体选择、排版预设、滚动模式拖拽。
- 不改分页算法与设置页排版项。
- 不改书签/搜索。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥239 tests，0 failures；新增进度换算用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 49 |
| 用户 | 阅读中可调四项、可拖进度、位置不丢、可恢复默认 |
| 视觉 | 底栏高度不变，thumb 不压页码 |
| 发布 | 提交 + tag `v1.4.2` + 推送 |

## 5. 回滚

改动集中在 `ReaderProgress`、`ReaderViewModel`、`ReaderComponents/Route`、新增 Sheet；
无数据迁移。`git revert` 单提交即可。
