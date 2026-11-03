# 0.9.6 审查与打磨

日期：2026-11-03

## 审查方式

用三个只读子 agent 分别审查 UI/UX、功能/兼容性、产品流程/性能；汇总后只修高影响问题。

## 修复

- 任务页进入阅读器后打开「目录」：任务 NavHost 现在注册完整 `bookRoutes`，不再导航到不存在的目的地。
- 网络异常：`DeepSeekClient` 把 `IOException`/明文 HTTP 拦截统一转成 `TranslationException`，翻译和世界线不再闪退；Android 9+ 本地端点可用。
- Python 备份：识别 `0000.txt` 的 0 基章号，索引 +1 并在 staging 同步重命名文件，避免整本错位一章。
- 书架：移出只写 `hidden=1`，新增「已移出」入口和撤销 Snackbar；重新加入保留中文书名、阅读进度和收藏状态。
- 备份：导出 `episodes`/`added_at`/`created_at`，导入时用章节数补 `episodes`；旧备份恢复后不再显示 0 话。
- 阅读进度：翻页立即写库；滚动防抖 120ms 后立即写库，不再等 500ms 导致返回丢最后一页。
- 翻译任务注册：`ConcurrentHashMap.compute` 原子替换已完成 Job，修复取消竞态。
- 世界线：拒绝超出本书章数的分叉点；plan 继续兼容对象形 beats，失败重试一次。
- 查询模式：取消按钮现在能真正取消资料抽取；「本页词条」改为更准确的「附近词条」。

## UI/UX

- 主题补齐 `surfaceContainer*`/`inverse*`/`scrim` 等 Material3 角色；底栏使用 `surfaceContainer`，系统栏图标随强制浅/深色切换。
- 阅读器顶栏移除 A-/A+/纸色按钮，收进「更多」；标题获得更多空间。
- 查询/术语输入框跟随阅读纸色；错误色使用 `ReaderTheme.danger`。
- 任务卡改为标题行 + 操作行；大书库预览可滚动、简介限 8 行；发现「从链接添加」错误直接显示在 Sheet 内。
- 查询词条按类型分组、字号分层；已移出空态、筛选空态和清除逻辑补齐。

## 兼容性

- 保持 `minSdk 26`。
- 修掉 `Stream.toList()`（API 34）等新 API，改用 API 26 可用的 `Collectors.toList()`。
- `usesCleartextTraffic` 打开，允许用户显式配置的本地/局域网 HTTP LLM 端点。

## 验证

- `154 JVM tests / 0 failures / 1 skipped`
- lint `0 errors`
- `assembleDebug` 通过；真机覆盖安装
- 真实 LLM 世界线/翻译未跑（会消耗 token）

## 世界线返修（2026-11-03 晚）

- 真实模型不会总把正文放在 `text`：实测 `deepseek-v4.1-flash` 返回 `{"title": "...", "content": "..."}`，旧解析只认 `text`，会报「正文为空」。现在兼容 `text/content/body/chapterText`，并自动补标题和梗概。
- 网络错误由世界线重试：规划、写作、校对、差异分析、分支知识抽取遇 503/超时按退避重试；校验器不可用时不再误杀已生成正文。
- plan 解析兼容根数组、`beats` 对象数组、`plot/outline/scenes` 别名；未来实体 plan 会带着纠正重试，而不是直接失败。
- 分叉前原文节选进入 Planner/Writer：只读分叉点前的已翻译章节/当前章前缀，避免没有知识库时凭空续写。
- 真实模型实测通过：DeepSeek 官方 `deepseek-flash` 生成 2713 字分支成功；OpenCode Go `deepseek-v4.1-flash` 生成 3915 字分支成功。两者分别验证了官方端点和强推理端点的 JSON 形状。
- 分支知识抽取在强推理模型上仍可能因 `finish=length` 显示「未抽取」；分支正文不会丢，可稍后手动更新资料。
