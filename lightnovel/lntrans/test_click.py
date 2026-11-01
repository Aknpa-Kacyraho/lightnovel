#!/usr/bin/env python3
"""回归：**真的把每个按钮点一遍**，断言发出去的请求和界面状态都对。

为什么单独有这个测试（和 test_ui.py 的区别）：
  test_ui.py 只做两件事——把内联 JS 交给 Node 编译、用 HTTP 打服务端接口。
  它能证明"语法没错、API 能改状态"，但**查不出用户报的那 4 个 bug**：
    · 详情页 ★收藏 的 class 被写死 on → 前端永远发 value:false
      （语法完全合法；API 也能改状态；只有"点下去发了什么"是错的）
    · 「更新了 +N 话 · 点我翻译」不在 .ctrls 里 → 没有 handler
      （服务端和 JS 语法都看不出"这个按钮没人管"）
    · 一条 getElementById(...).onclick 抛异常 → 后面所有绑定失效
      （编译期查不出运行时异常）
  所以这里用 test_click_dom.js 的最小 DOM 桩把页面脚本**真的执行**，
  再按 HTML 里每个按钮**真的点一次**，然后断言：
    A. 页面脚本执行期间没抛异常；
    B. 全局动作委托注册上了（一次绑定覆盖全站）；
    C. 每个动作按钮点下去都发出了**正确的**请求（动作名、value、payload）；
    D. **UI 等于实际**：按钮的 on 状态必须等于 /api/library 里的真实状态
       （这条直接抓住"★收藏 写死 on"那类 bug）；
    E. 书架卡的中文书名来自详情缓存（用户报的"标题没翻译"），
       并且未译时不会把同一行日文显示两遍。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, "test_click_dom.js")
fails: list[str] = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def get(path: str) -> str:
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return r.read().decode("utf-8")


# ---------------------------------------------------------------- 抓按钮
CARD_RE = re.compile(r'<div class="card"([^>]*)>')
BTN_RE = re.compile(r"<button([^>]*)>(.*?)</button>", re.S)
ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
ACT_ATTRS = ("data-act", "data-d-act", "data-add", "data-d-add",
             "data-want", "data-gopage", "data-stale-retranslate")


def buttons_of(html: str) -> list[dict]:
    """把页面里的按钮抽出来，并记下它属于哪张卡（card 的 slug / wid）。"""
    out: list[dict] = []
    # 只解析真正的 HTML 标记；<style>/<script> 里的注释和字符串可能也含
    # "<button>" 字样，直接全文正则会把后面的真按钮吞掉（本次就踩到了：
    # 一条 CSS 注释里写了 <button> 里放 <input>，导致收藏按钮从样本里消失）。
    html = re.sub(r"<(style|script)\b[^>]*>.*?</\1>", "", html,
                  flags=re.S | re.I)
    # 按卡片切段：段头给出 slug/wid，段内的按钮都算这张卡的
    marks = [(m.start(), ATTR_RE.findall(m.group(1))) for m in CARD_RE.finditer(html)]
    for m in BTN_RE.finditer(html):
        attrs = dict(ATTR_RE.findall(m.group(1)))
        if not any(a in attrs for a in ACT_ATTRS):
            continue
        card = None
        for pos, cattrs in marks:
            if pos < m.start():
                cd = dict(cattrs)
                card = {"slug": cd.get("data-slug", ""), "wid": cd.get("data-wid", "")}
            else:
                break
        cls = attrs.get("class", "")
        label = (attrs.get("data-act") or attrs.get("data-d-act")
                 or ("add:" + (attrs.get("data-add") or attrs.get("data-d-add") or "")[:60])
                 or ("want:" + attrs.get("data-want", ""))
                 or ("gopage:" + attrs.get("data-gopage", ""))
                 or ("stale:" + attrs.get("data-stale-retranslate", "")))
        out.append({"attrs": attrs, "cls": cls, "text": m.group(2), "card": card,
                    "label": label})
    return out


# ---------------------------------------------------------------- 挑页面
lib = json.loads(get("/api/library"))
items = lib.get("items") or []
if not items:
    # 不能 exit 0：隔离自检里书库一定有种子，空 = 测试环境坏了。
    # 直接"跳过通过"会变成假绿（整套报绿但这些断言一条没跑）。
    print("❗ 书库为空（隔离环境里应该有种子的）—— 这是失败，不是跳过")
    sys.exit(1)

scripts_re = re.compile(r"<script>(.*?)</script>", re.S)
pages: list[dict] = []


def add_page(name: str, path: str, flush: int = 0, keys=None, keys_in_input=None) -> None:
    try:
        html = get(path)
    except Exception as e:  # noqa: BLE001
        # 偶发的 500 / 连接抖动：重试一次并**大声警告**（不静默吞掉）。
        # 真出现时要去隔离服务的 data/server.log 看 traceback ——
        # 那正是用户说的"页面有时候要自己刷新一下"。
        print(f"  ⚠ {name} 第一次打不开（{e}），重试一次…")
        time.sleep(1.0)
        try:
            html = get(path)
        except Exception as e2:  # noqa: BLE001
            print(f"  ❌ {name} 打不开：{e2}")
            fails.append(f"{name} 打不开")
            return
    pages.append({"name": name, "html": html, "path": path, "flush": flush,
                  "keys": keys or [], "keysInInput": keys_in_input or [],
                  "chapters": [int(x) for x in re.findall(
                      r'<section class="ch[^"]*"[^>]*?data-ch="(\d+)"', html)],
                  "scripts": [s for s in scripts_re.findall(html) if s.strip()],
                  "buttons": buttons_of(html),
                  # 页面 HTML 里真实存在的 id 列表：DOM 桩据此决定
                  # getElementById 返回元素还是 null（和浏览器一致）
                  "ids": sorted(set(re.findall(r'\bid="([^"]+)"', html)))})


add_page("书架首页", "/classic")
_slug0 = items[0]["slug"]
add_page("阅读页", f"/read/{_slug0}?nocheck=1")
# 落地章（第 1 章）没译文、且已开自动翻译的阅读页：
# 用来证明"一进页面就自己去翻第 1 章"和"不偷偷跳到第 2 章"。
# flush=6：手动推进异步轮询链（tick↔poll），否则"定时器空实现"的桩查不到
# 轮询是否真的闭环（这正是"读到哪翻到哪"死锁当初藏身之处）。
add_page("阅读页(落地章缺译)", "/read/__need_seed__?nocheck=1", flush=6)
# 连续阅读：从第 2 章起、一次渲染 3 章（?n=3），页内确有多个 section.ch[data-ch]，
# 才能验证键盘翻章真的滚动、且在 textarea 里不抢键。
add_page("阅读页(多章·键盘)", "/read/__need_seed__?from=2&n=3&nocheck=1",
         keys=["ArrowRight", "ArrowRight", "ArrowLeft"],
         keys_in_input=["ArrowRight", "j"])
# 默认单章页（用户嫌 3 章一页太长）：页内只有一章，←/→ 应**跨页**翻到相邻章
# （location.href='/read/...?from=N'），并用 next 变量把下一章章号/是否已译告诉前端。
add_page("阅读页(单章·跨页翻)", "/read/__need_seed__?from=3&n=1&nocheck=1",
         keys=["ArrowRight", "ArrowLeft"])
# 落地章**已译**、下一章**还没译**：一进页面就该开始预翻下一章
# （用户报「感觉翻译速度变慢了」的根因：一页只渲染一章之后，只有滚到底才开工，
#  于是每翻一章都要干等 30~45 秒）。__reader_seed__ 的第 7 章已译、第 8 章没有。
add_page("阅读页(下一章未译·预翻)", "/read/__lookahead_seed__?from=7&n=1&nocheck=1",
         flush=3)
# 术语表改过：这一章是用旧表翻的，阅读页必须给提示 + 一键重翻入口。
add_page("阅读页(术语过期)", "/read/__stale_seed__?from=1&n=1&nocheck=1")
# 本地导入页：文件选择 + 上传按钮；脚本必须能执行、imp-go 必须绑上 handler。
add_page("本地导入页", "/import")
# 详情页：必须挑**在书架上**的（那才有收藏/在读那一排按钮）。
# 而且要覆盖两种取值：已收藏 / 未收藏 —— 曾经的 bug 就是这里被写死成 on，
# 只有两种取值都点过，断言才抓得住它。
_shelved = [it for it in items if it.get("on_shelf")] or items
_fav = next((it for it in _shelved if it.get("favorite")), None)
_nofav = next((it for it in _shelved if not it.get("favorite")), None)
if _nofav:
    add_page("详情页(未收藏)", f"/book?id={_nofav['id']}")
if _fav:
    add_page("详情页(已收藏)", f"/book?id={_fav['id']}")
if not (_nofav or _fav):
    add_page("详情页", f"/book?id={items[0]['id']}")

print("=" * 70)
print("A–C. 真点一遍：脚本能不能跑完、按钮点下去发了什么")
print("=" * 70)

payload = {"pages": [{"name": p["name"], "scripts": p["scripts"],
                      "buttons": p["buttons"], "ids": p["ids"],
                      "flush": p.get("flush", 0),
                      "keys": p.get("keys", []),
                      "keysInInput": p.get("keysInInput", []),
                      "chapters": p.get("chapters", [])} for p in pages],
           # 只对预翻页伪造一个"正在翻第 8 章"的任务：j.done=1 是本次任务进度，
           # j.translated=6 才是全书累计。进度条必须用后者，不能从 6/10 掉回 1/10。
           "fake": {
               "/api/job?slug=__lookahead_seed__":
                   {"status": "running", "done": 1, "translated": 6,
                    "total": 10, "message": "第 8 章 · 段 3/7"},
               "/api/next?slug=__lookahead_seed__&from=8":
                   {"html": "", "done": 6, "need": 8, "total": 10},
           }}
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    json.dump(payload, f, ensure_ascii=False)
    payload_path = f.name

r = subprocess.run(["node", HARNESS, payload_path],
                   capture_output=True, text=True, timeout=180)
os.unlink(payload_path)
if r.returncode != 0 or not (r.stdout or "").strip():
    print("  ❌ 仿真器本身失败：", (r.stderr or "")[:600])
    sys.exit(1)
sim = json.loads(r.stdout)
if sim.get("fatal"):
    print("  ❌ 仿真器内部错误：", str(sim["fatal"])[:800])
    sys.exit(1)

# A. 脚本执行没抛异常
for p in sim["pages"]:
    check(f"{p['name']}：内联脚本全部执行完没抛异常",
          not p.get("loadError"), str(p.get("loadError") or "")[:160])
# B. 动作委托注册
# 导入页是单按钮表单动作（局部 onclick），不需要全站委托；B2 会单独查它有没有 handler。
for p in sim["pages"]:
    if p["name"] == "本地导入页":
        continue
    check(f"{p['name']}：注册了全局动作委托", (p.get("clickHandlers") or 0) >= 1,
          f"handlers={p.get('clickHandlers')}")

# B2. **每一个** 带 id 的按钮都必须有 handler —— 除非它走事件委托。
#     踩过（高手审出来的）：`document.getElementById('btn-fav').onclick=` 在
#     元素早已不存在时抛 "Cannot set properties of null"，**整段脚本后面的绑定
#     集体失效**（日文折叠开关、主题按钮成了死按钮）。只挑 check-all/theme 两个
#     id 去查是查不出来的，必须全查。
DELEGATED_ATTRS = ("data-act", "data-d-act", "data-add", "data-d-add",
                   "data-want", "data-gopage")
dead_buttons = []
for p, spec_page in zip(sim["pages"], pages):
    h = p.get("idHandlers") or {}
    for m in re.finditer(r'<button([^>]*)>', spec_page["html"]):
        attrs, bid = m.group(1), re.search(r'\bid="([^"]+)"', m.group(1))
        if not bid or any(a in attrs for a in DELEGATED_ATTRS):
            continue
        if not h.get(bid.group(1)):
            dead_buttons.append(f"{p['name']}#{bid.group(1)}")
check("每个带 id 的按钮都有 handler（要么显式绑定、要么走事件委托）",
      not dead_buttons, "死按钮：" + "、".join(dead_buttons[:8]))
# 旧断言保留（关键的两个 id 必须绑上）
for p, spec_page in zip(sim["pages"], pages):
    ids = set(re.findall(r'<button[^>]*\bid="([^"]+)"', spec_page["html"]))
    ids |= set(re.findall(r'<(?:input|select)[^>]*\bid="([^"]+)"', spec_page["html"]))
    h = p.get("idHandlers") or {}
    missing = sorted(i for i in ids if i in ("check-all", "theme") and not h.get(i))
    check(f"{p['name']}：关键按钮都绑上了 handler", not missing, str(missing))

# B3. 阅读页的「章节划分」（用户报：我第一话呢？译好了怎么不刷新？）
#     服务端产出在 test_reader.py 里测；这里测**浏览器里真的发生了什么**。
for p, spec_page in zip(sim["pages"], pages):
    if "落地章缺译" not in p["name"]:
        continue
    html = spec_page["html"]
    check("落地章缺译：渲染占位块，页面上**没有**第 2 章正文（不偷跳）",
          'id="need-1"' in html and 'id="c2"' not in html)
    check("落地章缺译：已译数字是 4（第 2~5 章），不是 0",
          ">4/5<" in html)
    check("落地章缺译：已译章节列表把第 2~5 章都列出来（可点进去读）",
          all(f"?from={i}" in html for i in range(2, 6)))
    load_reqs = [r for r in (p.get("loadRequests") or [])
                 if not r["url"].startswith("/api/log")]
    auto = [r for r in load_reqs if "/api/translate" in r["url"]]
    check("★ 一进页面就自己去翻第 1 章（不用等滚到底、也不用手动刷新）",
          bool(auto) and (auto[0].get("body") or {}).get("after") == 1,
          str([r.get("body") for r in auto])[:160])
    # ★ 轮询链必须真的闭环：tick 发出 /api/translate 后，必须真的去 poll /api/job，
    #   且 poll 会再排下一轮 tick（translate 出现 ≥2 次）。若这条链断了
    #   （如 tick 设 polling=true 后交棒前没解锁 → 第一个 poll 被自己设的锁挡回），
    #   译好的章节永远不会自动追加，读者被迫手动刷新。旧桩把 setTimeout 空实现，
    #   整条链静默不跑，故这里得靠 flush=6 推进定时器后才断言得到
    #   （负向验证：把 reader.js 的 tick 交棒处改回不清锁，这两项必变红）。
    jobs = [r for r in load_reqs if "/api/job" in r["url"]]
    check("★ 自动续译轮询链真的闭环（tick→poll /api/job→再排下一轮 tick）",
          len(jobs) >= 1 and len(auto) >= 2,
          f"job×{len(jobs)} translate×{len(auto)}（要求 job≥1 且 translate≥2）")
    check("轮询链 flush 期间没有定时器回调抛异常",
          not (sim["summary"].get("timerErrors") or []),
          str((sim["summary"].get("timerErrors") or [])[:3])[:160])

# B3c. 连续阅读：键盘翻章（←/→/j/k）——handler 接线、健壮、且不抢输入框
for p, spec_page in zip(sim["pages"], pages):
    if not spec_page.get("keys"):
        continue
    check(f"{p['name']}：注册了键盘翻章 handler",
          (p.get("keyHandlers") or 0) >= 1, f"handlers={p.get('keyHandlers')}")
    _keys = p.get("keys") or []
    check(f"{p['name']}：←/→ 派发均不抛异常",
          bool(_keys) and all(not k.get("error") for k in _keys),
          str([k for k in _keys if k.get("error")])[:160])
    # 序列断言（互评·A 抓到过假绿）：→→← 的目标章号必须 **递增再递减**。
    # 只断言"至少滚动过一次"会放过 curCh 不自我更新的 bug —— 桩里的
    # IntersectionObserver 是 no-op，若 gotoChapter 不等 observer 回调就把 curCh
    # 推到位，这串序列才对得上；否则每次都用旧 curCh → 原地打转 → 序列不符。
    # 只在**多章页**（页内 ≥2 章）适用；单章页的 ←/→ 是跨页跳转，见 B3d。
    _tgt = [str(x) for x in (p.get("scrollTargets") or [])]
    if len(spec_page.get("chapters") or []) >= 2:
        check(f"{p['name']}：翻章目标序列正确（→→← 应递增再递减）",
              _tgt == ["3", "4", "3"], f"实际={_tgt}")
    _ki = p.get("keyInInput") or {}
    check(f"{p['name']}：在 textarea 里按键不翻章（不抢输入框）",
          (_ki.get("scroll") or 0) == 0 and not _ki.get("error"),
          str(_ki)[:160])

# B3d. ★ 默认单章页：页内只有一章，←/→ 跨页翻到相邻章（修复"一次 3 章太长"）
for p, spec_page in zip(sim["pages"], pages):
    if "单章·跨页翻" not in p["name"]:
        continue
    html = spec_page["html"]
    check("单章页：页面只渲染一章（section.ch 只有一个）",
          (p.get("chapters") or []) == [3], f"chapters={p.get('chapters')}")
    check("单章页：把下一章章号/是否已译告诉前端（__NEXT__ / __NEXTHAVE__）",
          "__NEXT__=4" in html and "__NEXTHAVE__=true" in html, "")
    # 链接必须带 `#c4` 锚点：点下去落在正文，不是回到页面顶部再翻过标题/目录。
    check("单章页：章末「下一章」是**可点链接**（译好就点亮，且带正文锚点）",
          'id="nav-next"' in html and '?from=4#c4">下一章' in html, "")
    check("单章页：页内没有可滚动的下一章（不往本页追加）",
          not (p.get("scrollTargets") or []), f"scrollTargets={p.get('scrollTargets')}")
    # →→ 都越界到"下一章"（4），← 退到"上一章"（2）；用真实 location.href 跳转记录
    check("★ 单章页 → 翻到下一章、← 翻到上一章（跨页跳转 URL 正确，带 #c 锚点）",
          (p.get("hrefs") or []) == ["/read/__need_seed__?from=4#c4",
                                     "/read/__need_seed__?from=2#c2"],
          f"hrefs={p.get('hrefs')}")

# B3e. ★ 落地章已译、下一章未译：**一进页面就预翻下一章**（不等滚到底）
for p, spec_page in zip(sim["pages"], pages):
    if "下一章未译·预翻" not in p["name"]:
        continue
    html = spec_page["html"]
    check("预翻页：服务端把「链接可点」和「已有译文」分开告诉前端",
          "__NEXTHAVE__=true" in html and "__NEXTTRANS__=false" in html, "")
    load_reqs = [r for r in (p.get("loadRequests") or [])
                 if not r["url"].startswith("/api/log")]
    auto = [r for r in load_reqs if "/api/translate" in r["url"]]
    check("★ 一进页面就开始预翻下一章（第 8 章，不等读者滚到底）",
          bool(auto) and (auto[0].get("body") or {}).get("after") == 8,
          f"after={[(r.get('body') or {}).get('after') for r in auto]} "
          f"status={p.get('statusText')!r} "
          f"reqs={[r['url'] for r in load_reqs][:5]}")
    # 目录默认折叠：以前 23 章目录顶在正文前面，每次翻章都要先往下翻过它。
    check("★ 目录默认折叠（正文紧跟标题栏，不用先翻过一屏目录）",
          'class="tocbox"' in html and 'class="tocbox" open' not in html, "")
    # 底部条：一条稳定状态 + 一条进度（用户要求「希望能看到翻译进度」）
    check("★ 底部翻译条有独立的「状态 / 进度」两个槽（不再一句话来回变）",
          'id="tb-status"' in html and 'id="tb-prog"' in html and 'id="tb-fill"' in html
          and 'id="tb-seg"' in html, "")
    m = re.search(r'id="tb-prog"[^>]*>([^<]*)<', html)
    prog = m.group(1) if m else ""
    check("★ 进度一进来就写着「已译 x/y（p%）」",
          bool(re.search(r'已译 \d+/\d+（\d+%）', prog)), prog)
    # 回归：任务运行中 j.done=1（本次任务），但全书累计 j.translated=6。
    # 进度条必须停在 6/10，不能因为"本次任务翻第 1 章"就倒退成 1/10。
    check("★ 翻译中进度只用全书累计 j.translated，不倒退",
          "6/10" in (p.get("progText") or "")
          and "1/10" not in (p.get("progText") or ""),
          f"prog={p.get('progText')!r}")
    # ★ 状态槽只许写一套模板，段进度写进 tb-seg。
    #   用户原话：「下面依旧是正在翻译和第x章几段互相抢前端显示」——
    #   服务端 message 是「第 8 章 · 段 3/7」，以前整句塞进状态槽，
    #   与 tick() 的「正在翻译第 N 章…」每 1.5~2.5 秒互相覆盖，就是闪烁的来源。
    _st = p.get("statusText") or ""
    _seg = p.get("segText") or ""
    _plain = re.sub(r"<[^>]+>", "", _st)
    check("★ 状态槽只有「正在翻译第 N 章…」一套模板（不写整句服务端 message）",
          _plain.startswith("正在翻译第 8 章") and "段 3/7" not in _plain,
          f"status={_plain!r}")
    check("★ 段进度写进独立槽 tb-seg",
          "段 3/7" in _seg, f"seg={_seg!r}")

# B3f. 术语过期提示 + 一键重翻（术语表改过之后最容易「提示消失/点了没反应」）
for p, spec_page in zip(sim["pages"], pages):
    if "术语过期" not in p["name"]:
        continue
    html = spec_page["html"]
    check("术语过期：阅读页渲染提示 + 重翻入口",
          'class="stale-note"' in html and 'data-stale-retranslate="1"' in html,
          "")
    stale_clicks = [c for c in (p.get("clicks") or [])
                    if "data-stale-retranslate" in (c.get("attrs") or {})]
    reqs = [r for c in stale_clicks for r in (c.get("requests") or [])
            if r["url"].startswith("/api/translate")]
    body = (reqs[0].get("body") or {}) if reqs else {}
    check("术语过期：点重翻发 force 请求（after/ceiling=1）",
          bool(reqs) and body.get("force") is True
          and body.get("after") == 1 and body.get("ceiling") == 1,
          str(reqs[:1])[:200])

# B3g. 本地导入页：脚本能跑、按钮有 handler、上传接口写对
for p, spec_page in zip(sim["pages"], pages):
    if p["name"] != "本地导入页":
        continue
    html = spec_page["html"]
    check("导入页：文件选择 + 上传按钮 + /api/import",
          'id="imp-file"' in html and 'id="imp-go"' in html
          and "/api/import" in html, "")
    check("导入页：imp-go 绑上了 handler",
          bool((p.get("idHandlers") or {}).get("imp-go")),
          str(p.get("idHandlers"))[:160])

# B4. 补中文标题：轮询里必须**再次排批**（translate_batch 出现 ≥2 次），
#     否则 >40 本时 pending 永远降不到 0、剩下的书名一直是日文
#     （用户报「刷新推荐有一部分是日文没翻译」的根因）。
try:
    _home = next(p for p in pages if p["name"] == "书架首页")
    _home_js = "\n".join(_home["scripts"])
    check("★ 首页补标题的轮询里会**继续排批**（>40 本也能补全）",
          _home_js.count("translate_batch") >= 2,
          f"translate_batch×{_home_js.count('translate_batch')}")
except StopIteration:
    check("★ 首页补标题的轮询里会继续排批", False, "找不到书架首页")

# C. 每个按钮点下去的请求必须正确
errors = []
checked = 0
for p, spec_page in zip(sim["pages"], pages):
    for click in p["clicks"]:
        a = click.get("attrs") or {}
        # clog() 会先发一条 /api/log 埋点，它不是动作请求
        reqs = [r for r in (click.get("requests") or [])
                if not r["url"].startswith("/api/log")]
        label = f"{p['name']} · {click['label']}"
        if click.get("error"):
            errors.append(f"{label} 抛异常：{click['error']}")
            continue
        if not reqs:
            errors.append(f"{label} 点了没有任何请求（按钮是死的）")
            continue
        checked += 1
        url, body = reqs[0]["url"], reqs[0].get("body") or {}
        if "data-add" in a or "data-d-add" in a:
            want_url = a.get("data-add") or a.get("data-d-add")
            if "/api/add" not in url or body.get("url") != want_url:
                errors.append(f"{label} 加入书架请求不对：{url} {body}")
        elif "data-want" in a:
            if "/api/want" not in url or str(body.get("id")) != str(a["data-want"]):
                errors.append(f"{label} 想看请求不对：{url} {body}")
        elif "data-gopage" in a:
            if "page=" + str(a["data-gopage"]) not in url and \
               str(body.get("page")) != str(a["data-gopage"]):
                errors.append(f"{label} 翻页请求不对：{url} {body}")
        elif "data-stale-retranslate" in a:
            ch = str(a["data-stale-retranslate"])
            if ("/api/translate" not in url or not body.get("force")
                    or str(body.get("after")) != ch
                    or str(body.get("ceiling")) != ch):
                errors.append(
                    f"{label} 术语过期重翻请求不对：{url} {body}")
        else:
            act = a.get("data-act") or a.get("data-d-act")
            if act == "check":
                if "/api/check" not in url:
                    errors.append(f"{label} 查更新请求不对：{url}")
                continue
            if act == "autotrans":
                if "/api/transcfg" not in url:
                    errors.append(f"{label} 自动翻译开关请求不对：{url}")
                continue
            if act == "fill":
                if "/api/translate" not in url or not body.get("fill"):
                    errors.append(f"{label} 「点我翻译」请求不对：{url} {body}")
                continue
            if act == "trname":
                if "/api/translate_meta" not in url or not body.get("id"):
                    errors.append(f"{label} 翻书名请求不对：{url} {body}")
                continue
            # 状态类：动作名 + value 都必须对
            if "/api/status" not in url or body.get("action") != act:
                errors.append(f"{label} 状态请求不对：{url} {body}")
                continue
            was_on = "on" in (click.get("cls") or "").split()
            if bool(body.get("value")) == was_on:
                errors.append(
                    f"{label} 的 value 与按钮状态矛盾：按钮 on={was_on} "
                    f"却发了 value={body.get('value')}（点了不会有反应）")
check(f"每个动作按钮点下去都发出正确请求（共 {checked} 个）", not errors,
      "；".join(errors[:6]))

# 明确的回归点：★收藏 必须**能开也能关**，而且发的 value 必须与按钮状态相反。
# 用户实际踩到的是：详情页 ★收藏 的 class 被写死成 on → 永远发 value=false →
# 怎么点都开不了（server.log 里连着 5 条 favorite=False）。
def _status_value(c):
    for r in c.get("requests") or []:
        if r["url"].startswith("/api/status"):
            return (r.get("body") or {}).get("value")
    return None


fav_clicks = [c for p in sim["pages"] for c in p["clicks"]
              if (c.get("attrs") or {}).get("data-act") == "favorite"
              or (c.get("attrs") or {}).get("data-d-act") == "favorite"]
fav_opens = [c for c in fav_clicks if not ("on" in (c.get("cls") or "").split())]
fav_ok = [c for c in fav_clicks
          if _status_value(c) == (not ("on" in (c.get("cls") or "").split()))]
check("★收藏：value 必须与按钮状态相反（能开也能关）",
      bool(fav_clicks) and len(fav_ok) == len(fav_clicks),
      f"{len(fav_clicks)} 个收藏按钮，{len(fav_ok)} 个正确")
check("★收藏：样本里必须包含「未收藏→发 value=true」的用例",
      bool(fav_opens) and all(_status_value(c) is True for c in fav_opens),
      f"未收藏的收藏按钮 {len(fav_opens)} 个")

fill_clicks = [c for p in sim["pages"] for c in p["clicks"]
               if (c.get("attrs") or {}).get("data-act") == "fill"]
# 隔离测试环境里**必须**能造出"有更新"的书（否则这条断言就是摆设 = 假绿）
_isolated = os.environ.get("LNTRANS_TEST_SERVER") == "1"
if _isolated:
    check("★「更新了 · 点我翻译」徽标按钮（不在 .ctrls 里）也有 handler",
          bool(fill_clicks) and all(c.get("requests") for c in fill_clicks),
          f"找到 {len(fill_clicks)} 个" if fill_clicks else "隔离环境里一个都没造出来（fixture 坏了）")
else:
    check("「更新了 · 点我翻译」徽标按钮有 handler（本页没有带更新的书，未覆盖）",
          all(c.get("requests") for c in fill_clicks) if fill_clicks else True,
          f"找到 {len(fill_clicks)} 个")

print()
print("=" * 70)
print("D. UI 必须等于实际：按钮的 on 状态 == /api/library 的真实状态")
print("=" * 70)


def state_of(slug: str):
    for it in json.loads(get("/api/library"))["items"]:
        if it["slug"] == slug:
            return it
    return None


ui_errors = []
ui_checked = 0
for p, spec_page in zip(sim["pages"], pages):
    for click in p["clicks"]:
        a = click.get("attrs") or {}
        card = click.get("card") or {}
        slug = a.get("data-slug") or a.get("data-d-slug") or card.get("slug") or ""
        act = a.get("data-act") or a.get("data-d-act")
        if not slug or act not in ("favorite", "reading", "finished", "dropped"):
            continue
        it = state_of(slug)
        if it is None:
            continue
        want = bool(it.get("favorite")) if act == "favorite" \
            else (it.get("tracking") == act)
        got = "on" in (click.get("cls") or "").split()
        ui_checked += 1
        if want != got:
            ui_errors.append(f"{p['name']} {slug} {act}: 界面={got} 实际={want}")
check(f"状态按钮的 on 状态与真实状态一致（共 {ui_checked} 个）", not ui_errors,
      "；".join(ui_errors[:6]))

# 详情页的 ★收藏 曾经被写死成 on（永远显示"已收藏"，且永远发 value=false）。
# 光看字符串不够 —— 必须让"界面状态 == 接口状态"这条断言在**两种取值**下都被走到，
# 否则一个全写死 on 的实现也能蒙混过关（D 段的通用断言会真的抓住它）。
det_fav_on = [c for p in sim["pages"] for c in p["clicks"]
              if p["name"].startswith("详情页")
              and (c.get("attrs") or {}).get("data-d-act") == "favorite"
              and "on" in (c.get("cls") or "").split()]
det_fav_off = [c for p in sim["pages"] for c in p["clicks"]
               if p["name"].startswith("详情页")
               and (c.get("attrs") or {}).get("data-d-act") == "favorite"
               and "on" not in (c.get("cls") or "").split()]
if _fav:
    check("详情页 ★收藏 的样本覆盖「已收藏」和「未收藏」两种取值",
          bool(det_fav_on) and bool(det_fav_off),
          f"on={len(det_fav_on)} off={len(det_fav_off)}")
else:
    check("详情页 ★收藏 覆盖到「未收藏」样本（库里没有收藏的书）",
          bool(det_fav_off), f"off={len(det_fav_off)}")

print()
print("=" * 70)
print("E. 书架中文书名（来自详情缓存）+ 不重复显示日文标题")
print("=" * 70)

home = [p for p in pages if p["name"] == "书架首页"][0]["html"]
shelf = re.search(r'<div class="pane" id="pane-shelf">(.*?)<div class="pane" id="pane-lib">',
                  home, re.S)
check("能定位书架面板", bool(shelf))
if shelf:
    body = shelf.group(1)
    cards = re.findall(r'<div class="card"(.*?)(?=<div class="card"|</details>)', body, re.S)
    check("书架里有卡片可检查", bool(cards), f"{len(cards)} 张")
    dup, zh_ok = [], 0
    for c in cards:
        t = re.search(r'<div class="t">(.*?)</div>', c, re.S)
        jp = re.search(r'<div class="jp">(.*?)</div>', c, re.S)
        # 标题是 .t 里的**第一个文本节点**，后面跟着 <span> 徽标（章数/状态），
        # 所以要从第一个 "<" 截断，不能把徽标文字也算进书名
        title = re.sub(r"<.*", "", t.group(1), flags=re.S).strip() if t else ""
        jpline = re.sub(r"<.*", "", jp.group(1), flags=re.S).strip() if jp else ""
        if jpline and jpline == title:
            dup.append(title[:40])
        if re.search(r"[\u4e00-\u9fff]", title):
            zh_ok += 1
    check("书架上没有'同一行日文显示两遍'的卡片", not dup, "；".join(dup))
    check("书架上的书名至少有一本是中文（说明能读到详情缓存）", zh_ok > 0,
          f"{zh_ok}/{len(cards)} 张")
    # 通用断言：卡上显示的书名必须等于 API 给出的书名（"显示的东西不能骗人"），
    # 并且只要书名和日文原名不同，就一定是中文 —— 详情缓存里的中文名也算数。
    api = {it["slug"]: it for it in json.loads(get("/api/library"))["items"]}
    bad_title, bad_zh, no_wid = [], [], []
    for c in cards:
        wid = re.search(r'data-wid="([^"]*)"', c)
        slug = re.search(r'data-slug="([^"]*)"', c)
        t = re.search(r'<div class="t">(.*?)</div>', c, re.S)
        # 标题是 .t 里的**第一个文本节点**，后面跟着 <span> 徽标（章数/状态），
        # 所以要从第一个 "<" 截断，不能把徽标文字也算进书名
        title = re.sub(r"<.*", "", t.group(1), flags=re.S).strip() if t else ""
        it = api.get(slug.group(1)) if slug else None
        title = title.lstrip("★ ").strip()      # 收藏的书卡标题前有 ★
        if it and title and title != it["title"]:
            bad_title.append(f"{slug.group(1)}: 卡上「{title[:20]}」≠ 接口「{it['title'][:20]}」")
        if it and it["title"] != it["title_jp"] and not re.search(r"[\u4e00-\u9fff]", title):
            bad_zh.append(f"{slug.group(1)}: 「{title[:20]}」不是中文")
        if not wid or not wid.group(1):
            no_wid.append(slug.group(1) if slug else "?")
    check("书架卡显示的书名等于接口给的书名", not bad_title, "；".join(bad_title[:4]))
    check("中文名存在时（含只在详情缓存里的）卡上就是中文", not bad_zh, "；".join(bad_zh[:4]))
    check("每张卡都带 data-wid（「翻书名」按钮要用）", not no_wid, str(no_wid[:4]))

print()
print("=" * 70)
print("F. ★ 端到端：「＋ 加入书架」→ 书架里能看到，且**不是收藏**")
print("=" * 70)
# 用户原话：「我加入书架不等于收藏，因为我（不加）看不了」。
# 也就是：加进来只是为了能读，不该被当成"我喜欢"，更不该拿去学口味。
# 这里用本地已有目录的书（不走网络）真的走一遍 /api/add。
_WID = "888000555"
_URL = "https://kakuyomu.jp/works/" + _WID


def api_lib():
    return {it["slug"]: it for it in json.loads(get("/api/library"))["items"]}


# 这套端到端只对**隔离自检**（有 fixture 书）成立：
# 真实环境里那本 fixture 书根本不存在，硬跑会得到"错误"的假失败。
if api_lib().get("__shelfless_seed__") is None and not _isolated:
    print("  ⏭ 跳过：这是真实环境，没有 fixture 书（隔离自检里一定会跑这一段）")
else:
    before = api_lib().get("__shelfless_seed__")
    check("前置：这本书本地有目录、但不在书架上（fixture 正确）",
          before is not None and before.get("on_shelf") is False,
          f"on_shelf={before.get('on_shelf') if before else 'book 不存在'}")
    try:
        r = json.loads(urllib.request.urlopen(
            urllib.request.Request(BASE + "/api/add", data=json.dumps({"url": _URL}).encode(),
                                   headers={"Content-Type": "application/json"}),
            timeout=30).read().decode())
    except Exception as e:  # noqa: BLE001
        r = {"ok": False, "error": str(e)}
    check("/api/add 成功", bool(r.get("ok")), str(r)[:140])
    after = api_lib().get("__shelfless_seed__")
    check("★ 加入书架后：书架里能看到它（on_shelf=True）",
          bool(after) and after.get("on_shelf") is True,
          f"on_shelf={after.get('on_shelf') if after else '-'}")
    check("★ 加入书架**不算收藏**（favorite 仍为 False）",
          bool(after) and after.get("favorite") is False,
          f"favorite={after.get('favorite') if after else '-'}")
    check("★ 加入书架后的状态是「想读」", bool(after) and after.get("tracking") == "want",
          f"tracking={after.get('tracking') if after else '-'}")
    _h2 = get("/classic")
    _sh = re.search(r'<div class="pane" id="pane-shelf">(.*?)<div class="pane" id="pane-lib">',
                    _h2, re.S)
    _body = _sh.group(1) if _sh else ""
    check("★ 书架页里真的出现了这张卡",
          'data-slug="__shelfless_seed__"' in _body)
    # 只取这张卡那一小段来判断，避免误伤别的卡（收藏那本确实有收藏徽标）
    _card_seg = _body.split('data-slug="__shelfless_seed__"', 1)[-1][:2500]
    check("★ 这张卡没被标成收藏（data-fav=0、也没有『收藏』徽标）",
          'data-fav="0"' in _card_seg
          and '<span class="badge fav">收藏</span>' not in _card_seg)
    # 跑完把状态复原（共享同一份隔离数据根，别把别的测试弄脏）
    try:
        urllib.request.urlopen(urllib.request.Request(
            BASE + "/api/status",
            data=json.dumps({"slug": "__shelfless_seed__", "action": "off",
                             "value": True}).encode(),
            headers={"Content-Type": "application/json"}), timeout=30).read()
    except Exception:  # noqa: BLE001
        pass

print()
print("=" * 70)
if fails:
    print(f"❌ {len(fails)} 项失败：")
    for f in fails:
        print("   ·", f)
    sys.exit(1)
print("✅ 按钮真点测试全部通过（请求正确 + UI 等于实际 + 书名来自缓存）")
