# 0.9.5 打磨记录

发布时间：2026-11-02

## 修复

- **查询模式“API 返回空正文”**：DeepSeek `deepseek-flash` 的 thinking 会把答案写进 `reasoning_content`，官方端点显式关闭 thinking；错误信息补充 `finish` 与 `reasoning` 长度。
- **知识抽取全空**：补全 `entities/facts/relations/voiceFacts/secrets` 的完整 JSON schema，`sourceQuote` 强制逐字复制日文原文。
- **出处校验**：精确匹配失败后按去空白文本、实体名兜底，仍找不到才锚到本章开头，不再整章丢弃。
- **术语表为空**：抽取成功后把实体 `source -> canonicalName` 写入本书 `story.json`，已有词条不覆盖。
- **章节标题空白**：打开详情时从源站目录回填 `fillChapterTitle`，并立即更新目录 UI。
- **滚动掉帧**：`onScrollParagraphChanged` 加 120ms 防抖，避免每滑过一段就重组整页；进度写入仍保留 500ms 防抖。

## 改动

- 阅读器「编辑并生成世界线」改为全屏正文编辑器，`forkText` 进入 Planner/Writer 上下文。
- 大书库标签增加可搜索的 `TagPickerSheet`，「更多」固定在「全部」后面。
- 查询模式开启且本章未抽取时自动抽取；`queryNames` 变化时递增 revision 触发重新分页高亮。
- 翻译分段在无空行时按单换行切段，再按 `maxChars` 聚合；上下文本尾部 400 → 1200 字。
- 精简发现页、大书库、本书设定、世界线和查询面板文案。

## 验证

- `141 tests / 0 failures / 1 skipped`
- lint `0 errors / 25 warnings / 2 hints`
- 真机：本书知识库 10 个实体、29 条资料；术语表 9 条；查询模式出现下划线。
- 滚动实测：查询模式关 0.52% janky，开 0.13%，90th 12ms。
- 世界线真实生成未执行（会消耗 token）。

## 产物

- 版本：`0.9.5` / code28
- APK：`lightnovel-0.9.5-debug.apk`
- Release：https://github.com/Aknpa-Kacyraho/lightnovel/releases/tag/v0.9.5
