# 0.9.10 世界线子 agent 审查返修

日期：2026-11-03

三个只读子 agent 分别审查后端/数据、UI/交互、真实链路/发布。只修影响真实使用的问题。

## 修复

- 滚动阅读模式：`scrollParagraph` 是行号，世界线分叉点必须经 `paragraphIndexForScrollLine` 映射成段落；ReaderRoute 的当前位置映射也按 raw/translated/bilingual 使用同一显示文本。
- Reader 世界线：正文编辑器虽然显示整章，但 Planner/Writer 只接收截至当前分叉段的 `forkText`；分叉段之后的原文不再进入未来 canon。
- 分叉锚点严格化：`fork()` 改为只包含分叉段之前的事实；分叉段本身不再算角色已知。`canonReference` 接收 `forkParagraph`，同章分叉前事实不再被误报为未来。
- 连续续写 UI：进度条和“正在续写 N/M 章”文案放进受 Scaffold padding 约束的独立区域，不再被顶栏遮挡；生成中顶栏提供「取消生成」。
- 旧数据兼容：加载旧 worldline 时若 `chapterStates` 为空，按章节数补齐并把旧 state 回填到最后一章，避免 continue/regenerate 永久错位。
- 生成取消：重写时协程取消会恢复旧分支知识；Reader 世界线 Sheet 的生成按钮在运行时可「停止生成」。
- 校验：`canProceed=false` 即使 violations 为空也会触发一次重写；plan 的 futureRisks 不再进入 Writer 上下文。
- 文件安全：世界线 id 拒绝 `.`、`..` 和路径分隔符；列表/删除文件 IO 移到 IO 线程。
- 可读性：Reader 世界线成功文案和进度条改用 ReaderTheme 颜色，避免浅纸色下低对比；设置卡说明设置会在下次续写/重写时保存。
- 上下文：旧分支摘要/最近正文分别控制，最近正文取结尾；知识事实按距分叉点近的优先。

## 验证

- `160 JVM tests / 0 failures / 1 skipped`
- lint `0 errors`
- `assembleDebug` 通过，真机安装
- 真实 DeepSeek 测试沿用 0.9.9 的创建/连续续写/重写结果；本轮主要修交互与数据一致性，未重复跑完整 20 章长线。
