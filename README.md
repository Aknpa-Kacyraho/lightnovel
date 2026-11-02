# Lightnovel / Ka小说家

本地优先的日文轻小说翻译与阅读工具，包含两个可独立使用的部分：

- `lightnovel/`：Python 3.10+ 标准库实现的翻译核心与书架 Web 服务。负责找书、增量翻译、
  术语/人物/前情记忆、阅读进度、EPUB/TXT 导入与局域网访问。
- `android/`：Kotlin + Jetpack Compose 原生阅读器「Ka小说家」。书架、发现、任务、设置四个
  Tab，支持本地 TXT/EPUB、Kakuyomu / 成为小说家吧、后台下载与直接翻译。

译文、术语表、阅读进度和口味画像都保存在本机；仓库不包含任何书籍正文、译文或个人数据。

## 最新版本

Android **0.9.4**（versionCode 27）：

- 大书库：搜索/推荐/翻译元数据持久化，支持来源、状态、标签多选（同时满足）与排序。
- 发现池：排行榜扩充目录、7 天防重复爬、随机推荐与「换一批」；已加入书架的书不再推荐。
- 标签本地化：常用日文标签显示中文，热门标签点击仍用原文搜索。
- 阅读器：按页构建排版、滚动知识状态防抖；单换行正文按段落锚定，世界线分叉点精确到当前段。
- 阅读体验：封面按尺寸显示 8–30 字、长作者省略、HTML 数字实体解码、查询模式空态提示。

下载：[Release v0.9.4](https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v0.9.4)

APK：`lightnovel-0.9.4-debug.apk`

自检：140 JVM tests / 0 failures / 1 skipped；lint 0 errors。

## 快速开始（Web）

```bash
cd lightnovel/lntrans
python run_selftests.py          # 35 项自检，全绿再继续
python lnserve.py --port 8099    # 打开 http://127.0.0.1:8099/
```

翻译需要 OpenAI 兼容的 Chat Completions 端点。复制 `lightnovel/.env.example` 到自己的私有
环境配置，填入端点和 Key；本地回环端点（Ollama / LM Studio / llama.cpp）通常不需要 Key。
完整变量说明见 `lightnovel/docs/MODEL-CONFIG.md`。

## Android

要求 JDK 17、Android SDK 36、minSdk 26。Windows 下先开 UTF-8：

```powershell
chcp 65001 | Out-Null
$env:ANDROID_HOME="D:\Android\Sdk"
$env:ANDROID_SDK_ROOT="D:\Android\Sdk"
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

APK 在 `android/app/build/outputs/apk/debug/app-debug.apk`。真机安装：

```powershell
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

## 翻译 API：不只 DeepSeek

Android 设置页内置了这些 OpenAI 兼容预设，也可以填任意自定义端点：

- DeepSeek、OpenAI、OpenRouter、硅基流动、Moonshot、Gemini 兼容入口
- Ollama / LM Studio 本机端点（通常免 Key）
- one-api 等自建网关

不同模型能稳定吃下的块大小差别很大。首次保存新端点/模型时，App 会自动用内置日文样章
做一次**安全翻译范围校准**：

1. 自动识别模型适合「编号批量」还是 Sakura 式整块翻译；
2. 从大到小测试块大小，检查段落/编号/对白/中文比例是否完整；
3. 取通过的最大块并留 10% 余量，结果按「端点 + 模型」缓存；
4. 之后可在设置页随时「测试连接」或「重新校准」。

校准只发送内置样章，不碰你的书；会消耗少量 token。Key 只保存在 Android Keystore。

## 故事记忆：让同一角色始终是同一个人

Android 端每本书有独立的 `story.json`（术语表 / 人物卡 / 章节梗概 / 风格 / 本书经验），
不再共用全局术语表，避免 A 书译名污染 B 书。翻译时只注入本段实际出现的术语、人物卡、
相关前情，以及上一块**译文**的尾部；prompt 里带 `work_id` 做作品隔离。

- 每章译完自动生成中文梗概，下一章按出场人物注入相关前情；
- 「本书设定」页可编辑术语、人物卡（语气/称呼/词汇习惯/句法习惯）、风格与经验；
- 「扫描人物」从原文/译文提取人物并锁定译名；
- 「检查译名一致性」找出同一日文名的不同中文写法，一键写入术语表/人物卡；
- 阅读器「润色本章」只改写表达，保留段落数、对白行数和锁定译名，校验不过就保留原译。

旧全局 `glossary.json` 不再参与翻译；可在「本书设定 → 术语」里手动导入到当前书。

## 查询模式与世界线

- **查询模式**：阅读器「更多 → 查询模式」开启后，已读实体在正文里显示下划线；点词或「本页词条」打开人物卡。卡片按当前阅读锚点过滤，同章后半和未来章的信息不会提前出现；每条信息带章节出处。
- **事实级知识库**：每本书独立 `knowledge.json`，存 Entity / Fact / Relation / VoiceFact / Secret，每条事实带原文引用和锚点；翻译完成后增量抽取，查询面板显示「资料更新至第 N 章」。
- **完整世界线**：详情页「更多 → 世界线」可从指定章分叉，输入「角色 + 行动 + 约束」，选择探索型或对照型。生成走 plan → Writer → Validator → 分支知识抽取；分支独立存储，不覆盖原书。Writer 永不看 `reveal_content`；对照型的差异报告只给 Planner/Diff，并明确标注含原作剧透。

## 目录

```text
lightnovel/        Python 翻译/书架服务、自检、skill、文档
android/           Ka小说家 Android App
CONTEXT.md         领域模型与术语
icon-preview.png   图标预览
```

## 数据与隐私

以下内容被 `.gitignore` 排除，也不会随仓库分发：

- `lightnovel/lntrans/novels/`、`lightnovel/lntrans/data/`
- `lightnovel/lnfinder/taste_profile.json`、候选池、历史与报告
- `.env`、凭据、token、日志、备份 zip
- Android `local.properties`、构建产物

## 许可

Apache License 2.0，见 `lightnovel/LICENSE` 与 `lightnovel/NOTICE`。
