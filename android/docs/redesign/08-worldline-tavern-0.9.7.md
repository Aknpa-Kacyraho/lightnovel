# 0.9.7 世界线酒馆式续写

日期：2026-11-03

> 0.9.8 仅收尾连续续写进度提示：改为页面内联，不再逐条弹 Snackbar；世界线能力不变。
> 0.9.9 收尾长篇上下文：前情摘要保留最近 20 章，最近两章正文取结尾；Writer JSON 明确要求梗概和状态。

## 目标

把世界线从「一次性生成一段」补成可持续写的分支工具，参考 SillyTavern 的有效机制：作者备注、世界信息/角色知情边界、上下文历史、长度控制、重写与连续生成；不复制其 GPL 代码。

## 实现

- 分支设置：`WorldlineFile` 新增 `lengthMode`、`creativity`、`directive`、`chapterStates`。
- 长度档位：短 800–1800、标准 1600–3200、长 3000–6000 字；Writer prompt、`maxTokens`、校验范围都按档位变化。
- 创作强度：稳定 0.55 / 均衡 0.8 / 放开 1.0，写入 Writer temperature。
- 作者备注：长期生效，进入 Planner 和 Writer；不得越过 canon 安全边界。
- 长篇上下文：`branchHistory` 带最近两章正文 + 更早章节摘要；同时保留上一章梗概/结尾、分支状态、分支知识、角色知情边界和分叉前原文。
- 连续续写：一次 1/3/5 章，逐章保存；中途失败保留已生成章节。
- 重写本章：删除最后一章及其分支知识，按新设置重生成，保留前面章节。
- 正文兼容：真实模型返回 `content` 而非 `text`；同时兼容 `body/chapterText`，标题/梗概/状态/偏离缺失自动补。
- 网络与解析：规划、写作、校对、差异、知识抽取统一 503/超时退避重试；plan 兼容根数组与对象 beats。
- UI：世界线设置卡、长度/创意/连续续写 chips、作者备注、自动滚到最新章、重写确认、正文可选中复制；颜色全部来自 MaterialTheme。

## 真实 token 验证

- DeepSeek 官方 `deepseek-flash`，短档 + 稳定 + 作者备注：
  - 创建 1375 字
  - 连续续写 2 章：1981、1726 字
  - 重写最后一章：2200 字
- 另一次标准档创建 2713 字；OpenCode Go `deepseek-v4.1-flash` 标准档 3915 字。
- 以上均通过同一 `WorldlineService`、真实 JSON 解析和校验链路。

## 验证

- `159 JVM tests / 0 failures / 1 skipped`
- lint `0 errors / 25 warnings / 2 hints`
- `assembleDebug` 通过，真机覆盖安装
- 发布：`v0.9.7`
