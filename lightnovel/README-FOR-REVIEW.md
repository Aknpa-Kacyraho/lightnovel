# 给审阅者的说明（lightnovel：找书 + 翻译 + 书架网站）

一句话：这是两个**自用**小工具合起来的一套东西 —— 按自己的口味去日文小说站找书
（`lnfinder`）、把挑中的书按需增量翻译成简体中文、再用一个本地 Web 书架给中文读者读
（`lntrans`）。

- 纯 **Python 3.10+ 标准库**，**零第三方依赖**（没有 pip 包、没有前端框架、没有构建步骤）。
- 规模：Python 约 20k 行，独立 `static/*.js` 约 1.4k 行，自检 29 个。
- 运行环境：已验证 Windows 原生与 Linux；手机/平板通过浏览器访问同一个数据根。

## 30 秒跑起来（**不需要 API key、不需要联网、不花一分钱**）

```bash
cd lntrans
python3 run_selftests.py            # 29 个自检，全绿才算过
python3 run_selftests.py -v         # 同上，打出每一条断言
python3 run_selftests.py -k test_reader,test_click   # 只跑某几个，不用等全套

cd ../lnfinder
python3 selftest.py                 # 画像/打分/套路折扣
```

自检自带**桩 LLM**（本地起一个假的 `/chat/completions`）、把数据根重定向到临时目录，
所以：不联网、不调用真实模型、**不会碰真实书架/画像数据**；跑完还会比对真实数据的
指纹（跑前跑后必须一致）。

想真的跑起来（会抓源站、会调真实 LLM，**要自备 key**）：

```bash
cd lntrans && python3 lnserve.py --port 8099     # 浏览器开 http://127.0.0.1:8099/
```

凭据读取顺序见 `lntrans/lntrans.py` 顶部的 `api_key()`。

## 想请重点看什么（按我自己最没底的程度排序）

1. **`lnserve.py` 是单文件服务**：HTTP handler、翻译 worker、页面 HTML 渲染和
   大部分业务函数仍在一个文件里（不写死行数，避免文档与源码漂移）。前端脚本已拆
   到 `static/*.js`，运行时仍内联注入页面；改完必须走 `test_js_static.py`、
   `test_ui.py` 和真实点击仿真。
2. **并发与一致性**：`ThreadingHTTPServer` + 一个翻译 worker 线程 + `threading.Lock`
   + `fcntl` 文件锁；状态是"每个 slug 一个 JSON 文件"的读改写。
   `update_book()` 是锁内读改写，但别处仍有 `_read_book → 改 → _write_book` 的组合。
   这套并发模型最大的坑在哪？（我最担心"部分写入被读到"和 worker 卡死判定）
3. **测试策略**：容器里开不了浏览器，所以前端做了两层 ——
   `node -e "new Function(...)"` 只证明能解析；`test_click.py` + `test_click_dom.js`
   用**最小 DOM 桩**把页面脚本真的执行一遍、按 HTML 里每个按钮**真的点一次**，
   断言"发出去的请求"和"按钮状态 == 接口返回的真实状态"。
   这套做法值不值得推广？有没有更省事的替代？
4. **抓取健壮性**：上游是 kakuyomu（Next.js）。主路径读 `__NEXT_DATA__` 里的 Apollo
   state；站点改版后该字段消失，退回 DOM 解析（按标签深度只取
   `widget-episodeBody` 那个 div）。"上游随时会变"的解析怎么组织才好维护？
5. **成本控制**：LLM 按段落分段翻译，输出两项机械校验（段数一致 + 必须含中文），
   连续 3 次不过就**二分降级**重试；术语表/人物/前情梗概（"故事记忆"）注入 prompt。
   有没有明显能省 token 的空间？
6. **安全**：`--lan` 会绑 `0.0.0.0`，现在改为**表单登录**：网址不携带口令，
   浏览器只保存随机会话 Cookie；主口令可来自 `LNTRANS_TOKEN` 或独立
   `LNTRANS_TOKEN_FILE`。写请求校验 Host/同源 Origin，登录与翻译启动有限速，
   页面带 CSP、frame、Referrer、nosniff 等安全头。回环地址仍免登录。
   公共网络仍应通过 HTTPS/Tailscale，而不是直接暴露 HTTP 服务。

## 已知问题 / 我自己的疑虑（诚实清单）

- ~~**无鉴权**（见上），局域网模式下是真风险。~~ 已加访问口令门禁（见上第 6 条）。
- **前端脚本最终仍内联注入页面**：源文件已独立，但语法或 DOM 错误仍要到运行时
  才暴露；因此保留语法层与真实点击仿真两层测试。
- **LLM 输出只有机械校验**（段数 + 含中文），没有语义/术语一致性校验；
  译名靠事后批量替换修正。
- **上限规则改过一次**（花过真金白银）：原来自动翻译上限是
  `max(读到 + N, 已译章数)`，而已译章数会随翻译增长 → 上限自己往上爬，
  一本从没读过的书几分钟内被从头翻到尾（真实的 23/23 事故）。
  现在**自动上限只看阅读位置**，已译章数只作为手动请求的地板。
- 持久任务日志、中断恢复、章节旁车、模型角色费用账本与预算已加入 v5 alpha。
- 存储是文件 + JSONL，带 schema/契约；同一个数据根由跨进程排他锁保护。
- **历史数据瑕疵**：某章译文比原文少 2 段（当年翻译漏了），只影响"显示日文原文"
  的对照行错位一段；代码无事，数据不自动修（宁可留着也不猜）。
- **中文书名有两个来源**（章节翻译写的 `meta.zh_titles.book`、列表页写的
  `details/<id>.json` 的 `zh_title`），必须合并读 —— 这是补出来的坑，不是设计。

## 代码地图

| 文件 | 职责 |
| --- | --- |
| `lnfinder/lnfind.py` | 口味画像、打分（套路折扣、误解系减免）、负反馈归因 |
| `lnfinder/lnlib.py` | 上游抓取（kakuyomu 为主，小说家 API 作备），缓存/gzip/Referer 处理 |
| `lnfinder/README.md` | 上游站点 API 的逆向笔记（含 Cloudflare/SNI 那类坑） |
| `lntrans/lntrans.py` | 翻译核心：LLM 调用、分段、段落校验、二分降级、术语/人物/梗概注入 |
| `lntrans/lnserve.py` | 书架 Web 服务（HTTP 路由 + 翻译 worker + 页面组装） |
| `lntrans/lnmodels.py` | OpenAI-compatible 模型角色、价格、预算与脱敏费用账本 |
| `lntrans/lnjobs.py` | 持久任务日志、中断恢复、损坏隔离 |
| `lntrans/lnrecs.py` | 推荐缓存 + 书库留档 + lnfinder 惰性加载 |
| `lntrans/lnrender.py` | 章节/整本 HTML 渲染（阅读页与导出共用同一套段落模型） |
| `lntrans/repair_chrome.py` | 维护脚本：重抓干净原文，按段对齐清掉历史章节里的网站页脚残留 |
| `lntrans/run_selftests.py` | 自检唯一入口：隔离数据根 + 桩 LLM + 隔离服务，跑完比对真实数据指纹 |
| `lntrans/test_*.py`、`test_click_dom.js` | 模块回归（`test_click` 是"真点按钮"的前端仿真器） |
| `lntrans/STATE-MACHINE.md` | 状态机与交互语义（每条规则后面都写着"踩过什么坑"） |
| `lntrans/PRIOR-ART.md` | 与 Kavita / LightNovelReader / auto-novel 的取舍理由 |
| `skills/lightnovel/SKILL.md` + `references/` | 入口（§0 开网站）+ 五份分册（找书 / 翻译 / 网站实现 / 踩坑 / 部署），按需只读一份 |
| `AGENTS.md` | 这个仓库给 AI 协作者的项目约定 |

## 关于隐私（这份导出里没有我的东西）

已排除：我的译本与原文、书架/进度/收藏数据、口味画像文件、推荐缓存与报告、
以及任何凭据。**没有 API key**（代码只从环境变量或凭据文件读）。

唯一可能算"我的信息"的是 `lnfinder/lnfind.py` 顶部的
`DEFAULT_PROFILE` / `DEFAULT_SCAN_QUERIES`：那是代码主人的口味默认值
（首次部署应替换成自己的，skill 里已写明）。审阅时当"业务默认值示例"看即可。

## 运行环境

- Python 3.10+（用了 `X | None` 等新语法），只依赖标准库。
- `node` 只在跑 `test_click.py` 那层前端仿真时需要（没有 node 会跳过并说明）。
- Windows 使用 `msvcrt`/内核 mutex，Linux 使用 `fcntl`；两者都跑同一套自检。
