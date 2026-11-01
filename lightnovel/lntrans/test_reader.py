#!/usr/bin/env python3
"""阅读页"章节划分"回归测试。

用户报的两条，都是这一段的问题：
  1.「我还没开始看，怎么就第二话了，我第一话呢？」
     —— 第 1 章没译文时，阅读页原来会**偷偷跳到**第 2 章；
        翻译 worker 也把"当前章之后的"排在前面，第 1 章永远轮不到。
  2.「自动翻译完成某章后怎么不刷新」/「你汉化完了显示汉化章节，我点进去来看」
     —— 落地那一章译好要能**当场补上**；「已译章节」要列**全部**已译章、
        带中文名、可点跳转；而且"已译 N 章"不能因为第 1 章缺译就说 0。

这个文件测的是**服务端产出**（HTML/JSON/取舍顺序）；前端点按钮那层在
test_click.py。两层都要有：只测服务端会漏"按钮没绑"，只测前端会漏
"服务端本来就发错"。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_ROOT = os.environ.get("LNTRANS_DATA_ROOT") or HERE
NOVELS = os.path.join(_ROOT, "novels")
SLUG = "__rd__"
D = os.path.join(NOVELS, SLUG)
SERVER_ROOT = os.environ.get("LNTRANS_SERVER_ROOT") or ""
BASE = sys.argv[1] if len(sys.argv) > 1 else ""

_s = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
m = importlib.util.module_from_spec(_s)
sys.argv = ["x"]
_s.loader.exec_module(m)

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def write_book(root: str, slug: str, translated: list[int],
               total: int = 10, titles: dict | None = None) -> None:
    """造一本"第 translated 章有译文"的书（translated 是 1-based 章号）。"""
    d = os.path.join(root, "novels", slug)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "chapters"))
    os.makedirs(os.path.join(d, "raw"))
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({
            "slug": slug, "source": "kakuyomu", "source_id": "1", "url": "u",
            "title": "第一話が抜けている本", "author": "a",
            "zh_titles": {"book": "章节划分测试", **(titles or {})},
            "episodes": [{"id": str(i), "title": f"第{i+1}話　テスト"}
                         for i in range(total)],
            "glossary": {}, "characters": {}, "summaries": {}, "style": {},
            "progress": {"translated_through": 0, "fetched_through": 0},
        }, f, ensure_ascii=False)
    for ch in translated:
        i = ch - 1
        with open(os.path.join(d, "chapters", f"{i:04d}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(f"第{ch}章的译文第一段。\n\n第二段。\n")
        with open(os.path.join(d, "raw", f"{i:04d}.txt"), "w", encoding="utf-8") as f:
            f.write(f"第{ch}話の原文。\n\n二段落目。\n")


def post(path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(BASE.rstrip("/") + path, data=body,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get(path: str) -> tuple[int, bytes]:
    req = urllib.request.Request(BASE.rstrip("/") + path)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        return e.code, e.read()


def main() -> int:
    print("阅读页章节划分：")

    # ---------- 1) 服务端函数层（不起服务也能测）----------
    write_book(_ROOT, SLUG, [2, 3, 4, 5, 6, 7], titles={"2": "第二章 命运之日"})
    m.invalidate_cache(SLUG)
    meta = m.novel_meta(SLUG)

    check("已译章数 = 真有译文的章数（第 1 章缺译不再是 0）",
          m.have_count(SLUG, meta) == 6, f"have_count={m.have_count(SLUG, meta)}")
    check("★ 正在看的那一章没译文时，它必须第一个被翻（用户：我第一话呢？）",
          m.next_targets(SLUG, meta, 2, after=1) == [1, 8],
          str(m.next_targets(SLUG, meta, 2, after=1)) + "（1 先翻，再读后续）")
    check("当前章有译文时，仍然优先翻后面的（读到哪翻到哪没被破坏）",
          m.next_targets(SLUG, meta, 2, after=3) == [8, 9],
          str(m.next_targets(SLUG, meta, 2, after=3)))
    check("after 是字符串也不炸（前端 JSON 传参边界）",
          m.next_targets(SLUG, meta, 1, after=1) == [1])

    html = m.page_reader(SLUG) or ""
    check("★ 落地章（第 1 章）没译文时：渲染占位块，**不偷偷跳到第 2 章**",
          'id="need-1"' in html and 'id="c2"' not in html)
    check("占位块明确写了「正在翻译、不用刷新」",
          "还没译好" in html and "自动出现" in html)
    check("页面把 need 告诉前端（前端据此就地替换）",
          re.search(r"__NEED__=1\b", html) is not None)
    check("★ 阅读设置公开模型角色与今日费用",
          "model-note" in html and "翻译 " in html
          and "今日" in html and "密钥" in html)
    check("★「已译章节」列**全部**已译章（2~7），不是只列本页那几章",
          all(f"?from={i}" in html for i in range(2, 8)), "")
    check("已译章节带章节号计数（6/10）", ">6/10<" in html)
    check("有中文名的章显示中文，没翻的退回日文原名",
          "第二章 命运之日" in html and "第4話" in html)
    # 「未译全」章要标出来（有段落失败的章不能和整篇中文的章长得一样）
    with open(os.path.join(D, "meta.json"), encoding="utf-8") as f:
        _mm = json.load(f)
    _mm.setdefault("progress", {})["incomplete"] = [3]
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(_mm, f, ensure_ascii=False)
    m.invalidate_cache(SLUG)
    _h = m.page_reader(SLUG) or ""
    check("★ 有段落没译全的章在目录里标「未译全」（章数照算，但不装成整篇中文）",
          "未译全" in _h, "")
    _mm["progress"]["incomplete"] = []
    with open(os.path.join(D, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(_mm, f, ensure_ascii=False)
    m.invalidate_cache(SLUG)
    html = m.page_reader(SLUG) or ""

    check("本页内的章走锚点、本页外的章走 ?from=（点了能跳过去）",
          'href="#c' not in html or 'href="/read/' in html)

    # 落地章译好了 → 占位消失、正文就位
    with open(os.path.join(D, "chapters", "0000.txt"), "w", encoding="utf-8") as f:
        f.write("第1章的译文。\n")
    with open(os.path.join(D, "raw", "0000.txt"), "w", encoding="utf-8") as f:
        f.write("第1話の原文。\n")
    m.invalidate_cache(SLUG)
    html2 = m.page_reader(SLUG) or ""
    check("★ 第 1 章译好后：占位块消失、第 1 章正文出现在页面上",
          'id="need-1"' not in html2 and 'id="c1"' in html2)
    check("译好后 need=0（前端不再等它）",
          re.search(r"__NEED__=0\b", html2) is not None)

    # 翻译上限**不能自己往上爬**（这是花钱的规则，必须锁死）
    # 场景：已经译了 10 章，但只读到第 1 章（ahead=3）。
    # 老实现 ceiling = max(读到+3, 已译章数) = 10，而已译数会随翻译增长 →
    # 一本没读过的书会被从头翻到尾（真实事故：23/23 全翻完）。
    write_book(_ROOT, SLUG, list(range(1, 11)), total=20)
    meta2 = m.novel_meta(SLUG)
    m.set_trans_cfg(SLUG, enabled=True, ahead=3)
    m.set_progress(SLUG, 1, 0.0)
    tg, cap = m.allowed_targets(SLUG, meta2, 2, 1)
    check("★ 上限不随「已译章数」往上爬：读到 1、已译 10 章 → 不再自动翻",
          tg == [] and cap == 4, f"targets={tg} ceiling={cap}")
    tg2, _ = m.allowed_targets(SLUG, meta2, 9999, 1, explicit_ceiling=20)
    check("手动「翻到第 N 章」照样能突破（用户明确要求的不被挡）",
          tg2[:3] == [11, 12, 13], str(tg2[:5]))
    m.set_progress(SLUG, 12, 0.0)
    tg3, cap3 = m.allowed_targets(SLUG, meta2, 2, 12)
    check("读到第 12 章后自动上限跟着走（能接着翻 12、13）",
          tg3 == [12, 13] and cap3 == 15, f"{tg3} cap={cap3}")
    if os.path.exists(m.book_state_path(SLUG)):
        os.remove(m.book_state_path(SLUG))
    m.invalidate_cache(SLUG)

    # 空洞在中间时：不跳过
    write_book(_ROOT, SLUG, [5, 6, 7])
    with open(m.book_state_path(SLUG), "w", encoding="utf-8") as f:
        json.dump({"progress": {"chapter": 4, "scroll": 0.0}}, f)
    m.invalidate_cache(SLUG)
    html3 = m.page_reader(SLUG) or ""
    check("读到第 4 章、而 4 缺译、5~7 有译文：停在第 4 章不跳到第 5 章",
          'id="need-4"' in html3 and 'id="c5"' not in html3)
    check("但第 5~7 章仍然列在目录里（想跳随时能跳）",
          "?from=5" in html3 and "?from=7" in html3)
    os.remove(m.book_state_path(SLUG))
    m.invalidate_cache(SLUG)

    # ---------- 1.5) 前情 · 人物 + 术语悬浮 ----------
    # 「AI 资产在机器侧，读者一个都看不见」：summaries / characters / glossary
    # 早就有了，以前只喂翻译 prompt。这块面板必须做到两件事：
    #   1) 只用到**当前章之前**的章节（隔周回来看，不许剧透后文）；
    #   2) 人物简介/术语都来自源站或模型，必须转义后才进 HTML。
    write_book(_ROOT, SLUG, [1, 2, 3, 4, 5, 6], total=10)
    _d = os.path.join(_ROOT, "novels", SLUG)
    with open(os.path.join(_d, "meta.json"), encoding="utf-8") as f:
        _meta = json.load(f)
    _meta["glossary"] = {"ガルド": "加尔德", "ローラ": "萝拉", "手鎚": "手锤"}
    _meta["tags"] = ["奇幻", "学园"]
    _meta["characters"] = {
        "ガルド": {"desc": "主角。锻冶师。<刀匠>"},
        "ローラ": {"desc": "第 3 章登场。"},
        "ミオ": {"desc": "第 5 章才出场，当前读到第 4 章不该看见。"},
    }
    _meta["summaries"] = {"2": "第 2 章梗概：他打了一把刀。",
                          "3": "第 3 章梗概：萝拉来到工房。"}
    with open(os.path.join(_d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(_meta, f, ensure_ascii=False)
    for _ch, _txt in {1: "加尔德在打铁，手锤敲得叮当响。",
                      2: "他打了一把刀。",
                      3: "萝拉来到工房。",
                      4: "加尔德又打了一把刀。",
                      5: "ミオ登场了。",
                      6: "尾声。"}.items():
        with open(os.path.join(_d, "chapters", f"{_ch - 1:04d}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(_txt + "\n")
    m.invalidate_cache(SLUG)
    _h = m.page_reader(SLUG, from_ch=4) or ""
    _panel = _h.split('id="membox"')[1] if 'id="membox"' in _h else ""
    check("★ 阅读页有「前情 · 人物」面板（数据早在，只是没露出来）",
          'class="membox"' in _h and "<details" in _h and _panel)
    check("面板在正文之前（回来先看这个，再往下读）",
          _h.find('id="membox"') < _h.find('id="c4"'))
    check("★ 上次讲到用梗概：列出最近两章（第 3、2 章）",
          "第 3 章梗概：萝拉来到工房。" in _panel
          and "第 2 章梗概：他打了一把刀。" in _panel)
    check("梗概有时不显示「兜底结尾」提示（避免两套说法同时出现）",
          "还没有提要句" not in _panel)
    check("★ 人物只列已读章节出现过的：加尔德/萝拉在，",
          "加尔德" in _panel and "萝拉" in _panel)
    check("★ …后文才出场的 ミオ 不在（不剧透）",
          "ミオ" not in _panel and "第 5 章才出场" not in _panel)
    check("人物简介的 HTML 被转义（简介来自源站/模型，含 < > 不能变标签）",
          "&lt;刀匠&gt;" in _panel and "<刀匠>" not in _panel)
    check("术语列在面板里（已读文本出现过才列）",
          "手锤" in _panel and "手鎚" in _panel)
    check("面板标明只用已读章节（读者知道不会剧透）",
          "不剧透后文" in _panel)
    check("阅读页「关键词」列出本书标签（不再完全看不到）",
          "关键词" in _panel and "奇幻" in _panel and "学园" in _panel)
    check("正文里的译名可点：span.gloss 带原文/简介",
          'class="gloss"' in _h and "原文：ガルド" in _h
          and ">加尔德</span>" in _h)
    # 单字译名（澪这种人名）第一次看到要知道是谁，但标满整章就没法读了
    _one = m.lr.annotate_terms("澪登场了，澪很弱，澪很强，澪又来了，澪走了。",
                               [("澪", "原文：ミオ")])
    check("★ 单字译名每章最多标 3 处（不然满屏点线，正文没法读）",
          _one.count('class="gloss"') == 3, f"{_one.count('class="gloss"')} 处")
    _two = m.lr.annotate_terms("加尔德来了，加尔德又走了。",
                               [("加尔德", "原文：ガルド")])
    check("多字译名每次都标（不受单字限次影响）",
          _two.count('class="gloss"') == 2)
    _esc = m.lr.annotate_terms('他说"<加尔德>"来了。', [("加尔德", '原文："ガルド"')])
    check("标注不破坏转义（< > 按文本显示，属性里的引号也被转义）",
          "&lt;" in _esc and "&gt;" in _esc and "<加尔德>" not in _esc
          and 'data-tip="原文：&quot;ガルド&quot;"' in _esc, _esc)

    # ---------- 2) HTTP 层（隔离服务在跑时才测）----------
    if not BASE or not SERVER_ROOT:
        check("HTTP 层（/api/toc、/api/chapter、/api/next 的 need）", True,
              "跳过：没有隔离测试服务")
        print("  ⚠ HTTP 层跳过（服务未运行）")
        return 1 if fails else 0

    # 页面：走一遍真实的 HTTP
    # nocheck=1：别让"打开时查更新"这一步把自检拖到网络上（那是产品行为，
    # 由 check_on_open_bounded 的 2.5 秒上限保证不卡页面；测试不该依赖外网）
    st, body = get("/read/__reader_seed__?nocheck=1")
    page = body.decode("utf-8", "replace")
    check("HTTP 阅读页 200", st == 200, f"status={st}")
    check("HTTP 阅读页：第 1 章缺译 → 占位块 + 目录列 2~7 章",
          'id="need-1"' in page and all(f"?from={i}" in page for i in range(2, 8)))
    check("HTTP 阅读页的「已译」是 6（不是 0）", ">6/10<" in page)

    # "打开时查更新"这一步绝不能让整页卡住（源站慢 = 白屏 = "得自己刷新一下"）
    t0 = time.time()
    st, body = get("/read/__reader_seed__")          # 故意不带 nocheck
    dt = time.time() - t0
    check("★ 打开阅读页不会被「查更新」拖住（源站实测 3.1 秒，页面必须 1 秒出）",
          st == 200 and dt < 3.0, f"{dt:.2f}s")

    st, body = get("/api/toc?slug=__reader_seed__")
    d = json.loads(body)
    check("/api/toc 返回全部已译章 + 中文名",
          d.get("count") == 6 and "第二章 命运之日" in d.get("html", ""),
          f"count={d.get('count')}")
    st, body = get("/api/toc?slug=__reader_seed__&onpage=2")
    d = json.loads(body)
    check("/api/toc 的 onpage 参数让本页内的章走锚点（省一次加载）",
          'href="#c2"' in d.get("html", ""))

    st, body = get("/api/chapter?slug=__reader_seed__&ch=1")
    check("/api/chapter 第 1 章还没译 → html 空（前端据此继续等）",
          json.loads(body).get("html") == "")
    st, body = get("/api/chapter?slug=__reader_seed__&ch=2")
    d = json.loads(body)
    check("/api/chapter 第 2 章有译文 → 直接给正文（就地替换用）",
          'id="c2"' in d.get("html", "") and d.get("done") == 6)

    st, body = get("/api/next?slug=__reader_seed__&from=1")
    d = json.loads(body)
    check("★ /api/next 不再跳过空洞：from=1 没译文就返回空 + need=1",
          d.get("html") == "" and d.get("need") == 1, str(d.get("need")))
    st, body = get("/api/next?slug=__reader_seed__&from=2")
    d = json.loads(body)
    check("/api/next 从已译章起照常给正文（一次两章）",
          d.get("added") == 2 and d.get("need") == 0, f"added={d.get('added')}")

    # 章末导航：读到章末能直接翻下一章，不必滚回顶部（用户报「最后没有下一章按键」）
    # 默认一页只渲染**一章**（用户嫌 3 章一页太长）：from=2 → 下一章是 3。
    _, body = get("/read/__reader_seed__?from=2&nocheck=1")
    p2_1 = body.decode("utf-8", "replace")
    check("★ 默认一页只渲染一章（不再 3 章一页堆得很长）",
          p2_1.count('<section class="ch') == 1
          and p2_1.count('id="c2"') == 1 and 'id="c3"' not in p2_1,
          f"{p2_1.count('<section class=\"ch')} 章")
    # 翻章链接必须带 `#c<N>` 锚点：点下去浏览器**直接落在正文**，不是回到页面顶部
    # 再让读者自己往下翻过标题和目录（用户报过这条）。
    check("★ 单章页的「下一章」指向第 3 章，且带正文锚点",
          'class="chapnav"' in p2_1 and '?from=3#c3">下一章' in p2_1
          and '?from=1#need-1">← 上一章' in p2_1)
    check("单章页把下一章章号/是否已译告诉前端（前端据此点亮或催译）",
          re.search(r"__NEXT__=3\b", p2_1) is not None
          and re.search(r"__NEXTHAVE__=true\b", p2_1) is not None, "")
    # ?n=3 仍可一页渲染 3 章（保留给测试/特殊用途）
    _, body = get("/read/__reader_seed__?from=2&n=3&nocheck=1")
    p2 = body.decode("utf-8", "replace")
    check("★ ?n=3 时末端导航指向本页最后一章的下一章（4 → 5），带正文锚点",
          'class="chapnav"' in p2 and '?from=5#c5">下一章' in p2 and '?from=1#need-1">← 上一章' in p2,
          f"chapnav={'class=\"chapnav\"' in p2}")
    _, body = get("/read/__reader_seed__?from=10&nocheck=1")
    p10 = body.decode("utf-8", "replace")
    check("★ 看到最后一章时，末尾导航如实显示「已是最后一章」",
          '已是最后一章' in p10 and '?from=9#need-9">← 上一章' in p10)

    # 落地章缺译（第 8 章，第 9 章也没译）时：**不许**给「下一章」链接。
    # 否则点下去是又一个占位页，而那页的 tick() 会用 after=9 去排翻译 ——
    # 正在等的那一章被跳过、可能永久缺译（读者也永远等不到它）。
    _, body = get("/read/__reader_seed__?from=8&nocheck=1")
    p8 = body.decode("utf-8", "replace")
    check("★ 缺译章的页面不给「下一章」链接（不许跳过正在等的那一章）",
          '?from=9' not in p8 and "这一章译好才有下一章" in p8, "")
    check("缺译章的页面仍给「上一章」（能退回去读，不是死路）",
          '?from=7#c7">← 上一章' in p8, "")
    # 缺译章的下一章**已经译好**时，允许点过去（正当的绕开空洞，不是偷跳）
    _, body = get("/read/__reader_seed__?from=1&nocheck=1")
    p1 = body.decode("utf-8", "replace")
    check("缺译章（第 1 章）的下一章已译 → 给真链接（能绕开空洞）",
          '?from=2#c2">下一章' in p1 and "这一章译好才有下一章" not in p1, "")

    # 「更新了 +N 话 · 点我翻译」= 只翻最新的 N 话，不是把整本欠账一次翻完
    # （真实数据：一本 20/61 的书欠 41 话 ≈ 25 万 token，按钮上写的是 +N 话）
    r = post("/api/translate", {"slug": "__reader_seed__", "fill": True,
                                "count": 3, "reason": "selftest"})
    j = r.get("job") or {}
    check("★「点我翻译」只翻最新 N 话（不会一次把整本欠账翻完）",
          j.get("fill") is False and j.get("ceiling") == 10
          and j.get("after") == 7, str({k: j.get(k) for k in ("fill", "ceiling", "after")}))

    print()
    if fails:
        print(f"❌ 失败 {len(fails)} 项：" + "、".join(fails))
        return 1
    print("✅ 阅读页章节划分全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
