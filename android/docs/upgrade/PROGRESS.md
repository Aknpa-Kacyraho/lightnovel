# Android 升级进度

> 基线：`main` Android-only。升级分四批：
> 1.0.4–1.1.1 可用性；1.2.0–1.2.2 视觉疲劳；1.3.0–1.3.2 翻译与书库；
> 1.4.0–1.4.2 阅读功能（书签、书内搜索、排版与跳页）。

## 轮次总览

| 轮次 | 版本 | 主题 | 指南 | 自检 | 发布 |
| --- | --- | --- | --- | --- | --- |
| Round 1 | 1.0.4（38） | 误触可撤销、阅读器无障碍、lint 清理 | ✅ | ✅ | ✅ [v1.0.4](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.0.4) |
| Round 2 | 1.1.0（39） | 空态主次、设置深链、菜单分组 | ✅ | ✅ | ✅ [v1.1.0](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.1.0) |
| Round 3 | 1.1.1（40） | 横屏限宽、大字体换行、翻译字数、长章节提示 | ✅ | ✅ | ✅ [v1.1.1](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.1.1) |
| Round 4 | 1.2.0（41） | 纸色跟随系统、未翻译横幅降噪、夜间调光 | ✅ | ✅ | ✅ [v1.2.0](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.2.0) |
| Round 5 | 1.2.1（42） | 深色次要文字降亮、标签降饱和、卡片去亮框 | ✅ | ✅ | ✅ [v1.2.1](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.2.1) |
| Round 6 | 1.2.2（43） | 单击正文沉浸、底栏进度线、继续阅读进度 | ✅ | ✅ | ✅ [v1.2.2](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.2.2) |
| Round 7 | 1.3.0（44） | 本地导入去重、书架排序、数据库 v4 | ✅ | ✅ | ✅ [v1.3.0](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.3.0) |
| Round 8 | 1.3.1（45） | 单段重译指纹、费用预估、队列重试 | ✅ | ✅ | ✅ [v1.3.1](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.3.1) |
| Round 9 | 1.3.2（46） | 已移出书彻底删除、删除前停后台 | ✅ | ✅ | ✅ [v1.3.2](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.3.2) |
| Round 10 | 1.4.0（47） | 阅读书签：添加、列表、同章定位 | ✅ | ✅ | ✅ [v1.4.0](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.4.0) |
| Round 11 | 1.4.1（48） | 书内搜索：逐章扫描、上下文、跳转 | ✅ | ✅ | ✅ [v1.4.1](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.4.1) |
| Round 12 | 1.4.2（49） | 排版 Sheet、可拖进度 | ✅ | ✅ | ✅ [v1.4.2](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.4.2) |
| Round 13 | 1.5.0（50） | 真沉浸、模式行精简、菜单去重 | ✅ | ✅ | ✅ [v1.5.0](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.5.0) |
| Round 14 | 1.5.1（51） | 术语表搜索、覆盖提示、删除确认 | ✅ | ✅ | ✅ [v1.5.1](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.5.1) |
| Round 15 | 1.5.2（52） | 书架筛选折叠、阅读器菜单 Sheet | ✅ | ✅ | ⏳ |

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

## 历史摘要（Round 1–9）

- 1.0.4：任务忽略可撤销、阅读器页码语义、lint 三件套。
- 1.1.0：空态两条路径、备份提醒直达数据分组、菜单四组。
- 1.1.1：横屏 680dp、FlowRow、翻译字数、长章节提示。
- 1.2.0：纸色跟随系统、未翻译横幅降噪、夜间正文 `#BDBAB2`。
- 1.2.1：8 套深色 `onSurfaceVariant` 7–10:1、卡片去亮框。
- 1.2.2：单击正文沉浸、阅读进度线。
- 1.3.0：本地导入 SHA-256 去重（DB v4）、书架排序。
- 1.3.1：单段重译指纹、费用预估、队列重试。
- 1.3.2：已移出书删除本地数据（DB 级联 + 文件清理）。

## Round 10（已发布）

- 指南：`round-10/`；自检：`round-10/SELF-REVIEW.md`
- 版本：1.4.0 / 47
- 变更：
  - 数据库 v5 `bookmarks`（book/chapter/paragraph 主键 + preview + createdAt）。
  - 阅读器菜单「添加书签 / 书签列表」；同章跳转写进度并定位，跨章到章首。
  - 新增 `BookmarkSheet`、`relativeTime(...)`；删除书时级联删除书签。
- 验证：249 tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。

## Round 11（已发布）

- 指南：`round-11/`；自检：`round-11/SELF-REVIEW.md`
- 版本：1.4.1 / 48
- 变更：
  - 阅读器「搜索本书」：`findHits` + `BookSearchService` 逐章扫描。
  - 结果含章节、上下文、关键词高亮；同章 `jumpToAnchor`，跨章到章首。
  - 每章 3 条、总数 30，输入 300ms 防抖，关闭即取消。
- 验证：255 tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。

## Round 12（已发布）

- 指南：`round-12/`；自检：`round-12/SELF-REVIEW.md`
- 版本：1.4.2 / 49
- 变更：
  - 阅读器「排版」BottomSheet：字号/行距/边距/段距；恢复默认。
  - 翻页模式底栏可拖进度（2dp 轨道 + 8dp thumb），拖动显示页码。
  - 分页前捕获锚点，调整排版尽量不丢位置。
- 验证：258 tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。

## Round 13（已发布）

- 指南：`round-13/`；自检：`round-13/SELF-REVIEW.md`
- 版本：1.5.0 / 50
- 变更：
  - 沉浸隐藏系统栏/导航栏，`onDispose` 恢复；底部 12dp 间距。
  - 模式行只留语言/朗读；滚动切换进菜单。
  - 菜单移除字号 ±（排版 Sheet 统一调整）。
- 验证：258 tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。

## Round 14（已发布）

- 指南：`round-14/`；自检：`round-14/SELF-REVIEW.md`
- 版本：1.5.1 / 51
- 变更：
  - 术语表搜索（原文/译名/别名）、条数统计、空态区分。
  - 同名原文覆盖提示；删除术语二次确认（说明过期影响）。
  - 新增 `filterGlossary` 纯函数与 `GlossaryFilterTest`。
- 验证：264 tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。

## Round 15（已发布）

- 指南：`round-15/`；自检：`round-15/SELF-REVIEW.md`
- 版本：1.5.2 / 52
- 变更：
  - 书架筛选：书架下拉（全部/在读/想读/读完）+ 收藏 + 已移出 + 排序。
  - 阅读器「更多」改为 `ReaderMenuSheet`（70% 高、可滚动、分组完整）。
- 验证：264 tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。

## Round 13 候选

- 滚动阅读模式限宽 680dp。
- 章节列表批量翻译确认显示总章数。
- 导入完成摘要（书 N 本、进度 M 条、译文 K 章）。
- `ClickableText` → `LinkAnnotation`。
- 依赖升级与 `UseKtx` 清理。
