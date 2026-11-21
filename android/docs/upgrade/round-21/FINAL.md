# Round 21 · 统一升级指南（v1.7.2）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：过期提示只对「术语真的变了」负责；翻译时的事实不能被事后覆盖。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 + E3 | 摘要变化误报术语过期 | **采纳，P1** | 独立 `glossaryRevision` + `glossaryOutdated` |
| U2 + D2 + E2 | 翻译后追平掩盖术语变更 | **采纳，P1** | sidecar 记录 `glossary_hash`，sync 不覆盖 |
| U3 + D3 + E4 | 简介为空永不补翻 | **采纳，P2** | 缓存命中要求源简介非空时译文也非空 |

## 2. 实施清单

### 2.1 纯术语版本（P1）

- [ ] `StoryMemoryStore.glossaryRevision(memory)`；`revision(memory)` 输出不变。
- [ ] `StoryMemoryGlossaryRevisionTest`：术语变 / 人物变 / 空术语。

### 2.2 sidecar 字段（P1）

- [ ] `ChapterSidecar` 新增 `glossary_hash`（`String? = null`）。
- [ ] `TranslationConfig.glossaryHash`；`toTranslationConfig` 填充。
- [ ] `ChapterTranslator.sidecar`、`polishChapter`、`retranslateParagraph` 写入。
- [ ] `syncSidecarRevision` 只更新 `storyRevision` 与 `translationConfigHash`。

### 2.3 过期判定（P1）

- [ ] 新增 `glossaryOutdated(...)` 纯函数。
- [ ] `ReaderViewModel` 维护 `currentGlossaryHash`，`staleReasons` 使用新函数。
- [ ] `TranslationFreshnessTest` 覆盖新/旧字段四个分支。

### 2.4 元数据缓存（P2）

- [ ] `translateBook` 缓存条件加入「源简介非空 → 缓存简介必须非空」。
- [ ] `MetadataTranslationServiceTest` 新增两次调用补简介用例。

### 2.5 版本与文档

- [ ] `versionCode = 58`，`versionName = "1.7.2"`。
- [ ] `CHANGELOG.md`、`README.md`、`04-final.md` §8.1、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不改术语表 UI 与编辑流程。
- 不强制重译历史章节；旧 sidecar 保持旧判定。
- 不改元数据翻译 prompt 与字段。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥283 tests，0 failures；新增版本/判定/元数据用例 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 58 |
| 用户 | 摘要不误报；翻译中改术语会提示；简介可补翻 |
| 发布 | 提交 + tag `v1.7.2` + 推送 |

## 5. 回滚

改动集中在 `StoryMemoryStore`、`ChapterSidecar`、`TranslationConfig`、
`ChapterTranslator`、`TranslationService`、`ReaderViewModel`、
`MetadataTranslationService` + 测试；无 DB 迁移。`git revert` 单提交即可。
