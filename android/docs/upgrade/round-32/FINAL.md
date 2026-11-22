# Round 32 · 统一升级指南（v1.9.5）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：进度不近似、完整不降级、一书一身份、旧备份可见、缓存可失效。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 非连续 idx 进度回退 | **采纳，P1** | `continueChapterIndex` |
| U2 + D2 + E2 | Partial 覆盖完整译文 | **采纳，P1** | complete 时拒绝覆盖 |
| U3 + D3 + E3 | 唯一键冲突产生孤儿 | **采纳，P0/P1** | 多键匹配 + id 重映射 |
| U4 + D4 + E4 | 旧备份目录不完整 | **采纳，P2** | 按 episodes 合成占位 |
| U5 + D5 + E5 | 缓存回滚润色结果 | **采纳，P2** | `TranslationStore.invalidate` |
| U6 + D6 + E6 | 清除筛选关闭已移出 | **采纳，P2** | 只清有值条件 |
| U7 + D7 + E7 | 预览错误串书 | **采纳，P2** | `preview()` 清空 |

## 2. 实施清单

### 2.1 进度与翻译（P1）

- [ ] `continueChapterIndex` 纯函数 + 测试（1,2,3,50）。
- [ ] `TranslationService.commit` 保护 complete 旧译文 + 测试。
- [ ] `TranslationStore.invalidate`；润色/单段 commit 后调用 + 测试。

### 2.2 导入身份与旧备份（P0/P1/P2）

- [ ] `ImportPlan.remapBookIds`；`ImportCoordinator` 多键匹配 + overrides。
- [ ] `apply` 旧备份按 `episodes` 合成 `online` 占位章节（上限 5000）。
- [ ] 测试：同 hash 不同 id 合并；旧备份无 chapters.json 的在线书。

### 2.3 UI（P2）

- [ ] `LibraryScreen` 清除按钮只调用有值的 setter。
- [ ] `DiscoverViewModel.preview()` 清空 `previewError`；失败仅预览时设置；
      `runCatchingCancellable`。

### 2.4 版本与文档

- [ ] `versionCode = 69`，`versionName = "1.9.5"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不做源站章节重排/删除同步。
- 不改备份 format；`data/chapters.json` 仍可选。
- 不新增恢复旧译文按钮（Partial 保护优先）。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥335 tests，0 failures；新增进度/合并/旧备份/缓存用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 69 |
| 用户 | 进度不丢、完整不降级、不重复、旧备份目录可见、润色不被回滚 |
| 发布 | 提交 + tag `v1.9.5` + 推送 |

## 5. 回滚

改动集中在 `data/translation`、`data/import`、`data/local`、`feature/chapters`、
`feature/library`、`feature/discover`；无 DB schema 变化。`git revert` 单提交即可。
