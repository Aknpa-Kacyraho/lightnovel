# Android 三轮升级进度

> 基线：`main` Android-only，1.0.3（versionCode 37），168 JVM tests。
> 每一轮先出「用户 / 设计师 / 工程师」三份独立指南，再合并为 `FINAL.md`，
> 按最终版实施，最后做三视角自检并发布一个 GitHub 版本。

## 轮次总览

| 轮次 | 版本 | 主题 | 指南 | 自检 | 发布 |
| --- | --- | --- | --- | --- | --- |
| Round 1 | 1.0.4（38） | 基线归零：误触可撤销、无障碍、lint 清理 | ✅ | ⏳ | ⏳ |
| Round 2 | 1.1.0（39） | 体验一致性：空态主次、设置深链、任务语义 | ⏳ | ⏳ | ⏳ |
| Round 3 | 1.1.1（40） | 打磨：性能、可访问性、工程可维护性 | ⏳ | ⏳ | ⏳ |

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

## Round 1 记录

- 指南：`docs/upgrade/round-1/{01-user,02-design,03-engineering,FINAL}.md`
- 版本：1.0.4 / 38
- 主要变更：
  - 任务忽略改为可撤销（Snackbar + 撤销），并补「取消 / 忽略」语义说明。
  - 阅读器每页页码 `contentDescription`，未滑动点击触发 `performClick()`。
  - 备份提醒写清「设置 → 数据 → 导出备份」路径。
  - 合并 `mipmap-anydpi-v26`；3 处装箱状态改 primitive state。
  - 新增 `TaskIgnoreStoreTest`、`CHANGELOG.md`、本档案。
- 验证：见 `round-1/SELF-REVIEW.md`（实施完成后补）。
