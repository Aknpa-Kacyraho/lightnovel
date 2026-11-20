# Android 升级进度

> 基线：`main` Android-only。升级分三批：
> 1.0.4–1.1.1 可用性；1.2.0–1.2.2 视觉疲劳；1.3.0–1.3.2 翻译与书库。

## 轮次总览

| 轮次 | 版本 | 主题 | 指南 | 自检 | 发布 |
| --- | --- | --- | --- | --- | --- |
| Round 1 | 1.0.4（38） | 误触可撤销、阅读器无障碍、lint 清理 | ✅ | ✅ | ✅ [v1.0.4](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.0.4) |
| Round 2 | 1.1.0（39） | 空态主次、设置深链、菜单分组 | ✅ | ✅ | ✅ [v1.1.0](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.1.0) |
| Round 3 | 1.1.1（40） | 横屏限宽、大字体换行、翻译字数、长章节提示 | ✅ | ✅ | ✅ [v1.1.1](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.1.1) |
| Round 4 | 1.2.0（41） | 纸色跟随系统、未翻译横幅降噪、夜间调光 | ✅ | ✅ | ✅ [v1.2.0](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.2.0) |
| Round 5 | 1.2.1（42） | 深色次要文字降亮、标签降饱和、卡片去亮框 | ✅ | ✅ | ✅ [v1.2.1](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.2.1) |
| Round 6 | 1.2.2（43） | 单击正文沉浸、底栏进度线、继续阅读进度 | ✅ | ✅ | ✅ [v1.2.2](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.2.2) |
| Round 7 | 1.3.0（44） | 本地导入去重、书架排序、数据库 v4 | ✅ | ✅ | ⏳ |
| Round 8 | 1.3.1（45） | 单段重译指纹、费用预估、队列重试 | ✅ | ⏳ | ⏳ |
| Round 9 | 1.3.2（46） | 已移出书彻底删除、删除前停后台 | ✅ | ⏳ | ⏳ |

## 约束

- `main` 只维护 Android App，不重新引入 `lightnovel/`、Python 服务或 Web。
- 每个版本使用新的 `versionCode` / `versionName`；不改写既有 Release。
- 面向用户文案使用简体中文；触控目标 ≥44dp；深浅色与 8 套主题都不写死颜色。
- 用户资产（书籍、译文、术语、世界线、进度、备份）不因升级丢失。
- 每轮验证：

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

## 历史摘要（Round 1–6）

- 1.0.4：任务忽略可撤销、阅读器页码语义、lint 三件套、`TaskIgnoreStoreTest`。
- 1.1.0：空态两条路径、备份提醒直达数据分组、菜单四组、任务筛选带数量。
- 1.1.1：横屏 680dp、FlowRow、翻译字数、长章节提示、`PrimaryTabRow`。
- 1.2.0：`ReaderTheme.AUTO` 跟随系统、未翻译横幅降噪、夜间正文 `#BDBAB2`。
- 1.2.1：8 套深色 `onSurfaceVariant` 7–10:1、容器 0.24、卡片去亮框。
- 1.2.2：单击正文沉浸、底栏/继续阅读进度线、首次沉浸提示。

## Round 7（已发布）

- 指南：`round-7/`；自检：`round-7/SELF-REVIEW.md`
- 版本：1.3.0 / 44
- 变更：
  - 数据库 v4：`books.import_hash` + 唯一索引 + `MIGRATION_3_4`。
  - 本地导入按 SHA-256 去重；重复导入提示已存在，已移出的书恢复。
  - 书架排序：标题 / 最近阅读 / 最近添加，`SettingsStore.librarySort` 持久化。
- 验证：228 tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。

## Round 8（进行中）

- 指南：`round-8/`
- 版本：1.3.1 / 45
- 范围：单段重译补齐 sidecar 指纹、费用区间预估、队列可重试失败自动再试一次、
  任务页上限 300。

## Round 9（计划）

- 指南：`round-9/`
- 版本：1.3.2 / 46
- 范围：已移出书「删除本地数据」（二次确认、仅已移出视图）、删除前停下载/翻译/预译、
  `ContentStore.deleteBook` + DAO 级联删除。

## Round 10 候选

- 滚动阅读模式限宽 680dp。
- 章节列表批量翻译确认显示总章数与单价（当前只有单价）。
- 导入完成摘要（书 N 本、进度 M 条、译文 K 章）。
- `ClickableText` → `LinkAnnotation`。
- 依赖升级与 `UseKtx` 清理。
