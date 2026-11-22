# Lightnovel / Ka小说家

本地优先的日文轻小说翻译与阅读 Android App。

`main` 现在只维护 Kotlin + Jetpack Compose 原生客户端。旧 Web/Python 实现不再参与构建、测试或发布，最终源码仅保留在远端只读归档分支：

- 归档分支：<https://github.com/Aknpa-Kacyraho/lightnovel/tree/archive/web>
- 当前发布：[v1.9.5](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v1.9.5)
- 变更记录：[android/CHANGELOG.md](android/CHANGELOG.md)

## 当前版本

Android **1.9.5**（versionCode 69）：

- 书架、发现、任务、设置四个一级入口。
- 本地 TXT / EPUB 导入，Kakuyomu 与成为小说家吧搜索和下载。
- DeepSeek 与通用 OpenAI-compatible 翻译端点，支持模型校准、预算和后台任务。
- 阅读器支持字号、纸色、翻页手势、朗读、术语标注、查询模式与世界线。
- 每本书独立保存术语、人物、章节梗概、事实知识、译文版本与阅读进度。
- 备份导出、备份导入、旧 Python 备份兼容和可验证恢复。
- Release APK 使用独立证书签名；签名私钥与密码不进入仓库。
- 任务页忽略可撤销；阅读器补齐页码无障碍描述。
- 空书架只有「去发现」一个主按钮；备份提醒直达设置的数据分组；
  阅读器菜单按阅读 / 翻译 / 资料 / 世界线分组。
- 平板/横屏正文限宽 680dp；大字体下动作行自动换行；翻译前显示当前章字数。
- 阅读纸色支持跟随系统；未翻译章节不再常驻提示；夜间正文更柔和。
- 深色模式次要文字与标签降噪，卡片描边减淡。
- 单击正文切换沉浸；底栏与继续阅读卡有阅读进度线。
- 本地导入按内容去重；书架支持按标题 / 最近阅读 / 最近添加排序。
- 单段重译不再误报过期；翻译确认显示费用区间；可重试失败自动再试一次。
- 已移出的书可「删除本地数据」，删除前停止后台任务。
- 阅读器支持添加书签、查看书签列表并回到原段落。
- 阅读器支持书内搜索：结果带上下文，同章定位到段落。
- 阅读器可调排版（字号/行距/边距/段距），翻页进度可拖动。
- 沉浸阅读隐藏系统栏；阅读页常驻控件更精简。
- 术语表可搜索；覆盖与删除都有提示。
- 书架筛选收敛为 4 个控件；阅读器「更多」改为可滚动底部 Sheet。
- 修复滚动/翻页模式进度错位、滚动书签位置错误与跳转不滚动。
- 修复快速切换语言模式的内容错乱；跨章书签/搜索自动定位到段落。
- 修复退出丢最后一页、书架筛选闪烁与书名翻译重复请求。
- 翻译异常不再卡在「翻译中」；重译本段保留原排版；不可重试错误立即失败。
- 手动翻译优先于自动预译；重复任务不计失败；暂停立即停止。
- 术语过期只在术语真变时提示；翻译中改术语仍会提示；简介可补翻。
- 重复导入备份不再覆盖书名、标签、章节信息与阅读进度；只补缺失内容。
- 单段重译不再掩盖整章术语过期；EPUB 导入清理注音；备份跳过旧目录。
- 滚动书签不再跳回旧页；跨模式位置一致；恢复备份后本地导入去重仍有效。
- 批量重试不受筛选影响；搜索加载状态正确；世界线失败回滚知识。
- 取消翻译/搜索/世界线后，后台请求不再继续写摘要、人物、知识或缓存。
- 统一中文排版与五档圆角；卡片描边减淡，页面更安静。
- 书架改为书单；封面统一 2:3；设置分组去掉描边卡片。
- 夜间纸色更柔和；纸白/护眼更暖；阅读器警告条与 Sheet 圆角统一。
- 导入旧备份不再把本机进度清零；导出失败不留半成品；取消翻译后状态恢复。
- `.txt` 的 EPUB 按文件头识别；单引号 spine 顺序正确；下载取消可穿透。
- 书签随备份恢复；未下载的书不再消失；坏 sidecar 不再导致润色崩溃。
- 未译全章节可真正重试；滚动搜索/书签/模式切换不再偏移。
- 章节元数据随备份恢复；重试对应原操作；设置页与阅读器同步。
- 已移出空态准确；预览加书错误可见；目录选章后返回不再经过旧阅读器。
- 非连续章节号的进度不再被重置；完整译文不会被部分重译降级。
- 同文件不同 id 的备份合并到现有书；旧备份目录按话数补齐；润色后缓存失效。

## 环境要求

- JDK 17
- Android SDK 36
- minSdk 26
- Windows、Linux 或 macOS

Windows 首次构建建议先设置 UTF-8：

```powershell
chcp 65001 | Out-Null
$env:ANDROID_HOME="D:\Android\Sdk"
$env:ANDROID_SDK_ROOT="D:\Android\Sdk"
```

## 构建与验证

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

Debug APK：

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

安装：

```powershell
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Linux/macOS 使用 `./gradlew`。CI 在 `ubuntu-latest` 执行 JVM 测试、lint 和 debug 构建；标签构建额外执行签名 Release 与证书验证。

## 翻译端点

设置页提供 DeepSeek、OpenAI、OpenRouter、硅基流动、Moonshot、Gemini 兼容入口，也支持 Ollama / LM Studio 和 one-api 等自建网关。

首次保存新端点或模型时，App 会使用内置日文样章校准：

1. 判断适合编号批量还是整块翻译；
2. 从大到小测量稳定块大小；
3. 校验段落、编号、对白和中文比例；
4. 保存端点与模型专属配置。

校准只发送内置样章，会消耗少量 token。API Key 只保存在 Android Keystore。

## 阅读与故事记忆

- 每本书有独立的 `story.json`，保存术语、人物卡、章节梗概、风格与本书经验。
- 翻译只注入本段实际出现的术语、相关人物、前情和上一块译文尾部。
- 查询模式按当前阅读锚点过滤事实，不提前展示后文剧透。
- 世界线分支独立存储，不覆盖原书正文。
- 阅读器润色只修改表达；段落数、对白数和锁定译名校验失败时保留原译。

## 数据与隐私

以下内容不进入 Git 或发布 APK：

- 用户书籍、原文、译文、阅读进度、收藏和备份。
- 术语表、人物卡、知识库、世界线和个人画像。
- API Key、签名私钥、密码、Token、日志和构建产物。

书籍和备份默认只保存在设备本机；应用不提供云端账号同步。

## 目录

```text
android/           Android App、测试、设计文档与发布说明
.github/           Android CI 与签名 Release 工作流
CONTEXT.md         Android 领域模型与术语
AGENTS.md          Android-only 开发约束
LICENSE            主许可证
NOTICE             版权与项目声明
```

## 许可

GNU Affero General Public License v3.0 or later（AGPL-3.0-or-later）。

你可以商用、修改和分发；但分发修改版，或将它作为网络服务提供给他人使用时，必须按 AGPL 提供完整对应源码。

`0.9.5` 及更早的 Android 版本按 Apache-2.0 发布；既有授权不可撤销。
