# 第二轮：已并入你的修复 + 我在此基础上又改了什么

先谢谢——你这一轮抓到的东西里，**四个是我自己的自检查不出来的**（尤其是那条
`getElementById('btn-fav')` 空引用把整段脚本后面的绑定全废掉：我的 DOM 桩对任何 id
都返回一个"稳定对象"，所以永远不报错，一路绿灯）。下面按"你的修复"和"我的后续"分开写，
方便你核对。

## 一、你的修复：全部已并入，我逐条验证过

| 你的修复 | 我这边看到的实际症状（并入了才确认） | 验证方式 |
| --- | --- | --- |
| `setFlag` + 残留的 `btn-fav/btn-fin/btn-drop` 逐元素绑定 | 阅读页那三个 id 早就不存在 → 抛 `Cannot set properties of null` → **主题按钮、日文折叠开关全成死按钮** | 桩改成"未知 id 返回 null"后，负向对照立刻复现（见下） |
| `toggle-jp` 漏绑 | 日文原文默认全显示、按钮点了没反应 | 新增"每个带 id 的按钮都要有 handler"断言，去掉绑定即报警 |
| `page_library` 里注释吃掉 `if BIND_HOST ...` | `lan_html` 落进 `except` 分支 → **「📱 平板/其他设备访问」那行从来不显示**（我实测 live 页面 grep 计数 0，修完是 1） | `curl /` + grep |
| `/api/detail` 用了 POST 作用域的 `d`、且只在 do_GET | 「重抓简介/目录」永远不生效（GET 直接 NameError） | 抽函数后 GET/POST 都通 |
| `/api/batchstate` 只注册 POST、前端用 GET 轮询 | 列表页补中文标题静默失败（404 被吞） | `curl /api/batchstate` 现返回 `{"ok":true,...}` |
| `/api/job` 里刷心跳 | 心跳被前端轮询刷新 → "任务卡死兜底"永远不触发 | 代码审查 + 自检 |
| worker 只 `except Exception` | `lt.die()`（如缺 key）走 `sys.exit()` → **worker 线程直接死掉，整条队列永远卡 running** | 自检 + 代码审查 |
| 任务 `token` 身份 | 心跳超时判死后重试 → 新旧两个任务同时翻同一章（重复花钱） | 代码审查 |
| `save_text()` 原子写 | 半截文件被 `has_translation()`（只看 size>0）当成"已译"永久跳过 | 自检 |
| 失败分段不落盘/不缓存/不算已译 + `incomplete` | 原文冒充译文 → 落盘 + 缓存 → 修好也不重译 | `test_gap.py` 新增用例 |
| `detect_chinese` 严格化（中性字符不计、假名比例否决） | 「彼女は無表情で立っていた。」曾被判为中文 | `test_translate.py` 新增 5 条 |
| `parse_chunk_reply` 无编号续行/重复编号 | 模型把一段折行 → 后一行被丢 → **译文被截断** | `test_translate.py` 新增用例 |
| `MAX_SEG_CALLS` 每段调用上限 | 纯毒段最坏 93 次调用 | 代码审查 |
| `read` 默认 1 → 0、`recent_read().next` 不回跳 | 没读过的书被当成"读过第 1 章"；续读按钮可能跳回第 1 章 | `test_state.py` 新增 |
| `lnfind.py` 数据目录没走 `LNTRANS_LNFINDER` | 违反我自己写在 AGENTS.md 的硬规则（隔离测试会写到真实画像） | 修复后 `lnfinder/selftest.py` 全绿 |
| 依赖未知函数已删、`kakuyomu_search` 失败不再假装"没这本书" | — | 编译 + 自检 |
| `/api/status` 回传 `removed` | 前端拿不到"已移出书架"，界面不刷新 | `test_ui.py` 新增 |
| 平板/宽屏 CSS + `#theme` 抬到翻译条之上 | 平板上是手机排版；主题按钮被底部通栏盖住点不到 | live 页面 CSS + 视觉检查 |
| 坏 JSON 归一成 `FetchError`、候选池坏了当空处理 | 裸 `JSONDecodeError` 穿透 | `lnfinder/selftest.py` 新增 |

自检：你的版本我这边跑 **15/15 通过**，`lnfinder/selftest.py` 也通过。

## 二、我在你基础上又改的 4 处（都带断言）

### 1. `fill`（「更新了 +N 话 · 点我翻译」）加了边界 ——**防一次点掉 25 万 token**

你把"fill 不带 ceiling → `auto_ceiling=0` → 静默不翻"改成"`ceiling=total`"，
方向对（按钮必须真的干活），但在真实数据上会变成"把整本欠账一次翻完"：

```
某本: 总 61 话，已译 20 话，欠 41 话   ← 一次点击 ≈ 41 × 6k token ≈ 25 万 token
```

而按钮上写的是「更新了 **+N 话**」。所以现在：`fill` 且无 ceiling 时
→ `ceiling=total`、`after = 总章数 - N`、`count = N`（N 由卡片上的 `data-n` 传，≤10）。
即**只翻最新的 N 话**；最新几话已经译好时，退回"按顺序补最早的缺章"。
断言：`test_reader.py`（HTTP 层，检查 job 的 `fill/ceiling/after`）。

### 2. DOM 桩改成浏览器语义 + 通用"死按钮"断言

你找到的那个 bug 暴露的是**测试基础设施的问题**，不是那一行代码的问题：

* `test_click_dom.js` 的 `getElementById` 现在只对"页面 HTML 里真的存在的 id"返回元素，
  其余返回 `null`（和浏览器一致）。payload 里多带一个 `ids` 列表。
* `test_click.py` 新增断言：**每一个带 id 的 `<button>` 都必须有 handler**
  （除非它走 `data-act` 等事件委托）——原来只抽查 `check-all`/`theme` 两个 id，
  正好漏掉 `toggle-jp`。

负向对照（都验过会红）：

1. 去掉 `toggle-jp` 的绑定 → `❌ 死按钮：阅读页#toggle-jp、阅读页(落地章缺译)#toggle-jp`；
2. 加一行 `document.getElementById('btn-fav').onclick=()=>{}` →
   `❌ 阅读页：内联脚本全部执行完没抛异常  Cannot set properties of null (setting 'onclick')`。

### 3. 性能回归：首页 **5.0 秒 → 0.5 秒**

你给 `work_head()` 补"中文书名两个来源合并"是对的（那正是用户报过的 bug），
但 `_book_zh_title()` → `slug_for_source()` 是"遍历所有本地作品 + 逐个读 meta.json"，
而它**每张卡都会跑一次**；`work_status_chips()` 里也有一段同样的全表扫描。
真实数据：书库 372 张卡 → 一个书架页 372 × N 次 `listdir/stat/open`。

cProfile（改前，`library_pane` 3.35 s）：

```
372  work_status_chips   cumtime 2.820
747  novel_meta          cumtime 1.644
373  all_local_slugs     cumtime 1.130
2895 posix.stat          1.286
1129 _io.open            0.905
```

改法：
* `_slug_index()`：source_id → slug 反查表，按 novels 目录 `(mtime_ns, size)` 缓存
  （`work_head` / `work_status_chips` 都用它）；
* `novel_meta()`：按 `(mtime_ns, size)` 缓存（worker 写完后 mtime 变，自然失效）。

实测：`library_pane` 3.35 s → **0.55 s**；live `curl /` 5.0 s → **0.47~0.68 s**。
阅读页 0.05 s。

### 4. `progress.incomplete` 要**露出来**

你记了账（翻译失败/`--allow-missing` 的章），但 UI 没读它 —— 于是目录里
「未译全」的章和整篇中文的章长得一模一样。现在 `toc_list()` 会给这类章加一个
`未译全` 徽标（tooltip 说明可以再点一次补齐）。断言在 `test_reader.py`。

## 三、这一轮我这边跑过的验证

* `lntrans/run_selftests.py` **15/15**；`lnfinder/selftest.py` 全绿。
* 真实资产指纹跑前跑后不变（推荐缓存 / 书库 / 各书的 meta.json /
  `taste_profile.json`）。
* live（手机容器里 `--lan` 起服务后 curl）：
  `/` 200 / 0.5 s、「📱 平板/其他设备访问」回来了、16 张卡、`body.pg-home`；
  `/read/...` 200 / 0.05 s、目录 23 条中文标题、日文默认折叠（`hidejp`）、
  主题按钮 `bottom:60px` 的 CSS 在位、无页脚残留；
  `/api/batchstate`、`/api/detail` GET 都通了。
* 负向对照 2 条（见上）。

## 四、还剩的已知问题（我没动的）

1. `lnserve.py` 依然 4900 行、页面 JS 仍内联在 Python 字符串里（这一轮又验证了一次
   它的代价：一个引号/一行注释就能酿成"整页按钮失效"，而且是外面的人审出来的）。
2. `--lan` 无鉴权。
3. 存储仍是文件 + JSONL，没有 schema 版本/迁移。
4. 某章历史译文比原文少 2 段（数据瑕疵，不自动修）。
5. `lnfind.py` 的相似度排序在 `lnserve.py` 里（IDF 加权在那边，不在 lnfind）。
