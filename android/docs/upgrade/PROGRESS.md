# Android 升级进度

> 基线：`main` Android-only。前一批三轮（1.0.4 / 1.1.0 / 1.1.1）解决可用性；
> 这一批三轮（1.2.0 / 1.2.1 / 1.2.2）专注用户视角体验与视觉疲劳。

## 轮次总览

| 轮次 | 版本 | 主题 | 指南 | 自检 | 发布 |
| --- | --- | --- | --- | --- | --- |
| Round 1 | 1.0.4（38） | 误触可撤销、阅读器无障碍、lint 清理 | ✅ | ✅ | ✅ [v1.0.4](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.0.4) |
| Round 2 | 1.1.0（39） | 空态主次、设置深链、菜单分组 | ✅ | ✅ | ✅ [v1.1.0](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.1.0) |
| Round 3 | 1.1.1（40） | 横屏限宽、大字体换行、翻译字数、长章节提示 | ✅ | ✅ | ✅ [v1.1.1](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.1.1) |
| Round 4 | 1.2.0（41） | 阅读纸色跟随系统、未翻译横幅降噪、夜间调光 | ✅ | ✅ | ✅ [v1.2.0](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.2.0) |
| Round 5 | 1.2.1（42） | 深色次要文字降亮、标签降饱和、卡片去亮框 | ✅ | ⏳ | ⏳ |
| Round 6 | 1.2.2（43） | 单击正文沉浸、底栏进度线、继续阅读进度 | ✅ | ⏳ | ⏳ |

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

## Round 1–3（已发布）

详见 `round-1/`、`round-2/`、`round-3/` 的 `FINAL.md` 与 `SELF-REVIEW.md`。

- 1.0.4：任务忽略可撤销、阅读器页码语义、lint 三件套、`TaskIgnoreStoreTest`。
- 1.1.0：空态两条路径、备份提醒直达数据分组、菜单四组、任务筛选带数量。
- 1.1.1：横屏 680dp、FlowRow、翻译字数、长章节提示、`PrimaryTabRow`。

## Round 4（已发布）

- 指南：`round-4/`；自检：`round-4/SELF-REVIEW.md`
- 版本：1.2.0 / 41
- 变更：
  - `ReaderTheme.AUTO`「跟随系统」，新安装默认 auto；系统深色 → 夜间纸色。
  - `shouldShowTranslationBanner(...)`：未翻译且无任务/错误/队列时不显示横幅。
  - 夜间正文 `#C8C5BE` → `#BDBAB2`；`contrastRatio` 回归断言。
  - 新增 `ReaderThemeTest`、`ReaderBannerTest`，补 `SettingsStoreTest` 默认值。
- 验证：212 tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。

## Round 5（进行中）

- 指南：`round-5/`
- 版本：1.2.1 / 42
- 范围：8 套 dark 的 `onSurfaceVariant` 降亮（7–10:1）、容器混合 0.30→0.24、
  书架/任务卡统一 `surfaceContainerLow` + 0.6 alpha 描边、`ThemeContrastTest`。

## Round 6（计划）

- 指南：`round-6/`
- 版本：1.2.2 / 43
- 范围：单击正文切换沉浸（查询模式优先）、底栏 2dp 进度线、继续阅读卡进度、
  首次沉浸 3 秒提示、`ReaderProgressTest`。

## Round 7 候选

- 滚动阅读模式限宽 680dp。
- 章节列表批量翻译确认显示「共 N 章」。
- 导入完成摘要（书 N 本、进度 M 条、译文 K 章）。
- `ClickableText` → `LinkAnnotation`。
- 依赖升级与 `UseKtx` 清理。
