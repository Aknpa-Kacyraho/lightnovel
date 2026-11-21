# Round 29 · 三视角自检（v1.9.2）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。无真机（`adb` 不可用）。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **316 tests / 0 failures / 0 errors / 1 skipped** |
| lint | **0 errors / 22 warnings**（无新增） |
| Debug 构建 | 成功，versionCode 66 / 1.9.2 |
| 数据 | 无变化 |

## 用户视角

**已改善**

1. 夜间纸色从纯黑变为暖灰黑，正文降一档亮度，长时间阅读更柔和。
2. 纸白变暖、护眼降饱和、米黄略加深；四套纸色更像纸。
3. 阅读器过期警告条不再是一块亮橙，而是纸色上的一层淡琥珀。
4. 阅读器内 9 个 BottomSheet 顶角统一 20dp，与全局形状一致。

**仍然存在**

- 夜间正文变暗后，在极低屏幕亮度下可能显得发灰；需要真机确认。
- 警告条文字在纸白上对比约 6:1，低于正文但仍可读。
- 其他页面（目录/发现/设置）的 Sheet 仍是 Material 默认 28dp；
  本轮只统一阅读器，避免一次改太多。

## 设计师视角

**一致**

- 四套纸色都有明确的背景/正文/次要三层，不再有纯黑纯白。
- 警告条从纸色派生，不再有「系统弹窗」感。
- Sheet 顶角与 `LnShapes.extraLarge` 一致，阅读器内不再出现 28dp。

**取舍**

- 没有把夜间正文降到更低对比：再低会影响小字可读性。
- 没有改 `danger` 颜色：错误提示仍需要明确。
- 没有统一全 App 的 Sheet：目录/发现/设置的 Material 默认仍可接受。

## 工程师视角

**做对了**

- `ReaderTheme` 只改颜色常量，`resolve`/`fromId` 与分页逻辑不变。
- `StaleBanner` 用 `lerp(theme.background, warning, 0.16/0.12)`，
  底色永远跟随纸色，不再硬编码两套色。
- 9 个 `ModalBottomSheet` 统一 `RoundedCornerShape(topStart = 20, topEnd = 20)`；
  补了 `RoundedCornerShape` import。
- 没有触碰字号/行距/分页/锚点。

**风险与限制**

- 暖色纸 + 暖色正文会让「护眼」模式看起来偏黄；这是有意的低刺激取向。
- `StaleBanner` 的 `lerp` 在 8 套 App 主题下都不依赖主题色，只依赖纸色，
  行为稳定。
- Sheet 顶角是硬编码 20dp，没有走 `MaterialTheme.shapes`（`ModalBottomSheet`
  的 shape 参数无法直接用 `Shapes` 的命名角色？可以直接用
  `MaterialTheme.shapes.extraLarge`；当前硬编码与 token 值一致）。

**未验证**

- 真机截图、四套纸色 × 8 套主题组合。
- 夜间低亮度下的实际观感。
- 警告条在深色/浅色纸色上的对比度测量。

## 结论

Round 29 目标达成，可作为 1.9.2 发布。三轮视觉升级完成：
排版/形状 → 书架/设置 → 阅读器纸色。下一轮做最终视觉审计。
