# Round 1 · 统一升级指南（v1.0.4）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：先修「用户会踩的坑」，再修「工程会复发的债」；能用一处改动同时满足
> 用户与工程的，合并实施；纯审美项一律推迟。
> 状态：**已实施并通过验证**，详见 `SELF-REVIEW.md`。

## 1. 三方指南合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 | 任务忽略不可撤销 | **采纳，P0** | 用户会误触，且无恢复入口；一个 Snackbar 同时解决信任与操作 |
| U2 + E2 | 阅读器无无障碍语义、未 performClick | **采纳，P0** | 同一处代码；lint 与真实 TalkBack 都受影响 |
| U4 | 备份提醒路径不清 | **采纳文案，P1** | 只改一句话，零风险 |
| D3 | 任务动作权重相同 | **部分采纳，P1** | 只补语义标签，不改颜色体系 |
| U5 + D4 | 空态三按钮无主次 | **推迟到 Round 2** | 需要重新设计空态，不与本轮混合 |
| E1 | 文档/版本漂移 | **采纳，P0** | 发布前必须可追溯 |
| E3 | mipmap 冗余 + 装箱状态 | **采纳，P2** | 低风险，顺手清 lint |
| E4 | TaskIgnoreStore 无测试 | **采纳，P1** | 忽略变成可撤销后，存储正确性更关键 |
| E5 | 阅读器测试盲区 | **推迟到 Round 2/3** | 需要单独设计测试夹具，不能赶工 |

## 2. 实施清单（已完成）

### 2.1 版本与文档

- [x] `android/app/build.gradle.kts`：`versionName = "1.0.4"`，`versionCode = 38`。
- [x] 新增 `android/CHANGELOG.md`，补 1.0.1 / 1.0.2 / 1.0.3 / 1.0.4。
- [x] `android/docs/redesign/04-final.md` 补 §8.1（1.0.2–1.0.4）。
- [x] `README.md` 当前版本改为 1.0.4，补本轮用户可见变化。
- [x] 新增 `android/docs/upgrade/` 三轮档案（本目录 + `PROGRESS.md`）。

### 2.2 任务页忽略可撤销

- [x] `TaskCenterScreen` 增加 `SnackbarHostState` 与 `SnackbarHost`。
- [x] 忽略后显示「已忽略第 N 话，只从列表隐藏」+「撤销」；撤销调用 `viewModel.unignore(task)`。
- [x] 「取消」补语义「取消，停止正在进行的翻译」；「忽略」补语义
      「忽略，只从列表隐藏，不删除译文」。
- [x] 新增 `TaskIgnoreStoreTest`（Robolectric）：写入、去重、定向清除、缺失键、损坏分隔符。

### 2.3 阅读器无障碍

- [x] `ReaderPageView.onTouchEvent` 在未滑动点击时调用 `performClick()`；
      `handleTap` 不再重复调用。
- [x] 每页写入 `contentDescription = "第 x 页，共 y 页"`（`ReaderRoute` 的 `AndroidView`）。
- [x] 未改变现有触摸行为（查询模式点词、Pager 翻页保持原样）。

### 2.4 lint 清理

- [x] `mipmap-anydpi-v26` 合并到 `mipmap-anydpi`（minSdk 26）。
- [x] `ChapterListScreen` → `mutableIntStateOf`。
- [x] `reader/ReaderScreen.kt` → `mutableFloatStateOf`。
- [x] `StoryMemoryScreen` → `mutableIntStateOf`。

## 3. 非目标（明确不做）

- 不重做书架空态、不做设置深链、不做翻译费用预估（Round 2）。
- 不拆 `ReaderViewModel`、不做整页正文语义、不做全量 Compose UI 测试（Round 3）。
- 不改主题色、不改导航、不改翻译管线、不新增依赖。
- 不为了让 lint 归零而改 `UseKtx` / 依赖升级；这些不是缺陷。

## 4. 验收结果

| 项 | 标准 | 结果 |
| --- | --- | --- |
| 测试 | JVM tests ≥168，0 failures | **178 / 0 / 1 skipped** |
| lint | 0 errors；三个目标 id 消失 | **0 errors / 22 warnings**，目标 id 全为 0 |
| 构建 | `assembleDebug` 成功 | 成功 |
| 用户 | 忽略 → Snackbar → 撤销 → 任务恢复 | 代码与状态流验证；真机待补 |
| 无障碍 | TalkBack 能听到页码 | 语义已写入；真机待补 |
| 发布 | 提交 + tag `v1.0.4` + 推送 | 待执行 |

## 5. 回滚

代码改动集中在 8 个文件 + 1 个测试 + 文档；如需回滚，`git revert` 单个提交即可，
无数据库迁移、无备份格式变化、无用户资产写入。
