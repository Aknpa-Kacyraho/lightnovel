# AGENTS.md — DSHAWORKAREA/Andoroid

两个自用工具：**lnfinder**（按口味画像去找轻小说）+ **lntrans**（按需把日文轻小说译成中文，
并用书架 Web 服务给用户读）。用户是**中文读者，不吃生肉**，所有面向用户的文案一律中文。

> 深度内容在 skill 与文档里，**按需加载**，不要在这里重复：
> `.dsh/skills/lightnovel/SKILL.md`（入口 + §0 开网站，约 5KB）与其同目录
> `references/{finder,translate,lnserve,lessons,setup}.md`（找书 / 翻译 / 网站实现 /
> 踩坑 / 部署；**按需只读一份**）、
> `lntrans/STATE-MACHINE.md`（4 状态 + on_shelf 语义）、
> `lntrans/PRIOR-ART.md`（Kavita / LightNovelReader / auto-novel 的取舍理由）、
> `lnfinder/README.md`（上游站点 API 逆向笔记）。
>
> skill 只有 `lightnovel` 这一个（原来拆成 lnfinder / lntrans 两个，因为流程本来就是
> 连着的，拆开每次都要两边各读一遍，而且"怎么开网站"两边都没写清楚）。
> 它是**要分享出去给人用的**：写进去的任何东西都可能被陌生人看到 ——
> 绝对不写 key、凭据、绝对路径、用户口味的具体取值、书名/slug。

## 目录地图

| 位置 | 是什么 |
| --- | --- |
| `lnfinder/lnfind.py` | 画像、打分、`/api/dislike` 背后的 `learn_from_work()` |
| `lnfinder/lnlib.py` | 上游抓取（Kakuyomu + 成为小说家吧，一般向/R18 全闭环） |
| `lnfinder/taste_profile.json` | **用户口味画像**（真实资产，见下） |
| `lntrans/lnserve.py` | 书架 Web 服务（HTTP + 翻译 worker + 全部页面；内嵌前端 JS 见 `static/`） |
| `lntrans/lntrans.py` | 翻译核心（LLM 调用、段落校验、二分降级、术语过期） |
| `lntrans/lnimport.py` | 本地 EPUB/TXT 导入（标准库拆章，`source=local`，不联网） |
| `lntrans/lnrecs.py` | 推荐缓存 + 书库留档 + lnfinder 惰性加载 |
| `lntrans/lnbackup.py` | 备份/校验/恢复（`/api/backup` 背后的实现）——**只装钱买不到的**，见下 |
| `lntrans/lnrender.py` | 章节/整本 HTML 渲染；正文里的术语/人名标注也在这里 |
| `lntrans/lnepub.py` | 导出 EPUB 3（`/export/<slug>.epub` 背后的实现），只放译文 |
| `lntrans/lncovers.py` | 源站 og:image 抓取与本地缓存（详情页横幅用），渲染路径不联网 |
| `lntrans/lnsched.py` | **翻译调度**：在读持续翻 / 翻译列表 / 每日预算（纯逻辑，可单测） |
| `lntrans/lndata.py` | v5 数据根：单一 `LNTRANS_HOME`、代际指针、迁移、跨进程排他锁 |
| `lntrans/lnjobs.py` | 可恢复的翻译任务记录（八状态、损坏隔离、启动时不自动重放） |
| `lntrans/lncontracts.py` + `lntrans/contracts/*.json` | 段落/章节边车的契约与 `dir_sigs()`（一次 scandir） |
| `lntrans/lnmodels.py` | 模型配置（端点/key/三个角色模型/价格与预算） |
| `lntrans/lnmigrate.py` | v4 → v5 数据根迁移（默认干跑，`--write` 才复制并换指针） |
| `docs/` | `V5-DATA-SAFETY.md`（数据根/锁/边车/任务恢复）、`MODEL-CONFIG.md` |
| `make_share.py` + `lntrans/test_share_package.py` | 白名单打分享包，并审计包里有没有个人数据 |
| `VERSION` `pyproject.toml` `.env.example` `LICENSE` `NOTICE` `SECURITY.md` | 版本与分发元数据 |
| `lntrans/static/*.js` + `app.css` | 前端脚本（ACTION/LIB/DISLIKE/READER/DETAIL/REVIEW）与页面样式，由 `lnserve._read_static()` 读入后内联注入（CSS 缺失服务起不来） |
| `lntrans/run_selftests.py` | **一键自检**（唯一入口，见下）；`-v` 打印每条断言，`-k a,b` 只跑匹配的测试 |
| `lntrans/test_*.py`、`test_click_dom.js`、`lntrans/selftest*.py` | 各模块回归（`test_click` 是"真点按钮"的前端仿真器，`test_reader` 管章节划分/自动补章） |
| `lntrans/repair_chrome.py` | 维护脚本：清掉历史章节里的网站页脚残留（先抓干净原文再中日同索引删；对不上就跳过） |
| `lntrans/align_quotes.py` | 维护脚本：把存量译文的引号字形**对齐到原文**（默认干跑、只动引号、自动备份、报结构不一致的段） |
| `lntrans/repair_dialogue.py` | 维护脚本：重译「多行对白只译了第一行」的坏段（调真实 LLM；默认干跑 + 估算 token） |
| `lnfinder/selftest.py` | lnfinder 自检（画像/打分/套路折扣） |
| `skills/lightnovel/PHONE-HANDOFF.md` | 手机侧交接页（环境差异 / 三条硬边界 / 最近一轮的坑），给下一位接手的人看 |
| `lntrans/novels/` `lntrans/data/` | **用户真实数据**（见下） |
| `vs.sh` | 虚拟屏操作助手（不打扰用户真实屏幕） |
| `phone-report.md` `shots/` | 早前的手机体检报告与截图 |

## 硬规则：路径必须走环境变量

**任何碰目录的模块都必须读环境变量，不许写死路径。** 已经踩过两次：
`lnrecs` 没读 → 隔离测试把假数据写进真实目录；`lnrender` 没读 → 渲染读错树，
`/api/next` 永远返回 0 章且**真实环境看起来正常**，极难查。

| 变量 | 含义 |
| --- | --- |
| `LNTRANS_DATA_ROOT` | 数据根（`novels/` + `data/`） |
| `LNTRANS_LNFINDER` | 画像/候选池等**数据**所在目录（注意：`lnfind.py` 代码始终在真实 `lnfinder/`） |
| `LNTRANS_LLM_BASE` | LLM 端点，默认 api.deepseek.com；自检指向本地桩 LLM |
| `LNTRANS_TOKEN` | `--lan`（绑非回环地址）时的访问口令；不设则启动时随机生成并打进终端。回环地址免口令 |
| `LNTRANS_TEST_SERVER` | 标记"这是隔离测试服务"，测试据此决定可否执行会写数据的检查 |
| `LNTRANS_SERVER_ROOT` | 隔离服务的数据根；测试要**直接调生产函数**读同一份数据时用它（否则断言永远跳过 = 假绿） |
| `LNTRANS_CRED` | 凭据文件路径（不设就用 `lntrans.py` 里的默认值） |
| `LNTRANS_VERBOSE` | `=1` 等价于 `run_selftests.py -v` |
| `LNTRANS_HOME` | v5 数据根（不设则用旧 v4 布局；设了就用 `<home>/generations/gen-*`） |
| `LNTRANS_TOKEN_FILE` | 从文件读局域网口令（比环境变量更不容易泄漏给 `ps`） |
| `LNTRANS_LLM_BASE_URL` / `LNTRANS_LLM_API_KEY` | v5 全局端点与 key；`LNTRANS_LLM_BASE` 仍是别名 |
| `LNTRANS_LLM_BASE_URL_TRANSLATE/_AUXILIARY/_REVIEW` + 对应 `_API_KEY_*` | 按角色覆盖端点与 key（翻译/辅助可本地，校对可 DeepSeek） |
| `LNTRANS_LLM_FALLBACK` / `_BASE_URL` / `_MODEL` / `_API_KEY` | 翻译/辅助主端点不可达时切 DeepSeek（120 秒熔断；校对不回落） |
| `LNTRANS_DEEPSEEK_PRICE_INPUT/OUTPUT_CNY_PER_M` | 云端兜底/校对的独立价格；本地价格可设 0 |
| `LNTRANS_MODEL_TRANSLATE` / `_AUXILIARY` / `_REVIEW` | 按角色选模型；`LNTRANS_MODEL` 兜底 |
| `LNTRANS_ALLOWED_HOSTS` | 局域网访问的 Host 白名单（逗号分隔） |
| `LNTRANS_DEVICE_DAYS` | 「记住这台电脑」的有效期（默认 180 天，用一次自动续期） |
| `LNTRANS_SEG_LINES` | 单段最多多少段落（默认 60；小参数本地模型调小，如 20） |
| `LNTRANS_TRANSLATE_MODE` | `batch`（默认，#N 编号批量）或 `sakura`（模型自带单段格式，一次一段） |
| `LNTRANS_CHAPTER_CHARS` | 本地模型每块最多多少字（实测 Sakura 2400 全对、3200 漏；取 90% ≈ 2160） |
| `LNTRANS_DEEPSEEK_CHAPTER_CHARS` | 云端每块最多多少字（默认 6000；实测 7.4k 字整块仍完整） |
| `LNTRANS_DEEPSEEK_MAX_TOKENS` | 云端单次 max_tokens（默认 32000；深度思考会吃掉份额） |
| `LNTRANS_JOB_STALE_SEC` / `_STALL_LOG_SEC` | 任务判死阈值 / 卡死栈 dump 阈值（本地整章翻译要放宽） |
| `LNTRANS_CHAPTER_TOK` | 单章 token 预算（默认 30000，重试/二分的总闸） |

**真实资产，绝不写入**：`lntrans/novels/`（译文与章节）、`lntrans/data/`
（`recs.json`、`library.json`、`books/`、`details/`、`history.jsonl`、日志）、
导出的 `lntrans/*-中文.md`、`lnfinder/taste_profile.json`、`lnfinder/history.jsonl`、
`lnfinder/candidates.json`、`lnfinder/reports/`、`lnfinder/recommend-latest.md`、
以及任何凭据文件。自检的 `run_selftests.py` 会比对它们的指纹（跑前跑后必须一致）。

**主库不一定在代码目录里**：设了 `LNTRANS_DATA_ROOT`（例如手机用
`$HOME/lightnovel-data`，配置集中在 `~/.ln-phone.env`）时，真实资产是那棵树；
`lntrans/novels|data` 在迁移后只是**只读留档**。任何写数据/跑维护脚本前先
`echo "$LNTRANS_DATA_ROOT"` 确认写的是哪棵树，别把旧留档当主库改。

## 常用命令

**开网站走 `~/ln-phone.sh start`**（它会 `source ~/.ln-phone.env` 再以 `--lan` 起 8099）。
别裸跑 `python3 lnserve.py`：那样会读代码目录里的旧数据根，并连默认云端端点，
既不是主库也不会用本地模型。

```bash
~/ln-phone.sh start|stop|restart|status|logs   # 手机主库：起/停/重启/看状态/看日志
cd lntrans && python3 run_selftests.py        # 自检（35 个，见 run_selftests.py 的 TESTS），全绿才算过
cd lntrans && python3 run_selftests.py -v     # 同上，但打出每个测试的完整断言
cd lntrans && python3 run_selftests.py -k test_click,test_reader  # 只跑受影响的（改一处别等全套）
cd lntrans && python3 lntrans.py import ~/book.epub   # 导入本地 EPUB/TXT（建书，不花 token）
cd lntrans && python3 lntrans.py stale <slug>          # 术语表改过：哪些章译名可能过时（只报告）
cd lntrans && python3 lntrans.py stale <slug> --retranslate --limit 2   # 真重翻（花钱）
cd lntrans && python3 lntrans.py terms <slug>          # 片假名候选术语（0 token）
cd lntrans && python3 repair_chrome.py                            # 干跑：查章节里有没有网站页脚残留
cd lntrans && python3 align_quotes.py                              # 干跑：引号字形是否与原文一致；加 --write 对齐（自动备份）
cd lntrans && python3 repair_dialogue.py                           # 干跑：查漏译对白的段落；加 --write 重译（花钱，先估算）
cd lnfinder && python3 selftest.py            # lnfinder 自检
cd lntrans && python3 lnbackup.py export --out ~/Download   # 备份（译文/书架/画像）
cd lntrans && python3 lnbackup.py verify 文件.zip           # 逐文件核 sha256
cd lntrans && python3 lnbackup.py restore 文件.zip          # 干跑，看要动什么
cd lntrans && python3 lnbackup.py restore 文件.zip --write  # 真恢复（只增不删）
cd lntrans && python3 lnmigrate.py migrate --home /data --source-root . --source-profile ../lnfinder   # 迁移干跑
cd lntrans && python3 lnjobs.py list                       # 看任务记录（只读）
cd lntrans && python3 lnjobs.py verify                     # 校验任务记录可否恢复
cd lntrans && python3 lnserve.py --port 8099              # 只在本机（用户手机浏览器）
cd lntrans && python3 lnserve.py --port 8099 --lan        # 同时开给局域网（平板/热点）
cd lntrans && python3 lnserve.py --port 8099 --watch      # 另开定时查更新（默认只在打开书时查）
```

* 服务会随会话结束而死，**用户要读的时候重新起**，并确认返回 200。
* `--lan` 绑 `0.0.0.0`，用户手机开热点后平板就能用；平板要输的地址在**设置页**
  （首页右上「设置」→ 局域网访问；`/api/net` 现查，热点开关一次地址就变）。
  **表单登录**：绑非回环地址时，启动日志给地址和口令，但网址不带口令；平板输入一次后
  会种随机会话 Cookie，**并记住这台设备**（`data/devices.json`，只存 sha256）——
  服务重启、浏览器重开都不用再输；设置页「退出本设备」才忘掉，`LNTRANS_DEVICE_DAYS`
  控制有效期（默认 180 天，用一次续一次）。可用 `LNTRANS_TOKEN` / `LNTRANS_TOKEN_FILE`
  固定口令；回环地址免登录，手机自己不受影响。
* **绝不用 `pkill -f lnserve.py`**：这条命令的 cmdline 里也含 `lnserve.py`，会杀掉自己。
  要停就用精确 argv 匹配（`/proc/<pid>/cmdline` 里 `argv[1]` 以 `/lnserve.py` 结尾）。
* 手机能力走 `127.0.0.1:3090` 的 `/app/*`（凭证在 header 文件，别写进 URL）。
* **Windows 开发机上跑自检必须先开 UTF-8 模式**：`chcp 65001` 后设
  `$env:PYTHONUTF8="1"; $env:PYTHONIOENCODING="utf-8"`。否则 `run_selftests.py`
  的子进程按 locale(cp936/gbk) 编码，成片测试在 `open()`/`json.load` 上炸
  （`'gbk' codec can't encode '\u2715'`、`'utf-8' codec can't decode byte 0xa5`），
  **看着像回归、其实是环境**。Linux/Android（真实目标）默认 UTF-8，无需此步。

## 禁止

* **自检的 DOM 桩必须和浏览器一样"未知 id 返回 null"**，并断言"每个带 id 的按钮
  都有 handler（除非它走事件委托）"。踩过：桩对任何 id 都返回一个稳定对象，
  于是 `getElementById('btn-fav').onclick=`（元素早没了）在真实浏览器里抛
  "Cannot set properties of null" → **整段脚本后续绑定全废**（日文折叠开关、
  主题按钮集体失灵），而桩里一路绿灯 —— 这个 bug 是外面的人审出来的。
* **不要操作用户的手机屏幕**（`ui/tap`、`ui/swipe`、`ui/screenshot` 一律不用）——
  用户明确说过"我自己来就好了"。验证服务端用 `curl`；验证前端分两层：
  `node -e "new Function(...)"` 只证明语法能解析，**不够** ——
  于是有了 `lntrans/test_click.py` + `test_click_dom.js`（最小 DOM 桩）：
  把页面脚本真的执行、按每个按钮真的点一次，断言发出去的请求和 UI 状态。
  "按钮点了没反应"这类 bug 只有这一层查得出来。
* 不要在自检里调用真实 LLM：既慢又**真的花用户的钱**。自检自带桩 LLM，token 成本为 0。
* 不要为了"跑通"放宽断言，也不要让断言假绿（拿到空数据就 skip 掉的真断言 = 没测）。

## 设计红线：画像要能「自升级」

人的口味会变，**不许把画像一次定死**。`lnfind.py` 的反馈加减
（`learn_from_work`，步长 0.6 / 套路标签 ×0.4）之外，已内建**时间半衰期衰减**
（`apply_time_decay`）：每次写入画像前，把长期没被触碰的权重向中性 1.0 收缩
（`w ← 1.0 + (w-1) × 0.5^(elapsed/90)`，半衰期 90 天；两次结算间隔 <12h 不动）。
旧偏好自然退场、近期信号占比更大；总在 reinforce 的标签衰减后又被加回，稳定在偏好位。
护栏：`blocked_tags` 与 `formula_tags` 数值不衰减、只衰减不删除。每次衰减都写
`decay` 事件进 `history.jsonl` 可回溯。任何后续改动仍要给画像留**持续进化**空间
（如按样本再衰减、调半衰期），别让初始偏好永久主导。

## 代码约定

* **卡片渲染只能走 `lntrans/lnserve.py` 的 `work_head()` / `work_status_chips()`**。
  推荐卡和书库卡曾是两处独立渲染，改一处漏一处，用户报过两次 bug。
  新增第三种卡片也必须调这两个。
* **"隐藏 / 不感兴趣"必须在所有列表生效**。数据层 `lnrecs.cached()` 默认就排除隐藏项；
  需要"按 id 找元数据"的路径显式传 `include_hidden=True`（隐藏是"别再推给我"，不是"删了它"）。
* 负反馈要**归因**：原因决定扣哪些标签（「太套路了」只扣 `formula_tags`，
  绝不能连带扣掉 `勘違い`／`悪役令嬢` 这类误解系偏好）。
* **按钮名字就是承诺，别让它骗人**（用户报过"点了换一批没用"）：
  「换一批」= 本地换页（`recs.rotate` / `recs.rank_library`，秒回、不打源站），
  「重新抓取」才是慢操作（打源站，必须异步 + 显示 `x/y` 进度）。
  同一个关键词集合重抓一次**必然**拿回同一批书，所以"换"永远不能靠"重抓"实现。
  做本地轮换时按**页**对齐（`_next_page`）：`(start+step)%total` 在两页数不能整除时
  会让两屏重叠 6 本。**慢操作不许同步等**（原来点了要等 1 分 53 秒，页面零反馈 = "卡死"）。
* 界面遵循**中文优先**：中文大标题 + 日文小字副标题（`jp-sub`，约 0.68em、50% 透明）。
  书架卡的书名有两个来源，**必须合并读**：`novels/<slug>/meta.json` 的
  `zh_titles.book`（章节翻译写的）与 `data/details/<源id>.json` 的 `zh_title`
  （列表页/详情页翻译写的）。只读前者 → 同一本书在推荐卡是中文、书架上是日文
  （用户报过「书架里的书标题没翻译」）。日文原名只在中日不同时才显示第二行。
* **状态按钮一律走事件委托**（`lnserve.ACTION_JS`），不许再逐个 `.onclick=`：
  漏绑过一次（不在 `.ctrls` 里的「点我翻译」徽标）和一次"class 写死 on 导致
  收藏永远发 value:false"，还有一次是一处未捕获异常废掉后面全部绑定。
  新增动作按钮只要带 `data-act` / `data-d-act` 就能用。
  这些脚本（连同 LIB/DISLIKE/READER/DETAIL/REVIEW）都在 **`lntrans/static/*.js`**（不再内嵌在
  `lnserve.py` 的 Python 字符串里），由 `lnserve._read_static()` 读入后内联注入 `<script>`。
  改前端就改 `static/*.js` 并跑 `node --check`（`test_js_static.py` 守着），别再写回 `.py`。
* `read_tracking()` 在**不在书架**时必须返回 `None`（不许伪造 `"want"`）：
  否则「打开阅读页 → want 转 reading」会把已移出的书自动加回书架。
  `/api/add`（加入书架）要显式 `ensure_on_shelf()` 写 `want`，**绝不碰 `favorites`**
  —— 用户原话：「我加入书架不等于收藏，因为我不加看不了」。
* 数字不能骗人：显示的数量必须等于实际渲染的条目数；耗时说明按实测算，不写"约 1 分钟"；
  分页列表里的筛选数字要标明是**本页**。
  「已译 N 章」一律用 `have_count()`（真有译文的章数），**不许**用
  `translated_count()`（从第 1 章起的连续前缀）—— 第 1 章缺译时会显示 0，而下面
  明明列着 6 章（用户当场问「我第一话呢？」）。
* **分页的"总数"必须与真正渲染的卡同源、同一次过滤**，且用**未被 `limit` 截断**的
  完整条数（`lnrecs.library_count`）。踩过：书库面板总用 `len(_load_lib())`（418，
  含隐藏、不看筛选）而渲染用 `library_items(limit=400)`（400）→ 页数显示 28 却只
  翻到 27，末尾整页翻不到。`/api/booklib` 的 `total` 同理；这个接口 `items` 默认
  截断到 300 条，所以它必须**自报 `limit` / `offset` / `more`**，否则拿到 300 条的
  人会以为"书库只有 300 本"（前端要翻页就用 `?limit=&offset=`，硬上限 1000）。
* 「更新了 +N 话 · 点我翻译」（`fill`）**只翻最新的 N 话**（`after = 总章数 - N`，
  一次最多 10 话），不许理解成"把整本欠账翻完"：按钮上写的是 +N 话，而一本 20/61 的
  书欠 41 话 ≈ 25 万 token。按钮名字就是承诺。
* 翻译失败的**不许落盘/不许缓存/不许算已译**（`progress.incomplete` 记一笔），
  `--allow-missing` 写出但标 `incomplete`：目录里要显示「未译全」。
  原文冒充译文是最坏的结果 —— 一旦落盘就会被永久复用。
* **状态字段必须有人置位、也必须有人清除**：`has_update` 三处清（复查确认无新章 /
  弃文 / 移出书架，`_clear_update_flags()`），亮不亮只看 `_item_watches()`（收藏永远亮，
  弃文/看完/读完/搁置不亮）。踩过：一旦置位再没人清，读者处理完更新徽标还永远亮着，
  点进去根本没有新章 —— 按钮名字成了谎话。新增任何 `*_flag` 字段先问"谁清"。
* **请求里的数字参数一律走 `_as_int(v, default, lo, hi)`**：`?page=abc`、`count="abc"`
  不许打成 500（JSON 接口的调用方只能静默失败）。夹范围也在这一步做。
* **按标题生成的目录名（slug）必须按 source_id 判重，不能按"目录存在"就跳过**：
  `slugify()` 只保留 ASCII，日文标题常常缩成两三个字母（「TS転生してたので…」→ `ts`），
  两部作品撞同一个 slug 是常态。踩过（用户报「点加入书架永远失败」）：`cmd_init`
  发现同名目录就静默 return，`/api/add` 却回 `ok:true` —— 书既没建也没上架，
  点几次都一样。现在撞车就改用 `kakuyomu-<源站id>`，并且 `/api/add` **按结果验证**
  （本地有这个 source_id + 状态文件里真的在书架上）才回 ok。
* **会写状态接口必须校验实体存在**：`/api/progress`、`/api/feedback` 先 `novel_meta(slug)`，
  不存在的 slug 直接拒绝 —— 否则 `update_book()` 会在 `data/books/` 里凭空造出
  `__no_such_book__.json`（真实数据污染，本机复现过）。
* **HTML 转义分两种**：文本节点用 `lr.esc()`，属性值用 `attrescape()`
  （标题/作者来自源站或 LLM，含 `"` 会把 `data-*` 截断、含 `<` 会变真标签）。
* **引号跟着原文，不做任何"统一"**：用户原话「不要强制用「」，我说过忠于原著。
  我不希望我自己的意志影响翻译。信达雅，先是信。」原文用「」就「」，原文用“”就“”，
  原文没引号就不加。字形由 `align_quotes_with_source()` 在
  `robust_translate_paras` 返回前 + 缓存命中路径对齐到原文，**只在引号数量与
  开/闭角色序列完全一致时才换字形**，结构不同就整段不动（那是译者对句子的处理）。
  **别为了"好看/中文排版惯例"选一种字形统一** —— 那正是用户否掉的方案。
* **多行对白漏译必须拦**：原文一个段落里可能连着三行对白（行间无空行），
  模型常常只译第一行 —— 而段数、编号、中文校验、回抄比对**全都过**，界面看着正常。
  踩过：某部 20 话的作品有 152 段如此（49 段少 2 处以上）。
  现在 `_missing_dialogue()` 用引号对数兜底：译文对白数少于原文 → 重试并在 prompt 里
  点名哪一段；prompt 也明写「每一行都要译出来」。存量用 `repair_dialogue.py`
  （默认干跑、只重译坏段、章内合并成一次请求、同步补段缓存、自动备份）。
* **人名一致性要走闭环，不许靠"模型这次应该记得"**：逐 chunk 请求意味着模型每次都
  独立决定译名。标准流程：`names`（找一名多译，一次 3~4k token）→ **grep 实数核频次**
  （模型报的"约 N 次"是幻觉，实测它说 15/5、真实是 103/17，按模型的话会把主角锁反）
  → `learn --term 日文=选定译法` → `fix --rename 旧=新`（不花 token、自动备份）
  → 再跑 `names` 复核到 0。**三类"假冲突"不要动**：称呼后缀（千岁/千岁酱）、
  子串（贝尔贝特/贝尔贝）、全称与简称（波特曼伯爵家/波特曼家）—— 合并会把语感改没。
  残留假名用 `residue` 看：**引号内的刻意引用、颜文字 `(つд⊂)`、装饰性 `゛/ーーー` 都不算**
  （不豁免的话指标永远假红，假红的指标等于没有指标）。`residue --context` 直接打上下文。
* **润色（polish）只能"改写表达"，不许"改写事实"**：它重写已译文本，比翻译更容易改坏。
  实现上四道校验后才替换：仍是中文 / **对白数不变** / 术语表里的锁定译名没丢 /
  长度没离谱（0.6~1.7 倍）；任一条不过就**保留原译**，且不进二分（失败就停）。
  只润色 ≥24 字的段（短句改了没收益），一批最多 6 段/1400 字，单轮有 token 上限，
  落盘前把原文件备份到 `novels/<slug>/cache/polish-backup-*.txt`。
  引号用 `align_quotes_with_source()` 对齐回原文，不换体系。
* **worker 不许"整本原文一次抓完再翻"**：逐章 `ensure_raw(slug, meta, i+1)` 紧挨着
  该章的翻译做 —— 踩过：翻到第 185 章时先静默下载 ~9 分钟、已译恒为 0、界面零进度，
  看着就是卡死。逐章抓后第一段译文几秒内就出现。
* 阅读页「翻到第 N 章」的**输入框不许嵌在按钮里**（点输入框会冒泡成按钮点击 → 直接按
  默认值开翻），默认值也不许是总章数（一次点击 = 静默翻完整本，踩过一本 185 章）：
  结构用 `.ceil-row`，默认 `auto_ceiling()`，没开翻译就回退"读到 + ahead"。
* **前端轮询链的锁必须成对**：`tick()` 设 `polling=true` 后才去调 `poll()`，而 `poll()`
  开头就是 `if(polling) return;` —— 不在交接处 `polling=false` 的话，轮询链在启动瞬间
  就断（"任务运行中"这条最常走的分支也会把自己锁死），译好的章节永不追加、必须手动
  刷新 = "读到哪翻到哪"直接失效。**每个分支都要先清锁再 `setTimeout`**（踩过两次）。
* 抓来的原文/译文一律 `save_text()` 原子写（先 .tmp 再 replace）：
  否则进程被杀留下半截文件，而 `has_translation()` 只看 size>0 → 截断内容被当成"已译"。
* **翻章链接必须带正文锚点**：`/read/<slug>?from=N#cN`（缺译则是 `#need-N`）。
  踩过：点「下一章」回到页面顶部，前面是标题 + 一整屏目录，读者还得自己往下翻一段
  才看到正文（用户原话）。目录也**默认折叠**成 `<details id="tocbox">`，正文紧跟标题栏。
* **底部翻译条只有一套文案模板 + 独立进度槽**：`#tb-status` 只写状态（只有章号会变），
  `#tb-prog` / `#tb-fill` 只写 `已译 x/y（p%）`。踩过：`tick()` 和 `poll()` 各写一种
  说法（"正在请求翻译…" / "后台正在翻译…" / "正在补译…"），轮询每 1.5~2.5 秒在
  它们之间来回切 → 一句话在三四种说法间闪（用户："下面的翻译提示一直在反复变化"）。
* **不可翻段落必须原样穿透，不许送模型、更不许因此判失败**：装饰分隔线
  （`――――――`）、纯符号、纯数字、颜文字都没有可翻文字，模型只会照抄回来，而
  「输出必须是中文」的校验会把照抄判成"抄回原文" → 重试 3 次 → **整章不落盘**。
  踩过：第 31 章末尾一条 18 字的 `――――――` 让整章白烧 ~4.7k tok 还失败。
  现在 `has_translatable()`（假名或汉字）判定，纯装饰段整段跳过（0 次请求），
  混合段按索引穿透原文、不计入「未译全」。护栏：`test_translate` G 段。
* **服务重启会把正在跑的任务标成 interrupted —— 所以要能自己接回来**：
  `_resume_interrupted_after_restart()` 只认「因重启中断」（error 含
  `服务重启或进程中断`）+ 书开着自动翻译 + 剩余 ≤10 章 + 上一条不是自动续跑的
  任务，然后按原剩余章节续跑一次。`LNTRANS_NO_AUTO_RESUME=1` 可关。
  踩过（2026-10-21）：我在第 30-31 章跑到第 5 秒时重启服务，启动 reconcile 把
  任务标成 interrupted，用户看到的就是「翻译又卡了」—— 其实是**我掐了任务**。
  这种"部署即失败"必须由系统兜住，不能靠记性。
  另外：自动续跑的**去重不能按"第一次见到的 slug"**（`records()` 顺序不是最新在前），
  要每本取 `created_at` 最新的一条 —— 否则静默返回 0，日志里什么都没有。
* **翻译调度只有一个决策点**（`lnsched.py`）：旧模型把策略写在阅读页 + worker 里
  （「读到 + N 章」），读者连读几章必然断粮 —— 用户原话「翻译跟不上我阅读的速度」。
  现在：**在读就一直翻**（`last_read_at` 在 `idle_minutes` 内，默认 30 分钟），
  上限模型整个删掉；另有**翻译列表**（`/queue`）可提前攒书；全局**每日 token 预算**
  （默认 30 万，仅提醒）和全局暂停。策略是纯函数，`test_sched` 覆盖，
  别再往 worker 里塞"翻什么"的判断。
* **废弃的 `translate.enabled` 不许再当闸门**：阅读页 tick 的 `/api/translate`
  不带 ceiling 时，worker 仍会走 `allowed_targets → auto_ceiling(enabled)`；
  enabled 已废弃 → 上限 0 → 建出一条 `done` 的"未开启翻译"任务，
  界面上就是"点了没反应/卡住"（2026-10-22 真实事故）。现在
  **任何入口不给 ceiling 就默认翻到全书**（`start_job` 兜底 + 阅读页传 total）。
* **预算是提醒，不是刹车**（`lnsched.over_budget`）：超预算时**不阻止**在读的书
  继续翻，只在阅读页/翻译列表显示"已用 X（超出预算）"。硬停只有两个：全局暂停、
  暂停本书。踩过两轮：把预算当硬闸 → 用户为继续读只能反复加预算，
  体感就是"读到一半又卡了"（用户当天把额度从 15 万一路加到 100 万）。
  预算 = 0 表示不限。
* **`/api/job` 不是"在读信号"**：任何客户端查状态（curl / 别的标签页 / 脚本）
  都会打这个接口；把它当在读会污染调度（踩过：查了 4 本书状态，
  调度器把它们全排上翻译）。真正的信号只有两个：打开阅读页、上报进度。
* **打开但没读的书（进度 0 且无读取记录）不自动开翻**：否则"点开看一眼"
  就会让调度器翻整本（一本 133 章 ≈ 45 万 token）。读起来（进度 ≥1 章）才开始。
* **`/api/transcfg` 是兼容壳**：`enabled` 现在只表示"没被暂停"，`ahead/max_chapters`
  接受但忽略。新代码只用 `paused`。旧前端/旧测试读它不该 500。
* **`note_read` 的高频路径不许写盘**：阅读页每 2.5 秒轮询一次，每次都 fsync 等于
  拿手机闪存当草稿纸。`note_reading(persist=False)` 只更新内存；打开页面 /
  上报进度才落盘。进程重启最多丢 30 秒"正在读"。
* **已读完 / 已弃文的书不再自动翻**：标了读完还继续译 = 替用户花钱（踩过）。
  `note_reading` 先查 `finished/dropped` 直接返回。
* **调度线程不许跑在自检服务里**：测试用 fixture 精确控制"哪一章被翻"，
  后台自动开翻会让断言变竞态（踩过：fill 测试撞上自动任务，拿到别人的 after）。
  `LNTRANS_TEST_SERVER` 一置位，dispatcher 直接返回。
* **句子级模型（Sakura 等）有自己的协议，不要塞进 #N 批量**：它们训练的是
  「将下面的日文文本翻译成中文：{原文}」→ 只输出译文，把多段拼成带编号的一坨
  会漏行（实测 7B：20 行漏 7 行、60 行漏 28 行），重试/二分烧光整章预算仍补不齐，
  该章永远不落盘、整本卡在一个章号上（GPU 一直转、进度不动）。
  现在 `LNTRANS_TRANSLATE_MODE=sakura` 走**单独一条路径**，而且**整章一块**送进去
  （用户明确要求：一段一段翻语义会断）。块大小按模型能力分两档、按实际端点取：
  本地 Sakura 2160 字（实测 3941 字 22/28 对白、3189 字 16/20、2389 字 10/10 →
  上限约 2400，取 90%）；DeepSeek 6000 字（实测 7.4k 字整块，60/60 对白、ratio 0.79、
  不截断）。超长章节在段落边界切块，块间把上文尾巴塞 system 续上下文；缓存按块存。
  实测：1578 字一章 = 1 次请求 / 2077 tok / 约 1 分钟；3620 字一章 = 4504 tok，**0 元**。译文里的空行结构由模型保留，写盘前把
  连续 3 个以上空行压成 2 个。
  失败块（回抄/非中文）留原文、本章照常写出并标「未译全」；`_first_missing_chapter`
  跳过 `progress.incomplete` 里的失败章，毒章不许堵整本。
  另外 `LNTRANS_SEG_LINES` / `LNTRANS_CHAPTER_TOK` 可调；批量模式别放宽「编号必须齐全」。
* **弃文 / 看完必须同时停调度**：只写书状态不够 —— 调度器还记着"在读"，
  `idle_minutes` 内会继续翻（踩过：14:04 标弃文，14:25 还在翻 51/54，钱一直花）。
  现在 `set_flag` 里同时 `SCHED.set_paused` + `cancel_job(disable=False)`；
  恢复要用户显式点「继续翻译」，不自动解除。
* **兜底切换不能等 socket 超时**：PC 关机时 TCP 连接会卡到我们给"生成"留的
  超时（600 秒），界面看着就是"卡住、不切"。`call_llm` 现在先做 2 秒 TCP 探测
  （`lnmodels.probe`），端口不通立刻判主端点失败、切 DeepSeek，并打一行
  `⚠ translate 主端点不可达（…），120 秒内改用 deepseek/deepseek-flash`。
  护栏：`test_routes` 熔断测试。
* **DeepSeek 的"思考"也算 completion**：整章翻译时 reasoning 能到 ~11k，
  `max_tokens` 给小了内容会被截断甚至只剩思考（空回复 → 反复重试、烧钱）。
  现在云端单次给 32000（`LNTRANS_DEEPSEEK_MAX_TOKENS`），本地模型仍用配置值。
* **自动续跑不能用废弃的 `translate.enabled` 当闸门**：v5.1 调度器根本不看它，
  用调度器翻的书 enabled 恒为 false → 重启后永远不续跑。现在看
  "没弃文/没看完/没被暂停"（`SCHED.is_paused`）。踩过：改完调度后一重启就停，
  日志里连「自动继续」都没有。
* **整章模式按 provider 选模板**：本地 Sakura 用它的固定 system+user；
  DeepSeek（含兜底）用通用整章格式（`build_chapter_prompt`，带术语/前情，
  要求保留段落空行、只输出译文）。同一套"一章一块"流程，两种模型都能跑。
  引号：块级精确对齐失败时退化为**纯字形映射**（原文「」而译文“”且两两配对
  就换字形），不改模型在哪加引号。护栏：`test_translate` I 段。
* **重启自愈与"暂停"要分清**：重启中断 → 自动续跑（有闸门）；用户点「停止」→
  `paused=True`，只有显式「继续」或手动翻译才解除（`note_read` **不许**顺手解除，
  否则读着读着"停止"就失效了）。
* **翻译「卡住」先看线程栈，别猜**。2026-10-21 的真实案例：界面一直显示
  「正在翻译」，其实章节**早就译完并写盘了**（边车 hash 与正文一致），只是任务记录
  停在 `running`。当时我按 `futex_wait` 推断「卡在锁上」——**错的**：worker 线程
  空闲等队列（`JOBS_Q.get` 也是 futex），真正原因见下一条。
  诊断工具：`py-spy`（`pip install py-spy`；容器里**必须加 `--nonblocking`**，
  否则报 "All threads failed to lock"）：
  ```bash
  py-spy dump --pid <lnserve pid> --nonblocking
  ```
  没有 py-spy 时：服务已注册 `SIGUSR1` → `kill -USR1 <pid>` 会把全部线程栈写进日志；
  另外心跳停 120 秒会自动 dump 一次（`job-watchdog` 线程）。
* **`_sync_job` 对 token 不匹配是静默返回 `{}` 的**（这是对的：旧任务不许覆盖新任务）。
  但它带来一个必须补的动作：**worker 收尾时要按 `job_id` 自己关掉记录**
  （`_close_own_record`），否则被取代/重试后的旧任务记录永远停在 `running`，
  界面就一直「进行中」直到 240 秒超时。护栏：`test_state` 里直接测这个原语
  （幂等、留下 completed/remaining）。
* **「记住这台电脑」不是会话**：浏览器登录原本只种内存会话，服务一重启就全没了 ——
  用户每次重启都要重新输一遍局域网口令（原话「太麻烦了」）。现在登录同时发一枚
  **长期设备凭据**（随机值，绝不是主口令；`data/devices.json` 里只有 sha256，
  默认 180 天、用一次续一次），`_gate` 在会话失效后认它；
  **「退出本设备」必须同时撤销这枚凭据**，否则"退出"是假动作（下次请求又被认回来）。
  文件损坏先另存 `.bak-<时间戳>` 再重建，不静默删；最多记 32 台，淘汰最久没用的。
  护栏：`test_devices`（发/验/过期/续期/上限/损坏/撤销、文件无明文）+
  `test_auth` C 段（清空内存会话后设备凭据仍 200、退出后 401）。
* **v5：数据根只有一份「当前代」，切代际只改指针**（`lndata.py`）：`LNTRANS_HOME`
  下 `<home>/generations/gen-*/`，`.lntrans-state.json` 是唯一指针；迁移先复制校验、
  再原子换指针，回滚就是把指针换回去 —— **不重命名/不移动数据目录**（踩过：分包迁移
  中途崩溃留下半棵树，而两个目录名一半新一半旧，事后无法判断哪边是完整的）。
* **同一份数据只许一个进程写**：`lnserve.py` 全程持 OS 排他锁（`fcntl.flock` /
  `msvcrt.locking` + 路径派生互斥量）；`lntrans.py` 的变更命令、`lnbackup.py export`、
  `restore --write` 共用同一把锁 —— **服务在跑时它们会被拒绝**，这是正确的行为，
  不许改成"锁忙就排队"。锁标记文件只用于诊断，**绝不许**用它判断进程是否活着。
  只读命令（`status`/`list`/`lessons`/`residue`/`verify`/干跑）不占锁。
* **章节边车先装、正文后换**（`chapters/NNNN.meta.json`）：记录原文/译文 hash、模型与
  prompt 版本、token/成本、未译全段落。顺序反过来就会在崩溃时把"半新半旧"当成品；
  读端遇到 hash 不匹配一律当不可用（可重译），v4 无边车章节照常读。
  确定性编辑（术语替换/校对/引号修复/润色）必须刷新边车的内容与配置 hash。
* **任务记录损坏 = 只读恢复，不是"模型坏了"**：`JobRecordCorrupt` / `JobRecordMissing`
  都属于 `RecoveryRequired`；书架、阅读、进度、备份继续，翻译写入回 503，坏文件挪进
  `data/jobs/quarantine/` 且**永不静默删除**。启动时遗留的 `running` 标 `interrupted`，
  重译要用户确认（花钱的事不许自动重放）。
* **相对路径/相对身份必须跨平台归一**：`record_backup()` 只留文件名，而 Windows 的
  `C:\dir\x.zip` 在 POSIX 上 `os.path.basename` 不切分 → 宿主机绝对路径进了状态文件
  （`test_data_safety` 当场红）。凡是"只存名字/相对路径"的地方，先
  `replace("\\", "/")` 再取 basename。
* **备份唯一有意义的形态是「离开容器」**（`lnbackup.py` + `/api/backup`）：
  译文/画像/书架**只有一份**，而容器会被重置 —— 写在同一棵树里的 zip 跟着一起没，
  所以服务端给的是浏览器下载（落到手机「下载」目录），命令行只是补充。
  三条不许破：① 每个文件带 sha256，**恢复前先校验**，坏一字节整包拒绝（宁可恢复
  不了，也不能把好数据覆盖成坏的）；② **恢复只增不删**，同名但内容不同先把本地
  那份挪成 `.bak-<时间戳>`，重复恢复必须幂等；③ 默认**干跑**，`--write` 才写盘。
  manifest 只写相对路径 —— 备份包换机器/换数据根要能直接用。新增任何"搬家/导出"
  功能都走这一套，别另写一个半成品。
* **「前情 · 人物」面板只用已读章节**（`lnserve.memory_panel`）：它把
  `summaries` / `characters` / `glossary` 搬到阅读页 —— 这三样本来只喂翻译 prompt，
  读者一个都看不见（"AI 资产全在机器侧"）。扫描范围**严格是第 1 章到当前章 -1**，
  后文才出场的人物/术语不许出现：剧透比"没有功能"更伤人。一项都凑不出来就返回空串，
  不渲染空壳面板。没有梗概时兜底显示上一章**结尾**（读者自己读过的内容），
  并明说"还没有提要句"，不许把结尾伪装成剧情摘要。
* **正文里只标中文译名**（`lnrender.annotate_terms`）：读者不读日文，标日文名等于
  标了个看不懂的东西；单字译名（「澪」这种人名）每章最多标 3 处（第一次看到知道是谁够了），
  全部标注每章上限 60 处（标太密干扰阅读）。
  点击气泡在 `reader.js`，`#gtip` **只许它创建**（`test_js_static.py` 扫全部脚本守着）。
  标注和点击两半缺一不可：只有标注 = 点了没反应，只有 JS = 永远没有可点的东西。
* **`__NEXTHAVE__`（链接可点）≠ `__NEXTTRANS__`（已有译文）**：预翻必须看后者。
  踩过：只看前者 → 它恒真 → 预翻永不触发 → 读者每翻一章都要干等 30~45 秒
  （用户："感觉翻译速度变慢了"）。落地章有译文就**立刻预翻下一章**，别等滚到底。
* 阅读页的**落地章**没译文时，不许偷偷跳到后面第一个有译文的章：渲染 `#need-N`
  占位块 + `window.__NEED__`，译好后前端用 `/api/chapter` **就地替换**（不许让用户
  手动刷新）。`/api/next` 遇到空洞也**不跳过**，返回 `need=N` 让前端等这一章。
  章末导航（`.chapnav`）同理：**缺译章的那一页不许给「下一章」链接** —— 那会落到
  又一个占位页，而那页的 `tick()` 用 `after=need+1` 排翻译 → 正在等的那一章被跳过、
  可能永久缺译。下一章真有译文才给链接（那是正当的"绕开空洞"出口）。
  翻译 worker 算 targets 之前先 `ensure_zh_titles()` 把书名/章节名翻成中文，
  否则目录和章节大标题永远是日文（用户要求「显示汉化章节，我点进去来看」）。

## 性能与并发（都是实测出来才写的）

* **卡片渲染路径不许"每张卡扫一遍全表"**：`work_head()` / `work_status_chips()`
  每张卡都要"这本的中文名/我在不在读"，如果那里 `listdir` + 逐个读 `meta.json`，
  一个书架页就是 372 × N 次文件读。踩过：首页 **5.0 秒**。现在走
  `_slug_index()`（source_id → slug 反查表，按 novels 目录 mtime 缓存）+
  `novel_meta()` 的 (mtime,size) 缓存，同一个页面 **0.5 秒**。
  新增"按源站 id 找本地书"的代码，一律用 `_slug_index()`。
* **打开阅读页的更新检查必须限时**（`check_on_open_bounded`，默认 1 秒）：
  实测一次源站查询 3.1 秒，同步等就是"页面卡住/要刷新"。超时就丢给后台线程，
  结果下次打开可见。
* worker 里所有可能调 LLM/抓站的步骤都要 `except (Exception, SystemExit)`：
  `lt.die()` 走的是 `sys.exit()`，只 `except Exception` 接不住 —— 踩过：缺 key 时
  worker 线程直接死掉，之后所有翻译任务永远卡在 running。
* 后台任务用 `JOBS[slug]["token"]` 认"我还是当前任务吗"：心跳超时判死后用户重试
  会建新任务，旧任务必须自己停手，否则两遍重复翻译同一章（重复花钱）。
* `/api/job` **不许**刷新心跳：心跳要反映 worker 真实存活，前端每 2.5 秒轮询一次，
  轮询也刷心跳的话"卡死兜底"永远不触发。
* **写书状态一律经 `update_book(slug, fn)`（`LOCK` 内"读-改-写"）**，不许"先 `_read_book`
  取快照、隔一段再 `_write_book` 整体回写" —— 中间只要有耗时操作（抓站 / LLM），并发写的
  `tracking`/`favorites`/`progress` 会被旧快照**静默覆盖**。踩过：`check_updates` 在
  `fetch_work`（实测 3.1s）**之前**取快照、抓完整对象回写 → 后台 `chk-<slug>` 线程把用户
  刚点的「弃文/收藏」冲回旧值（`test_ui` 曾因此整套偶发红 1/5~1/6）。慢操作放锁外，只把
  **字段合并**塞进 `fn`。
* **"这本译了几章"只许扫一次目录，不许逐章 `os.stat`**：`zh_chapters` /
  `has_complete_zh` 走 `lncontracts.dir_sigs()`（一次 scandir，Windows 上
  mtime/size 直接来自目录项）。30 本 × 200 章的首页实测 **320ms → 62ms**
  （`/api/library` 310ms → 40ms，`/api/next` 30ms → 2.3ms）。未译章是常态，
  逐章 stat 还会为不存在的文件发 2 次失败 syscall。
* **文件签名缓存必须配"写端显式失效"，且签名要带 inode**：`file_sha256` /
  `_ZH_CHAPTER_CACHE` / `_ZH_COMPLETE_CACHE` / `_META_CACHE` 都靠
  (mtime, size) 判断变化，而 exFAT / sdcardfs 的 mtime 只有 **2 秒**粒度、
  内容长度又可能不变（引号对齐、错字修正）—— 刚写完的章节可能与旧版本签名
  完全相同。两层防线：① 签名带 inode（`dir_sigs` 返回
  `(mtime_ns, size, inode)`；`save_text`/`save_json` 用临时文件 + `os.replace`，
  原子替换一定换 inode，所以**跨进程**（命令行维护脚本 → 服务进程）也能失效）；
  ② 写端显式失效：`save_text`/`save_json` 落盘后调
  `lncontracts.invalidate_file_hash(path)`；worker 每译完一章调
  `invalidate_cache(slug, i)` 并 `_META_CACHE.pop(slug)`。
  **Windows 坑**：`os.scandir` 的 `DirEntry.stat().st_ino` 恒为 **0**，必须用
  `DirEntry.inode()` 才拿得到文件索引（零额外 syscall）；`os.stat()` 的
  `st_ino` 正常。不提供 inode 的文件系统退回 0，行为同只有 (mtime, size)。
  护栏 `test_jobs` 1b（哈希层）、`test_zh_cache`（目录签名层：等长替换 +
  mtime 回拨后必须重算该章）。
* **`novel.md` 是导出汇总，不是阅读路径**：阅读页只读 `chapters/NNNN.txt`。
  `rebuild_novel_md` 每译完一章都会调用，所以它必须增量 —— 按章缓存
  (签名, 可读, 正文)，只有变过的章才重新校验/重读；刚写的章用
  `override_chapter/override_text` 传内存正文（不依赖低精度 mtime）。
  维护脚本（align_quotes / repair_dialogue / lnreview / polish）传
  `force=True`，宁可重读也不要复用进程内旧正文。200 章实测 6.4ms/次
  （旧实现 60~110ms/次，且每次读全书 = O(章数²)）。
* **任务记录只持久化"恢复需要的字段"**：`_VOLATILE_JOB_FIELDS`
  （`message`/`done`/`translated`/`total`/`targets`）只留在内存。段级进度回调
  原本每段一次 `atomic_write_json`（带 fsync，手机闪存几十毫秒），现在完全不写盘；
  重启后需要的是章节级 `completed_chapters`，段进度没有恢复价值。
  护栏 `test_jobs` 4c 段（mtime 不变 + 内存 message 已更新）。
* **单条任务记录损坏 = 恢复，不是模型错误**：`JobRecordCorrupt(RecoveryRequired)`
  由 `JobStore.get()` 抛出；worker 把它映射成 `interrupted` + 只读恢复，
  **不许**变成 `provider_error`（那会告诉用户"翻译失败/模型坏了"）。
  同类还有**活跃记录被外部删除**（手工删 / 恢复备份漏掉）：`update()` 抛
  `JobRecordMissing`（也是 `RecoveryRequired` 子类），但**不**锁整站、**不**写
  `trans_error`——只停这一本书并说清「记录丢失，可重新开始」。否则卡片会亮
  「翻译失败」徽标、或整站翻译永久锁死。护栏 `test_jobs` 4d 段。
  4d 里必须**真的**先建一条同书旧 `done` 记录再断言 `job_view.job_id` 仍指向刚丢失
  的活跃记录——只断言 `status=interrupted` 是空转（没有旧记录可回退），会漏掉
  「`latest(slug)` 把旧 done 翻出来覆盖视图」这一回归。

## 工作方式

* 用户要求**每次改动都做三方自检**：用户角度（他真的会用到吗）、工程师角度
  （真的验证过吗、隔离了吗）、设计师角度（看得见吗、位置对吗、会不会被埋没）。
* 用户喜欢**自主执行**：能自己做决定的就做完再报告，别每步问。
* 报 bug 时按"根因"修，不只修表面；顺手记进对话，别让它复发。
