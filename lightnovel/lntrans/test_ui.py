#!/usr/bin/env python3
"""回归：按钮/前端 JS 完整性（真实 HTTP + 真语法编译）。

**为什么必须有这个测试**：
用户报过三次「按钮点了没反应」，根因都是**生成的内联 JS 语法错误**
（属性引号未转义、替换时把 catch 删掉导致 try 悬空）。
这类 bug 服务端 API 全绿、Python 也 compile OK，
但浏览器整段脚本解析失败 → 所有 handler 失效。

所以这里做两件事：
  1. 把页面里的 <script> 抽出来，交给 Node 的 `new Function()` 编译
     —— 这正是浏览器的解析行为，语法错会直接暴露。
  2. 用真实 HTTP 走一遍状态接口，确认四个标记都能改。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def get(path: str) -> str:
    with urllib.request.urlopen(BASE + path, timeout=25) as r:
        return r.read().decode("utf-8")


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


print("=" * 64)
print("A. 页面内联 JS 必须能被浏览器解析（编译期错误会让所有按钮失效）")
print("=" * 64)

# 阅读页路径不能写死 slug（隔离测试服务里没有真实作品）
_items = []
try:
    _items = json.loads(get("/api/library")).get("items") or []
except Exception:  # noqa: BLE001
    pass
_read_url = f"/read/{_items[0]['slug']}" if _items else None
PAGES = [("书架", "/classic")] + ([("阅读页", _read_url)] if _read_url else [])

for page_name, url in PAGES:
    try:
        html = get(url)
    except Exception as e:  # noqa: BLE001
        check(f"{page_name}可访问", False, str(e))
        continue
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    check(f"{page_name}：有内联脚本", len(scripts) > 0, f"{len(scripts)} 段")
    for i, s in enumerate(scripts):
        if not s.strip():
            continue
        # 用 Node 的 new Function 编译（等价浏览器解析，不执行）
        r = subprocess.run(
            ["node", "-e",
             "const fs=require('fs');"
             "try{new Function(fs.readFileSync(0,'utf8'));"
             "console.log('OK')}catch(e){console.log('ERR '+e.message)}"],
            input=s, capture_output=True, text=True, timeout=30)
        out = (r.stdout or "").strip()
        check(f"{page_name} script[{i}] 可编译", out == "OK", out[:90] or (r.stderr or "")[:90])

if _read_url:
    print()
    print("=" * 64)
    print("A2. 阅读页校对入口（规则不花 token；AI 才显式消耗）")
    print("=" * 64)
    rh = get(_read_url)
    check("有「校对本章」按钮", 'id="review-open"' in rh)
    check("有校对面板", 'id="reviewbox"' in rh and 'id="review-list"' in rh)
    check("规则检查与 AI 校对分开",
          'id="review-rules"' in rh and 'id="review-ai"' in rh)
    check("校对脚本已加载（能提交 /api/review）", "/api/review" in rh)

print()
print("=" * 64)
print("B. try/catch 必须配对（我删 catch 删出过一次）")
print("=" * 64)
html = get("/classic")
js = "".join(re.findall(r"<script>(.*?)</script>", html, re.S))
opens = len(re.findall(r"\btry\s*\{", js))
catches = len(re.findall(r"\}\s*catch\s*\(", js))
check(f"try({opens}) 与 catch({catches}) 数量一致", opens == catches,
      f"try={opens} catch={catches}")

print()
print("=" * 64)
print("C. 卡片按钮必须真的能改状态（真实 HTTP，跑完恢复原状）")
print("=" * 64)
# 注意：这段会**真的改状态**。为了不污染用户数据：
#   · 跑之前记录原状态，跑完精确恢复；
#   · 由 run_selftests.py 指向隔离的测试服务时更安全。
lib = json.loads(get("/api/library"))
if not lib.get("items"):
    print("  （书架为空，跳过）")
else:
    slug = lib["items"][0]["slug"]

    def snapshot():
        it = [i for i in json.loads(get("/api/library"))["items"]
              if i["slug"] == slug]
        return (bool(it[0].get("favorite")), it[0].get("tracking")) if it else (None, None)

    orig_fav, orig_tk = snapshot()
    for action, label in (("finished", "看完"), ("dropped", "弃文"),
                          ("favorite", "收藏")):
        r1 = post("/api/status", {"slug": slug, "action": action, "value": True})
        st1 = json.loads(get("/api/library"))
        it = [i for i in st1["items"] if i["slug"] == slug]
        key = "favorite" if action == "favorite" else "tracking"
        want = True if action == "favorite" else action
        check(f"标记「{label}」生效",
              bool(r1.get("ok")) and bool(it) and it[0].get(key) == want,
              f"api={r1.get('ok')} 状态={it[0].get(key) if it else '-'}")
    # /api/status 必须回传 removed：前端 ACTION_JS 靠它知道"已移出书架"。
    r_rm = post("/api/status", {"slug": slug, "action": "remove", "value": True})
    check("★ 移出书架：/api/status 回传 removed=True（不回传前端就不刷新）",
          bool(r_rm.get("ok")) and r_rm.get("removed") is True, str(r_rm))

    # 恢复原状态
    post("/api/status", {"slug": slug, "action": "favorite",
                         "value": bool(orig_fav)})
    if orig_tk in ("reading", "finished", "dropped", "want"):
        post("/api/status", {"slug": slug, "action": orig_tk, "value": True})
    now_fav, now_tk = snapshot()
    check("测试结束后状态已精确恢复",
          now_fav == orig_fav and now_tk == orig_tk,
          f"原=({orig_fav},{orig_tk}) 现=({now_fav},{now_tk})")

print()
print("=" * 64)
print("C2. ★ 防 UI 重叠（用户报过：提示文字压在按钮上、按钮挤成一行）")
print("=" * 64)
_h = get("/classic")


def css_props(text: str) -> dict:
    """从一段 CSS 里解析属性。先剥掉注释——注释里的 `bottom:12px` 之类
    会污染解析（我自己踩过，导致断言误报）。"""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return dict(re.findall(r"([a-z-]+)\s*:\s*([^;}]*)", text))

# 按钮必须能换行：7 个按钮不换行会横向溢出、被裁切
_i = _h.find(".ctrls{")
check("能找到 .ctrls 规则", _i >= 0)
if _i >= 0:
    _rule = _h[_i:_h.find("}", _i)]
    _rp = css_props(_rule)
    check("★ .ctrls 有 flex-wrap:wrap（否则按钮溢出重叠）",
          _rp.get("flex-wrap") == "wrap", str(_rp.get("flex-wrap")))

# 提示条不能压在按钮行上：应是 top/right 定位 + 有实底 + 不挡点击
_j = _h.find(".toast{")
check("能找到 .toast 规则", _j >= 0)
if _j >= 0:
    _t = _h[_j:_h.find("}", _j)]
    # 只看真正的位置属性，不能用 "bottom:" in 判断（会被 padding-bottom 之类误伤）
    _props = css_props(_t)
    check("★ toast 用 top/right 定位（不能靠 bottom，会压住按钮行）",
          "top" in _props and "right" in _props and "bottom" not in _props,
          str({k: _props[k] for k in ("top", "right", "bottom") if k in _props}))
    check("★ toast 有背景色（无背景会糊在按钮上）", bool(_props.get("background")))
    check("★ toast 设置 pointer-events:none（不挡按钮点击）",
          _props.get("pointer-events", "").strip() == "none", _props.get("pointer-events"))

# 主题/字号等偏好集中在 /settings；各页只留一个入口，别再各自放切换按钮
check("★ 首页有设置入口（/settings）", 'href="/settings"' in _h)
check("★ 首页不再有独立主题按钮（避免和设置页重复）", 'id="theme"' not in _h)

# toast 必须会自动消失（否则一直留在卡片上 = 用户看到的"重叠"）
_js_all = "".join(re.findall(r"<script>(.*?)</script>", _h, re.S))
check("★ flash() 里有定时隐藏（否则提示永不消失）",
      "clearTimeout" in _js_all and "_hide" in _js_all)

print()
print("=" * 64)
print("C2b. ★ 阅读页控件：输入框不被包在按钮里 / 底栏五格 / 反馈入口")
print("=" * 64)
_lib4 = json.loads(get("/api/library"))
_items4 = _lib4.get("items") or []
if not _items4:
    print("  （书架为空，跳过：没有阅读页可验）")
else:
    _slug4 = _items4[0]["slug"]
    _rh = get(f"/read/{urllib.parse.quote(_slug4)}?nocheck=1")

    class _ReaderProbe(HTMLParser):
        """只回答：input 是否在 btn-ceil 里。"""

        VOID = {"input", "img", "br", "meta", "link", "hr", "source"}

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack: list[tuple[str, str]] = []
            self.btn_depth: int | None = None
            self.found_btn = False
            self.input_inside_btn = False

        def handle_starttag(self, tag, attrs):
            d = dict(attrs)
            if tag in self.VOID:
                if tag == "input" and self.btn_depth is not None:
                    self.input_inside_btn = True
                return
            self.stack.append((tag, d.get("id") or ""))
            if tag == "button" and d.get("id") == "btn-ceil":
                self.found_btn = True
                self.btn_depth = len(self.stack)
            if tag == "input" and self.btn_depth is not None:
                self.input_inside_btn = True

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)

        def handle_endtag(self, tag):
            if not self.stack:
                return
            if self.btn_depth is not None and len(self.stack) == self.btn_depth:
                self.btn_depth = None
            self.stack.pop()

    _probe = _ReaderProbe()
    _probe.feed(_rh)
    check("阅读页有「翻到第 N 章」确认按钮", _probe.found_btn)
    check("★ 章数输入框不再嵌在按钮里（点输入框会误触翻译）",
          not _probe.input_inside_btn,
          "input 在 btn-ceil 内部" if _probe.input_inside_btn else "")
    check("★ 章数输入框独立存在", 'id="ceil"' in _rh)
    check("★ 底栏五格：上一章 / 详情 / 目录 / 设置 / 下一章",
          'id="readerbar"' in _rh
          and all(x in _rh for x in ('← 上章', '/book?id=', 'href="#tocbox"',
                                     'id="rb-settings"', '下章 →')))
    check("★ 反馈入口收进设置面板（不再是悬浮球）",
          'id="open-feedback"' in _rh and 'id="fab"' not in _rh
          and 'id="floatdock"' not in _rh)
    check("★ 阅读页不再有独立主题按钮（在 /settings 里）", 'id="theme"' not in _rh)

    _rb_i = _rh.find("#readerbar{")
    check("能找到 #readerbar 规则", _rb_i >= 0)
    if _rb_i >= 0:
        _rb_p = css_props(_rh[_rb_i:_rh.find("}", _rb_i)])
        check("★ 底栏固定定位且避开手机底部安全区",
              _rb_p.get("position") == "fixed"
              and "env(safe-area-inset-bottom)" in _rb_p.get("padding-bottom", ""),
              str({k: _rb_p.get(k) for k in ("position", "padding-bottom")}))
    check("★ 正文给底栏留出高度（不会被最后一行挡住）",
          "body.pg-read main" in _rh and "padding-bottom" in _rh)
    _js4 = "".join(re.findall(r"<script>(.*?)</script>", _rh, re.S))
    check("★ 章数输入框支持回车确认",
          any(k in _js4 for k in
              ("getElementById('ceil').onkeydown",
               'getElementById("ceil").onkeydown',
               "ceilEl.onkeydown")))
    _cn_i = _rh.find(".chapnav{")
    check("★ 章末导航允许换行（320px 窄屏不会横向溢出）",
          _cn_i >= 0
          and css_props(_rh[_cn_i:_rh.find("}", _cn_i)]).get("flex-wrap") == "wrap")
    check("★ 主题选择会记住（刷新/换页不丢）",
          "localStorage.getItem('ln-theme')" in _rh
          and "localStorage.setItem('ln-theme'" in _rh)

print()
print("=" * 64)
print("C3. ★ 卡片不再渲染「来源」（与标签/类型重复，完整标签在详情页）")
print("=" * 64)
# 去重：推荐卡只回答"这是什么、我读到哪"。来源/标签不再单独占一行。
_h3 = get("/classic")
_rec3 = re.search(r"为你推荐(.*?)</details>", _h3, re.S)
_rec3 = _rec3.group(1) if _rec3 else ""
check("★ 推荐卡不再出现「来源：」chip（避免与标签重复）",
      "来源：" not in _rec3, f"推荐位仍出现 {_rec3.count('来源：')} 次")
check("★ 卡片里没有 .chip.src（来源行已移除）",
      'class="chip src"' not in _rec3)
# .chip.src 规则仍保留（别的页面将来要用），但这里验证 .chips 容器能换行：
_c3 = _h3.find(".chips{")
check("★ .chips 容器 flex-wrap:wrap（多 chip 在窄屏换行，不横向溢出）",
      _c3 >= 0 and css_props(_h3[_c3:_h3.find("}", _c3)]).get("flex-wrap") == "wrap")

print()
print("=" * 64)
print("D. 按钮的 data-act 必须与 JS 分支一一对应")
print("=" * 64)
# 状态类是**同一个通用分支**处理的（ACTION_JS 里按 action 名发 /api/status），
# 所以它们不在"显式分支"里是正常的；其余动作必须各有显式分支。
STATE_ACTS = {"favorite", "reading", "finished", "dropped", "off"}
acts_html = set(re.findall(r'data-act="([a-z]+)"', html))
acts_js = set(re.findall(r"act==='([a-z]+)'", js))
check("卡片按钮种类齐全", {"favorite", "finished", "dropped", "check", "autotrans"}
      <= acts_html, str(sorted(acts_html)))
missing = acts_html - acts_js - STATE_ACTS
check("每个 data-act 都有对应 JS 分支（状态类走通用状态分支）", not missing,
      str(sorted(missing)))
# ★ 事件委托必须覆盖全部动作前缀 —— 少一个前缀，那一类按钮就"没人管"
#   （用户报过：不在 .ctrls 里的「更新了·点我翻译」点了完全没反应）
for _attr in ("data-act", "data-d-act", "data-add", "data-d-add",
              "data-want", "data-gopage"):
    check(f"★ 全局委托覆盖 [{_attr}]", f"[{_attr}]" in js)
check("★ 不再在加载时逐个绑 .ctrls button（这就是漏绑的根源）",
      "querySelectorAll('.ctrls button')" not in js)

print()
print("=" * 64)
print("E. ★ 书架筛选 + 「不感兴趣」（隐藏必须真的消失，学习必须真的写画像）")
print("=" * 64)

# E1 筛选条：按钮的 data-f 必须被 JS 全部认领
_fs = re.findall(r'<div class="filters" id="sfilter">(.*?)</div>', html, re.S)
_fs = _fs[0] if _fs else ""
_fkeys = set(re.findall(r'data-f="([a-z]+)"', _fs))
check("筛选条有按钮", len(_fkeys) > 0, str(sorted(_fkeys)))
check("覆盖 全部/收藏/在读/想读/未开始/看完/弃文",
      {"all", "fav", "reading", "want", "new", "finished", "dropped"} <= _fkeys,
      str(sorted(_fkeys)))
for _k in sorted(_fkeys - {"all"}):
    check(f"筛选键「{_k}」在 JS 里有分支", f"'{_k}'" in js or f"==='{_k}'" in js)

# E2 筛选必须**只在书架面板内**生效
# 踩过：原来全局 querySelectorAll('.card')，在书架搜索框打字会把
# 推荐卡/书库卡一起 display:none，切过去就是一片空白。
check("★ 筛选/搜索限定在 #pane-shelf 内（不能全局隐藏其它面板的卡）",
      "getElementById('pane-shelf')" in js and
      "pane.querySelectorAll('.card')" in js,
      "见 applyShelfFilter")
check("★ 筛选后分组计数跟着变成「显示 / 总数」（数字不能骗人）",
      "' / '" in js and "data-shelfkey" in html)
check("书架分组带 data-shelfkey（筛选要按组开关）", "data-shelfkey" in html)

# E3 「不感兴趣」：按钮 + JS 分支 + 原因菜单
_dis_html = set(re.findall(r'data-dislike="([^"]+)"', html))
check("卡片上有「不感兴趣」按钮", len(_dis_html) > 0, f"{len(_dis_html)} 个")
for _r in ("meh", "theme", "cliche"):
    check(f"原因菜单含「{_r}」", f'data-r="{_r}"' in js)
check("★ 菜单吞掉点击（否则冒泡到卡片会跳进阅读页）",
      "m.onclick" in js and "stopPropagation" in js)
check("★ 旧的「✕ 隐藏」已并入不感兴趣（只隐藏不学画像 = 白点）",
      "data-hide" not in html)

# E4 真打接口：隐藏必须真的从推荐里消失，学习必须真的改画像。
# 这一段会**写画像**，所以只在隔离测试服务上跑（run_selftests.py 会设这个变量）。
if not os.environ.get("LNTRANS_TEST_SERVER"):
    print("  ⚠ 不是隔离测试服务（缺 LNTRANS_TEST_SERVER），跳过写画像的检查")
else:
    _before = json.loads(get("/api/recs")).get("items") or []
    _target = None
    for _c in _before:
        if _c.get("tags"):
            _target = _c
            break
    if not _target:
        print("  （推荐缓存为空，跳过）")
    else:
        _tid = str(_target.get("id"))
        _r1 = post("/api/dislike", {"id": _tid, "reason": "theme"})
        check("★ /api/dislike 返回成功", bool(_r1.get("ok")), str(_r1))
        check("★ 「不感兴趣」真的改了画像", (_r1.get("learned") or 0) > 0,
              f"调整 {_r1.get('learned')} 处 {str(_r1.get('changes'))[:120]}")
        _after = json.loads(get("/api/recs")).get("items") or []
        check("★ 隐藏后不再出现在推荐列表",
              _tid not in [str(x.get("id")) for x in _after],
              f"前 {len(_before)} → 后 {len(_after)}")
        try:
            _libp = json.loads(get("/api/library"))
            _found = [x for x in (_libp.get("items") or [])
                      if str(x.get("id")) == _tid]
            check("★ 隐藏后也不再出现在书库列表",
                  not _found, f"still={bool(_found)}")
        except Exception as e:  # noqa: BLE001
            check("书库接口可读", False, str(e))
        # 同一本只学一次：重复点不能反复扣分（否则标签会被越扣越低）
        _r2 = post("/api/dislike", {"id": _tid, "reason": "theme"})
        check("★ 同一本重复点不会重复扣分",
              bool(_r2.get("ok")) and (_r2.get("learned") or 0) == 0,
              str(_r2.get("note"))[:80])
        # 不在书库档案里的 id：别假装已经永久屏蔽了，要如实回答
        _r3 = post("/api/dislike", {"id": "definitely-not-a-real-id",
                                    "reason": "cliche"})
        check("未知 id 如实回答「没真正屏蔽」而不是假装成功",
              bool(_r3.get("ok")) and _r3.get("hidden") is False,
              str(_r3.get("note"))[:70])

        # ★ 「太套路了」只该扣套路标签，绝不能连带扣有辨识度的标签
        # （把 勘違い/悪役令嬢 这种"误解系"偏好扣掉就是在教坏画像）
        _lfdir = os.environ.get("LNTRANS_LNFINDER") or ""
        _prof = {}
        try:
            with open(os.path.join(_lfdir, "taste_profile.json"),
                      encoding="utf-8") as _f:
                _prof = json.load(_f)
        except Exception:  # noqa: BLE001
            _prof = {}
        _formula = set((_prof.get("formula_tags") or {}).keys())
        if not _formula:
            print("  （读不到画像/没有套路标签表，跳过「太套路」归因检查）")
        else:
            _t2 = None
            for _c in (json.loads(get("/api/recs")).get("items") or []):
                _tg = set(_c.get("tags") or [])
                if _tg & _formula and _tg - _formula:
                    _t2 = _c
                    break
            if not _t2:
                print("  （没有同时含套路/非套路标签的书，跳过）")
            else:
                _r4 = post("/api/dislike", {"id": str(_t2.get("id")),
                                            "reason": "cliche"})
                _chg = _r4.get("changes") or []
                # 变更行格式是 f"  {tag}  {旧:5.2f} → {新:5.2f}"
                # （空格宽度不固定，所以两侧都要 \s*）
                _names = [re.sub(r"\s+[\d.]+\s*→\s*[\d.]+$", "", c).strip()
                          for c in _chg]
                _bad = [n for n in _names if n not in _formula]
                check("★「太套路了」只扣套路标签，不误伤有辨识度的标签",
                      bool(_chg) and not _bad,
                      f"扣了 {_names}；越界的 {_bad}")

    # ★ 收尾：把隐藏的都放回去。
    # 隔离服务是**所有测试共用**的，一个测试改了共享状态不还原，
    # 后面的测试就会莫名其妙地失败（test_detail 曾因此拿不到详情缓存 → 报"没有目录"）。
    for _hid in list(_dis_html):
        try:
            post("/api/hide", {"id": _hid, "value": False})
        except Exception:  # noqa: BLE001
            pass
    _restored = [str(x.get("id")) for x in
                 (json.loads(get("/api/recs")).get("items") or [])]
    check("★ 测试结束后推荐列表已还原（共享服务不能被上一个测试改脏）",
          len(_restored) >= len(_before), f"还原后 {len(_restored)} 本")

print()
print("=" * 64)
print("F. 畸形数字参数不能把请求打成 500（JSON 接口要给可解析的回复）")
print("=" * 64)
try:
    _j = json.loads(get("/api/library?page=abc"))
    check("★ /api/library?page=abc 仍返回 JSON", _j.get("ok") is True,
          str(_j)[:80])
except Exception as e:  # noqa: BLE001
    check("★ /api/library?page=abc 仍返回 JSON", False,
          f"{type(e).__name__}: {e}")
finally:
    try:
        get("/api/library?page=1")       # 别把共享服务的页码留在脏值
    except Exception:  # noqa: BLE001
        pass

try:
    _j = json.loads(get("/api/next?slug=__nope__&from=abc"))
    check("★ /api/next?from=abc 仍返回 JSON", "html" in _j, str(_j)[:80])
except Exception as e:  # noqa: BLE001
    check("★ /api/next?from=abc 仍返回 JSON", False,
          f"{type(e).__name__}: {e}")

try:
    _j = post("/api/translate", {"slug": "__nope__", "count": "abc"})
    check("★ /api/translate count=abc 不 500（按作品不存在处理）",
          _j.get("ok") is False, str(_j)[:80])
except Exception as e:  # noqa: BLE001
    check("★ /api/translate count=abc 不 500（按作品不存在处理）", False,
          f"{type(e).__name__}: {e}")

for _path, _label in (("/api/feedback", "反馈"),
                      ("/api/progress", "阅读进度")):
    try:
        _j = post(_path, {"slug": "__no_such_book__", "chapter": 1,
                          "vote": "good"})
        check(f"★ 不存在的作品不能写{_label}（否则会生成 data/books/.json 垃圾）",
              _j.get("ok") is False, str(_j)[:80])
    except Exception as e:  # noqa: BLE001
        check(f"★ 不存在的作品不能写{_label}", False,
              f"{type(e).__name__}: {e}")

print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("✅ UI 回归全部通过")
