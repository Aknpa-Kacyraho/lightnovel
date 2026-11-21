# Round 23 · 三视角自检（v1.8.1）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。无真机（`adb` 不可用）。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **307 tests / 0 failures / 0 errors / 1 skipped**（+7） |
| lint | **0 errors / 22 warnings**（无新增） |
| Debug 构建 | 成功，versionCode 60 / 1.8.1 |
| 数据 | 无 DB schema 变化；sidecar 字段不变 |

## 用户视角

**已改善**

1. 改术语后只重译一段：整章仍显示「术语已更新」，不会被单段操作掩盖。
2. EPUB 导入后正文不再出现「漢字かんじ」这类注音残留。
3. 备份不再包含 `.bak-*` 旧目录与 `cache`，体积更小、隐私面更窄。

**仍然存在**

- 单段重译后用户仍需要整章重译才能消除过期提示；没有「逐段进度」显示。
- `<rt>` 若被作者用于非注音内容（少见的注释），会随注音一起移除。
- 本地 `.bak-*` 目录仍占用存储，应用不自动清理。

## 设计师视角

**一致**

- 没有新增/删除控件、文案或 loading。
- 过期横幅只在真正需要时出现，且不会再被单段重译误清除。
- EPUB 正文更接近「可读文本」，段落结构与换行不变。

**取舍**

- 没有为「单段已重译」增加特殊标记：整章仍未完成，提示保留是正确的。
- 没有在备份完成提示里说明「已跳过旧目录」：用户不需要知道过滤规则。

## 工程师视角

**做对了**

- `retranslatedParagraphSidecar` 只更新内容字段，`old.copy` 天然保留
  `translationConfigHash/modelProvider/modelId/promptVersion/glossary*`。
- `stripHtml` 先移除 `<rt>/<rp>` 再处理换行，正则使用 `DOT_MATCHES_ALL`，
  跨行注音也能清理。
- `isExportableRelativePath` 按路径段判断 `.bak-` 与 `cache`，
  比只看文件名更完整；`filesUnder` 复用同一规则。
- 新增 2 条 sidecar、1 条注音、4 条路径测试，全部纯 JVM。

**风险与限制**

- 单段重译保留旧 `translationConfigHash`，模型切换后整章会持续提示过期，
  直到整章重译；这是符合事实的状态。
- `Files.copy` 在合并目录时不保留原文件属性；内容正确，时间戳可能变化。
- `isExportableRelativePath` 会排除任何名为 `cache` 的目录；当前书籍目录里
  只有翻译缓存使用该名字。

**未验证**

- 真机上重译一段后的横幅出现/消失。
- 复杂 EPUB（嵌套 `<ruby>`、`<rt>` 内含标签）的清理效果。
- 大备份导出时路径过滤的性能。

## 结论

Round 23 目标达成，可作为 1.8.1 发布。下一轮做全量扫描，确认是否还有
P0/P1/P2 级可复现 bug；若只剩设计权衡与 P3，则收敛。
