# Android-only Collaboration Rules

## Product Boundary

`main` 只维护 `android/` 下的 Kotlin + Jetpack Compose App。产品、测试、CI、文档和发布都以 Android 为唯一交付面。

旧 Web/Python 实现只在远端 `archive/web` 归档分支保留，用于历史恢复。它们不属于当前运行时、构建依赖或测试入口；历史研究文档可以描述需要保留的行为，但当前事实来源永远是 Android 代码与测试。禁止把 `lightnovel/`、Python 服务、Docker Web 部署或 Web skill 重新加入 `main`。

Android 代码中保留的 `lntrans` / `lnfinder` 路径名，只用于兼容导入旧备份格式。

## Source Map

- `android/app/src/main/`：Compose UI、阅读器、翻译、下载、导入、备份和本地数据库。
- `android/app/src/test/`：JVM/Robolectric 回归。
- `android/docs/`：ADR、设计决策和历史研究。
- `.github/workflows/ci.yml`：Android JVM 测试、lint、debug 构建。
- `.github/workflows/release-android.yml`：标签签名 Release。
- `android/RELEASE.md`：签名变量与 APK 验证。

## Required Verification

修改 Android 代码后执行：

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

Release 变更还要使用仓库外 keystore 构建 `assembleRelease`，再执行 `apksigner verify --print-certs` 与 SHA-256 校验。缺少签名变量时必须失败。

## Product Rules

- 所有面向用户的文案使用简体中文。
- 本地书籍、原文、译文、术语、人物、画像、阅读进度和备份都视为真实用户资产。
- 导入、恢复、迁移采用可回滚流程；默认干跑，写入前先备份，失败不得覆盖好数据。
- 编辑器与设置中的 API Key 只存 Android Keystore，不写日志、不进入备份、不回传 UI。
- 公网模型端点必须 HTTPS；HTTP 仅允许回环或私有局域网。
- 阅读助手与世界线按当前阅读锚点过滤内容，服务端或本地数据层先约束剧透，再交给模型。
- 新增操作必须真实可用；全书完成、空书架、未上架等状态不能显示无效按钮或错误导航。
- 移动端触控目标至少 44dp；键盘、TalkBack、字号缩放、横屏和平板布局纳入验证。

## Change Hygiene

- 不提交签名文件、密码、Token、用户备份、构建产物或真实书籍数据。
- 不改写既有 Release 资产；新 APK 使用新的 `versionCode` 和 `versionName`。
- 修改高风险数据路径时，先补失败测试，再做最小修复并跑相关回归。
