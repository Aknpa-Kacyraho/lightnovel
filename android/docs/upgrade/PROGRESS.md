# Android 三轮升级进度

> 基线：`main` Android-only，1.0.3（versionCode 37），168 JVM tests。
> 每一轮先出「用户 / 设计师 / 工程师」三份独立指南，再合并为 `FINAL.md`，
> 按最终版实施，最后做三视角自检并发布一个 GitHub 版本。

## 轮次总览

| 轮次 | 版本 | 主题 | 指南 | 自检 | 发布 |
| --- | --- | --- | --- | --- | --- |
| Round 1 | 1.0.4（38） | 基线归零：误触可撤销、无障碍、lint 清理 | ✅ | ✅ | ✅ [v1.0.4](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.0.4) |
| Round 2 | 1.1.0（39） | 体验一致性：空态主次、设置深链、菜单分组 | ✅ | ✅ | ✅ [v1.1.0](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.1.0) |
| Round 3 | 1.1.1（40） | 打磨：横屏限宽、大字体换行、翻译字数、长章节提示 | ✅ | ✅ | ✅ [v1.1.1](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.1.1) |

## 约束

- `main` 只维护 Android App，不重新引入 `lightnovel/`、Python 服务或 Web。
- 每个版本必须使用新的 `versionCode` / `versionName`；不改写既有 Release。
- 面向用户文案使用简体中文；触控目标 ≥44dp；深浅色与 8 套主题都不写死颜色。
- 用户资产（书籍、译文、术语、世界线、进度、备份）不因升级丢失。
- 每轮验证命令：

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

## Round 1 记录（已发布）

- 指南：`round-1/{01-user,02-design,03-engineering,FINAL}.md`；自检：`round-1/SELF-REVIEW.md`
- 版本：1.0.4 / 38
- 变更：
  - 任务忽略改为可撤销（Snackbar + 撤销），补「取消 / 忽略」语义。
  - 阅读器每页页码 `contentDescription`，未滑动点击触发 `performClick()`。
  - 备份提醒写清「设置 → 数据 → 导出备份」。
  - 合并 `mipmap-anydpi-v26`；3 处装箱状态改 primitive state。
  - 新增 `TaskIgnoreStoreTest`、`CHANGELOG.md`、本档案。
- 验证：178 tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。
- 发布：tag `v1.0.4`，Release 含签名 APK（11,340,376 bytes）。

## Round 2 记录（已发布）

- 指南：`round-2/`；自检：`round-2/SELF-REVIEW.md`
- 版本：1.1.0 / 39
- 变更：
  - 空态两条路径，「去发现」唯一主按钮；`emptyShelfCopy(...)` 纯函数 + 5 项测试。
  - 备份提醒直达设置「数据」分组并高亮 2 秒；`SettingsFocus` 白名单 + 3 项测试。
  - 阅读器菜单四组（阅读 / 翻译 / 资料 / 世界线）；`readerMenuItems(...)` + 5 项测试。
  - 任务筛选标签显示数量，点数字即筛选；补 1 项分组筛选断言。
- 验证：192 tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。
- 发布：tag `v1.1.0`，Release 含签名 APK（11,340,372 bytes）。

## Round 3 记录（已发布）

- 指南：`round-3/`；自检：`round-3/SELF-REVIEW.md`
- 版本：1.1.1 / 40
- 变更：
  - 翻页阅读正文上限 680dp 并居中；`readerContentWidthDp(...)` + 5 项测试。
  - 任务卡动作行、空态次级入口改 `FlowRow`，大字体自动换行。
  - 翻译菜单显示「约 N 字」/「约 X.X 千字」；`formatCharCount(...)` + 2 项测试。
  - 超大章排版超过 300ms 显示「正在排版长章节…」。
  - `TabRow` → `PrimaryTabRow`（章节列表、本书设定）。
- 验证：199 tests / 0 failures / 1 skipped；lint 0 errors / 22 warnings。
- 发布：tag `v1.1.1`，Release 含签名 APK（11,356,756 bytes）。

## Round 4 候选（未排期）

- 滚动阅读模式同样限宽 680dp。
- 章节列表批量翻译确认框显示「共 N 章」。
- 导入完成摘要（书 N 本、进度 M 条、译文 K 章）。
- `ClickableText` → `LinkAnnotation`（点词命中映射需重写）。
- 升级依赖与清理 `UseKtx`（需独立回归）。
