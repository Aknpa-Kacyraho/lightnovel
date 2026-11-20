# Round 6 · 统一升级指南（v1.2.2）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：阅读手势只加一个（单击切换沉浸），进度只加两条 2dp 细线；
> 不重排导航、不改翻译逻辑。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 沉浸只能从菜单进 | **采纳，P1** | 单击正文切换，查询模式优先 |
| U2 + D3 + E2 | 底栏没有本章进度 | **采纳，P1** | 2dp 细线 + 纯函数进度 |
| U3 + D4 + E3 | 继续阅读卡无进度 | **采纳，P2** | 与列表卡一致，更淡 |
| U4 + D2 + E4 | 沉浸无退出提示 | **采纳，P2** | 3 秒轻提示，不阻塞 |
| — | 点击左右区域翻页 | **不做** | Pager 已支持滑动，避免误触 |

## 2. 实施清单

### 2.1 单击切换沉浸（P1）

- [ ] `ReaderPageView` 增加 `onCenterTap`；查询模式点词优先，点空白不切换。
- [ ] `ReaderRoute` 的 `AndroidView.update` 接线 `{ immersive = !immersive }`。
- [ ] 保留底部「退出沉浸」按钮。

### 2.2 进度纯函数（P1）

- [ ] 新增 `ReaderProgress.kt`：`readerChapterProgress(...)`、`shelfProgress(...)`。
- [ ] 新增 `ReaderProgressTest`：翻页首末、滚动首末、0 页/0 段/0 话、越界。

### 2.3 两条进度线（P1/P2）

- [ ] `ReaderBottomBar` 加 2dp 进度线：已读 `textColor.copy(alpha = 0.28f)`，
      轨道透明，全宽。
- [ ] `ContinueCard` 加 2dp 进度线：`primary.copy(alpha = 0.45f)`。
- [ ] 不改字号、间距与按钮顺序。

### 2.4 沉浸提示（P2）

- [ ] 进入沉浸显示 3 秒「单击正文或点底部按钮退出沉浸」，`labelSmall`。
- [ ] 退出立即清除提示。

### 2.5 版本与文档

- [ ] `versionCode = 43`，`versionName = "1.2.2"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不做左右点击翻页、不做自动隐藏定时器。
- 不改顶栏/底栏功能项、不改菜单、不改翻译状态。
- 不做选词/复制正文。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥199 tests，0 failures；新增 `ReaderProgressTest` |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 43 |
| 用户 | 单击正文切换沉浸；首次有退出提示；底栏有进度 |
| 设计 | 2dp 细线不抢正文；查询模式不误触 |
| 发布 | 提交 + tag `v1.2.2` + 推送 |

## 5. 回滚

改动集中在 `ReaderPageView`、`ReaderRoute`、`ReaderComponents`、`LibraryScreen` +
1 个纯函数/测试；无数据迁移。`git revert` 单提交即可。

## 6. 三轮收束（Round 4–6）

- Round 4 解决「刺眼与常驻提示」；Round 5 解决「深色层级与眩光」；
  Round 6 解决「界面感太强、进度不可见」。
- 三轮均为视觉/交互层改动，未触碰翻译管线、Room、备份格式。
