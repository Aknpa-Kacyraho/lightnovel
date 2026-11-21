# Round 23 · 统一升级指南（v1.8.1）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：状态要诚实；正文要干净；备份只包含当前数据。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 | 单段重译掩盖整章过期 | **采纳，P1** | sidecar 保留旧版本字段 |
| U2 + D2 + E2 | EPUB 注音混入正文 | **采纳，P2** | `stripHtml` 移除 `<rt>/<rp>` |
| U3 + D3 + E3 | 备份包含 `.bak-*` 目录 | **采纳，P2** | 路径级过滤 |

## 2. 实施清单

### 2.1 单段重译 sidecar（P1）

- [ ] 新增 `retranslatedParagraphSidecar` 纯函数（只改内容字段）。
- [ ] `retranslateParagraph` 使用该函数，不再覆盖配置/术语字段。
- [ ] `ParagraphRetranslationSidecarTest` 断言旧 hash 保留。

### 2.2 EPUB 注音（P2）

- [ ] `stripHtml` 先移除 `<rt>` / `<rp>`；改为 `internal`。
- [ ] `LocalTextParserTest` 覆盖汉字+注音、含 `<rp>` 括号两种。

### 2.3 备份路径（P2）

- [ ] 新增 `isExportableRelativePath(rel)`；过滤 `.bak-` 目录、cache、临时文件。
- [ ] `filesUnder` 使用该函数。
- [ ] `BackupFilesTest` 覆盖 4 种路径。

### 2.4 版本与文档

- [ ] `versionCode = 60`，`versionName = "1.8.1"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改术语表/翻译流程/EPUB 排版。
- 不删除本地 `.bak-*` 目录。
- 不改备份格式与 manifest 校验。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥302 tests，0 failures；新增 sidecar/注音/路径用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 60 |
| 用户 | 单段重译仍提示过期；EPUB 无注音；备份无 `.bak-` |
| 发布 | 提交 + tag `v1.8.1` + 推送 |

## 5. 回滚

改动集中在 `TranslationService.kt`、`LocalTextParser.kt`、`BackupExporter.kt` + 测试；
无 DB 迁移。`git revert` 单提交即可。
