# Round 1 · 工程师视角升级指南（v1.0.4）

> 目标：把基线做干净，让后续两轮有可信的「绿」。
> 基线事实：168 JVM tests / 0 failures / 1 skipped；lint 25 warnings / 0 errors；
> Android 1.0.3 (37)；main 已 Android-only，Web 代码在 `archive/web`。

## 1. 工程问题清单

### E1. 文档与版本漂移（P0）

- `README.md` 已写 1.0.3，但 `android/docs/redesign/04-final.md` §8 只写到 1.0.1。
- 没有 CHANGELOG，1.0.2/1.0.3 的改动只能从 git log 猜。
- 当前版本 1.0.3 但即将发布 1.0.4，版本号必须同批更新。

**本轮**：补 04-final §8 的 1.0.2–1.0.4 记录；新增 `android/CHANGELOG.md`；
版本 1.0.4 / versionCode 38。

### E2. 无障碍 lint 未清零（P1）

`ReaderPageView#onTouchEvent` 未在点击时调用 `performClick()`：
`ClickableViewAccessibility` 警告。阅读器是核心路径，不能留着。

**本轮**：ACTION_UP 且未滑动时调用 `performClick()`；AndroidView 更新时写入页码
`contentDescription`。验收：lint 该 id 消失。

### E3. 资源与装箱的小债（P2）

- `res/mipmap-anydpi-v26/` 在 minSdk 26 下是冗余目录（`ObsoleteSdkInt`）。
- 3 处 `mutableStateOf(0/0f)` 可用 `mutableIntStateOf` / `mutableFloatStateOf`
  （`ChapterListScreen.kt:452`、`ReaderScreen.kt:46`、`StoryMemoryScreen.kt:119`）。

**本轮**：合并 mipmap 目录；替换 3 处装箱状态。验收：lint 对应 id 消失，测试仍绿。

### E4. `TaskIgnoreStore` 没有测试（P1）

忽略键是持久化状态，当前只有 ViewModel 层调用，没有任何回归证明
「ignore → load 包含 → clear → load 不含」。存储格式用 `\u001F` 分隔，损坏时行为未定义。

**本轮**：补 Robolectric 测试，覆盖写入、去重、清除、空值、损坏分隔符。

### E5. 测试盲区（记录，不在本轮解决）

- 阅读器 `ReaderViewModel` 54KB，是最大文件；翻译队列/分页/查询都在里面，
  但 JVM 测试主要覆盖纯函数。
- `androidTest` 只有 4 个文件，阅读器语义测试依赖真机。
- 备份恢复的真实大文件 fixture 不在仓库（正确），但缺少合成的最小 round-trip 断言。

**Round 2/3 处理**：优先补翻译队列状态机和阅读器锚点恢复，不为了数字加测试。

## 2. 本轮实施顺序

1. 版本号与 CHANGELOG（先让发布可追溯）。
2. 任务忽略撤销（UI + ViewModel 测试）。
3. ReaderPageView 无障碍与页码语义。
4. lint 清理三件套。
5. 全量 `testDebugUnitTest + lintDebug + assembleDebug`。
6. 提交、打 tag、推送。

## 3. 验收命令

```powershell
cd android
.\gradlew.bat --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

通过标准：tests 只增不减、0 failures、lint 0 errors 且目标 warning 消失、APK 产出。
