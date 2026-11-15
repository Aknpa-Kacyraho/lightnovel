# 贡献指南

## 开发原则

- 所有面向用户的文案使用简体中文。
- 不提交书籍正文、译文、画像、书架数据、API Key、Token、Cookie 或签名私钥。
- 数据安全优先于新功能；涉及恢复、迁移、覆盖写入时必须提供回滚或备份路径。
- 模型端点、备份导入和阅读进度属于高风险路径，改动必须带自动化测试。

## 本地验证

Android：

```bash
cd android
./gradlew --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

Release 签名与 APK 证书验证见 `android/RELEASE.md`。普通 PR 只能使用 debug 构建；
签名 Release 由标签或手动工作流使用 GitHub Secrets 构建。

`main` 只接受 Android 客户端变更。旧 Web/Python 源码位于远端 `archive/web`
归档分支，不作为当前运行时、规格来源或构建依赖重新引入。

## 提交要求

- 一个提交解决一个可说明的问题。
- 测试失败必须给出真实原因，不允许跳过、放宽或删除有效断言来“变绿”。
- 新增外部地址时说明协议、认证方式、保存内容与失败行为。
