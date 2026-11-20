# Round 4 · 三视角自检（v1.2.0）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。无真机（`adb` 不可用）。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **212 tests / 0 failures / 0 errors / 1 skipped**（+13：纸色 6、横幅 6、默认值 1） |
| lint | **0 errors / 22 warnings**（无新增） |
| Debug 构建 | `:app:testDebugUnitTest :app:lintDebug :app:assembleDebug` 成功 |
| 版本 | `versionName 1.2.0` / `versionCode 41` |
| 数据 | 无 schema/迁移/备份格式变化 |

过程中有一次真实失败：`ReaderBannerTest.translatedChapterWithoutQueueShowsNothing`
发现 `shouldShowTranslationBanner` 对「已翻译」仍返回 true，已修正为按状态白名单返回。

## 用户视角

**已改善**

1. 系统深色 + 新安装：阅读器自动用夜间纸色，不再白屏刺眼；浅色系统用纸白。
2. 未翻译章节不再常驻「本章还没翻译」横幅；只有翻译中、失败、预译队列才出现。
3. 夜间正文从 `#C8C5BE` 调到 `#BDBAB2`，关灯阅读不再觉得字在发光。
4. 设置页纸色从 4 项变 5 项，「跟随系统」排第一，可一眼选中。

**仍然存在**

- 已有用户如果手动选过「纸白」，升级后不会自动跟随系统（这是有意的，不覆盖用户选择）。
- 顶部仍是三层 chrome（Round 6 处理）。
- 阅读器没有亮度/暖色调节（明确不做）。

## 设计师视角

**一致**

- 「跟随系统」chip 与其余纸色同一组件、同一选中态，不新增图标或色块。
- 横幅消失后，翻译状态点仍在顶栏，状态可查；不是「隐藏信息」。
- 夜间正文仍是中性灰，不偏蓝/偏黄；对比度 9.7:1，低于原 11.2:1。
- 纸色切换仍即时生效，无重启、无闪屏。

**取舍**

- 没有为「自动翻译开启但未开始」保留一行轻提示：菜单里「翻译本章」足够。
- 没有把纸色预览做成色块：文字标签在 5 项时更紧凑。

## 工程师视角

**做对了**

- 偏好（`state.theme` 可能是 `auto`）与渲染（`resolve(dark)`）分离；
  `persistSettings` 回写偏好，不会把解析结果固化。
- `ReaderTheme.fromId` 的 fallback 仍是 PAPER，未知值不会崩。
- 对比度用 WCAG 公式独立实现，测试不依赖 UI。
- 横幅纯函数有 6 个场景，包含「已翻译且无队列」这个容易写错的边界。

**风险与限制**

- `ReaderTheme.entries` 现在含 `AUTO`：任何「遍历 entries 直接渲染」的新代码都要先 resolve。
- `isSystemInDarkTheme()` 在阅读器内是 Compose 状态，系统切换会重组；
  `DisposableEffect(readerTheme)` 会重设状态栏图标，理论上无闪烁，未真机确认。
- `SettingsStoreTest` 共享 DataStore 文件，测试顺序可能影响默认值断言；
  当前同文件内先读默认再写入，顺序稳定。

**未验证**

- 真机深色系统下进出阅读器的实际亮度跳变。
- 自动翻译场景中横幅抑制是否符合预期（需要真实翻译任务）。
- 8 套主题下「跟随系统」chip 的选中态对比度。

## 结论

Round 4 目标达成，可作为 1.2.0 发布。深色全局层级与眩光留给 Round 5。
