# Round 18 · 统一升级指南（v1.6.2）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：三个小修复，全部不产生视觉变化。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 退出丢最后一页 | **采纳，P1** | `UNDISPATCHED` + `NonCancellable` |
| U2 + D2 + E2 | 筛选切换闪一下 | **采纳，P2** | 一次 copy 的 `applyShelfFilter` |
| U3 + D3 + E3 | 书名翻译重复请求 | **采纳，P2** | Mutex + 缓存过滤 |

## 2. 实施清单

### 2.1 进度抗取消（P1）

- [ ] `onPageChanged` / `onScrollParagraphChanged` 的写入改为
      `launch(start = UNDISPATCHED) { withContext(NonCancellable) { ... } }`。
- [ ] 保留 `saveJob?.cancel()` 防止堆积。

### 2.2 筛选原子更新（P2）

- [ ] `LibraryViewModel.applyShelfFilter(shelf)` 一次 copy（shelf + 清收藏/已移出）。
- [ ] `LibraryScreen` 书架下拉只调用一次；空态清除保持现有多项（不改）。

### 2.3 标题翻译去重（P2）

- [ ] `MetadataTranslationService` 加 `Mutex.tryLock`，并发请求直接返回。
- [ ] 过滤 `cardCache` 已有 `titleZh` 的书。
- [ ] 成功后写内存缓存。

### 2.4 版本与文档

- [ ] `versionCode = 55`，`versionName = "1.6.2"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改进度防抖策略、不改筛选 UI、不重写翻译管线。
- 不做旧数据迁移。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥270 tests，0 failures |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 55 |
| 用户 | 退出不丢页、筛选不闪、标题不重复请求 |
| 发布 | 提交 + tag `v1.6.2` + 推送 |

## 5. 回滚

改动集中在 `ReaderViewModel`、`LibraryViewModel`、`LibraryScreen`、
`MetadataTranslationService`；无迁移。`git revert` 单提交即可。
