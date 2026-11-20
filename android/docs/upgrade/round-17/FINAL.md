# Round 17 · 统一升级指南（v1.6.1）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：竞态用取消解决，跨章用一次性锚点解决，提示用替换解决。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 快速切换显示错内容 | **采纳，P1** | `loadJob` 取消 + `ensureActive` |
| U2 + D2 + E2 | 跨章跳转只到章首 | **采纳，P1** | `PendingReaderJump` 一次性锚点 |
| U3 + D3 + E3 | 提示延迟叠加 | **采纳，P2** | `collectLatest` |

## 2. 实施清单

### 2.1 加载竞态（P1）

- [ ] `ReaderViewModel` 增加 `loadJob`，`load()` 先取消旧请求。
- [ ] IO 返回后 `ensureActive()`，取消的请求不写 `_state`。

### 2.2 跨章跳转（P1）

- [ ] 新增 `PendingReaderJump`（put/take/clear），挂到 `AppContainer`。
- [ ] `ReaderRoute` 跨章跳转前写入锚点，再 `onOpenChapter`。
- [ ] 目标章加载完成（非 loading、无 error）时 take 并 `jumpToAnchor`。
- [ ] `PendingReaderJumpTest` 覆盖覆盖写、take 清除、clear。

### 2.3 提示（P2）

- [ ] `bookmarkNotice` 收集改用 `collectLatest`。

### 2.4 版本与文档

- [ ] `versionCode = 54`，`versionName = "1.6.1"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不重写加载/分页、不做跨书跳转、不改书签/搜索 UI。
- 不持久化 pending 锚点（进程级）。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥264 tests，0 failures；新增 pending 用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 54 |
| 用户 | 快速切换最终一致、跨章跳到段、提示不叠加 |
| 发布 | 提交 + tag `v1.6.1` + 推送 |

## 5. 回滚

改动集中在 `ReaderViewModel`、`ReaderRoute`、新增 `PendingReaderJump` + 测试；无迁移。
`git revert` 单提交即可。
