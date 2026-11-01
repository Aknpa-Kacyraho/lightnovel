# 02 · 视觉系统与主题改造方案

> 范围：Android 原生 App「Ka小说家」的视觉 token、主题、标签、详情/发现/书架/设置四页与无障碍适配。只做设计，不改代码、不构建、不新增依赖。
> 参考：`auto-novel` 的 `web/src/pages/novel`、`home`、`list`、`reader` 组件。只吸收“信息分层、留白、标签主次、简介折叠、设置分栏”思想；GPL 代码、样式和资产一律不复制。
> 基线：`Theme.kt`、`BrandChips.kt`、`DiscoverScreen.kt`、`ChapterListScreen.kt`、`LibraryScreen.kt`、`SettingsScreen.kt`、`ReaderComponents.kt`、`ReaderTheme.kt`。

## 1. 设计原则 / 非目标

**原则**

1. **阅读优先**：书架和详情先回答“读哪本、从哪继续”，装饰让位于可读性。
2. **安静表面**：大面积用纸色/低彩表面，主色只出现在主操作、当前项和关键状态。
3. **一个语义一个来源**：标签、状态、来源、进度全部从当前 `ColorScheme` 派生，禁止在业务页面写死蓝/粉/绿；同一含义在发现页、详情页、阅读页必须同色同形。
4. **先分区再堆内容**：简介、标签、目录、统计不共用一条滚动流；能收进 Tab、底部面板、折叠区的功能不常驻首屏。
5. **触控与对比先于美观**：正文对比度 ≥ 4.5:1，可点区域 ≥ 48dp，状态不能只靠颜色。

**非目标**

- 不改导航结构、不改阅读器分页/翻译管线、不引入图片加载库或第三方 UI 库。
- 不复制 `auto-novel` 的 Vue 组件、CSS、插画；不追求“网页搬进 App”。
- 不做动态取色默认开启、不做每本书自定义主题、不做复杂玻璃拟态/大面积阴影。
- 不为了“有设计感”牺牲中文长标题、日文书名、2 倍字号的可用性。

## 2. 现状诊断（用户反馈对应）

| 反馈 | 现状证据 | 直接后果 |
| --- | --- | --- |
| 标签颜色和主题对不上 | 发现页用默认 `AssistChip`（`DiscoverScreen.kt:226-229`、`:305-308`）；详情页标签是 `secondary` 纯文本（`ChapterListScreen.kt:208-216`）；`BrandChips.kt:18-22` 只定义选中态 | 默认 AssistChip 与主题脱节；详情页看不出“标签”，三处语义不一致 |
| 只有 3 套主题且不喜欢 | `Theme.kt:10-22` 仅 `teal/lavender/sakura`；`LightnovelTheme` 只传 `colorScheme` | 选择少、三套都是“主色换皮”，没有明显不同的色相与气质 |
| 简介和章节挤在一起 | 详情页 `BookHeader` 把标题、标签、6 行简介、分割线放在章列表前（`ChapterListScreen.kt:167-177`） | 首屏信息密度高，简介像“章节前言”，找不到目录起点 |
| 界面杂乱、功能没归类 | 发现页两个输入框+两个按钮常驻（`:102-143`）；详情页顶栏“下载全部/导出 EPUB”文字按钮（`:105-122`）；设置页所有分组平铺（`SettingsScreen.kt:140-291`）；阅读顶栏 7 个文字按钮（`ReaderComponents.kt:234-277`） | 主要动作被次要动作稀释，常用功能找不到 |
| 状态色散落 | 阅读页状态点硬编码蓝/黄/绿/红（`ReaderComponents.kt:44-50`）；章节状态直接用 primary/tertiary/error 纯文字（`ChapterListScreen.kt:281-289`） | 换主题后状态色仍是“另一套 App”，且没有容器/形状区分 |

**参考吸收（只借层级，不借代码）**：`NovelTag` 的“关注标签加粗、关键词标签弱化”；`WebNovelIntroduction` 的 6 行折叠 + 渐隐 + 展开；`WebNovelMetadata` 的“标题→作者→操作→统计→简介→标签”顺序；`NovelListWeb` 的“标题在前、元信息压低”；`ReaderSettingModal` 的“内容/样式分 Tab、滑杆、纸色色块”；`style.css` 的“桌面 1000px 内容宽度、手机 12px 边距”改为 App 的 840dp / 16dp。

## 3. 视觉系统

### 3.1 Token 分层：哪些用 MaterialTheme，哪些扩展

| 层 | 提供者 | 内容 | 使用规则 |
| --- | --- | --- | --- |
| Material 标准 | `MaterialTheme.colorScheme` | primary/onPrimary/primaryContainer、secondary、tertiary、background、surface、surfaceVariant、outline、error | 所有通用控件、正文、按钮、导航 |
| Material 标准 | `MaterialTheme.typography` | 全部文字层级 | 页面只能引用 `MaterialTheme.typography.*`，不写 `fontSize = 15.sp` |
| Material 标准 | `MaterialTheme.shapes` | extraSmall 4 / small 8 / medium 12 / large 16 / extraLarge 28 | 卡片、按钮、面板统一取 shapes |
| 扩展 | `LnTokens`（CompositionLocal） | 间距、圆角别名、动效、表面层级、内容最大宽度 | 只在布局/容器使用，不用来覆盖 Material 语义 |
| 扩展 | `LnExtendedColors`（CompositionLocal） | `tagType*`、`tagKeyword*`、`tagStatus*`、`tagSource*`、`success/warning/info`、`surfaceTier1/2`、`divider`、`coverGradient` | 只给标签/状态/封面占位/分区卡；全部由 `ColorScheme` 计算 |
| 禁止 | 业务文件 | 任何 `Color(0xFF...)`；任何 `Color.Blue/Pink/Green` | 只允许 `ui/theme/` 和 `reader/engine/ReaderTheme.kt` 出现字面色值 |

```kotlin
// 设计示意，不是实现代码
data class LnTokens(
    val space: Spacing, val radius: Radius, val motion: Motion,
    val contentMaxWidth: Dp = 840.dp, val coverAspect: Float = 3f / 4f,
)
@Composable fun LnTheme.colors(): LnExtendedColors = LocalLnColors.current
```

### 3.2 色彩规则

- 60/30/10：背景 60%，表面/容器 30%，primary 不超过 10%。一屏只保留一个主按钮。
- `background` 是纸色底；`surface` 是卡片/列表底；`surfaceVariant` 只给输入框、未选 FilterChip、中性标签；不要拿 primary 做大面积背景。
- 主色用于：当前章节、主按钮、选中态、进度条；secondary 用于次级强调/进行中；tertiary 用于“未译全/过期/提醒”；error 只给失败/危险操作。
- 表面层级不靠重阴影：浅色用 1dp `outlineVariant` 描边，深色用更亮的 surface 分层。
- 所有颜色在 `LightnovelTheme` 内按 `themeId + darkTheme` 选择，不在 Composable 里判断。

### 3.3 字体层级

| Token | 字号/行高 | 字重 | 用途 |
| --- | --- | --- | --- |
| `displaySmall` | 28/36 | SemiBold | 空态大标题、关于页品牌字（少用） |
| `headlineSmall` | 22/30 | SemiBold | 详情页书名、页面主标题 |
| `titleLarge` | 20/28 | SemiBold | 书架/发现页标题 |
| `titleMedium` | 16/24 | Medium | 卡片标题、设置分组标题 |
| `titleSmall` | 14/20 | Medium | 小节标题、简介卡标题 |
| `bodyLarge` | 16/26 | Normal | 简介正文、阅读器默认正文参考 |
| `bodyMedium` | 14/22 | Normal | 常规说明、设置项副标题 |
| `bodySmall` | 12/18 | Normal | 元信息、辅助说明（最多 2 行） |
| `labelLarge` | 14/20 | Medium | 按钮文字 |
| `labelMedium` | 12/16 | Medium | 标签、FilterChip |
| `labelSmall` | 11/14 | Medium | 状态徽标、页码、脚注 |

- UI 用系统 sans（中文回退 Noto Sans CJK）；书名 hero 可用系统 serif（Noto Serif CJK），不打包字体。阅读器仍按用户选择的宋体/黑体/等宽，不受 App 主题影响。
- 中文正文行高不低于字号的 1.55 倍；`bodySmall` 不承载长段落；标题最多 2 行。

### 3.4 间距、圆角、触控

- 间距刻度只取 **4 的倍数**：2 / 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48dp。
- 手机左右边距 16dp；平板 24dp；内容最大宽度 840dp。分区之间 24dp，卡片之间 12dp，列表项之间 8dp；卡片内边距 16dp（紧凑卡 12dp）；标签间距 6dp。
- 圆角：状态徽标 6dp；标签/FilterChip 8dp；普通卡片 16dp；封面/紧凑卡 12dp；底部面板顶部 28dp；按钮 12dp（不再用默认全圆角）；头像/圆形按钮用 50%。
- 所有可点元素视觉高度可小于 48dp，但必须用 `minimumInteractiveComponentSize()` 或外层 48dp padding 补足触控；标签视觉 24–32dp，触控 48dp。

### 3.5 表面层级、分割线、阴影

| 层级 | 颜色/样式 | 用途 |
| --- | --- | --- |
| L0 | `background` | 页面底 |
| L1 | `surface` + 1dp `outlineVariant`，无阴影 | 普通卡片、设置分组、简介卡 |
| L2 | `surfaceContainerLow` + 1dp 描边，elevation 1dp | 上次读到、悬浮主操作、底部栏 |
| L3 | `surfaceContainerHigh`，elevation 3dp | 底部 sheet、主题选择器 |
| L4 | `surfaceContainerHighest`，elevation 8dp | 危险确认对话框 |

- `surfaceContainerLow/High/Highest` 用 `surfaceVariant` 与 `surface` 按 24%/48%/72% 混合；`outlineVariant` 用 `outline` 与 `surface` 按 40% 混合。每个 scheme 显式写入，不依赖 Material 默认值。
- 分割线 1dp `outlineVariant`，列表内缩进 16dp；章节行之间优先用 8dp 间距而不是线。
- 深色模式阴影降到 0–1dp，用 surface 亮度差表达层级；禁止纯黑大面积 + 纯白正文。
- 卡片描边永远比阴影优先：一屏阴影不超过 2 处（悬浮续读、模态）。

### 3.6 动效

| 场景 | 时长 | 说明 |
| --- | --- | --- |
| 按压/ripple | 120ms | 标签、卡片、按钮 |
| 选中/颜色切换 | 180ms | FilterChip、Tab、收藏 |
| 主题切换 | 220ms | 颜色 crossfade，不闪白 |
| 页面进入/返回 | 240ms | fade + 4dp 位移 |
| 底部 sheet | 300ms | 标准 easing；不超过 400ms |

使用 `FastOutSlowInEasing`；不做弹跳、旋转、长时间骨架闪烁。系统“移除动画”开启时只保留 0–120ms 的状态变化。

## 4. 八套主题

保留 `teal` / `lavender` / `sakura` 三个 id 与迁移路径，但色板全部重画；新增 5 套明显不同色相的主题。新安装默认 `amber`（暖纸），存量设置按原 id 继续生效；未知 id 回退 `amber`。每套都提供 light/dark，全部 alpha = FF。

| id | 中文名 | 气质 / 色相 | 适合 |
| --- | --- | --- | --- |
| `teal` | 青灯 | 冷青 192° + 铜色，清透纸感 | 通用、白天、理性阅读 |
| `lavender` | 紫夜 | 灰紫 258° + 苔绿，低饱和夜色 | 文艺、夜间、女性向 |
| `sakura` | 樱纸 | 绯粉 343° + 墨绿，柔和和纸 | 恋爱、日常、轻喜剧 |
| `matcha` | 苔庭 | 苔绿 112° + 雾蓝，自然安静 | 治愈、慢节奏、随笔 |
| `amber` | 琥珀 | 琥珀 40° + 松绿，旧书暖光 | 默认、长时间阅读 |
| `indigo` | 靛蓝 | 靛蓝 226° + 珊瑚，深夜强对比 | 悬疑、科幻、夜读 |
| `slate` | 墨灰 | 低彩石墨 200° + 铁锈，克制 | 工具型、专业、极简 |
| `ember` | 枫烬 | 砖红 14° + 橄榄，戏剧性 | 奇幻、战斗、冒险 |

| 主题 | 模式 | primary | onPrimary | primaryContainer | secondary | tertiary | background | surface | surfaceVariant | outline | error |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| teal | L | `#176077` | `#FFFFFF` | `#C7E8F2` | `#8A5A2B` | `#8F4E63` | `#F7F4EC` | `#FFFCF5` | `#E7E0D2` | `#747C7E` | `#B3261E` |
| teal | D | `#8BD3E6` | `#00363F` | `#0B4E60` | `#E7BE8D` | `#F0B3C2` | `#0E1619` | `#151F23` | `#3B474B` | `#8B9597` | `#FFB4AB` |
| lavender | L | `#5B4B9A` | `#FFFFFF` | `#E6DEFF` | `#2E6F5E` | `#9A3F6B` | `#F8F6FC` | `#FFFBFE` | `#E7E0EE` | `#77707E` | `#B3261E` |
| lavender | D | `#CFC1FF` | `#302566` | `#473A85` | `#A7D8C8` | `#FFB0CE` | `#14121B` | `#1C1925` | `#3A3645` | `#958E9F` | `#FFB4AB` |
| sakura | L | `#9E3F58` | `#FFFFFF` | `#FFD9E2` | `#6A5A9E` | `#3F6B5A` | `#FDF6F4` | `#FFFBFA` | `#F0E2E2` | `#857278` | `#B3261E` |
| sakura | D | `#FFB1C6` | `#5F112C` | `#7E2A44` | `#CFC1FF` | `#A8D5C4` | `#1B1215` | `#241A1D` | `#47383C` | `#A58C92` | `#FFB4AB` |
| matcha | L | `#3F6B34` | `#FFFFFF` | `#BFEFAF` | `#59647E` | `#8F4E3F` | `#F7F7EE` | `#FDFCF4` | `#E4E5D6` | `#767A6C` | `#B3261E` |
| matcha | D | `#A5D394` | `#0C3900` | `#28511C` | `#BCC6E0` | `#F0B6A1` | `#11140E` | `#191D15` | `#3B4034` | `#8F9383` | `#FFB4AB` |
| amber | L | `#8A5A00` | `#FFFFFF` | `#FFDFA0` | `#326B63` | `#7B4E7E` | `#FBF6EA` | `#FFFCF3` | `#EDE3D0` | `#7E7565` | `#B3261E` |
| amber | D | `#FFC94D` | `#3C2500` | `#5C3E00` | `#9FD6C9` | `#E5BDE6` | `#16120A` | `#1F1A11` | `#433C2E` | `#9A9181` | `#FFB4AB` |
| indigo | L | `#2E4E9E` | `#FFFFFF` | `#DCE3FF` | `#9A4528` | `#6B5E00` | `#F5F6FB` | `#FCFBFF` | `#E2E2EC` | `#74747E` | `#B3261E` |
| indigo | D | `#B4C5FF` | `#0B2B6E` | `#27458F` | `#FFB59D` | `#E3C74E` | `#10121A` | `#181A23` | `#383A44` | `#90909B` | `#FFB4AB` |
| slate | L | `#4A5A66` | `#FFFFFF` | `#D3E5F0` | `#8A4F35` | `#5C5A8A` | `#F6F5F1` | `#FCFBF8` | `#E3E2DC` | `#767878` | `#B3261E` |
| slate | D | `#B9C9D5` | `#23313B` | `#3A4A56` | `#E8B7A1` | `#C5C0F0` | `#101314` | `#181C1D` | `#3B4042` | `#909493` | `#FFB4AB` |
| ember | L | `#9A3B25` | `#FFFFFF` | `#FFDBD1` | `#4F6350` | `#5A5E9E` | `#FBF5EF` | `#FFFBF6` | `#EDE1D7` | `#80746A` | `#B3261E` |
| ember | D | `#FFB4A0` | `#5C1906` | `#7E2C19` | `#B6CCB4` | `#C4C3F0` | `#17110D` | `#201915` | `#453A33` | `#9C8E85` | `#FFB4AB` |

其余前景/容器必须成对补齐，不要依赖 `lightColorScheme` 的默认紫色 errorContainer。`secondaryContainer` / `tertiaryContainer` / `errorContainer` 在浅色用对应色叠 12% surface、深色叠 18%，`on*Container` 浅色取 tone 10、深色取 tone 90；生成后按 §4 末的对比度门槛复验。

| 主题 | onPrimaryContainer L/D | onSecondary L/D | onTertiary L/D | onSurface L/D | onSurfaceVariant L/D | onError L/D |
| --- | --- | --- | --- | --- | --- | --- |
| teal | `#00343F` / `#C7E8F2` | `#FFFFFF` / `#442A00` | `#FFFFFF` / `#552434` | `#1B2428` / `#E3E2DD` | `#4B5559` / `#C0C8C9` | `#FFFFFF` / `#690005` |
| lavender | `#1A1140` / `#E6DEFF` | `#FFFFFF` / `#0E382D` | `#FFFFFF` / `#5C1136` | `#1D1B22` / `#E7E1EC` | `#4B4553` / `#CAC4D3` | `#FFFFFF` / `#690005` |
| sakura | `#3E0018` / `#FFD9E2` | `#FFFFFF` / `#352A61` | `#FFFFFF` / `#10382B` | `#221A1C` / `#F0DFE2` | `#534649` / `#D7C1C6` | `#FFFFFF` / `#690005` |
| matcha | `#0A2004` / `#BFEFAF` | `#FFFFFF` / `#262F44` | `#FFFFFF` / `#522014` | `#1B1E16` / `#E3E4D8` | `#474B3F` / `#C5C7B8` | `#FFFFFF` / `#690005` |
| amber | `#2C1A00` / `#FFDFA0` | `#FFFFFF` / `#003731` | `#FFFFFF` / `#48254C` | `#201B12` / `#EDE4D6` | `#4E4639` / `#D0C6B6` | `#FFFFFF` / `#690005` |
| indigo | `#00174B` / `#DCE3FF` | `#FFFFFF` / `#5B1B05` | `#FFFFFF` / `#372F00` | `#1A1B21` / `#E2E1E8` | `#46464F` / `#C6C5D0` | `#FFFFFF` / `#690005` |
| slate | `#0A1F29` / `#D3E5F0` | `#FFFFFF` / `#4F2414` | `#FFFFFF` / `#2D2A57` | `#1B1C1C` / `#E3E3E1` | `#48494A` / `#C6C7C5` | `#FFFFFF` / `#690005` |
| ember | `#3A0B00` / `#FFDBD1` | `#FFFFFF` / `#223423` | `#FFFFFF` / `#2D2D5F` | `#211A16` / `#EDE0D8` | `#50453D` / `#D2C4BB` | `#FFFFFF` / `#690005` |

**对比度校验**（WCAG 相对亮度；“文本”取 onPrimary/onPrimaryContainer/onSecondary/onTertiary/onSurface/onSurfaceVariant/onError/primary/error；“描边”取 outline/surface）：

| 主题 | 文本最低 L / D | 描边 L / D | 结论 |
| --- | --- | --- | --- |
| teal | 5.83 / 5.64 | 4.16 / 5.47 | 文本 ≥ 4.5，描边 ≥ 3 |
| lavender | 5.91 / 6.88 | 4.65 / 5.47 | 通过 |
| sakura | 5.88 / 6.49 | 4.37 / 5.45 | 通过 |
| matcha | 5.79 / 6.21 | 4.28 / 5.43 | 通过 |
| amber | 5.50 / 6.46 | 4.43 / 5.55 | 通过 |
| indigo | 6.06 / 6.62 | 4.49 / 5.49 | 通过 |
| slate | 5.99 / 6.19 | 4.29 / 5.60 | 通过 |
| ember | 5.95 / 6.48 | 4.41 / 5.47 | 通过 |

状态色叠 12% 到 surface 后，状态文字对比度仍为 4.87–8.3:1（浅色最低 4.87，深色最低 7.4），因此“浅底 + 同色文字”的 StatusBadge 方案可落地。

**主题选择器**：设置页用 2 列（平板 4 列）主题预览卡，不用一排 FilterChip。每张卡 64dp 预览区 + 名称；预览里画纸色底、primary 书脊、secondary/tertiary 两个标签点、`Aa` 样字；选中卡 2dp primary 描边 + 右上角 check；点击即应用，无“保存”。深色模式用“跟随系统 / 浅色 / 深色”三段按钮，放在主题网格上方。

## 5. 标签语义

所有标签从 `LnExtendedColors` 取色，`LnExtendedColors` 只从 `ColorScheme` 推导；形状、文案、位置同时承担语义，避免只靠颜色。

| 类型 | 用途 | 容器 | 文字 | 描边 | 形状 |
| --- | --- | --- | --- | --- | --- |
| 类型标签 | 转生、恶役千金等题材 | `secondaryContainer` | `onSecondaryContainer` | 无 | 6dp 圆角，24dp 高 |
| 关键词标签 | 搜索词、`ざまぁ` 等 | `surfaceVariant` | `onSurfaceVariant` | 1dp `outline` 40% | 8dp 圆角，24dp 高，可点 |
| 状态标签 | 已译/翻译中/未译全/失败/生肉 | 状态色 12% 叠 `surface` | 状态色本身 | 无 | 6dp 圆角 + 6dp 圆点 |
| 来源标签 | Kakuyomu / 成为小说家吧 | `surface` | `onSurfaceVariant` | 1dp `outline` | 全圆角，22dp 高，带 12dp 图标 |

**状态映射（全部由主题派生）**

| 状态 | 角色 | 说明 |
| --- | --- | --- |
| 已译 / 有译文 | `primary` | 完成态用品牌色，不用硬编码绿 |
| 翻译中 / 排队中 | `secondary` | 进行中，可加 8dp 进度环替代闪烁 |
| 未译全 / 译文过期 | `tertiary` | “需要处理”，比 error 弱 |
| 翻译失败 / 缺文件 | `error` | 唯一使用 error 的状态 |
| 生肉 / 未翻译 | `onSurfaceVariant` | 中性、不抢眼 |

**交互态**

| 组件 | 默认 | 按下 | 选中 | 禁用 |
| --- | --- | --- | --- | --- |
| TagChip（关键词） | `surfaceVariant` + `onSurfaceVariant` + 40% outline | `primaryContainer` + `onPrimaryContainer` | 搜索后保持 `primaryContainer` + 1dp primary | 容器 `onSurface` 8%，文字 38% |
| FilterChip | `surface` + 1dp outline + `onSurfaceVariant` | `surfaceVariant` | `primaryContainer` + `onPrimaryContainer` + 1dp primary + 前置 check | 容器 8%，文字 38% |
| StatusBadge | 12% 状态色 + 状态色文字 | 20% 状态色（仅可点重试） | 不适用 | 文字 38%，去掉圆点 |
| SourceBadge | 透明 + 1dp outline | `surfaceVariant` | 不适用 | 不适用 |

- 发现页热门标签用 FilterChip；卡片内标签用 TagChip；详情页标签用 TagChip 的只读版本（`onClick = null` 时不加 ripple，但仍保持容器/描边）。
- `BrandFilterChip` 升级为 `LnFilterChip`，保留旧名作为 thin wrapper，避免一次性改全仓。
- 标签最多显示 3 个 + `+N`；详情页最多 10 个 + “展开全部”。禁止把标签用 `/` 拼成一行（即当前 `ChapterListScreen.kt:211-216` 的写法）。

## 6. 书籍详情视觉分层

```
ChapterListScreen
├─ TopAppBar（返回、标题、更多）
└─ LazyColumn
   ├─ HeroSection（渐变底 + 封面 + 书名 + 作者 + 统计 + 主操作）
   ├─ ContinueReadingCard（有进度才显示）
   ├─ stickyHeader：DetailTabs（目录 / 简介）
   └─ 目录列表 或 简介/标签/信息
```

**Hero（手机 360dp）**

- 高度自适应，最小 196dp；背景 `verticalGradient(primaryContainer 55% → background)`，深色降到 30%，不铺满整屏。
- 封面 96×136dp、12dp 圆角、1dp `outline`；无图时用主题渐变 + 书名首字（大号 serif），不使用随机色。平板/横屏 120×168dp，两栏时 128×184dp。
- 书名 `headlineSmall` 22/30，最多 2 行；作者 13/20；统计用 `labelSmall`，三项以内（话数、状态、来源），超出收进“更多信息”。
- 主按钮“继续阅读/开始阅读”48dp 高、占满剩余宽度或整行；收藏、下载、更多用 48dp `IconButton`，下载全部/导出 EPUB 收进“更多”菜单，不放顶栏文字。

**上次读到卡**

- 有进度时显示在 Hero 与 Tab 之间：72dp 高、`surfaceContainerLow`、12dp 圆角、1dp `outlineVariant`，左侧 4dp primary 竖条；文案“上次读到 第 12 章”+ 章节名 1 行；右侧“继续”40dp 文字按钮。无进度时整卡隐藏，不留空框。

**Tab 分区（解决简介与章节混排）**

- 只保留两个 Tab：“目录 · N 章” / “简介”。Tab 高 48dp，`PrimaryTabRow`，选中下划线 2dp primary；用 `stickyHeader` 吸顶，切换时 `scrollToItem(tabIndex)`，不让用户迷失。
- 默认 Tab 规则：`progressIdx > 0` → 目录；否则 → 简介。这样老读者直接续读，新读者先判断要不要读。
- 简介与目录**永远不在同一滚动流**：简介卡只出现在“简介”Tab；目录只在“目录”Tab。
- 简介 Tab：`surface` 卡 + 1dp 描边 + 16dp 内边距；正文 15/26，最多 6 行，渐隐 + “展开全部”48dp；下面是独立“标签”卡（标题 14/20 + FlowRow 标签），再下面是“信息”卡（作者/来源/话数/更新时间，label 12 + value 14，行高 40dp）。
- 目录 Tab：头部“目录 · 共 N 章”+ 搜索/排序图标；行高 56dp，序号 40dp 右对齐，标题 15/22 单行，右侧 StatusBadge 20dp；当前章整行 `primaryContainer` + `onPrimaryContainer` + 左侧 4dp primary 条。超过 100 章每 50 章插一个 32dp 分组头。
- 空态：图标 48dp + 标题 16/24 + 说明 14/22 + 主按钮；目录空态给“下载全部/重试”，简介空态只显示“暂无简介”并保留标签/信息，不画大空卡。
- 加载态用 3 行骨架（封面块 + 文字条），不要居中转圈遮住整页。

## 7. 发现页卡片视觉

**顶部**

- 一个 48dp 搜索框（leading 搜索图标、trailing 清空、IME search），不再把“搜索”做成独立大按钮；说明文案压到 1 行 12/18。
- “从链接导入”降级为搜索框下方的 TextButton，点开底部 sheet 后再输入链接/ID；不让两个输入框 + 两个按钮同时占首屏。
- 热门标签用 `FilterChip` 横向排列，选中态表示当前查询；点击即搜索。

**横向推荐区（Cover-first）**

- `LazyRow`，卡片宽 148–156dp；封面 3:4、12dp 圆角；书名 14/20 两行；作者/来源 11/16 一行；最多一个类型标签。无简介、无“加入”按钮；点击打开预览 sheet，加入动作在 sheet 内完成，避免横向卡片信息过载。
- 区块标题“本周推荐”18/24 + “换一批”TextButton；与搜索结果用 24dp 间距分开。

**纵向搜索结果（Text-first）**

- 卡片内边距 12dp，圆角 16dp，1dp 描边；封面 72×96dp；右侧信息列：标题 16/22 两行 → 作者/来源/话数 12/18 一行 → 简介 12/18 两行 → 标签最多 3 个 + `+N`。右下角 40dp `FilledTonalIconButton`“加入书架”，48dp 触控；加入中显示进度点并禁用，已加入显示 check。
- 整卡点击进详情；不再额外放“详情”文字按钮。错误用 Snackbar + 重试；加载用 3 张骨架卡；空结果给“换个关键词”+ 热门标签。

## 8. 书架卡片视觉

- 顶栏：标题“书架”；一个搜索 IconButton（点开展开搜索框）、一个“发现”IconButton；导入/备份收进 overflow。常驻的备份警告改为可关闭的 inline banner，只在无备份时出现，带“去备份”动作。
- 筛选：`FilterChip` 一行 4 个（全部/在读/想读/读完），32dp 高、可横向滚动；不再用 4 个大文字按钮。筛选变化不改变卡片布局。
- 卡片：56×80dp 封面占位 + 12dp 间距；标题 16/22 两行、作者 12/18 一行；进度条 3dp + “12/134 章”11/16；翻译状态只在非完成时显示小圆点+文字；右侧收藏 IconToggleButton（48dp 触控，实心/空心星）与“继续”按钮分层，避免星号 TextButton 占掉一整列。
- 卡片点击进详情；“继续”按钮直接打开上次章节。整卡不超过 3 行信息，不加简介/标签。
- 平板/横屏 ≥600dp 可切 2 列网格，封面 96×128dp；默认仍用列表，保证文字可扫读。

## 9. 设置页视觉

- 结构改为 5 个分组卡：**外观**、**阅读**、**翻译与书源**、**数据与备份**、**关于**。每组 `surface` + 1dp 描边 + 16dp 圆角；组内行高 ≥56dp，行间 1dp 分割线内缩 16dp。
- 外观：深色模式三段按钮（跟随系统/浅色/深色）+ 主题预览网格（见 §4）；立即生效。
- 阅读：纸色卡（纸白/米黄/护眼/夜间/夜蓝/暖灰，4–6 个 64dp 色块，带 `Aa` 样字）、字号滑杆 14–30sp、行距 1.3–2.2、段距 0–24dp、页边距三段（紧凑/标准/宽松）、字体三段（宋体/黑体/等宽）、显示模式三段（译文/原文/双语）、翻页模式两段。用滑杆替代 A-/A+ 按钮，右侧固定显示当前值，便于单手操作。
- 翻译与书源：默认显示“已配置/未配置”状态卡；Base URL、模型、API Key 收进“高级设置”折叠区；Novelia 账号单独成组，不和应用外观混在一起。
- 数据与备份：上次备份时间 + 导出/导入主按钮；缓存大小 + 清理按钮；危险操作（清理缓存、退出账号）使用 `error` 文字按钮 + `AlertDialog` 二次确认，说明“只删缓存，不删书和进度”；确认按钮写具体动作，不写“确定”。
- 关于：版本、开源许可、诊断日志入口；不放大段说明。
- 平板最大宽度 720dp 居中；分组间距 16dp；任何页面不超过两级标题。

## 10. 深色、动态取色、无障碍、横屏/平板

**深色模式**

- 浅色纸感、深色墨感，不用纯黑底 + 纯白字；正文 `onSurface` 对比度 ≥ 12:1。
- 深色下卡片层级用 surface 亮度差，不用阴影；封面渐变降低 20–30% 饱和，避免刺眼。
- 阅读器夜间纸色独立（`ReaderTheme.NIGHT`），不强制跟随 App 深色；App 深色只影响书架/详情/设置的 chrome。纸色建议：纸白 `#FAFAF7/#242424`、米黄 `#F5ECD9/#3A3226`、护眼 `#EFF6E9/#081B16`、夜间 `#121212/#C8C5BE`、夜蓝 `#101820/#D6DEE8`、暖灰 `#EDE9E3/#2B2926`。
- 系统栏跟随背景，状态栏图标按深色切换；底部导航栏透明并加 1dp 顶部分割线。
- 阅读页 chrome：顶栏只留返回/书名/更多；A-/A+、主题、语言收进“阅读设置”面板；底栏保留上一章/目录/下一章/页码，减少文字按钮。

**动态取色**

- 默认**不采用**。8 套主题是品牌与标签语义的基础；动态色会让主色、secondary/tertiary 关系漂移，8 套预设失去意义。
- 若 P2 提供“跟随壁纸”，只作为第 9 个选项：固定 `on*` 由算法求解、标签仍走 `LnExtendedColors`、背景/表面保留当前主题的纸感偏移；生成后跑对比度测试，低于 4.5:1 的文本对直接回退 `amber`。不允许动态色覆盖已选预设。

**无障碍**

- 文本 ≥ 4.5:1，大字号 ≥ 3:1，非文本描边 ≥ 3:1；本方案 8 套均通过（见 §4）。
- 标签视觉高度 24–32dp，但点击区 48dp；图标按钮 48dp；章节行 56dp。
- 支持字体缩放 1.0/1.3/1.5/2.0：不固定文字容器高度，标题最多 2 行，标签 FlowRow 换行；2.0 倍下详情页 Hero 可纵向堆叠。
- 状态不能只靠颜色：StatusBadge 同时有圆点、文字；类型/关键词/来源用不同圆角与描边。
- TalkBack：封面“《书名》封面”；进度“已读 12/134 章”；收藏“已收藏/未收藏”；翻译状态点必须带 `contentDescription`（当前 `TranslationStatusDot` 已有，保留）。
- 尊重系统“移除动画”；不做自动播放的闪烁/滚动。

**横屏 / 平板最小适配**

- 断点用 `BoxWithConstraints`：<600dp 手机，600–839dp 平板竖屏，≥840dp 大屏/横屏；不强制新增 adaptive 依赖。
- ≥600dp：书架 2 列；发现推荐 3 张；设置主题 4 列；详情封面 120×168dp。
- ≥840dp：详情两栏（左侧 280dp Hero 固定，右侧 Tab + 列表）；设置最大宽 720dp；阅读正文最大行宽约 36–42 个中文字符，左右留白 32–48dp。
- 横屏：顶栏/底栏不遮内容，使用 `WindowInsets`；详情两栏时目录独立滚动；书架保持列表或 2 列，不强行拉伸卡片到整屏宽。

## 11. 组件与文件、优先级

| 优先级 | 组件 / 改动 | 文件 | 说明 |
| --- | --- | --- | --- |
| P0 | 8 套 palette + typography + shapes | `ui/theme/Theme.kt`、`ui/theme/Type.kt`（新） | 保留 3 个旧 id；默认 amber；补全 scheme |
| P0 | `LnTokens`、`LnExtendedColors` | `ui/theme/LnTokens.kt`、`ui/theme/LnExtendedColors.kt`（新） | 间距/圆角/动效/标签色/表面层级 |
| P0 | `LnFilterChip`、`TagChip`、`StatusBadge`、`SourceBadge` | `ui/components/BrandChips.kt` | 替换 AssistChip 与纯文本标签 |
| P0 | 详情 Hero / Tabs / 简介卡 / 目录 | `feature/chapters/ChapterListScreen.kt` | 拆 `BookHeader`；加 `ContinueReadingCard` |
| P0 | 书架卡片与筛选 | `feature/library/LibraryScreen.kt` | 进度条、收藏图标、紧凑卡片 |
| P0 | 主题预览网格 | `feature/settings/SettingsScreen.kt` | 取代一排 FilterChip |
| P1 | 发现页搜索/推荐/结果卡 | `feature/discover/DiscoverScreen.kt` | 链接导入收进 sheet |
| P1 | 设置分组、滑杆、折叠高级项、危险确认 | `feature/settings/SettingsScreen.kt` | 5 组卡片 + AlertDialog |
| P1 | 状态徽标/阅读器 chrome token | `feature/reader/ReaderComponents.kt` | 删除硬编码状态色 |
| P1 | 阅读纸色与对比度 | `reader/engine/ReaderTheme.kt` | 4–6 套纸色，补夜蓝/暖灰 |
| P1 | 通用 `SectionCard`、`EmptyState`、`BookCover`、`ConfirmDialog`、`ThemePreviewCard` | `ui/components/`（新） | 详情/书架/设置复用 |
| P2 | 动态取色、封面图片加载、动效细化 | `ui/theme/DynamicColor.kt` 等 | 需新依赖/额外验证，暂不做 |

**P0 验收**：换 8 套主题不出现硬编码色；详情页简介与目录分开；主题选择器不再是 FilterChip 排；书架卡片有进度与可点收藏。**P1 验收**：发现页首屏只有一个搜索框；设置页高级项默认折叠；阅读状态色随主题变化；600/840dp 不破版。

## 12. 主题验收清单

- [ ] `AppTheme` 含 8 个 id：`teal/lavender/sakura/matcha/amber/indigo/slate/ember`；旧设置可正常加载，未知 id 回退 `amber`。
- [ ] 每套 light/dark 均定义 §4 的 10 个关键色及成对 `on*`；不使用默认紫色 `errorContainer`。
- [ ] 所有文本对 ≥ 4.5:1、大字 ≥ 3:1、描边 ≥ 3:1；8 套实测最低文本 5.50:1。
- [ ] 业务代码无 `Color(0xFF...)` / `Color.Blue` 等硬编码；状态点、章节状态、阅读器状态全部走 `LnExtendedColors`。
- [ ] 类型/关键词/状态/来源四类标签容器、文字、描边、按下、选中、禁用态齐全；标签不再用 `/` 拼接成纯文本。
- [ ] 详情页有 Hero、上次读到卡、目录/简介 Tab；简介与章节不在同一滚动流；Tab 吸顶；无进度默认简介、有进度默认目录。
- [ ] 详情页手机 360dp 下封面 96×136、主按钮 48dp、章节行 56dp，不溢出。
- [ ] 发现页首屏只有一个搜索框；链接导入在 sheet；横向推荐与纵向搜索结果视觉区分；结果卡最多 3 个标签 + `+N`。
- [ ] 书架卡片最多 3 行信息，有进度条、收藏状态和“继续”；备份警告可关闭。
- [ ] 设置页分 5 组；主题为预览卡网格；字号/行距用滑杆；高级翻译项折叠；清理缓存/退出账号有二次确认。
- [ ] 深色模式逐页检查无纯黑大底 + 阴影堆叠；系统栏图标对比正常。
- [ ] 1.0/1.3/2.0 字号、360/411/600/840dp、横屏均无截断；触控区 ≥48dp；TalkBack 能读出封面、进度、收藏、状态。
- [ ] 主题切换 220ms 内完成、无闪白；系统移除动画时不出现长动画。
- [ ] 参考实现只借用层级思想，仓库中未出现 GPL 代码/样式/资产。
