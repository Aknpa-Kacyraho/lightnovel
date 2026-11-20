# Round 15 · 统一升级指南（v1.5.2）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：同维度选项收进一个控件；长菜单换容器；功能与顺序一个不丢。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 书架 7 个 chips | **采纳，P1** | 三个书架状态收进下拉 |
| U2 + D2 + E2 | 阅读器长下拉 | **采纳，P1** | 换 BottomSheet，分组完整 |
| U3 | 设置页太长 | **推迟** | 先观察本轮反馈 |

## 2. 实施清单

### 2.1 书架筛选（P1）

- [ ] 删除「全部/在读/想读/读完」四个 chip；
- [ ] 新增「书架：全部/在读/想读/读完」下拉 chip；
- [ ] 切换时清 `favoritesOnly` 与 `removedOnly`（与旧「全部」一致）；
- [ ] 保留收藏 / 已移出 / 排序。

### 2.2 阅读器菜单 Sheet（P1）

- [ ] 新增 `ReaderMenuSheet`：`ModalBottomSheet` + 组标题 + `LazyColumn`（70% 高）；
- [ ] `TranslationMenu` 用 Sheet 替换 `DropdownMenu`；
- [ ] 16 项顺序/禁用条件不变；点击关闭并执行；
- [ ] `ReaderMenuTest` 仍为 16/15 项。

### 2.3 版本与文档

- [ ] `versionCode = 52`，`versionName = "1.5.2"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不做设置页折叠/搜索、不做发现页筛选折叠。
- 不改筛选、排序、菜单业务回调。
- 不改书架卡片与阅读器其它 Sheet。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥258 tests，0 failures |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 52 |
| 用户 | 书架 4 个筛选控件；阅读器菜单为可滚动 Sheet |
| 发布 | 提交 + tag `v1.5.2` + 推送 |

## 5. 回滚

改动集中在 `LibraryScreen`、`ReaderComponents`、新增 `ReaderMenuSheet`；无迁移。
`git revert` 单提交即可。
