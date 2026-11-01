# Lightnovel / Ka小说家

本地优先的日文轻小说翻译与阅读工具，包含两个可独立使用的部分：

- `lightnovel/`：Python 3.10+ 标准库实现的翻译核心与书架 Web 服务。负责找书、增量翻译、
  术语/人物/前情记忆、阅读进度、EPUB/TXT 导入与局域网访问。
- `android/`：Kotlin + Jetpack Compose 原生阅读器「Ka小说家」。书架、发现、任务、设置四个
  Tab，支持本地 TXT/EPUB、Kakuyomu / 成为小说家吧、后台下载与直接翻译。

译文、术语表、阅读进度和口味画像都保存在本机；仓库不包含任何书籍正文、译文或个人数据。

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
