# Round 17 · 三视角自检（v1.6.1）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。无真机（`adb` 不可用）。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **274 tests / 0 failures / 0 errors / 1 skipped**（+4 PendingReaderJump） |
| lint | **0 errors / 22 warnings**（无新增） |
| Debug 构建 | 成功，versionCode 54 / 1.6.1 |
| 数据 | 无 schema 变化；pending 锚点只在内存 |

过程中修复了一处自己的编辑错误：`paginationJob` 与 `saveJob` 被误拼到同一行，
导致 `saveJob` 未声明；已恢复为两行。

## 用户视角

**已改善**

1. 快速切换原文/译文/双语，最终内容与最后一次选择一致。
2. 跨章书签点击后，目标章加载完成会自动定位到书签段落。
3. 跨章搜索结果同样自动定位。
4. 连续加书签，提示立即替换，不再排队延迟。

**仍然存在**

- 跨章定位依赖内存锚点；进程被杀后丢失（跳转本身也失败）。
- 目标章加载失败时停在章首，锚点保留到下次进入。
- 同章跳转仍会写阅读进度（预期）。

## 设计师视角

**一致**

- 没有新增 loading、弹窗或按钮。
- 跨章跳转后由正文位置体现结果，不额外提示。
- 提示仍 1.5 秒，视觉不变。

**取舍**

- 没有为跨章跳转做「正在定位」提示：加载很快，提示会闪。
- 没有把 pending 锚点持久化：跨进程场景不是主要路径。

## 工程师视角

**做对了**

- `loadJob` 只保留最新请求，`ensureActive()` 在写状态前拦截取消的旧请求。
- `PendingReaderJump` 是纯内存 map，take 即清，避免循环跳转。
- 消费时机用 `!loading && error == null`，失败不消费。
- `collectLatest` 用现有 `bookmarkNotice`，不新增状态。

**风险与限制**

- `jumpToAnchor` 会再触发一次 `load()`，目标章多一次分页；可接受。
- `ensureActive()` 在 `withContext(IO)` 内调用，取消时会抛异常并被 `withContext` 传播；
  不会吞掉真正的 IO 错误（IO 错误在 `runCatching` 内）。
- pending 锚点未做并发保护（只在主线程读写），当前调用点都在 Compose 主线程。

**未验证**

- 真机上快速切换模式的最终一致性。
- 跨章跳转的定位准确度（尤其长章节）。
- 连续提示替换的视觉效果。

## 结论

Round 17 目标达成，可作为 1.6.1 发布。最后三个小修复留给 Round 18。
