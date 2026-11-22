# Round 30 · 三视角自检（v1.9.3）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。无真机（`adb` 不可用）。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **325 tests / 0 failures / 0 errors / 1 skipped**（+9） |
| lint | **0 errors / 22 warnings**（无新增） |
| Debug 构建 | 成功，versionCode 67 / 1.9.3 |
| 数据 | 无 schema 变化 |

## 用户视角

**已修复**

1. 导入旧备份不再把本机阅读进度重置为第 1 话；重复导入幂等。
2. 备份/EPUB 导出失败或取消时，刚创建的目标文件会被删除。
3. 任务中心取消翻译后，阅读器横幅回到「已取消翻译」，可立即重新翻译。
4. `.txt` 的 EPUB 按 ZIP 文件头识别；单引号 spine 的章节顺序正确。
5. 停止下载 worker 时取消会穿透，不再多跑并记成失败。
6. 旧备份里字段不全的 sidecar 不再让「润色本章」崩溃。
7. 书签随备份导出/恢复，重复导入不重复；旧备份没有书签文件也能导入。
8. 只加入书架、从未下载的书在恢复后保留书与状态。
9. 「未译全」章节在任务中心/章节页重试时真正重译。
10. 滚动模式的搜索/书签/模式切换位置与段落对齐。

**仍然存在**

- 已发出的 OkHttp 请求无法中途打断；取消只阻止后续写入。
- 部分 SAF provider 不支持删除，导出失败仍可能留下空文件（已尽力）。
- 无真机：上述交互路径未在设备上逐条复现。

## 设计师视角

**一致**

- 失败路径遵循「回到上一个好状态」：导入保留本机进度，导出不留下坏文件，
  取消退出转圈。用户不需要理解数据层，也不会被中间态困住。
- 没有为这些修复新增弹窗、颜色或布局，正常路径的视觉不变。
- EPUB 容错优先于扩展名，减少「导入后乱码」这类不可解释的结果。

**取舍**

- 保守合并：备份状态文件缺少时间戳时保留本机，而不是猜备份更新。
- 取消后立刻重试可能短暂提示「已有任务」，换取不与旧任务清理竞争。
- ZIP 头误判（如导入备份 zip 到书库）会明确报错，而不是解码成乱码。

## 工程师视角

**做对了**

- `BackupImportService` 区分「备份有状态文件」与「只有 library 条目」：
  前者按时间合并，后者不触碰本机；`defaultState` 只服务新书。
- 导出统一走 `discardCreatedDocument`，失败与取消都清理，取消再重抛。
- `translateChapter` / `polishChapter` 的 job 捕获取消并复位 `_translationState`。
- `TranslationTaskRegistry` 把 job 保留到 completion，`register` 只接受空槽位，
  消除「取消后立刻重试」与旧任务 `NonCancellable` 清理的竞态。
- 队列遇到其他入口正在翻译的章节记为 skipped，不再虚增完成数。
- `ReaderViewModel.load`、`ReadingTranslationCoordinator`、`LibraryViewModel`、
  `SettingsViewModel.save` 的挂起调用改为取消透传。
- `FileContentStore.readSidecar` 解码失败返回 null，`polishChapter` 再兜底一层。
- `BackupExporter` / `BackupImportService` 支持 `data/bookmarks.json`；
  DAO 增加 `allBookmarks` / `upsertBookmarks`。
- `ImportPlanner` 把 `missing_dir` 书转成 `PlannedBook`，`LibraryCommitter`
  跳过没有 staging 目录的书。
- `mergeDirectory` 用 `<name>.part` + `ATOMIC_MOVE`，中断不再留下截断文件。
- `hasFinalTranslation` 让 `partial` 章节继续翻译。
- `readerScrollBlocks` 让滚动列表与 `Paragraphs.split` 的段模型一致，
  空行项零高度渲染。

**风险与限制**

- `defaultState` 用 `addedAt ?: now` 作为新书 `updated_at`，导入后可能出现在
  「最近阅读」前列；这是新书默认状态，不影响已有书。
- `register` 严格化后，取消到 completion 之间的重试会被拒绝；窗口通常几毫秒。
- `discardCreatedDocument` 的删除失败被静默忽略，不掩盖原始导出错误。
- EPUB 判定只看 ZIP 头；docx 等 ZIP 会报「缺少 content.opf」，不会乱码。

**未验证**

- 真机上的 SAF 删除行为（不同文件管理器 provider）。
- 任务中心取消 → 返回阅读器的实际动画与按钮状态。
- 旧备份在真实设备上的重复导入。

## 结论

Round 30 的 14 类修复全部落地（含 1 个 P0、7 个 P1），测试与 lint 通过。
数据恢复路径（进度、书签、未下载书、坏 sidecar）与阅读器滚动定位已覆盖；
P2 取消路径也做了透传。下一轮继续复审剩余 P1（章节元数据、唯一键冲突、
storageDir 一致性）与 P2 体验问题。
