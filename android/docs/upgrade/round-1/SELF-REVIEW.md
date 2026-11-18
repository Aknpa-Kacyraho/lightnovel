# Round 1 · 三视角自检（v1.0.4）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。
> 未连接真机（`adb` 不可用），TalkBack 与触控行为只做代码/静态验证，见「未验证」小节。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **178 tests / 0 failures / 0 errors / 1 skipped**（新增 `TaskIgnoreStoreTest` 6 项） |
| lint | **0 errors / 22 warnings**；`ClickableViewAccessibility`、`ObsoleteSdkInt`、`AutoboxingStateCreation` 均为 0 |
| Debug 构建 | `:app:assembleDebug` 成功，产出 `app-debug.apk` |
| 版本 | `versionName 1.0.4` / `versionCode 38` |
| 数据库迁移 | 无（不涉及表结构） |
| 用户资产 | 无写入路径变化；忽略键仍是独立 SharedPreferences |

## 用户视角

**已改善**

1. 任务页误点「忽略」不再不可逆：出现 Snackbar「已忽略第 N 话，只从列表隐藏」，
   点「撤销」恢复，和书架「移出书架」的交互一致。
2. TalkBack 聚焦阅读页会听到「第 x 页，共 y 页」，不再是无声画布；
   双击任意位置都有点击事件，不再只有点中术语时才响应。
3. 备份提醒直接告诉路径「设置 → 数据 → 导出备份」，不用自己找。

**仍然存在（记录到后续轮次）**

- 首次启动空书架仍是「导入备份 / 导入 TXT / 去发现」三个入口，主次不清（Round 2）。
- 阅读器菜单一屏十几项，没有分组（Round 2）。
- 设置页没有锚点，从书架点「去设置」后仍要手动滚到数据分组（Round 2）。

## 设计师视角

**一致**

- Snackbar 复用 Material3 默认样式与现有书架撤销模式，未新增颜色、圆角或阴影。
- 任务按钮视觉尺寸不变，只增加语义说明，不破坏按钮行在 360dp 下的布局。
- 阅读器页码语义是纯无障碍信息，不新增可见元素，不改变页码浮层。

**取舍**

- 未给「忽略」加红色/警告色：8 套主题下容易失衡，且忽略本身可撤销，不需要危险色。
- 未改任务卡按钮顺序：本轮只降低误解成本，不改变肌肉记忆。

## 工程师视角

**做对了**

- `ReaderPageView` 的 `performClick()` 放在 `ACTION_UP` 且 `!moved` 分支，
  翻页手势（Pager）与查询模式点词都不受影响；`handleTap` 不再重复调用。
- `contentDescription` 写在 `AndroidView.update`，页码变化时会刷新，不依赖重组时机。
- `TaskIgnoreStoreTest` 覆盖写入、重入、去重、定向清除、缺失键、损坏分隔符六种情况。
- 版本号、README、`04-final.md`、`CHANGELOG.md` 同批更新，发布可追溯。

**风险与限制**

- Snackbar 的撤销在页面离开后失效（协程随 Composable 销毁）；可接受，因为忽略本身
  持久化，用户仍可在重启后通过清除数据恢复——但这不算产品级恢复入口，Round 2 评估
  「已忽略」筛选。
- `ReaderPageView` 的 `contentDescription` 只描述页码，不描述正文；整页朗读仍由 TTS
  负责，避免伪造可读文本。
- lint 仍有 22 条警告：依赖版本提示、`UseKtx`、`TabRow`/`ClickableText` 弃用。
  这些不是缺陷，Round 3 统一处理弃用 API。

**未验证**

- 真机 TalkBack 朗读顺序与焦点框（无 `adb`）。
- 实际手指点击与滑动在 120Hz/60Hz 屏幕上的 `performClick` 时序。
- 8 套主题下 Snackbar 对比度（使用 Material 默认反色，理论安全）。

## 结论

Round 1 目标全部达成，可作为 1.0.4 发布。剩余问题已登记到 Round 2/3 指南。
