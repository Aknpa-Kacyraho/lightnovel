# NoveLA 翻译阅读 / TTS / 设置研究（A′ 设计输入）

> 只读研究。参考仓库 `.tmp/reference/novela`（GPLv3），只提炼设计与边界，不复制代码。
> 目标：`android/` 的 v1 A′ = 阅读 + 单章 DeepSeek 翻译最小闭环，无调度 / 无后台。
> 行号按当前参考快照；我们的现状是分页 `StaticLayout`（`app/.../reader/ReaderScreen.kt`），
> 数据侧已有 `chapters.raw_path / zh_path / status / model / token_*`（`app/.../data/local/Entities.kt`），
> 依赖已有 OkHttp / kotlinx.serialization / Room / DataStore（`app/build.gradle.kts`）。

## 0. 结论速览

1. NoveLA 的核心是**段落级双语模型**：同一 item 同时存原文与译文，渲染层决定“只译文 / 双栏 / 顺序”，而非在加载期改写正文。
2. 翻译**不是可视区增量**：开章时整章 batch 一次，可命中数据库后只补缺失段；开关翻译走“重载阅读器 + 清缓存”。
3. 缓存粒度是 `(chapterUrl, sourceLang, targetLang)` 一行 + 段落数组 JSON，位置对齐靠启发式修复；这是它最脆、我们最该改进的地方。
4. 章节加载是单队列 + 已加载集合去重，上一章头插、下一章尾插，位置用“章节 + 段序号 + 像素偏移”保存。
5. 错误按“章”处理（Error item + 重试），并有 5s×n（上限 60s）自动复位后重试；TTS 跳章会裁剪 ±10 章内存窗口。
6. TTS 以段落为 utterance，长段再按引擎上限切子片；队列空 = 章末信号，下一章等 `chapterLoadedFlow` 再续读。
7. 暂停 = stop + 记录当前段；恢复 = 从记录段重读。词级高亮依赖 `onRangeStart` + 网络语音校准，复杂度高，A′ 应后置。
8. 设置分三层（全局 / 插件 / 单书）且有“开关显示值”与“实际生效值”分离的坑；A′ 只需单层 + 单书可选覆盖。
9. DownloadManager 的 `translateMode`、前台服务、WakeLock、任务恢复、通知全部属于“有后台调度”的产品，A′ 不适用。
10. 给 A′ 的落点：段落模型用 `paragraphId + 原文 + 译文 + 状态`；翻译整章分块、逐块持久化、单飞行取消；TTS 只留接口。

## 1. 关键文件与行号

| 主题 | 路径（相对参考仓库） | 关键行 |
| --- | --- | --- |
| 段落模型 | `features/reader/src/main/java/my/noveldokusha/features/reader/domain/ReaderItem.kt` | `Text` 30-34；`Body` 44-51；`Title` 36-42；`Translating` 62-66；`Error` 77-82 |
| 双语渲染 | `.../domain/ReaderItemAdapter.kt` | 并行开关 180-181；双语 232-259；单语 260-277；词高亮 499-519；段背景 521-546；标题只译文 422-433；稳定 id 120-136 |
| 章节加载 | `.../features/ReaderChaptersLoader.kt` | 队列 65-70, 164-199；错误自愈 83-112；重试 215-278；初始 357-405；上一章 407-456；下一章 458-494；加载去重 496-532；翻译分支 650-794；翻译失败 795-820；裁剪 929-974, 1059-1060 |
| 翻译状态/设置 | `.../features/ReaderLiveTranslation.kt` | 状态 29-67；provider/开关解析 105-122；生效解析 231-293；重译清缓存 528-570；batch 工厂 578-596 |
| TTS 控制 | `.../features/ReaderTextToSpeech.kt` | `TextSynthesis` 73-79；buffer 123；启动/补队 431-475；暂停恢复 665-705；续读下一章 802-842；重读当前段 942-957；取文本 1015-1048 |
| TTS 引擎 | `tooling/text_to_speech/src/main/java/my/noveldokusha/text_to_speech/TextToSpeechManager.kt` | 状态 31-37；入队切分 365-407；回调/词高亮 498-624；完成/错误 626-692；校准 104-200 |
| TTS 切分 | `.../text_to_speech/DelimiterAwareTextSplitter.kt` | 9-42 |
| 下载/翻译批处理 | `data/src/main/java/my/noveldokusha/data/DownloadManager.kt` | `translateMode` 398-446；主循环 627-794；落库 1056-1130；等网 1239-1287；批重试 1288-1313；常量 173-179 |
| 设置键 | `core/src/main/java/my/noveldokusha/core/appPreferences/AppPreferences.kt` | 阅读 328-388；TTS 391-424；阅读开关/高亮 466-488；翻译开关/语言对 716-761；插件层 789-819；provider/OpenAI 1290-1345；prompt/并行/批大小 1386-1445 |
| 设置解析 | `.../core/appPreferences/TranslationSettingsResolver.kt` | 20-43, 68-76 |
| 提示词/解析 | `tooling/text_translator/translator_nop/.../TranslationUtils.kt` | 预设 13-138；编号解析 220-266 |
| OpenAI 兼容 | `.../TranslationManagerOpenAI.kt` | 批大小/超时 45-59；batch 128-159；key 轮换 167-228；prompt 285-286 |
| UI/VM | `features/reader/.../ReaderActivity.kt` | 适配器接线 187-249；初始位置 364-377；滚动触发 1054-1083；onPause 保存 1140-1155；onResume 重试 1157-1213 |
| UI 状态 | `.../ui/ReaderScreenState.kt` / `ReaderScreen.kt` / `ReaderScreenBottomBarDialogs.kt` | 状态树 32-91；工具栏 242-301；底部面板映射 72-139 |
| 阅读位置 | `.../ReaderRepository.kt` | 编码 32-38；保存 50-83；初始位置 133-157 |

## 2. 可复用设计（用我们的话）

### 2.1 段落模型与双语渲染

- `ReaderItem.Text` 的 `textToDisplay = textTranslated ?: text`（30-34）是整条链路的安全底线：**译文缺失永远回退原文**，不会出现空段或占位符。
- 双语不是两套列表，而是同一段落的两份文本；渲染时按 `parallelEnabled && textTranslated != null` 决定单/双栏（180-181）。副文本固定 0.85 字号（253），顺序由 `TRANSLATION_FIRST` / `ORIGINAL_FIRST` 切换（233-236）。
- 段落带 `Location.FIRST/LAST`，适配器在绘制首/末段时上报“章首/章末已可见”（292-296），用于已读标记与预取；A′ 可只保留“章末”信号给 TTS。
- `Translating` 与 `Error` 是**列表里的普通 item**（62-66, 77-82），进度/失败因此天然跟随章节位置，不需要独立浮层。
- 标题只渲染译文并隐藏原文（422-433）——产品上是简化；若做对照阅读，标题也应遵守同一显示模式。

### 2.2 章节加载、位置与错误

- `LoadChapter.Initial/Previous/Next` 三态投递到单消费者（65-70, 280-299），`loaderQueue` 去重（164-199）；`loadedChapters` + `Mutex` 防止重复加载/并发重复插入（496-532）。
- 初始位置 = `chapterIndex + chapterItemPosition + offsetPx`，并把“保存时是否按句切分”编码进符号位（`ReaderRepository:32-38`），结构变化时用映射函数还原（`mapRestoredPosition` 982-995）。**位置绑定段落而不是页码**，是分页 UI 也必须遵守的结论。
- 上一章头插并保持当前可视位置（407-456）；下一章尾插（458-494）；TTS 跨章跳转后按 ±10 章裁剪内存（929-974）。
- 错误处理：失败章插入 `Error` item，按钮分别“重试本章 / 浏览器打开”（396-411）；`hasLoadingError` 阻止继续自动加载，并按 5s×次数（≤60s）自动复位再试（83-112）。`retryChapter` 会删正文缓存后重载（215-278），但**不删译文缓存**，所以重试通常能复用已翻译段。
- 内容质量门（Cloudflare/空章/登录页）在解析前判定并直接报错（587-616）；翻译异常则替换为 Error item 并停自动加载（795-820）。
- 结论：A′ 单章可去掉队列/前后章，但“加载去重 + 失败可重试 + 位置绑段落”必须保留。

### 2.3 翻译触发、provider、缓存、并发

- 真实行为是**整章 batch**：`addChapter` 里把全部 `Body.text` 一次性交给 `translatorBatchTranslateOrNull`（650-794）。`ReaderLiveTranslation` 只负责设置、provider 解析和“重译”信号，不做可视区请求。
- 缓存命中：读出该章该语言对的段落数组，完整则直接贴回；不足则只翻缺失的尾部再整行覆写（686-729, 730-738）。数组长度漂移时靠“按句数分组”与“长度比窗口”两个假设修复（`ResolveParagraphTranslations:35-57`），失败就保留原样不覆写。
- 在线 provider 无 batch 时**拒绝退化为逐段**，直接报“翻译器未就绪”（774-791）；离线 MLKit 才允许逐段。A′ 只有一个在线 provider，应保持“要么整批成功，要么显式失败”。
- 并发模型是“单章单请求”：翻译在加载协程内串行执行，缺失段调用有 60s 超时（708-711）；取消靠 scope 取消 + 已加载集合清理（519-531）。`DownloadManager` 另加章间 1s 间隔与最多 2 次重试（178-179, 1288-1313）。
- 批次协议：系统提示词要求“按输入编号、以 `1.` 开头、不解释”（`TranslationUtils:13-71`），用户消息是 `N. 段落`；解析容忍 `1)`、`**1.**`、`№1.`，缺号回退原文（220-266）。
- 坑：解析结果以**原文文本为 key**（254-262），重复段落会折叠；加载器的 `textToIndices` 只取第一个命中（722-726）。A′ 必须改为“按序号 + 原文哈希”对齐。

### 2.4 TTS

- utterance 身份 = `chapterItemPosition-chapterIndex`（73-79），播放态 `PLAYING/FINISHED/LOADING`；高亮和“当前段”都靠这个身份。
- 长段按引擎 `getMaxSpeechInputLength()` 切子片依次入队（365-407），队列剩 `halfBuffer=5` 时补下一批（431-475）；队列空即章末，发 `reachedChapterEndFlow`。
- 播放下一章时先 `stop()`，未加载则触发加载并 `chapterLoadedFlow.filter{...}.take(1)` 等待，再从头读（802-842）。暂停会停引擎并记录当前段（665-705），恢复从该段重读（688-701）；换音色/语速也重读当前段（942-957）。
- 词级高亮：`onRangeStart` 的 frame 需按采样率与“网络语音偏慢”校准（104-200, 551-580），并用互斥 + 最小驻留避免短词被吞（583-624）。段落背景高亮则简单得多（521-546）。
- 结论：段落级状态 + 章末回调已能支撑“暂停/续读/切章”；词级高亮是独立复杂度，A′ 只留接口。

### 2.5 设置分层与 UI

- 阅读样式全部是独立 `Preference`（328-388）；TTS 与高亮独立（391-424, 466-488）；翻译有全局开关/全局模式、单书语言对与开关、插件层、prompt、provider、并行/批大小（716-819, 1290-1445）。
- `LiveTranslationSettingData.enable` 是“当前 UI 层开关”，真实是否翻译走级联解析（119-122, 231-243）。这是多级设置必然产生的“显示值 ≠ 生效值”，A′ 应避免。
- UI 用一棵 `ReaderScreenState`（32-91）聚合“章节信息 / 阅读样式 / TTS / 翻译 / 高亮”，`selectedSetting` 枚举驱动底部面板（`ReaderScreenBottomBarDialogs:72-139`），顶栏 5 个入口（`ReaderScreen:242-301`）。
- Activity 只在 `onPause` 存位置（1140-1155），`onResume` 重试失败章并做 TTS catch-up（1157-1213）；滚动到底触发下一章、到顶触发上一章（1054-1083）。
- `ReaderViewModel` 用 session 单例跨配置变更（45-53），把事件流（翻译变更/显示变更/TTS 滚动）直接暴露给 Activity（158-162）。A′ 没有常驻 TTS 需求，可简化为普通 `ViewModel` + `StateFlow`。

## 3. 与“单章 A′、无后台调度”不匹配，不建议照搬

- `DownloadManager` 的域队列、任务实体恢复、前台服务、WakeLock、通知、暂停/续传——A′ 只在阅读页内翻译当前章，退出即取消。
- 章间自动排队、1s 节流、批量“只补未译章”——属于后台能力；A′ 最多做“本章失败后手动重试”。
- `translateMode` 的语义是“只处理已缓存正文且未翻译的章”，需要全局章节库与下载任务；A′ 直接用“当前章是否需要翻译”判断。
- 三层翻译设置（全局/插件/单书）+ 13 个 Flow 合并 + 生效级别徽章——A′ 用单层设置 + 可选单书语言对即可。
- 多 provider（Google PA/Free、Gemini、OpenAI、MLKit）+ key 轮换 + 标题走免费通道——A′ 固定 DeepSeek，标题可与正文同请求或单独小请求。
- 句级切分与“位置随切分设置重映射”（982-995）——A′ 不做句子切分，避免位置迁移问题。
- 可视区/预取式增量翻译在参考实现里**并不存在**；不要据此设计“滚动触发翻译”的复杂状态机。
- 双 provider 并行的 TTS 音色切换、词级校准、媒体通知、悬浮窗、耳机按键、自动续读跨章——A′ 后置。
- 手动高亮、Regex 清洗、自动滚动、已读统计、漫画/视频分支——与最小闭环无关。
- `ReaderItemAdapter` 依赖 `ListView` 的 view type/稳定 id/头尾 padding；我们是 Compose 分页，照抄适配器结构没有收益，只借“身份 = 章节 + 段序号”的思想。

## 4. 给 A′ 的具体设计

### 4.1 数据与段落模型

- 新表 `chapter_translations`：主键 `(book_id, idx, target_lang)`；列 `source_lang, model, status, paragraphs_json, error, updated_at`。
  `paragraphs_json` 是按段序的数组，每项 `{ "i": Int, "h": "原文哈希", "t": "译文" }`；**哈希用于检测正文变化，只重翻变更段**。
- 段落模型（内存）：
  `ReaderParagraph(id: Int, role: TITLE|BODY, original: String, translated: String?, state: PENDING|OK|FAILED)`；
  `id` = 章内段序号，切章/切语言不重置；`translated` 为空即回退原文。
- 复用现有 `chapters.raw_path` 作为原文来源；`zh_path` 可写“纯译文导出”（TTS/导出用），但**真相以段落 JSON 为准**，避免位置丢失。
- 现有 `ChapterEntity.status/model/token_in/token_out` 可承载章级翻译状态与用量，不必另建章状态表。

### 4.2 双语渲染（适配我们的分页器）

- 显示模式用一个枚举而不是两个布尔：
  `TRANSLATION_ONLY`（默认；无译文则原文）/ `BILINGUAL_TRANSLATION_FIRST` / `BILINGUAL_ORIGINAL_FIRST` / `ORIGINAL_ONLY`。
- 每段渲染为“主文本 + 可选副文本（0.85 字号、低对比度）”；主/副按模式与 `translated != null` 决定，绝不显示空段。
- 分页输入从“整章字符串”改为“段落块列表 + 样式”；译文/模式/字号变化必须**重新分页**，但阅读位置按 `(paragraphId, charOffset)` 恢复，不能用页码。
- 失败段显示原文，并在章首横幅汇总“n 段未翻译 / 重试”，不做逐段红字，避免正文噪音。
- 标题遵守同一模式；若空间紧张，标题可固定“译文主、原文副”。

### 4.3 翻译触发、缓存、失败状态

- 触发：阅读页菜单“翻译本章”；设置 `autoTranslateOnOpen=true` 时在章节正文加载完成后自动开始。无 API key 时按钮变为“去设置”，不静默失败。
- 状态机（章级）：`NONE → TRANSLATING(done/total) → DONE | PARTIAL | FAILED`；
  `PARTIAL` = 有段失败但已有可用译文；`FAILED` = 首块失败或无任何译文。
- 请求：按段分块（建议 20 段或 ~3000 字符，先到者为准），**可见段优先**：先发当前可视范围内的块，再顺序补其余块；同一章同时最多 1 个在飞请求（DeepSeek 限流友好）。
- 每块成功即写库（`paragraphs_json` 合并 + `status`），因此退出/切章后重进可续；失败块标记 `FAILED`，其余块继续。
- 对齐：请求带序号，解析后按序号回填；回填前校验“非空 + 长度比 0.3–3.0 + 不含明显编号残留”，不通过则该段记 `FAILED`（保留原文），**不编造**。
- 失败分类：`NoKey/Auth(401/402)` 不重试、直接提示设置；`RateLimit(429)/5xx/超时` 自动重试 1 次（1s 退避），仍失败则章级 `PARTIAL/FAILED`；`Parse/Alignment` 不自动重试，提供手动“重试本章”。
- 取消：翻译 Job 挂 `viewModelScope`；切章、退出、切显示模式（仅重排，不取消）、手动停止都显式 `cancel()`；已落库块不丢。
- 缓存失效：`sourceLang/targetLang/model/prompt` 任一变化视为新缓存键（至少把 model 与 prompt 版本记入行内）；原文哈希变化只重翻对应段，不整章重来。
- 语言判断：`sourceLang == targetLang`、正文已是目标语言、或正文为空时直接 `DONE` 并标注“无需翻译”。

### 4.4 DeepSeek 适配

- `baseUrl=https://api.deepseek.com`，`/chat/completions`，`model=deepseek-chat`（可配）；`temperature=0.2`，`stream=false`，连接 30s / 读 120s。
- 提示词沿用“编号、逐段全译、不解释、保留人名、去广告/水印”的最小集；系统提示与用户消息分离，便于单书 prompt 覆盖（后置）。
- key 只存 Keystore 加密后的密文（DataStore 明文不可接受）；日志只打模型名、段数、耗时、token 用量，不打正文与 key。
- 解析失败时保留原始响应摘要（截断）进 `error` 字段供“诊断”面板，不写入正文。

### 4.5 TTS 后置接口

- 现在只定义 seam，不实现引擎：
  `interface ReaderSpeechController { val state: StateFlow<SpeechState>; fun play(fromParagraphId: Int); fun pause(); fun resume(); fun next(); fun previous(); val chapterEnded: SharedFlow<Int> }`
  `SpeechState(paragraphId: Int?, wordRange: IntRange?, playing: Boolean, loading: Boolean)`。
- 规则：朗读文本由“朗读语言”设置决定（译文优先，缺译文回退原文），**不与视觉显示模式耦合**；显示模式切换时若正在朗读，按 `paragraphId` 重读当前段。
- 身份一律用 `paragraphId`（不要用列表位置）；章末只发事件，由 UI 决定“下一章”还是停止——A′ 不自动跨章。
- 词级高亮、网络语音校准、媒体会话/通知留到 TTS 版本；段落背景高亮可先做。

### 4.6 设置项（DataStore）

- 阅读：字号、行高、段距、左右/上下边距、主题/背景、翻页方式、保持常亮。
- 翻译：总开关、开章自动翻译、源语言（默认 ja）、目标语言（默认 zh）、显示模式、副文本缩放（默认 0.85）、模型、批大小、超时、prompt 预设、API key（加密）。
- 单书覆盖（可选，二期）：该书源/目标语言、是否自动翻译；**不做**全局/插件/单书三级级联。
- TTS（后置）：开关、音色、语速/音调、朗读语言（译文/原文）、段落高亮。

## 5. 落地顺序与验证

1. 先落 `ReaderParagraph` + 现有分页器输入改造 + 位置 `(paragraphId, charOffset)`；用纯原文回归现有阅读。
2. 再加 `chapter_translations` 与 DeepSeek 客户端；用 MockWebServer 测编号解析、缺号、重复段、超时、401/429。
3. 最后加双语渲染与设置面板；验证“切模式不改位置、切章取消在飞请求、退出重进续译、失败段回退原文”。
4. 验收：单章 ≤N 段时一次成功；断网/错 key 有明确状态与重试；无 API key 不阻塞阅读；日志无正文/密钥。
