# Round 22 · 统一升级指南（v1.8.0）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：导入是补齐，不是重置；现有数据优先，文件与 DB 都不能被旧备份冲掉。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E2 | 重复导入覆盖书名/标签 | **采纳，P1** | `mergeBook` 现有非空优先 |
| U2 + D2 + E3 | 重复导入回退进度 | **采纳，P1** | `mergeReadState` 按 `updated_at` 取新 |
| U3 + D3 + E4 + E5 | 重复导入丢章节文件/元数据 | **采纳，P1** | 目录合并 + `missingChapters` |

## 2. 实施清单

### 2.1 纯函数（P1）

- [ ] 新增 `ImportMerge.kt`：`mergeBook` / `mergeReadState` / `missingChapters`。
- [ ] `ImportMergeTest` 覆盖新书、已存在书、较新/较旧状态、缺失章节。

### 2.2 接入 apply（P1）

- [ ] `BackupImportService.apply` 先查现有书/状态/章节。
- [ ] 书：`mergeBook(existing, planned, chapterCount)`。
- [ ] 状态：`mergeReadState(existing, plannedState)`；`favorite` 并集、`hidden` 保留。
- [ ] 章节：`missingChapters(plan.chapters, existingKeys)` 后再构造实体。

### 2.3 文件目录合并（P1）

- [ ] `LibraryCommitter` 目标目录存在且内容不同时改为逐文件合并：
      只复制本地缺失文件，现有文件不移动、不覆盖。
- [ ] `CommitResult` 增加 `merged` 计数；首次导入路径不变。
- [ ] `LibraryCommitterTest` 覆盖「保留现有 `zh/`，补缺失 `raw/0002.txt`」。

### 2.4 回归（P1）

- [ ] `ImportCoordinatorTest`：第一次导入 → 改书名/章节名/进度 → 第二次导入，
      断言修改仍在；`again.applied.chapters == 0`。

### 2.5 版本与文档

- [ ] `versionCode = 59`，`versionName = "1.8.0"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改备份格式、导入 UI、staging 解压顺序。
- 不做「选择恢复哪一版进度」的交互。
- 不覆盖现有同名文件；备份中内容不同的同名文件不会替换本地。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥300 tests，0 failures；新增合并/文件/回归用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 59 |
| 用户 | 重复导入不退化书名/标签、不回退进度、不丢章节文件与信息 |
| 发布 | 提交 + tag `v1.8.0` + 推送 |

## 5. 回滚

改动集中在 `BackupImportService.kt`、`LibraryCommitter.kt`、新增
`ImportMerge.kt` + 测试；无 DB 迁移。`git revert` 单提交即可。
