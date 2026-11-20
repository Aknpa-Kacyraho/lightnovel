# Round 4 · 统一升级指南（v1.2.0）

> 合并：`01-user.md`、`02-design.md`、`03-engineering.md`。
> 裁决原则：先消除「刺眼」与「常驻噪声」，再谈主题美化；能用一处解析解决的问题，
> 不做两套状态。

## 1. 合并结果

| 来源 | 主张 | 裁决 | 理由 |
| --- | --- | --- | --- |
| U1 + D1 + E1 + E2 | 深色 App 进入纸白阅读器刺眼 | **采纳，P0** | 新增「跟随系统」纸色，默认 auto，老用户不迁移 |
| U2 + D2 + E3 | 未翻译横幅常驻 | **采纳，P0** | 抽纯函数，只保留进行中/失败/队列 |
| U3 + D3 + E4 | 夜间正文偏亮 | **采纳，P1** | 单色值调整 + 对比度断言 |
| U4 + D4 | 纸色选项少、只能循环 | **采纳，P1** | 设置页随枚举自动变 5 项 |
| U5 | 顶部三层 chrome | **推迟到 Round 6** | 涉及重排顶栏，风险大于收益 |

## 2. 实施清单

### 2.1 纸色「跟随系统」（P0）

- [ ] `ReaderTheme` 增加 `AUTO("auto", "跟随系统", ...)` 与 `resolve(dark: Boolean)`。
- [ ] `ReaderRoute` 用 `ReaderTheme.fromId(state.theme).resolve(isSystemInDarkTheme())`。
- [ ] `SettingsStore` 默认 `readerTheme = "auto"`；已存值不迁移、不回写。
- [ ] 设置页纸色 chips 自动 5 项（跟随系统 / 纸白 / 米黄 / 护眼 / 夜间）。
- [ ] 阅读器「切换纸色」循环包含 AUTO，顺序 auto → paper → sepia → green → night。

### 2.2 未翻译横幅降噪（P0）

- [ ] 新增 `feature/reader/ReaderBanner.kt`：
      `shouldShowTranslationBanner(...)`，未翻译且无进行中/错误/队列时返回 false。
- [ ] `TranslationStatusBanner` 在计算标题前调用；false 直接 return。
- [ ] 「更多 → 翻译本章」与「立即翻译」入口不变。

### 2.3 夜间正文（P1）

- [ ] `ReaderTheme.NIGHT.text` 从 `#C8C5BE` 改为 `#BDBAB2`。
- [ ] `secondary` 保持 `#8E8B84`；`danger` 不变。
- [ ] 新增 `ReaderContrast.kt`（WCAG 相对亮度 / 对比度）。
- [ ] `ReaderThemeTest` 断言：NIGHT 正文 ≥7:1、次要 ≥3:1；其余纸色正文 ≥7:1。

### 2.4 测试

- [ ] 新增 `ReaderThemeTest`（resolve 5 种、fromId fallback、对比度）。
- [ ] 新增 `ReaderBannerTest`（5 种场景）。
- [ ] `SettingsStoreTest` 补默认 `auto` 与显式 `paper` 保留。

### 2.5 版本与文档

- [ ] `versionCode = 41`，`versionName = "1.2.0"`。
- [ ] `CHANGELOG.md`、`04-final.md` §8.1、`README.md`、`PROGRESS.md`、`SELF-REVIEW.md`。

## 3. 非目标

- 不做亮度滑杆、暖色滤镜、护眼定时。
- 不删朗读/滚动/翻页入口，不重排阅读器顶栏。
- 不改翻译管线、不改预译策略、不改 Room/备份。

## 4. 验收

| 项 | 标准 |
| --- | --- |
| 测试 | ≥199 tests，0 failures；新增两个测试文件 |
| lint | 0 errors；warning ≤22 |
| 构建 | `assembleDebug` 成功，versionCode 41 |
| 用户 | 深色系统新安装 → 夜间纸色；未翻译章节无横幅；夜间正文更柔和 |
| 设计 | 5 个纸色 chip；对比度达标；切换即时生效 |
| 发布 | 提交 + tag `v1.2.0` + 推送 |

## 5. 回滚

改动集中在 `ReaderTheme`、`ReaderRoute`、`ReaderComponents`（横幅调用）、`SettingsStore`
默认值与 3 个测试；无数据迁移。`git revert` 单提交即可。
