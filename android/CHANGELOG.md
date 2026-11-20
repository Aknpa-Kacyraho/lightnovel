# Changelog

本项目从 `1.0.2` 起使用签名 Release。`main` 只维护 Android App；
旧 Web/Python 实现保存在远端 `archive/web`，不再参与构建与发布。

## 1.2.0 — 2026-11-20

### 用户可见

- 阅读纸色新增「跟随系统」，并作为新安装默认：系统深色时自动用夜间纸色，
  浅色时用纸白；已手动选过纸色的用户保持原选择。
- 未翻译章节不再常驻「本章还没翻译」横幅；只有翻译进行中、失败、预译队列
  运行/暂停/出错时才显示。
- 夜间纸色正文调暗为 `#BDBAB2`，长时间关灯阅读不再觉得字在发光。

### 工程

- `ReaderTheme` 增加 `AUTO` 与 `resolve(dark)`；渲染前统一解析，偏好与显示分离。
- 新增 `shouldShowTranslationBanner(...)`、`contrastRatio(...)` 纯函数。
- 新增 `ReaderThemeTest`、`ReaderBannerTest`，补 `SettingsStoreTest` 纸色默认值。
- `versionCode 41` / `versionName 1.2.0`。

## 1.1.1 — 2026-11-18

### 用户可见

- 平板与横屏阅读：正文最大宽度 680dp 并居中，长行不再横跨整块屏幕；手机竖屏不变。
- 系统字体放大时，任务卡动作行与书架空态入口自动换行，不再挤压或截断。
- 阅读器「翻译本章」显示当前章规模（约 N 字 / 约 X.X 千字），
  0 字或加载中不显示。
- 超大章节首次打开超过 300ms 时显示「正在排版长章节…」，不再像卡死。

### 工程

- 新增 `ReaderViewportTest`（手机 / 临界 680 / 平板 / 零边距 / 极端边距）。
- 排版宽度抽为 `readerContentWidthDp(...)`；字数格式化抽为 `formatCharCount(...)`，
  `ReaderMenuTest` 补 0 / 800 / 1200 三档。
- `TabRow` 替换为 `PrimaryTabRow`（章节列表、本书设定）。
- 任务卡动作行与空态入口改用 `FlowRow`。

### 版本

- `versionName = "1.1.1"`，`versionCode = 40`。

## 1.1.0 — 2026-11-18

### 用户可见

- 空书架改为两条明确路径：「第一次用 → 去发现」是唯一主按钮；
  「导入备份 / 导入 TXT / EPUB」降为次级入口，不再与主路径抢注意力。
- 书架备份提醒的「去设置」直达「数据」分组，并高亮 2 秒，不再要求用户自己滚动寻找。
- 阅读器「更多」菜单按「阅读 / 翻译 / 资料 / 世界线」四组排列；功能一个不少，查找更快。
- 任务页筛选标签直接显示数量（失败 3、未译全 2、进行中 1），点数字即筛选。

### 工程

- 新增 `LibraryEmptyStateTest`、`SettingsFocusTest`、`ReaderMenuTest`，
  覆盖空态分支、设置深链白名单、菜单分组与禁用条件。
- 空态文案与动作抽成 `emptyShelfCopy(...)` 纯函数；阅读器菜单抽成
  `readerMenuItems(...)`，渲染层不再硬编码 13 个菜单项。
- `TaskGroupingTest` 补筛选一致性断言。

### 版本

- `versionName = "1.1.0"`，`versionCode = 39`。

## 1.0.4 — 2026-11-18

### 用户可见

- 任务页「忽略」现在可撤销：忽略后出现 Snackbar，点「撤销」即恢复原任务，
  不再出现「点错就永远找不到」。
- 阅读器每页补页码无障碍描述（「第 x 页，共 y 页」），TalkBack 不再只读到一块空白画布。
- 备份提醒写清路径：去设置 → 数据 → 导出备份。

### 工程

- `ReaderPageView` 在未滑动点击时调用 `performClick()`，消除
  `ClickableViewAccessibility` lint 警告。
- 清理 `ObsoleteSdkInt`（合并 `mipmap-anydpi-v26`）与 3 处
  `AutoboxingStateCreation`（改用 `mutableIntStateOf` / `mutableFloatStateOf`）。
- 新增 `TaskIgnoreStoreTest`：写入、去重、清除、空值、损坏分隔符。
- 新增 `docs/upgrade/` 三轮升级档案与 `CHANGELOG.md`；补齐 `04-final.md` 的
  1.0.2–1.0.4 记录。

### 版本

- `versionName = "1.0.4"`，`versionCode = 38`。

## 1.0.3 — 2026-11-06

- 对齐 Android 版本号与签名发布流程。
- Web 归档分支修复首启、导入、书架、详情、设置与阅读器路径；`main` 不包含
  Web/Python 运行时。
- Android 侧无用户可见功能变化。

## 1.0.2 — 2026-11-05

- 首个签名 Release（versionCode 36）。
- Release 构建强制校验 `LIGHTNOVEL_RELEASE_*` 四项签名变量，缺少任意一项直接失败，
  不再悄悄产出未签名 APK。
- CI 增加签名 APK 校验与产物上传。

## 1.0.1 — 2026-11-04

- 阅读翻译队列按书合并，切换章节不再取消正在进行的任务。
- 阅读器状态条显示当前进度、后台预译、失败原因，可暂停/继续/停止。
- 详情页「更多 → 翻译章节…」支持当前章、后续 N 章、全书未译，带费用确认。
- 在线章节先拉正文再翻译；任务中心支持原地重试、重试全部失败、停止本书。
- 全部分块失败不再写成 partial 原文；缓存与实际译文不一致时自动重建。
- 书架移出只隐藏，保留离线正文、译文、世界线和阅读进度，可恢复、可撤销。

## 1.0.0 — 2026-11-04

- 阅读时自动翻译当前章并预译后续章节；跳章回补有限章节。
- 发现页与作品详情页改为整页滚动。
- 世界线、查询模式、故事记忆、备份导入导出沿用 0.9.x 能力。
