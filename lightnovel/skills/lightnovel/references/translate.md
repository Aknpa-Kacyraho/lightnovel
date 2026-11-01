> 翻译核心：命令、工作流、故事记忆、内部机制、成本、翻译策略。
> 网站实现见 `lnserve.md`，踩坑与自查见 `lessons.md`。

---

# PART B-1：翻译核心（lntrans）

**什么时候用**：读者要看日文小说但不懂日语；要求翻译 kakuyomu / syosetu 等站点的作品；
说"帮我翻这本 / 这章""接着往下翻""从我看到的地方接着翻""这个名字翻译得不对"。
**token 预算有限，绝对不要一次翻整本**。

### 这个 skill 解决什么

目标读者是**不懂日语、但要读日文轻小说（生肉）的中文读者**。三个硬约束：

1. **token 不够，不能一次翻完** → 只在读者要看时翻接下来的几章
2. **普通翻译不懂故事** → 人名/术语前后不一致，语气断裂
3. **翻译质量要进化** → 读者纠正过的东西必须永久生效

参考实现：`auto-novel/auto-novel` 的 `packages/translator`
（按行分段、每行加 `#编号` 强制对齐、术语表按需注入、段级缓存）。

### 核心命令

```bash
cd <工具目录>/lntrans
python3 lntrans.py init "<kakuyomu作品URL>"        # 建作品，抓目录
python3 lntrans.py import <文件.epub|.txt>          # 导入本地书（不花 token，自动上架）
python3 lntrans.py next <slug> 3                   # ★核心：接着翻 3 章
python3 lntrans.py next <slug> 2 --summary         # 翻完顺便生成梗概
python3 lntrans.py status <slug>                   # 进度 / 故事记忆 / token 与费用
python3 lntrans.py learn <slug> --term "日文=中文"  # ★纠正译名，永久生效
python3 lntrans.py fix <slug> --rename "旧=新"      # 改已译章节的译名（不花 token）
python3 lntrans.py stale <slug>                    # 术语表改过：哪些章译名可能过时（只报告）
python3 lntrans.py stale <slug> --retranslate --limit 2  # 真重翻（花钱）
python3 lntrans.py terms <slug>                    # 片假名候选术语（0 token）
python3 lntrans.py summary <slug> --count 5        # 为已译章节生成前情梗概
python3 lntrans.py titles <slug>                    # ★批量中文章节名+书名（目录必需）
python3 lntrans.py review <slug>                    # 校对最近译好的一章（不花 token）
python3 lntrans.py review <slug> --chapter 3 --llm  # AI 校对第 3 章（花 token）
python3 lntrans.py review <slug> --chapter 3 --fix  # 只自动修可验证的旧译名
python3 lntrans.py lessons <slug>                   # 查看本书沉淀的翻译经验
python3 lntrans.py list                            # 所有作品
python3 lnserve.py --port 8099                     # ★书架服务（读者点开就读）
```

### 本地导入、术语过期、标题与候选术语（2026-10-22）

* **导入本地 EPUB/TXT**：`import <文件>` 或网页「导入本地 EPUB / TXT」(`/import`)。
  原文写进 `novels/<slug>/raw/`，`source=local`，不联网、不花 token；同一文件
  重复导入返回原 slug，不会建第二本。Web 端和 CLI 都会把书放进书架「想读」。
  EPUB 按 OPF spine 拆章；TXT 按 `第N話 / 序章 / 闲话` 等标题拆章，没有空行的
  TXT 会按「一行一段」重排（否则整章会变成一个巨型段落，翻不动）。
* **术语过期**：改了术语表之后，`stale <slug>` 只列出**真的用到该词**且边车指纹
  变了的章；默认只报告、不花钱。`--retranslate --limit N` 才会真重翻（旧译文会被
  覆盖，失败会明确列出，不会假装完成）。阅读页也会给本页章节一条就地提示 + 一键
  重翻；有别的翻译任务在跑时 force 会返回 409，等它结束再点。
* **标题**：`titles <slug>` 会先规则翻译 `第12話` / `閑話`（0 token），同名标题只发
  一次；带正文的标题交给模型。
* **候选术语**：`terms <slug>` 扫原文片假名频次，已在术语表里的不再列；用
  `learn --term "日文=中文"` 加进表，之后新翻的章节生效，旧章用 `stale` 查。

### 工作流（必须遵守）

**首选：保证书架服务在跑**（`python3 lnserve.py --port 8099`），
让读者自己点开读、系统自动续译。读者的使用被记进 `data/books/<slug>.json`，
下一次对话直接读它就能知道进度和反馈。

命令行 `next` 只在这些情况用：读者明确说"翻 N 章"、服务没跑、或者要一次性补译某个区间。

1. **永远先问"看到哪了 / 要翻几章"**，再用 `next <slug> N`。
   绝不要自作主张翻整本——token 有限，一章约 8–9k token。
2. 翻完把 `novels/<slug>/novel.md` 给读者看，或导出到手机。
3. **读者指出译名/语气问题时**：
   * 改已有的章节 → `fix --rename 旧=新`（按字符替换，零 token）
   * 让之后的翻译也一致 → `learn --term "日文=中文"`
   * 风格类 → `learn --style "..."` / `--honorifics "..."`
4. `fix` 会同步术语表；改完用 `learn` 确认一次术语表更稳。
5. 译了几章后跑 `summary`，把梗概喂进"故事记忆"，后文翻译会更连贯。

### 校对与自进化（2026-10-19）

校对分两层，**默认只报告、不改正文**：

1. **规则层（不花 token）**：段落数/漏译、日文残留、术语锁定与旧译名、
   数字、空行节奏、明显翻译腔、原文写“冷静”译文写“暴怒”这类情绪反义。
2. **AI 层（显式 `--llm`）**：按窗口读原文 + 译文 + 本书角色卡/术语/经验，
   只输出问题清单；没有原文依据的“疑似”自动降为观察级。

```bash
python3 lntrans.py review <slug> --chapter 3          # 规则检查
python3 lntrans.py review <slug> --chapter 3 --llm    # AI 校对（只报告）
python3 lntrans.py review <slug> --chapter 3 --fix    # 修旧译名，备份原译文
python3 lntrans.py review <slug> --chapter 3 --fix-ai # AI 修订阻断项（会备份）
```

报告写在 `novels/<slug>/qa/review-NNNN.json|md`；观察池、经验、修订记录
也都在同一本书的 `qa/` 下，**不会写到别的作品**。

自进化不是“让 AI 随便改风格”：每次校对会把带原文依据的问题压成短经验
（术语锁定、漏译/日文残留、角色声音、情绪强度），存进
`meta.lessons` 和 `qa/lessons.md`；下一章 prompt 只注入**本书最近 8 条**。
人工纠正也可直接追加：

```bash
python3 lntrans.py learn <slug> --lesson "アリス对主角用短句，不用敬语"
python3 lntrans.py lessons <slug>
```

### 多作品隔离（硬约束）

* `meta.work_id` / `meta.slug` 与请求的 slug 不一致时，`ensure_work_id()`
  直接拒绝，不靠模型自觉。
* 术语、角色、梗概、经验只从当前书的 `meta` 读取；prompt 里明确写
  `work_id`，测试会断言另一本文档的术语/人物不会出现。
* 缓存、报告、观察池、经验、修订备份全部在 `novels/<slug>/` 下；
  同一本书的翻译/校对用 `novel_lock()` 串行，不同书仍可并行。
* 段缓存记录原文 SHA256；原文更新后旧缓存自动失效，避免旧译文套新原文。
* 批量翻译的书目任务按 work_id 分开；模型请求每次都是独立的
  system/user，不共享对话上下文。

自检入口（改完必跑，别靠脑子想）：见 `references/setup.md` 的「首次部署」第 4 步；
工程铁律（清理断言、别写死日期、测试要调生产函数…）见 `references/finder.md` 的「自检怎么跑」。
**自检自带桩 LLM，不联网、不花 token** —— 所以"跑一遍"永远不是负担，别省这一步。

### 故事记忆（这是"了解故事再翻译"的实现）

每部作品维护 `novels/<slug>/meta.json`：

| 字段 | 作用 |
|---|---|
| `glossary` | 日文→中文术语表。**只注入本段实际出现的词**，省 token 且更准 |
| `characters` | 人物名 + 设定。同样按需注入 |
| `summaries` | 每章梗概。只注入"提到本段登场人物"的那几章 |
| `style` | 全篇风格 / 称谓 / 特别注意 |

所以它不是"把整本书塞进 prompt"，而是**按需检索故事状态**。
这也让每次请求的前缀保持稳定，能吃到 prompt cache。

### 轻小说翻译准则（已内置到 prompt）

内置规则不是泛泛的「忠实原文」，而是按轻小说实际读感写的：短句/对话驱动、
叙述者吐槽滤镜、角色×对象的语气差异、词汇/句法习惯、术语锁定、文化词不过度
本地化、双关功能对等、拟声动作化、保留段落和换行节奏、不过度润色加戏。

每本书可以继续补：

```bash
# 发布媒介会改变加注策略（web / ebook / paper）
python3 lntrans.py learn <slug> --medium web

# 第一人称叙述者的滤镜
python3 lntrans.py learn <slug> --narrator "自嘲、爱吐槽，但关键处会突然认真"

# 完整自定义准则（文本文件；prompt 会注入前 3000 字）
python3 lntrans.py learn <slug> --guide path/to/translation-guide.txt

# 结构化角色卡：语气 / 称呼 / 词汇 / 句法 / 本卷时间点 / 别名
python3 lntrans.py learn <slug> \
  --character "アリス=女主角|voice:傲娇，紧张时句子变短|address:叫主角「笨蛋」|lexicon:不用四字词|syntax:短句多，爱省略|volume:第一卷|aliases:アリスちゃん"

# 术语变更会记入 history.jsonl（旧值→新值），不会静默覆盖
python3 lntrans.py learn <slug> --term "魔法=魔力"
```

角色卡只在**本段原文出现该角色**时注入；术语表也只注入本段实际出现的词。
人物卡不是必填模板——至少写清「最想要什么、最怕什么、说话时最常回避什么」，
再按需要补词汇/句法。

### 引号与漏译（容易被忽略的"信"）

**引号跟着原文**：原文用「」就「」，原文用「」嵌套就照抄，原文用中文弯引号才用“”，
原文没加引号的地方也不加。不要为了"统一好看"选一种字形替换整个体系 ——
那等于把自己的排版偏好掺进译文。机械层只做**字形对齐**：引号数量与开/闭角色序列
完全一致时才换字形，结构不同整段不动（那是译者对句子的处理）。

只写进 prompt 不够：翻译是逐 chunk 独立请求的，模型会对每个 chunk 各自决定用哪种
引号，同一章里两种引号交替很常见（实测 19 章里 11 章如此）。

**多行对白漏译**：原文一个段落里可能连着好几行对白（行间没有空行），模型常常只译
第一行 —— 而段数、编号、中文校验全都过，界面看起来完全正常。现在用引号对数兜底
（`_missing_dialogue`）：对白数少于原文就重试，并在 prompt 里点名那一段。

存量修复（都会先备份）：

```bash
python3 align_quotes.py            # 干跑：引号字形与原文不一致的段落
python3 align_quotes.py --write    # 对齐

python3 repair_dialogue.py         # 干跑：漏译对白的段落 + token 估算
python3 repair_dialogue.py --write # 只重译坏段（同章合并成一次请求）
```

### 人名一致性（接入新书的 SOP）

逐 chunk 翻译时模型每次都独立决定译名，一个人名两三种写法很常见。流程：

```bash
python3 lntrans.py names <slug>                    # 找一名多译（3~4k token）
python3 lntrans.py learn <slug> --term "日文名=选定译法"
python3 lntrans.py fix <slug> --rename "旧=新"      # 不花 token、自动备份
python3 lntrans.py residue <slug> --context        # 残留假名 + 上下文
# 口径：引号内的刻意引用、颜文字 (つд⊂)、装饰性 ゛/ーーー 都不算 —— 否则指标永远假红
```

**必须用 `grep -ro 译名 novels/<slug>/chapters/ | wc -l` 核频次**：模型报的次数
经常是错的（实测报 15/5、真实 103/17），照它锁可能把主角名字锁反。
三类"假冲突"不要动：称呼后缀（千岁/千岁酱）、子串（贝尔贝特/贝尔贝）、全称与简称。

### 润色（polish，可选）

```bash
python3 lntrans.py polish <slug> --chapter 12          # 干跑，打印前后对比
python3 lntrans.py polish <slug> --chapter 12 --write  # 落盘（备份到 cache/polish-backup-*.txt）
```

只处理 ≥24 字的段；四道校验后才替换：还是中文 / 对白数不变 / 术语表译名没丢 /
长度在 0.6~1.7 倍之间。任一条不过就保留原译，不重试、不二分（润色失败不能影响可读性）。
术语表会作为硬约束写进 prompt —— 没有它，润色会把好不容易锁死的人名又改回去。

### 内部机制（改代码时别破坏）

* **整章一块，不一段一段**：段落级切分让模型看不到上下文（一段对白单拎出来，语气、
  指代、说话人都会漂）。默认按**整章**送模型，只在超过该模型上限时于段落边界切块；
  块间把上文译文尾部塞进 system 续上下文，缓存按块存。
  `LNTRANS_TRANSLATE_MODE` 决定协议：`batch`（默认，#N 编号块，通用聊天模型）或
  `sakura`（模型自带「将下面的日文文本翻译成中文：…」模板，句子级模型专用）。
  两种模式都是整章流程，模板按**实际执行的 provider** 选（兜底切云端时换通用模板）。
* **块大小按模型分档、必须实测**：本地 Sakura 上限约 2400 字（3941→22/28 对白、
  3189→16/20、2389→10/10、1550→18/18），取 90% = `LNTRANS_CHAPTER_CHARS=2160`；
  云端 `LNTRANS_DEEPSEEK_CHAPTER_CHARS=6000`（实测 7393 字整块 60/60 对白、不截断）。
  别为了"一次翻完"把本地块调大：句子级模型会静默漏行，重试/二分烧光整章预算。
* **推理模型的思考也算 completion**：`max_tokens` 给小了会只剩思考、正文截断甚至
  空回复，然后反复重试。云端默认 `LNTRANS_DEEPSEEK_MAX_TOKENS=32000`。
* **兜底前先探测**：请求前做 5 秒 TCP 探测（失败重试一次），本地引擎关机时几秒内
  切换，而不是卡到生成超时（600 秒）才切。
* **批量模式的对齐**：`#n:` 编号强制对齐，解析时按编号回填，**缺号会重试一次**。
* **缓存**：`cache/<章>.json` 存每段译文和原文 SHA256。同一段不重复请求；
  `--force` 会忽略旧缓存真正重译（改术语后必须这样验证）。
* **断点续译**：`meta.progress.translated_through` + `chapters/NNNN.txt` 落盘，
  随时中断、随时接着跑。
* **章节旁车**：v5 每次正文落盘都写 `chapters/NNNN.meta.json`，记录原文哈希、
  正文哈希、模型/prompt 配置、usage、费用和缺失段；正文与旁车错配时该章不可读，
  不会被误当成完成。
* **持久任务**：任务记录在 `data/jobs/<job-id>.json`。服务或命令行进程中断后，
  `queued/running` 会变成 `interrupted`；阅读页显示已完成与剩余章节，确认后才恢复。
  已可用章节按正文 + 有效旁车重新计算，不靠重放历史事件，也不会重复翻已完成章节。
* **梗概匹配坑**：梗概是**中文**写的，匹配登场人物时必须同时用
  日文名和它的中文译名（`glossary` 里的值）。只用日文名会永远匹配不上——
  这个 bug 修过一次，别改回去。
* **前情衔接**：每个块会带上上一块译文的尾部 400 字，保证跨段语气连贯。
* **语言校验**：光校验行数不够，模型会把日文原样抄回来冒充译文，
  必须过 `detect_chinese()`。

### 成本参考（实测）

| 项 | 实测值 |
|---|---|
| 单章消耗（云端整章） | 约 8,000–27,400 token；7393 字的章 = 27,380 tok（其中思考 17,428）≈ ¥0.16 |
| 单章消耗（本地 Sakura） | 1578 字 = 2077 tok / 约 1 分钟；3620 字 = 4504 tok，**0 元** |
| 61 章整本 | 约 50 万 token，按当前云端价格粗估约数元 |
| 重复翻译 | 0 token（命中块/段缓存、已有译文直接跳过） |

用 `next` 的 `--dry-run` 可以只看分段和字数，不花一分钱。

### 模型角色与预算

模型入口统一由 `lnmodels.py` 读取，不再在各个命令里散落固定模型名：

```bash
# 翻译/辅助本地；校对走云端；本地连不上自动切云端
LNTRANS_LLM_BASE_URL=http://127.0.0.1:11434/v1/chat/completions
LNTRANS_MODEL_TRANSLATE=<本地模型 id>
LNTRANS_MODEL_AUXILIARY=<本地模型 id>
LNTRANS_LLM_BASE_URL_REVIEW=https://api.deepseek.com/chat/completions
LNTRANS_MODEL_REVIEW=deepseek-flash
LNTRANS_LLM_FALLBACK=1
LNTRANS_LLM_FALLBACK_BASE_URL=https://api.deepseek.com/chat/completions
LNTRANS_LLM_FALLBACK_MODEL=deepseek-flash
LNTRANS_DAILY_BUDGET_CNY=5
LNTRANS_JOB_BUDGET_CNY=1
```

每个角色可用 `LNTRANS_LLM_BASE_URL_TRANSLATE/_AUXILIARY/_REVIEW` 和对应
`_API_KEY_*` 单独覆盖端点/key。兜底只给翻译/辅助（校对不回落）；连接失败/超时/
401/404/5xx 触发，120 秒内不再撞本地。本地回环端点可不配 key；旧
`LNTRANS_LLM_BASE` / `DEEPSEEK_API_KEY` 仍兼容。
真实调用只把角色、模型、token 和费用写进 `data/llm-usage.jsonl`，不记录 prompt、
译文或密钥。**预算是提醒，不是刹车**：超预算只在阅读页/翻译列表显示"已用 X（超出预算）"，
在读的书继续翻；硬停只有全局暂停和暂停本书，预算填 0 = 不限。详见 `docs/MODEL-CONFIG.md`。

### 翻译策略：默认**不自动翻**（硬要求，别改回去）

需求原话：「不要自动翻译没看过的小说，看过的最多自动翻译到看到的后面第三章。
除非玩家主动开启这本小说的翻译。希望玩家可以选择翻译到多少多少。」

实现集中在**三个函数**（只有这一处决定"翻什么"，自动/手动路径共用）：

| 函数 | 作用 |
|---|---|
| `trans_cfg(slug)` | 每本书的 `enabled` / `ahead`(默认 3) / `max_chapters` |
| `auto_ceiling(slug, meta)` | 自动翻译上限；**未开启 → 0**（一章都不翻） |
| `allowed_targets(...)` | 唯一入口，返回 (允许翻的章号, 天花板) |

关键规则：

* **默认 `enabled=False`** → `auto_ceiling()==0` → 自动续译拿不到任何目标，
  连"读到章末自动往下翻"也不会发生。
* 开启后上限 = `读到章 + ahead`（默认 3），可被 `max_chapters` 再压。
* 天花板**不低于已译章数**：读到 0 章时 `auto_ceiling=0`，但已花钱译出的
  20 章不该因此变成"超限"（踩过这个别扭逻辑）。
* 手动「翻到第 N 章」走 `explicit_ceiling`，能**突破**自动上限，
  但**不要**去改 `max_chapters`（那会变成永久限制）。
* `worker` 只在 `allowed_targets` 返回非空时才翻；空时把
  `idle_reason` 写给前端（"未开启翻译" / "已达策略上限"）。

