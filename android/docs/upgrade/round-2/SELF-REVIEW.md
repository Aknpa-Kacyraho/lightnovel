# Round 2 · 三视角自检（v1.1.0）

> 验证环境：Windows 开发机，Gradle 8.13，JDK 17，Android SDK 36。无真机（`adb` 不可用）。

## 结果摘要

| 项 | 结果 |
| --- | --- |
| JVM 测试 | **192 tests / 0 failures / 0 errors / 1 skipped**（+14：空态 5、设置 3、菜单 5、任务 1） |
| lint | **0 errors / 22 warnings**（与 1.0.4 持平，无新增） |
| Debug 构建 | `:app:assembleDebug` 成功 |
| 版本 | `versionName 1.1.0` / `versionCode 39` |
| 数据库 | 无 schema/迁移变化 |
| 用户资产 | 无写入路径变化 |

## 用户视角

**已改善**

1. 空书架第一次打开只看到一个实心按钮「去发现」；「导入备份 · 导入 TXT / EPUB」
   降为一行次级入口，旁边两行说明直接回答「第一次用」与「有旧备份」。
2. 备份提醒的「去设置」直达「数据」分组，高亮 2 秒；不用再从头滚。
3. 阅读器菜单分成阅读 / 翻译 / 资料 / 世界线四组，「世界线」不再夹在字号与术语之间。
4. 任务筛选标签直接显示数量（失败 3），点数字就是筛选，少一次「看数字→找 chip」。

**仍然存在**

- 1.5x 字体下动作行会挤（Round 3 FlowRow）。
- 横屏正文没有宽度上限（Round 3）。
- 翻译前没有字数提示（Round 3）。

## 设计师视角

**一致**

- 空态只有 1 个实心按钮，符合 Material 单一主操作；说明文字 `onSurfaceVariant`，
  不与标题抢层级。
- 菜单组标题 `bodySmall` + `onSurfaceVariant`，与菜单项左对齐；组间 `HorizontalDivider`
  使用 Material3 默认厚度，不新增颜色。
- 设置高亮用 `primaryContainer.copy(alpha = 0.6f)` + `animateColorAsState`，
  2 秒后回到 `surface`，8 套主题都不写死颜色。
- 统计 chip 复用 `BrandFilterChip`，不新增控件。

**取舍**

- 菜单没有改成底部 Sheet：分组已解决「找不到」，Sheet 会改变阅读器沉浸感。
- 「导入备份」不再是主按钮：旧备份用户少于新用户，主次按真实概率排。
- 任务统计不单独做一行数字：直接并入 chip，避免两套筛选 UI。

## 工程师视角

**做对了**

- `emptyShelfCopy(...)` 是纯函数，5 个分支全部有断言；Composable 只做渲染。
- `readerMenuItems(...)` 把 13 个动作、4 个组、启用条件集中到一处；
  `ReaderMenuTest` 防漏项、防组顺序漂移。
- 设置深链用 `settingsFocus` 状态 + 白名单 `SettingsFocus.parse`，
  非法值不会触发滚动；`withTimeoutOrNull(1_000)` 兜底，布局异常时最多等 1 秒。
- `settingsFocus` 用 `rememberSaveable`，进程重建后仍能完成定位；消费后置空，
  二次进入设置不会重复滚动。

**风险与限制**

- 设置滚动定位依赖 `onGloballyPositioned` 的首帧位置；若分组尚未测量（极慢设备），
  1 秒后放弃滚动，用户仍在设置顶部——不会卡死，但也没到达。
- 菜单分组后总高度不变，`DropdownMenu` 仍可能超出屏幕并内部滚动；这是原有行为。
- 空态文案变长，360dp + 大字体下可能增高；未在真机核对（无 `adb`）。

**未验证**

- 真机点击「去设置」后的滚动动画与高亮时长。
- 8 套主题下 `primaryContainer` 高亮的对比度（使用主题 token，理论安全）。
- 阅读器菜单在横屏下的滚动与分组标题可见性。

## 结论

Round 2 目标达成，可作为 1.1.0 发布。大字体、横屏与翻译字数提示移交 Round 3。
