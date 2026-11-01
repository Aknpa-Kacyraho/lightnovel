# PART B-3：经验、踩坑与自查清单

> 翻译核心见 `translate.md`，网站实现见 `lnserve.md`。

---

### 搜索与查文档（别盲人摸象）

需求原话：「你可以上网搜索别人的项目，搜索怎么做一个自己的轻小说网站，
搜索你不懂的语法，你都可以搜，而不是自己盲人摸象，这样效率太低。」

已验证可用的路子：

* GitHub API 通：`api.github.com`（repo/tree/search 都可，**code search 要鉴权**）
* MDN 可抓：`developer.mozilla.org`（查 HTML/CSS/JS 规范语义，
  例如 `disabled` 不触发 click 的行为）
* **能搜就搜**：一次搜索 ≈ 一次模型调用，慢但能搜到中文项目。
  如果搜索能力不可用，按通用凭据约定配：key 读环境变量 `DEEPSEEK_API_KEY`，
  其次读一个**可配置的凭据文件路径**；bundle 默认只找 `DEEPSEEK_API_KEY`，
  名字对不上会报"缺失"。**改完要重启宿主**才会生效。
* 搜索引擎**不稳**：Mojeek 偶发超时，DuckDuckGo/Startpage 不通。
* **自检必须隔离真实数据**：`lnserve`/`lntrans` 支持 `LNTRANS_DATA_ROOT`
  环境变量重定向数据根；`run_selftests.py` 会自动建临时根传给每个测试。
  踩过：自检直接写 `novels/`、`data/`，把真实 `favorites` 改成了 False。
* **参考对象**：`auto-novel/auto-novel`（同项目本体，`packages/crawler` 与
  `packages/translator` 最值得读）。注意 Legado 等仓库可能已下架源码。
* **读大仓库的正确姿势**：先
  `api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1` 列全部文件，
  **grep 路径**定位模型/枚举文件，再用 `raw.githubusercontent.com` 取单文件。
  Kavita 的树有 4500+ 文件、1.2MB JSON，直接猜路径会浪费很多次请求。
  （注意：大响应**可能被截断**，JSON 解析失败就重试，别以为格式错。）

**别抄别人的状态枚举**——业界共识（Goodreads/Open Library 三分法 + 弃文）够用，
真正缺的是**把状态机穷举清楚**，那靠自己列表格，不靠搜索。

### 踩坑清单（可复用的教训）

每条都是真踩过的：踩了什么 / 为什么 / 怎么避免。

**分页与性能**

* `library()` 逐章 `has_zh()` → 100 本 × 200 章 = 上万次 `posix.stat`，冷启动数秒（cProfile 实测 3.5 秒就是它）。**逐章 stat 是性能杀手**：数已译章必须走带 mtime 缓存的 `zh_chapters()`。
* 再把已译章号 + 目录 mtime 持久化到每本书的 `have` / `have_dir_mtime`（`note_translated()` 登记），只在目录 mtime 变了才重扫：冷启动 3548ms → 726ms。
* 分页：`PAGE_SIZE = 15`，书架**每个堆单独分页**（`SHELF_PAGE`），书库独立分页（`LIB_PAGE`），只渲染当前页 —— 首页响应 51ms。

**HTTP 查询参数**

* **路由分发条件漏参数**：`if "q" in q or "want" in q:` 会把只带 `?page=N` 的请求分到书架分支 → 页码从未保存，点"下一页"完全没反应。加参数时回头检查分发条件。
* **`parse_qs` 默认丢弃空值**：`parse_qs("q=&page=1")` 里 `q` 直接消失 → `?q=`（清空搜索）传不进来，**读者搜过一次就再也回不到全部列表**。用 `keep_blank_values=True`。
* 这类 bug **只在"某个参数单独出现"时暴露**，测试要覆盖参数组合与单独两种路径。

**测试写法**

* **不要写死数量**：断言"共 107 项 / 8 页"，而视图当时正在搜索过滤状态 → 5 项全红，**是测试错不是产品错**。期望值从 API 动态推导。
* **不要从自己构造的输入反推产品有 bug**：把关键词里的小写假名 `ぁ` 打成 `あ`，就断定是 latin-1 解码问题并加了"修复"；写了对照实验（真实 ThreadingHTTPServer + 三种解码）才发现都正确。加修复前先做**能证伪**的实验（去掉修复，看行为是否真的不同）。
* **别写恒真断言**（`naive != X or True` 永远通过 = 没测）。
* **别用名字/形状去猜网络事实**：判断「哪张网卡是热点」时按网卡名和「网关以 .1 结尾」
  猜，在真机上全错。改成实测 `:53` 上有没有 tethering 的 DNS 代理，才对。
  **能探测的就去探测，别猜。**
* **干净副本必须能跑绿**：`run_selftests.py` 要给"没有真实数据的干净拷贝"也准备好
  合成书库/合成画像（有真实数据时才用真实数据的只读副本）。否则接收方第一次跑自检
  因为"书库只有 3 本"而全红，会以为自己装错了 —— 而"跳过这些断言"是假绿，也不行。
* **断言"永远跳过" = 假绿**：`test_detail.py` 里"共用 head 输出中文标题 + 日文副标题"
  这条断言依赖"卡片有中文书名"，而中文书名来自 `data/details/<源站id>.json`
  （**不是** meta.json 的 `zh_titles`）。fixture 没给这本种详情 → `work_head` 走
  "未翻译"分支 → 断言要么永远 skip（本进程数据根是空的，`novel_meta` 永远 None），
  要么真跑起来就红。修法：① 测试进程用 `LNTRANS_SERVER_ROOT` 指向服务的数据根；
  ② 种种子作品时连详情缓存一起种。**每条断言都要确认它真的执行了**。
* **长函数里别用 `_t`/`_i` 这种极短名当循环变量**：`run_selftests.py` 顶部有
  `import time as _t`，中间一个 `_t = list(...)` 就把它覆盖成 list，
  跑到后面 `_t.sleep(0.25)` 直接 `AttributeError`（而且只在"需合成书库"的分支才触发，
  真实环境跑不出来的那种坑）。变量加前缀（`_syn_t`）就不会撞。

**卡片渲染**

* 推荐卡与书库卡曾是两处独立渲染，改一处漏一处（读者报"点了没用"时只修了一半）。现在统一走 `work_head(it, det)`（中文标题 + 日文小字 + 简介摘要）和 `work_status_chips(it)`（徽标 + 已译/读到第几章）；**加第三种卡片也必须调它们**，改完用 `grep -c 'onclick'` 数一遍每种卡片类型。
* 详情页每个新 class 都要有 CSS（`test_detail.py` C 段查 `.chip/.syn/.toc/.lnkbtn/.back`），不能只有 HTML 没样式。
* **"数某类元素"的测试必须先切到它所在的面板再数**：给推荐卡加了 `data-lib` 后，数 `data-lib=` 的分页测试立刻误报。

**列表页/详情页直出中文**

* 详情页标题层级：`<h1>` = **中文标题**，`.jp-sub` = 日文原名（`.66em` + `opacity:.55`），简介默认中文、日文原文收进 `<details>`；未翻时给「译成中文」按钮 + `.hint`「标题和简介很短，翻译几乎不花 token」降低顾虑。
* 列表卡片结构：中文标题（1.02em 粗体，2 行截断）→ 日文原名（`.jp-sub`，0.68em + 50% 透明）→ 中文简介（截 80 字）→ 标签 · 命中理由 · ＋加入书架。
* `batch_translate_missing()` 把没翻的推荐排进后台队列，`translate_one()` **一次请求同时翻标题+简介**（省一半调用），结果进 `data/details/<id>.json` **永久缓存**，前端轮询到 `pending==0` 再刷新。
* **并发必须加锁**（`DETAIL_LOCK`）：两个线程各自读旧文件、各自写回，后写的覆盖先写的。症状极具误导性：**单独测能翻出来，批量跑总有一本永远"未翻译"**。
* **必须区分"翻译中 / 译不出 / 未翻译"**：造词书名（如 `〈造词书名示例〉`）模型会拒绝翻译、原样返回，要标 `zh_title_failed` 并显示「书名是造词，模型译不出（保留原名）」，否则批量队列永不收敛、白花 token；简介同理 `zh_syn_failed`。
* 标题译后要**校验**（不能与日文相同、不能像一段解释/长度上限），简介必须过 `detect_chinese()`，再用 `_clean_line` 清掉模型爱加的书名号/引号/「译文：」前缀。
* LLM 调用**必须放后台线程**（`start_translation` + `TR_JOBS`），前端轮询 `/api/trstate` —— 绝不能让慢 LLM 卡住页面响应。
* **加路由要看清 HTTP 方法**：路由加到 `do_GET` 而前端用 POST → 一直返回 `{"ok":false,"error":"unknown"}`（catch-all 兜底）。

**作品详情页**

* 必须回答五个问题：简介 / 标签分类 / 话数字数积分状态 / 进度+目录 / 下一步动作。
* 数据取本地 meta ∪ 推荐缓存 ∪ 书库缓存，简介与目录**按需抓取**再缓存到 `data/details/<id>.json`：简介在 `og:description`，目录在 `__NEXT_DATA__` 的 Apollo（`Chapter` + `TableOfContentsChapter.episodeUnions` + `Episode`）。
* **标签 chip 必须能点**（链到 `/tags?q=`），否则标签只是装饰，而"按标签找同类书"是发现路径的核心。
* **形参名别用模块名**：`def page(html)` 遮蔽了 `import html` → `html.unescape` 报错。

**"接着读"与数字一致**

* `recent_banner()` 取最近有 progress 的书，直接给 `/read/<slug>?from=<上次章+1>`（**下一章**而不是章首）。
* **数量必须与实际渲染同源**：页签 `📚 书架 N`、标题 `N 本` 曾用 `len(items)`（含已移出书架的）而不是 `shelved`；推荐位写"缓存总量"却只渲染 6 张。要显示数量，就用与实际渲染相同的那个变量。
* 统计文案要准：`history.jsonl` 是"每半小时一条"的阅读日志，它是**阅读次数**不是**章数**（写「今天读的章」就是骗人）。

**自检隔离**

* **任何读写 `data/` 的新模块，加载时必须** `_ROOT = os.environ.get("LNTRANS_DATA_ROOT") or HERE`。漏掉 `lnrecs` 时，隔离测试把假推荐数据写进了真实 `data/recs.json`。
* **每个测试一个数据根**（`run_selftests.py` 各自 `mkdtemp`）：共用临时根时跑着的服务也在写文件 → `test_state` 偶发失败。信号是**单独跑通、成组跑挂** → 先怀疑共享状态/竞态。
* 跑完对比真实数据指纹（tracking/favorites/progress + 文件 md5+size），确认一个字节没变 —— 这类问题使用者不会主动报，但后果很重。
* **清理代码自己也会静默失败**：`ignore_errors=True` + 变量被覆盖 → 没清掉却照样打印"已清理"。目录路径用独立变量，并 `assert not os.path.exists(...)`。
* **泄漏断言要按命名规则识别自检产物**（`__*` / `book0*`）：只比"跑前跑后差异"，会把跑前就存在的残留当合法基线，抓不到泄漏。

**书架语义**

* **必须有「不在书架上」这个表达**：`on_shelf = bool(favorites) or tracking in TRACKING`，分组**先按 `on_shelf` 过滤**再分堆。
* 「移出书架」= `action=off` → **清空 tracking + favorites**（不是退回 `want`；`want` 也是一个分组，退回就永远删不掉）。译文目录**保留**，随时能加回来（不做单向删除）。
* **不要写"把漏掉的书兜回某个分组"的兜底** —— 那会掩盖分类 bug（兜底只用来收集/暴露漏掉的）。
* 旧数据迁移（有进度但无书架标记 → 标为在读）**必须只跑一次**（写 `.shelf-migrated`），否则主动移出的书会被反复自动加回书架。

**CSS / UI**

* 三类"重叠 / 不消失"其实都是 CSS 缺东西：`.toast{position:absolute;bottom:12px}` 无背景且正好压住 `.ctrls`（改 top/right + 实底胶囊 + `pointer-events:none`）；`flash()` 只设 `opacity=1` 没定时器（加 `setTimeout`）；`.ctrls{display:flex}` 缺 `flex-wrap`（7 个按钮挤一行）；`#theme` 完全没有 CSS（用浏览器默认样式浮在卡片上）。
* 检查 CSS 要用**解析属性**的方式，不能 `"bottom:" in css` —— 注释里的 `bottom:12px` 会误报。
* **短标题别用 flex 容器**：`summary` 上用 flex 把「★ 收藏」拆成两行，用行内元素 + 箭头 span。
* **别用 `disabled` 长时间锁按钮**（disabled 的按钮不触发 click）；状态按钮点完整页刷新会闪 → 先给即时反馈（按钮态 + toast）再延迟刷新。

**自己造坑（都很贵）**

* **模块加载时改 `sys.argv` 会让命令行参数全部失效**：为加载子模块写了 `sys.argv = ["lntrans"]`，`main()` 的 argparse 读到**假 argv**，`--port` 被静默忽略（服务"能起"但绑默认端口，误导性极强）。修法：先 `_REAL_ARGV = list(sys.argv)`，`main()` 用 `ap.parse_args(_REAL_ARGV[1:])`；**存 argv 那行必须在任何赋值之前**。
* **测试服务别用固定端口**：固定 8199 被残留进程占用 → 健康检查通过却连到空实例 → 报"书架为空"。用 `bind(0)` 让系统分配，并给测试服务**自己的数据根 + 种子数据**。
* **自检绝不能写真实数据**（最严重的一次：把真实 `favorites` 改成了 `False`）。两层修法：模块跟随 `LNTRANS_DATA_ROOT`；`run_selftests.py` 建临时根，并为 HTTP 测试**另起隔离服务**。
* **补丁脚本必须有原子性**：所有替换先在内存完成并逐条校验，**全部成功后才一次性写盘**，失败就报出是哪一条、多少处匹配。落地确认用 `grep -c`，比读脚本输出可靠。

**onclick 引号（最贵的一个）**

* `onclick` 里用单引号拼 HTML 属性 → 属性被提前结束 → DOM 被重解析 → **按钮脱离 `.card` 容器** → `b.closest('.card')` 返回 `null` → 点击无任何反应且**不报错**。正确写法：`onclick="...location.href=&quot;/read/x?from=3&quot;"`，并用 `attrescape()`。
* 排查手法值得复用：**在前端点击处理里 `POST /api/log` 上报诊断**，服务端就能看到浏览器里真实发生了什么（当时一行日志就定位了：`click act=finished card=false slug=-`）。
* 页面上"看起来正常"不代表 DOM 正确 —— 用**真正的 HTML 解析器断言嵌套关系**，并且**先拿坏样本验证断言会失败**。
* 判断元素可点性时，**不在视口内的元素会显示「区域高度 0 / 找不到可点击」**，那是假象：先滚动到可见再判断。

**并发 / 崩溃兜底**

* 反馈读改写无锁 → 并发丢反馈，统一走 `update_book()`（锁内读改写）。
* worker 崩了任务永远 `running` → 前端无限轮询；用心跳 + `JOB_STALE_SEC` 兜底标 `error`，前端给「重试」。
* 用 AST 扫一遍未使用的模块级名，清死常量。

**设计层面（三个已经抓到的真问题）**

* 「收藏」不该被「看完」覆盖（收藏夹会随读完变空）：**收藏是独立维度**，永远查更新、永远可用于学口味。
* 把"30 天没打开"自动判成放弃是错的：**搁置 ≠ 放弃**，只标注不挪走。
* 卡片显示源站总章数对不上读者关心的东西：他关心**可读**多少 → 显示「可读 16/61 章」。

**阅读页 UI / 数据入口（2026-10-18 本轮修复）**

* **输入框绝不能嵌在 `<button>` 里**：点输入框会冒泡成按钮点击，直接按默认值开翻，
  页面随即 reload，用户根本没机会输入。正确结构是「输入框 + 独立确认按钮」并列；
  回归测试用 HTMLParser 断言 `#btn-ceil` 内没有 `input`。
* **两个 fixed 悬浮按钮不要各自写 `bottom`**：反馈圆钮 78px、主题胶囊 60px 在阅读页
  重叠了 16px。收进同一个纵向 `#floatdock`，用 `flex-direction:column` + `gap` 排队；
  底部加 `env(safe-area-inset-bottom)`，并给内容留够 padding。
* **窄屏 `chapnav` 必须 `flex-wrap:wrap`**：320px 下「上一章 / 目录 / 下一章」撑出
  20px 横向滚动；390px 看不出来，别只用一种视口验收。
* **`/api/feedback` 与 `/api/progress` 必须先 `novel_meta(slug)` 校验**：
  空 slug 会生成 `data/books/.json`，伪造 slug 会生成对应垃圾状态文件。
* **主题选择用 `localStorage('ln-theme')` 记住**：只改 `data-t` 的话刷新/换页就丢。
  初始化脚本先读存储，再退回 `prefers-color-scheme`；点击时写回。
* **非阅读页的主题按钮不要 fixed 右下角**：它会一直压住卡片/简介的正文。
  放进正文顶部 `.pagebar`（随内容滚动）后，读者滚走就看不到它；阅读页仍留在
  `#floatdock` 里和反馈钮排队。
* **长目录默认折叠**：130 话全展开会把手机详情页撑到一万像素；≤20 话仍默认展开。
  详情页的「相似作品」仍放在目录之前，别把发现路径埋到目录后面。
* **空书架不要摆一排无效控件**：0 本时隐藏搜索、筛选和「全部查更新」，
  只给一条明确的下一步（去推荐/书库加一本）。「怎么用」也改成可展开。
* **文案要跟真实点击路径一致**：书库/推荐卡点开是详情，加入书架后书架卡才直接进阅读页；
  不能笼统写「点书进阅读页」。
* **书库标签 facet 不能平铺几十个**：40 个标签会把手机首屏直接铺满，书卡要滚很久才出现。
  只取前 20 个、放进单行 `overflow-x:auto` 横向滚动条；当前选中的标签排第一，
  刷新后不用横向找。数字仍用真实频次。
* **连续阅读的键盘/手势翻章要用「视口顶部那一章」**：IntersectionObserver 的观察带
  在屏幕中部，短章节下会把下一章判成当前章，快速连按两次方向键会原地打转。
  另用 `navCh` + scroll 监听对齐视口顶部；页面滚到底时把最后一章认成当前章，
  否则最后一章永远滚不到顶部，右键会卡住。
* **触屏翻章必须避开交互控件**：在反馈 textarea、主题/反馈按钮、输入框上横向滑动
  不能触发翻章；`touchstart` 先检查 `target.closest('textarea, input, button, #fbpanel, #floatdock')`。
* **测试解析 HTML 前先剥掉 `<style>/<script>`**：CSS 注释里写一个 `<button>` 字样，
  按全文正则找按钮的测试就会把后面的真按钮吞掉，表现为「收藏样本消失」的假故障。

**阅读体验三连（2026-10-19）**

* 点「下一章」后停在页面顶部（标题 + 一屏目录）＝ 读者还得自己往下翻：翻章链接要带
  `#c<N>` 锚点，目录默认折叠。
* 底部状态条被 `tick()`/`poll()` 各写一套文案、来回切换 → 看起来"一直在变"：
  只留一套模板（只有章号变），进度单独一槽。
* 一页只渲染一章之后，"滚到底才翻译"会变成每章干等 30~45 秒：进页面就预翻下一章。
  判据要用 `__NEXTTRANS__`（有译文），不能用 `__NEXTHAVE__`（链接可点，恒真）。

**v4.2 补充（2026-10-19）**

* **进度条的 `done` 和 `translated` 不是一个东西**：`done` 是本次任务翻了几章，
  `translated` 是全书累计。补译第 50 章时 `done` 会从 1 开始，前端若拿它画进度，
  就会从「已译 50/100」倒退成「1/100」。轮询期间用 `translated`，并在 worker
  每译完一章就更新它。
* **`<details>` 目录折叠后，`href="#tocbox"` 只滚动不会自动展开**：
  「↑ 目录」要显式 `tocbox.open=true`；目录/翻章链接统一带 `#c<N>`，
  否则点目录又回到页面顶部。
* **测试 fixture 的 source_id 不能撞车**：`__lookahead_seed__` 和
  `__shelfless_seed__` 共用同一个源站 id 时，`/api/add` 会按 id 选错目录，
  表现为「加入书架」假失败。fixture 也要遵守一本作品一个 source_id。

**v4.3 界面收敛（2026-10-19）**

* 阅读页首屏不是控制台：标题、进度、一个「继续翻译」加两个折叠入口就够了。
  自动翻译、翻到第 N 章、显示日文、校对都放进 `<details>`，不要把正文挤到第二屏。
* 首页卡片的「命中」经常只是标签的重复拷贝；只有存在标签外的新理由时才显示。
  简介限制两行、日文副标题单行省略，卡片高度会明显下降。
* 网格里放 `white-space:nowrap` 的子元素必须同时给 `minmax(0,1fr)` / `min-width:0`，
  否则窄屏会被长日文标题撑出横向滚动（本次在 390px 实测发现）。
* 详情页的规则解释（书架≠收藏）默认收起；继续阅读是主按钮，移出用弱化危险色。

**v4.5 维护与停止（2026-10-20）**

* 新装包没有 `lntrans/novels/` 是正常的：维护脚本（`align_quotes.py`、
  `repair_dialogue.py`）必须先判断目录是否存在，不能直接 `os.listdir()`。
* `repair_dialogue.py --write` 也要像引号脚本一样查 8099 的运行任务，
  否则会和 worker 同时写章节；正在翻的书跳过，稍后再跑。
* 阅读页的「停止」不是只停轮询：服务端要把任务标成 cancelled 并关闭自动翻译；
  之后「继续翻译」/「继续」必须重新轮询，不能因为自动翻译开关是关的就静默不动。

**加书失败（2026-10-18）**

* `slugify()` 只留 ASCII → 日文标题可能缩成 `ts` 这种两字母短名，**不同作品撞同名**。
  `cmd_init` 以前按"目录存在"就 `return`，调用方以为成功 → 用户点「加入书架」永远
  加不进来。现在撞车改 `kakuyomu-<源站id>`。
* 接口的 `ok:true` 必须是**验证过的结果**：`/api/add` 要确认"本地有这个 source_id"且
  "状态文件里真的在书架上"，不能只看被调函数没抛异常。

**翻译质量 / 角色声音（2026-10-18）**

* 角色卡只存一句 `desc` 不够：至少要有 `voice`（语气）、`lexicon`（词汇习惯）、
  `syntax`（句法习惯）、`volume`（本卷时间点）；昵称/称号用 `aliases`，
  否则正文出现别名时角色卡不会注入。
* 系统 prompt 必须明确写：短句/对话驱动、叙述者吐槽滤镜、角色×对象的语气差异、
  术语锁定、文化词不过度本地化、双关功能对等、拟声动作化、保留段落节奏、
  不过度润色加戏。只写「忠实、像中文小说」模型会退回统一书面腔。
* 用户提供的完整准则用 `learn --guide <file>` 存进 `style.guide`；prompt 注入前
  3000 字。媒介用 `--medium web|ebook|paper`，加注策略随之切换。
* 术语变更必须记录旧值→新值（`cmd_learn`/`cmd_fix` 写进 `history.jsonl`）；
  不要静默覆盖，否则系列翻译无法追溯。

**校对 / 多书隔离（2026-10-19）**

* **同一本书的翻译和校对必须共用同一把锁**。`lnserve` 用 `importlib` 加载
  `lntrans` 后要 `sys.modules.setdefault("lntrans", lt)`；否则 `lnreview` 里
  `import lntrans` 会再加载一份模块，两份 `_NOVEL_LOCKS` 互不相识。
* **报告/观察池/经验必须写在 `novels/<slug>/qa/`**，不能放全局目录。观察池
  重复追加会让同一条建议刷到阈值，必须按 `(chapter,type,para,evidence)` 去重。
* **原文变了，段缓存必须失效**：缓存 key 只有 `a-b` 段范围，不校验原文 SHA
  会把旧原文的译文套到新原文上。缓存里存 `_raw_sha256`，不一致就清空重译。
* **AI 校对只报告，不自动改**：`--fix` 默认只替换术语表里可验证的旧译名；
  `--fix-ai` 才让模型改阻断段，并且必须备份、校验段数/中文/术语，失败回退。
* **没有原文依据的“疑似”不能升级为阻断**：LLM JSON 里 `severity=blocker`
  但 `evidence` 为空时降为 observation，防止模型自报置信度乱杀。
* **经验只注入本书最近 8 条**，存 `meta.lessons` + `qa/lessons.md`；
  不要写全局人物卡或全局术语表，否则多书一定串味。

**局域网访问安全（2026-10-21）**

* **访问口令不能放 URL**：`?token=` 会进入浏览器历史、代理日志、截图和 Referrer。
  正确做法是表单 `POST /login`，成功后只发随机、过期的 HttpOnly 会话 Cookie；
  主口令不落到浏览器 Cookie 里。
* **会话启动时创建、重启后清空，所以另发「记住设备」凭据**：只发内存会话时，
  服务一重启用户就得重新输口令（用户原话「太麻烦了」）。现在登录同时发一枚
  长期随机凭据（`data/devices.json` 只存 sha256，默认 180 天、用一次续一次），
  `_gate` 在会话失效后认它；**「退出本设备」必须同时撤销它**，否则退出是假动作。
  换主口令不会自动让设备失效 —— 要全忘掉就删该文件或撤销记录。
* **写请求必须同时看同源与 SameSite**：`Origin` 和 `Sec-Fetch-Site` 拦截跨站表单；
  Cookie 用 `SameSite=Lax; HttpOnly`。非浏览器 API 客户端继续支持 Bearer。
* **Host 校验不是可选项**：只校验口令挡不住 DNS rebinding。允许回环、当前局域网 IP、
  本机名；Tailscale/反代域名必须显式写进 `LNTRANS_ALLOWED_HOSTS`，不要放通配符。
* **安全头要覆盖所有响应路径**：普通 HTML、JSON、登录页、下载、封面和 304 都要带
  CSP、`X-Frame-Options: DENY`、`X-Content-Type-Options: nosniff` 与
  `Referrer-Policy: no-referrer`。只给首页加等于没加。
* **限速只打会花钱/易爆破的动作**：登录失败按失败次数计数；翻译启动按“没有活跃任务
  的启动”计数，正常 `/api/job` 轮询不能被限速误伤。
* **Windows 启动日志不能假定 UTF-8**：普通 `python lnserve.py` 可能走 cp936/GBK；
  启动文案里的 emoji 会抛 `UnicodeEncodeError`，服务在进入监听前退出。启动时给
  stdout/stderr 设 `errors="replace"`，启动关键提示也优先用普通中文。

**性能与数据一致性（2026-10-21）**

* **"这本译了几章"只扫一次目录**：`zh_chapters`/`has_complete_zh` 走
  `lncontracts.dir_sigs()`（一次 scandir），不要逐章 `os.stat`。未译章是常态，
  逐章 stat 还会对不存在的 zh/sidecar 发失败 syscall。实测 30 本 × 200 章：
  首页 320ms → 62ms、`/api/library` 310ms → 40ms。
* **签名缓存必须配"写端显式失效"，且签名要带 inode**：`file_sha256` 与章节
  可读性/`meta.json` 缓存都靠 (mtime, size) 判断，而 **exFAT / sdcardfs 的
  mtime 只有 2 秒粒度**、内容长度又可能不变（引号对齐、错字修正）—— 刚写完的
  文件可能与旧版本签名完全相同，跨进程（命令行 → 服务）就会一直命中旧结论。
  两层防线：① `dir_sigs` 返回 `(mtime_ns, size, inode)`；`save_text`/`save_json`
  用临时文件 + `os.replace`，原子替换一定换 inode；② 落盘后调
  `invalidate_file_hash(path)`，worker 每章调 `invalidate_cache(slug, i)` 并
  `_META_CACHE.pop(slug)`。**Windows 上 `DirEntry.stat().st_ino` 恒 0，要用
  `DirEntry.inode()`**（零额外 syscall）。
* **`novel.md` 是导出汇总，阅读页不读它**：它每章都重建，所以必须增量
  （按章缓存签名 + 正文；刚写的章用 `override_chapter` 传内存正文）。
  维护脚本改完文件再重建时传 `force=True`，别复用进程内旧正文。
  200 章实测 6.4ms/次（旧实现 60~110ms/次且每次读全书 = O(章数²)）。
* **任务记录只持久化恢复需要的字段**：`message`/`done`/`translated`/`total`/
  `targets` 只留内存。段级进度原本每段一次 `atomic_write_json`（带 fsync，
  手机闪存几十毫秒），现在完全不写盘；重启后要的是章节级 `completed_chapters`。
  注意 `/api/job` 仍然**不许**刷新心跳（这条不变）。
* **单条任务记录损坏按"恢复"处理**：`JobRecordCorrupt(RecoveryRequired)` 由
  `JobStore.get()` 抛，worker 映射成 `interrupted` + 只读恢复，**不许**变成
  `provider_error`（那会谎称模型坏了）。活跃记录被**外部删除**时抛
  `JobRecordMissing`（同样是 RecoveryRequired 子类）：只停这一本书、**不**锁整站、
  **不**写 `trans_error`（否则卡片亮「翻译失败」徽标，把日志问题说成模型问题）。

**本地导入 / 术语过期（2026-10-22）**

* **编码不能按「谁先不报错」选**：GBK 中文在 cp932 下能"成功"解成半角片假名乱码。
  导入 TXT 必须对 cp932/euc_jp/gb18030 打分（假名/常用汉字加分，半角片假名重罚）。
* **EPUB 三处静默丢内容**：ruby 的 `rt`/`rp` 要剥（否则正文出现「亜里沙アリサ」）；
  manifest `href` 的 `#锚点`/`?query` 要剥（否则整章被跳过）；TXT 第一个标题前的
  短前言不能按长度丢掉。
* **TXT 没有空行 = 整章一个巨型段落**：`split_paragraphs()` 会合并连续非空行，
  而分段器只能按行切、单段无法二分降级。导入时无空行就按一行一段重排，超长单行
  再按句末标点切。
* **只建目录不上架 = 书在 UI 里消失**：书架只渲染 `on_shelf`。CLI `import` 必须写
  `data/books/<slug>.json` 的 `tracking="want"` 并打印 `/read/<slug>`。
* **过期提示不能被无关编辑刷掉**：`refresh_chapter_meta(update_glossary=False)` 给
  引号对齐 / 修页脚 / 补译个别段用；只有真正按新术语表改过的章才刷新指纹。
* **`stale --retranslate` 不许假报完成**：`translate_chapter()` 返回 False 的章要
  逐条列出，旧译文还在、提示还会亮。

### 改动时的自查清单

1. 有没有把两个独立概念**错误地做成互斥**？（如收藏 vs 看完）
2. 有没有"想当然"的自动行为会**让读者找不到东西**？（如自动归档）
3. 页面上显示的**数字对读者意味着什么**？是不是他真正关心的那个？
4. 读写状态的地方**都在锁里**吗？崩溃后**状态会不会卡死**？
5. 跑 `run_selftests.py`，确认**环境无残留**。
6. 输入框/按钮的 DOM 嵌套对吗？点输入框会不会误触提交？
7. 手机窄屏（至少 320px）有没有横向溢出、两个悬浮层会不会重叠？

### 注意

* 只翻译读者**确实要看**的内容。反过来说：读者说"我想看到哪就翻到哪"时，
  正确做法就是每轮 `next <slug> N`，不要预翻。
* 译文放在 `novels/<slug>/novel.md`（整本汇总）和 `chapters/NNNN.txt`（分章）。
* 尊重源站：抓取有内置延迟，别把 `count` 开很大。
* **slug 只用 ASCII**：日文标题直接进 slug 会让 URL 变成一长串百分号编码。
  `slugify()` 已改为只保留 ASCII，取不到就回退 `kakuyomu-<id>`。
* **`zh_titles` 里混着 `book` 键**，任何 `int(k)` 的排序都要先过滤 `k.isdigit()`。
* 这是**为个人阅读**服务的翻译，产物留在本地。
* **加新书后一定要做两件事**：`titles <slug>`（否则目录全是日文）
  和确认 `lnserve.py` 在跑（否则读者点开看不到东西）。
