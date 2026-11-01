#!/usr/bin/env python3
"""作品详情页测试。

用户报：「书库的书点了没用，至少要点进去有简介，有标签之类的吧。」

所以这里测的是**一个合格的轻小说作品页该回答的问题**：
  1. 讲什么？            → 简介
  2. 什么类型 / 写给谁？ → 标签、分类
  3. 多长、完结没、口碑？→ 话数、字数、积分、状态
  4. 我读到哪了？        → 进度 + 目录
  5. 下一步做什么？      → 加入书架 / 开始阅读 / 去源站

分两层：
  · 离线：`extract_work_page()` 用**合成 fixture** 测解析契约
    （不依赖真实站点，网络挂了也能跑）
  · 在线：打隔离测试服务，确认页面真的渲染出这些内容
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
_s = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
m = importlib.util.module_from_spec(_s)
sys.argv = ["x"]
_s.loader.exec_module(m)

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def get(path: str) -> str:
    with urllib.request.urlopen(BASE + path, timeout=45) as r:
        return r.read().decode("utf-8")


# ---------------------------------------------------------------- 离线
print("=" * 66)
print("A. 解析契约：从作品页抽出 简介 + 目录（离线合成 fixture）")
print("=" * 66)

APOLLO = {
    "Chapter:100": {"id": "100", "level": 1, "title": "第一章　始まり"},
    "Episode:1": {"id": "1", "title": "第1話　出会い", "publishedAt": "2026-01-02T03:04:05Z"},
    "Episode:2": {"id": "2", "title": "第2話　別れ", "publishedAt": "2026-01-03T03:04:05Z"},
    "TableOfContentsChapter:200": {
        "id": "200", "chapter": {"__ref": "Chapter:100"},
        "episodeUnions": [{"__ref": "Episode:1"}, {"__ref": "Episode:2"}],
    },
}
FIXTURE = (
    '<html><head>'
    '<meta property="og:description" content="これは&amp;テスト用のあらすじです。">'
    '<meta name="description" content="フォールバック用">'
    '</head><body>'
    '<script id="__NEXT_DATA__" type="application/json">'
    + json.dumps({"props": {"pageProps": {"__APOLLO_STATE__": APOLLO}}},
                 ensure_ascii=False)
    + '</script></body></html>'
)

got = m.extract_work_page(FIXTURE)
check("抽出简介", got["synopsis"] == "これは&テスト用のあらすじです。", got["synopsis"])
check("HTML 实体被还原（&amp; → &）", "&amp;" not in got["synopsis"])
check("抽出一章", len(got["toc"]) == 1, str(len(got["toc"])))
check("章标题正确", got["toc"][0]["title"] == "第一章　始まり", got["toc"][0]["title"])
check("话数正确", len(got["toc"][0]["episodes"]) == 2)
check("话标题正确", got["toc"][0]["episodes"][0]["title"] == "第1話　出会い")
check("话日期被截成 YYYY-MM-DD", got["toc"][0]["episodes"][0]["at"] == "2026-01-02",
      got["toc"][0]["episodes"][0]["at"])
check("episode_count 正确", got.get("episode_count") == 2, str(got.get("episode_count")))

# 只有 description（没有 og:description）时也要能兜住
noog = FIXTURE.replace('property="og:description"', 'property="og:x"')
check("没有 og:description 时用 description 兜底",
      "フォールバック用" in m.extract_work_page(noog)["synopsis"])

# 页面结构变化时不能抛异常，只能少给数据
check("没有 __NEXT_DATA__ 时不抛异常（只少目录）",
      m.extract_work_page("<html><head></head></html>")["toc"] == [])
check("完全空的输入不抛异常", m.extract_work_page("")["synopsis"] == "")

# ---------------------------------------------------------------- 失败标记
print()
print("=" * 66)
print("A2. * 译不出标记的重试与清除（zh_title_failed / zh_syn_failed）")
print("=" * 66)
# 旧版本只置位不清理：重试成功后 zh_title 与 zh_title_failed 会同时存在，
# 语义自相矛盾（现在 UI 只看成功字段才没露馅，但任何"看 failed"的逻辑都会误判）。
_RETRY_WID = "__zh_retry_probe__"
_orig_llm = m.lt.call_llm


def _stub_llm_reply(title_line, syn_line):
    def _f(*_a, **_k):
        return (f"T: {title_line}\nS: {syn_line}", {})
    return _f


try:
    # 先造一条"上次译不出"的旧记录
    m.save_detail(_RETRY_WID, {"zh_title_failed": True, "zh_syn_failed": True})
    m.lt.call_llm = _stub_llm_reply("中文书名", "这是中文简介。")
    _d = m.translate_one(_RETRY_WID, "原題", "あらすじ")
    check("★ 重试成功 → 清掉 zh_title_failed",
          not _d.get("zh_title_failed"), str(_d.get("zh_title_failed")))
    check("★ 重试成功 → 清掉 zh_syn_failed",
          not _d.get("zh_syn_failed"), str(_d.get("zh_syn_failed")))
    check("★ 重试成功 → 拿到中文标题/简介",
          _d.get("zh_title") == "中文书名" and bool(_d.get("zh_synopsis")),
          f"{_d.get('zh_title')} / {_d.get('zh_synopsis')}")

    # 仍然译不出时，失败标记必须继续留着（防"顺手清掉"改成无脑 pop）
    m.save_detail(_RETRY_WID, {})
    m.lt.call_llm = _stub_llm_reply("原題", "あらすじ")   # 标题=原名、简介=日文
    _d2 = m.translate_one(_RETRY_WID, "原題", "あらすじ")
    check("★ 仍译不出 → 继续记 zh_title_failed / zh_syn_failed",
          bool(_d2.get("zh_title_failed")) and bool(_d2.get("zh_syn_failed")),
          f"{_d2.get('zh_title_failed')}/{_d2.get('zh_syn_failed')}")
    check("★ 译不出时不许把原文当译文落盘",
          not _d2.get("zh_title") and not _d2.get("zh_synopsis"))
finally:
    m.lt.call_llm = _orig_llm

# ---------------------------------------------------------------- 标签页数字
print()
print("=" * 66)
print("A3. * 标签页「找到 N 本」必须与实际渲染的卡数同源")
print("=" * 66)
_orig_cached = m.recs.cached
_orig_lib = m.recs._load_lib


def _tag_pool(n):
    return [{"id": str(i), "title": f"标签书{i}", "tags": ["異世界"],
             "points": 1000 - i} for i in range(n)]


try:
    m.recs._load_lib = lambda: {}
    m.recs.cached = lambda *a, **k: _tag_pool(80)
    _h = m.page_tags("異世界")
    check("★ 超过 60 本 → 文案标注『显示前 60 本』",
          "找到 80 本" in _h and "显示前 60 本" in _h, _h[:160])
    check("★ 实际渲染卡片数 = 60（不是 80）",
          _h.count("data-rid=") == 60, f"{_h.count('data-rid=')}")
    m.recs.cached = lambda *a, **k: _tag_pool(40)
    _h2 = m.page_tags("異世界")
    check("★ 未截断时不写『显示前』", "找到 40 本" in _h2 and "显示前" not in _h2,
          _h2[:160])
finally:
    m.recs.cached = _orig_cached
    m.recs._load_lib = _orig_lib

# ---------------------------------------------------------------- 详情目录数字
print()
print("=" * 66)
print("A4. * 详情页分卷「N 话」必须与实际列出的条目数同源")
print("=" * 66)
_orig_refresh = m.refresh_detail
_orig_cached2 = m.recs.cached
_orig_lib2 = m.recs._load_lib
try:
    m.recs._load_lib = lambda: {}
    m.recs.cached = lambda *a, **k: [
        {"id": "toc-big", "title": "大目录书", "url": "https://example.invalid/x",
         "episodes": 450, "tags": []}]
    m.refresh_detail = lambda wid, url: {
        "toc": [{"title": "第一卷", "episodes": [
            {"title": f"第{i+1}話", "at": ""} for i in range(450)]}],
        "episode_count": 450, "synopsis": "测试"}
    _h = m.page_detail("toc-big") or ""
    check("★ 单卷 >400 话 → 标注『显示前 400』",
          "450 话 · 显示前 400" in _h, _h[:200])
    check("★ 实际目录条目数 = 400（不是 450）",
          _h.count('class="epn"') == 400, f"{_h.count('class=\"epn\"')}")
    check("★ 大目录默认折叠（130 话不会把手机详情页撑到一万像素）",
          'class="shelf" open' not in _h)
    m.refresh_detail = lambda wid, url: {
        "toc": [{"title": "短卷", "episodes": [
            {"title": f"第{i+1}話", "at": ""} for i in range(50)]}],
        "episode_count": 50, "synopsis": "测试"}
    _h2 = m.page_detail("toc-big") or ""
    check("★ 未截断的分卷不写『显示前』",
          "50 话</span>" in _h2 and "显示前" not in _h2, _h2[:200])
finally:
    m.refresh_detail = _orig_refresh
    m.recs.cached = _orig_cached2
    m.recs._load_lib = _orig_lib2

# ---------------------------------------------------------------- 在线
print()
print("=" * 66)
print("B. 页面真的渲染出这些内容（真实 HTTP）")
print("=" * 66)
try:
    lib = json.loads(get("/api/library"))
    ids = [i.get("lib_id") or i.get("id") for i in (lib.get("items") or [])]
except Exception as e:  # noqa: BLE001
    print(f"  （拿不到书库：{e}，跳过）")
    ids = []

# 隔离服务的书库是种子书；推荐缓存里有真实作品
WID = None
try:
    recs = json.loads(get("/api/recs"))
    items = recs.get("items") or []
    # 固定用种子作品：别的测试会改共享服务上的状态（隐藏 / 加书架），
    # 用 items[0] 就会随测试顺序漂移 —— 曾因此在整套跑时报「没有目录」，
    # 单独跑却通过（典型的共享状态耦合，别让它再发生）。
    _prefer = [i for i in items if str(i.get("id")) == "999000111"]
    _pick = _prefer or items
    if _pick:
        WID = str(_pick[0].get("id"))
except Exception:  # noqa: BLE001
    pass
if not WID:
    print("  （没有推荐缓存，跳过在线部分）")
else:
    # 注意变量名要用 `_html`：B2 段读的就是 `_html`。
    # 踩过：这里写的是 `html`，而 B2 读 `_html` → NameError。
    # 之前一直没暴露，是因为 /api/recs 只有 POST，GET 拿不到 WID，
    # 整段（含 B2）被跳过 —— 假绿藏了一个真 bug。
    _html = get(f"/book?id={urllib.parse.quote(WID)}")
    check("详情页能打开（不再是点了没用）", len(_html) > 2000, f"{len(_html)} 字节")
    check("★ 有标题 <h1>", bool(re.search(r"<h1>[^<]+</h1>", _html)))
    check("★ 有作者", bool(re.search(r'<div class="kicker">[^<]+</div>', _html)))
    check("★ 有简介区块", "简介" in _html and 'class="syn"' in _html)
    syn = re.search(r'<div class="syn">(.*?)</div>', _html, re.S)
    check("★ 简介不是空的",
          bool(syn) and len(re.sub(r"<[^>]+>", "", syn.group(1)).strip()) > 5,
          (syn.group(1)[:60] if syn else "-"))
    check("★ 有标签（可点进同类书）", 'class="chip tag"' in _html,
          f"{_html.count('chip tag')} 个")
    check("★ 有分类/话数/字数等元信息", _html.count('class="chip') >= 4,
          f"{_html.count('class=\"chip')} 个 chip")
    check("★ 有目录", 'class="toc"' in _html,
          f"{_html.count('<li><span class=\"epn\">')} 话")
    check("★ 有『在源站查看』链接", "在源站查看" in _html)
    check("★ 有下一步动作（加入书架 或 阅读）",
          "data-d-add" in _html or "data-d-act" in _html or "开始阅读" in _html)

    # 标签页
    t = get("/tags?q=" + urllib.parse.quote("百合"))
    check("标签页能打开", "按标签找书" in t or "「" in t)
    check("标签页显示命中数量", bool(re.search(r"找到 \d+ 本", t)),
          (re.search(r"找到 \d+ 本", t) or [""])[0] if re.search(r"找到 \d+ 本", t) else "")

print()
print("=" * 66)
print("B2. * 详情页 JS 必须能编译（语法错会让所有按钮失效，害过三次）")
print("=" * 66)
if WID:
    _scripts = re.findall(r"<script>(.*?)</script>", _html, re.S)
    check("详情页有内联脚本", len(_scripts) > 0, f"{len(_scripts)} 段")
    import subprocess
    for _i, _s in enumerate(_scripts):
        if not _s.strip():
            continue
        _r = subprocess.run(
            ["node", "-e",
             "const fs=require('fs');try{new Function(fs.readFileSync(0,'utf8'));"
             "console.log('OK')}catch(e){console.log('ERR '+e.message)}"],
            input=_s, capture_output=True, text=True, timeout=30)
        _o = (_r.stdout or "").strip()
        check(f"详情页 script[{_i}] 可编译", _o == "OK", _o[:80])
    _alljs = "".join(_scripts)
    check("try/catch 配对",
          len(re.findall(r"\btry\s*\{", _alljs)) == len(re.findall(r"\}\s*catch\s*\(", _alljs)))

print()
print("=" * 66)
print("B3. * 中文优先的标题层级（用户要求：中文大、日文小且透明）")
print("=" * 66)
if WID:
    # 翻译接口存在且可用（用未译的 id 触发一次）
    _fresh = None
    try:
        _recs = json.loads(get("/api/recs"))
        for _it in _recs.get("items") or []:
            _wid2 = str(_it.get("id"))
            _st = json.loads(get(f"/api/trstate?id={urllib.parse.quote(_wid2)}"))
            if not _st.get("zh_synopsis"):
                _fresh = _wid2
                break
    except Exception:  # noqa: BLE001
        _fresh = None

    if _fresh:
        _r = urllib.request.Request(
            BASE + "/api/translate_meta",
            data=json.dumps({"id": _fresh}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(_r, timeout=60) as _resp:
            _j = json.loads(_resp.read().decode())
        check("★ 翻译接口可用", bool(_j.get("ok")), str(_j)[:90])
        check("★ 返回排队/完成状态",
              _j.get("status") in ("queued", "running", "done"), str(_j.get("status")))
    else:
        print("  （所有作品都已翻译，跳过触发测试）")

    # 已有中文的作品：检查层级
    _tr = None
    try:
        _recs = json.loads(get("/api/recs"))
        for _it in _recs.get("items") or []:
            _wid3 = str(_it.get("id"))
            _st = json.loads(get(f"/api/trstate?id={urllib.parse.quote(_wid3)}"))
            if _st.get("zh_title") and _st.get("zh_synopsis"):
                _tr = _wid3
                break
    except Exception:  # noqa: BLE001
        _tr = None
    if _tr:
        _h = get(f"/book?id={urllib.parse.quote(_tr)}")
        _h1 = re.search(r"<h1>([^<]*)</h1>", _h)
        _sub = re.search(r'<div class="jp-sub">([^<]*)</div>', _h)
        check("★ 主标题是中文（h1）",
              bool(_h1) and any("\u4e00" <= c <= "\u9fff" for c in _h1.group(1)),
              (_h1.group(1)[:50] if _h1 else "-"))
        check("★ 日文原名在副标题里（小字）", bool(_sub),
              (_sub.group(1)[:50] if _sub else "无 .jp-sub"))
        if _h1 and _sub:
            check("★ 中文与日文不是同一个串",
                  _h1.group(1).strip() != _sub.group(1).strip())
        check("★ 有中文简介", 'class="syn"' in _h)
        check("★ 日文原文可展开查看（details）",
              "看日文原文" in _h and 'class="syn jp"' in _h)
        check("★ 有中文简介后不再显示『译成中文』按钮", 'id="d-tr"' not in _h)
        check("★ .jp-sub 有样式（要做到小 + 半透明）",
              ".jp-sub" in _h)
        _css2 = re.search(r"<style>(.*?)</style>", _h, re.S)
        if _css2:
            _jp_rule = re.search(r"\.jp-sub\{([^}]*)\}", _css2.group(1))
            check("★ .jp-sub 设置了 opacity（半透明）",
                  bool(_jp_rule) and "opacity" in _jp_rule.group(1),
                  (_jp_rule.group(1)[:80] if _jp_rule else "无规则"))
    else:
        print("  （还没有已翻译的作品，跳过层级检查）")

print()
print("=" * 66)
print("B4. * 推荐列表直接显示中文（用户要求：不用点进去就能看见翻译）")
print("=" * 66)
_home = get("/classic")
if "card rec" in _home:
    _css_home = re.search(r"<style>(.*?)</style>", _home, re.S)
    _css_home = _css_home.group(1) if _css_home else ""
    _cards = _home.count('class="card rec"')
    check("推荐卡片存在", _cards > 0, f"{_cards} 张")

    # 中文标题应当出现在卡片主标题位（.t），日文退到 .jp-sub
    _titles = re.findall(r'<div class="t">([^<]*)</div>', _home)
    _subs = re.findall(r'<div class="jp-sub">([^<]*)</div>', _home)
    _zh_titles = [t for t in _titles
                  if any("\u4e00" <= c <= "\u9fff" for c in t)]
    check("★ 卡片主标题出现中文（不是只有日文）", len(_zh_titles) > 0,
          f"{len(_zh_titles)}/{len(_titles)} 个是中文")
    check("★ 有日文副标题（原名保留）", len(_subs) > 0, f"{len(_subs)} 个")

    # 中文简介摘要
    _syns = re.findall(r'<div class="card-syn[^"]*">([^<]*)</div>', _home)
    check("★ 卡片上有中文简介摘要", len(_syns) > 0, f"{len(_syns)} 条")
    if _syns:
        check("★ 摘要被截断到合理长度（不是整篇）",
              all(len(s) <= 90 for s in _syns),
              f"最长 {max(len(s) for s in _syns)} 字")

    # 层级：中文标题要比日文副标题大、且日文更透明
    _t_rule = re.search(r"\.card \.t\{([^}]*)\}", _css_home)
    _s_rule = re.search(r"\.card \.jp-sub\{([^}]*)\}", _css_home)
    check("★ .card .t 有样式", bool(_t_rule))
    check("★ .card .jp-sub 有样式且更透明/更小", bool(_s_rule),
          (_s_rule.group(1)[:70] if _s_rule else "无"))

    # 译不出时要说明原因，而不是显示"未翻译"
    check("卡片能区分『翻译中/译不出/未翻译』",
          ("翻译中" in _home) or ("未翻译" in _home) or ("译不出" in _home)
          or (len(_zh_titles) == len(_titles)),
          "（全部已翻，无需提示）")

    # 自动补翻的接口存在
    _bs = urllib.request.Request(BASE + "/api/batchstate", data=b"{}",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(_bs, timeout=30) as _r:
        _bj = json.loads(_r.read().decode())
    check("★ 批量翻译状态接口可用", bool(_bj.get("ok")), str(_bj)[:70])
    check("★ 状态收敛（pending 不会永远挂着）",
          _bj.get("pending", 0) == 0 or _bj.get("done", 0) > 0, str(_bj))
else:
    print("  （没有推荐卡，跳过）")

print()
print("=" * 66)
print("B5. * 书库列表也要中文优先 + 状态 chip（和推荐卡共用同一套渲染）")
print("=" * 66)
if "pane-lib" in _home:
    _i = _home.find('id="pane-lib"')
    _lib = _home[_i:]
    _j = _lib.find('class="pane"', 10)
    if _j > 0:
        _lib = _lib[:_j]
    _lt = re.findall(r'<div class="t">([^<]*)</div>', _lib)
    _lzh = [x for x in _lt if any("\u4e00" <= c <= "\u9fff" for c in x)]
    check("书库有卡片", len(_lt) > 0, f"{len(_lt)} 张")
    check("★ 书库主标题是中文", len(_lzh) > 0, f"{len(_lzh)}/{len(_lt)}")
    check("★ 书库也有日文副标题",
          len(re.findall(r'class="jp-sub"', _lib)) > 0)
    check("★ 书库也有中文简介摘要",
          len(re.findall(r'class="card-syn', _lib)) > 0)
else:
    print("  （没有书库面板，跳过）")

# 状态 chip：直接调生产函数，构造一个"在跟的书"。
# **不要写死某个作品的 slug**：换台机器/换一本书就永远跳过这条断言，
# 而且会把"某人读过哪本书"写进代码里带出去。改成从服务端现取一个。
_slugs = []
try:
    _slugs = [it.get("slug") for it in
              (json.loads(get("/api/library")).get("items") or []) if it.get("slug")]
except Exception:  # noqa: BLE001
    pass
# 本进程的数据根是**空的**（runner 给每个测试单独一个根），而服务用的是另一个根。
# 不把这两个目录指过去，`novel_meta()` 永远返回 None → 下面三条断言永远"跳过" ——
# 那是最坏的一种绿：看起来通过，其实一句都没验证（这三条正是 chips/head 的共用渲染，
# 用户为它报过两次 bug，最不该假装测过）。
_srv_root = os.environ.get("LNTRANS_SERVER_ROOT")
if _srv_root:
    # 注意：只改 DATA 不够 —— `DETAIL_DIR` 是**导入时**由 DATA 算出来的模块级常量，
    # 后面再改 DATA 它也不会跟着变（踩过：以为指过去了，其实 load_detail 还在读空目录）。
    # 凡是"从 DATA/NOVELS 派生的模块级常量"都要一起改。
    m.NOVELS = os.path.join(_srv_root, "novels")
    m.DATA = os.path.join(_srv_root, "data")
    m.DETAIL_DIR = os.path.join(m.DATA, "details")
    m.HISTORY_PATH = os.path.join(m.DATA, "history.jsonl")
# 优先挑**有中文标题**的那本：`work_head` 的"中文大标题 + 日文小字副标题"
# 只有译过名的书才渲染得出来。随便挑一本日文原名书来测，会误报成产品 bug。
_mm = None
for _sl in _slugs:
    try:
        _cand = m.novel_meta(_sl)
    except Exception:  # noqa: BLE001
        _cand = None
    if not _cand:
        continue
    if _mm is None:
        _mm = _cand                      # 兜底：至少要有一本，否则下面会如实跳过
    if (_cand.get("zh_titles") or {}).get("book") or _cand.get("title_zh"):
        _mm = _cand
        break
if _mm:
    _fake = {"id": str(_mm.get("source_id")), "title": _mm.get("title"),
             "on_shelf": True, "url": _mm.get("url"), "tags": []}
    _chips = m.work_status_chips(_fake)
    check("★ 在跟的书显示状态 chip", 'class="chip' in _chips, _chips[:90])
    # 不能只断言"含『已译』"——"已译 0 章"也含这两个字，那是句废话（假绿）。
    # 种的书有 3 章译文，就必须真的是 3。
    _mtr = re.search(r"已译 (\d+) 章", _chips)
    _status_slug = m._slug_index().get(str(_mm.get("source_id") or ""), "")
    _status_have = (m.have_count(_status_slug, m.novel_meta(_status_slug) or {})
                    if _status_slug else -1)
    _chapter_dir = os.path.join(m.NOVELS, _status_slug, "chapters")
    _chapter_files = (sorted(os.listdir(_chapter_dir))
                      if os.path.isdir(_chapter_dir) else [])
    check("★ 显示已译章数（且数字是真的是 3，不是『已译 0 章』也过）",
          bool(_mtr) and int(_mtr.group(1)) == 3,
          (_mtr.group(0) if _mtr else "没渲染出章数")
          + f" / slug={_status_slug} have={_status_have}"
          + f" files={_chapter_files} / " + _chips)
    _head = m.work_head(_fake)
    check("★ 共用 head 输出中文标题 + 日文副标题",
          'class="jp-sub"' in _head and "zh" not in _head, _head[:80])
else:
    print("  （服务里还没有任何作品，跳过状态 chip 检查）")

# 样式：状态 chip 的四种 class 都要有定义
_css3 = re.search(r"<style>(.*?)</style>", _home, re.S)
_css3 = _css3.group(1) if _css3 else ""
for _c in ("chip.ok", "chip.fav", "chip.tk", "chip.tr"):
    check(f".{_c} 有样式", f".{_c}" in _css3)

print()
print("=" * 66)
print("B6. * 「接着读」入口（老读者打开就想继续，不该自己找书）")
print("=" * 66)
if 'class="resume"' in _home:
    _r = _home[_home.find('class="resume"'):]
    _r = _r[:_r.find("</div></div>") + 12]
    _bt = re.search(r'rs-b">([^<]*)', _r)
    _ss = re.search(r'rs-s">([^<]*)', _r)
    _lnk = re.findall(r'class="lnkbtn[^"]*" href="([^"]*)"', _r)
    check("★ 显示书名", bool(_bt) and len(_bt.group(1)) > 2,
          (_bt.group(1)[:44] if _bt else "-"))
    check("★ 说明上次读到第几章",
          bool(_ss) and "上次读至第" in _ss.group(1),
          (_ss.group(1) if _ss else "-"))
    check("★ 有继续阅读链接", any("/read/" in x for x in _lnk), str(_lnk))
    check("★ 有作品详情链接", any("/book?id=" in x for x in _lnk), str(_lnk))
    check("★ 继续阅读直接跳到下一章（不是章首）",
          any(re.search(r"from=\d+", x) for x in _lnk), str(_lnk))
else:
    print("  （没有在读的书，跳过）")

print()
print("=" * 66)
print("B7. ★ 相似作品（详情页是「要不要读」的决策点，读者下一句就是「有类似的吗」）")
print("=" * 66)

# —— 先离线钉死加权逻辑：不能用"重合标签个数"排序 ——
# 異世界/転生/チート 人人都有，谁重合得多谁排前面，推出来的就是"最热门"
# 而不是"最像"。所以合成一个池，把"冷门标签 > 大词"这件事测死。
POOL = [
    {"id": "me", "title": "我自己", "tags": ["百合", "勘違い", "異世界"]},
    {"id": "rare", "title": "冷门标签重合", "tags": ["勘違い", "学園"],
     "points": 10},
    {"id": "common", "title": "三个大词重合",
     "tags": ["異世界", "転生", "チート"], "points": 999999},
    {"id": "none", "title": "毫无重合", "tags": ["料理", "日常"]},
    {"id": "hp", "title": "只沾一个大词", "tags": ["異世界"], "points": 5000},
]
_rows = m.similar_works("me", ["百合", "勘違い", "異世界"], pool=POOL)
_ids = [r[0]["id"] for r in _rows]
check("★ 冷门标签重合排在大词重合之前（核心：IDF 加权）",
      _ids[:1] == ["rare"], str(_ids))
check("★ 自己不会推给自己", "me" not in _ids, str(_ids))
check("★ 毫无重合的不进列表", "none" not in _ids, str(_ids))
check("★ 返回共有标签（卡片要显示「共同标签 · xxx」）",
      all(isinstance(r[1], list) and r[1] for r in _rows), str(_rows[:1]))

_rows2 = m.similar_works(
    "me", ["百合"], author="同じ作者",
    pool=POOL + [{"id": "same-a", "title": "同作者", "author": "同じ作者",
                  "tags": ["百合"]}])
check("★ 同作者获得加成",
      [r[0]["id"] for r in _rows2][:1] == ["same-a"],
      str([(r[0]["id"], round(r[2], 2)) for r in _rows2]))

# 隐藏（"不感兴趣"）过的书不能作为相似推荐出现，否则又推回来。
# 这里注入合成书库：这个测试进程的数据根是空的，
# 不注入的话断言会"通过"但什么都没验证（假绿）。
_saved_lib = m.recs._load_lib
_saved_cached = m.recs.cached
_saved_local = m.all_local_slugs
try:
    m.recs._load_lib = lambda: {
        "hid1": {"id": "hid1", "title": "已隐藏", "tags": ["百合"], "hidden": True},
        "vis1": {"id": "vis1", "title": "可见", "tags": ["百合"]},
    }
    m.recs.cached = lambda include_hidden=False: []
    m.all_local_slugs = lambda: []
    _pool = m._work_pool()
finally:
    m.recs._load_lib = _saved_lib
    m.recs.cached = _saved_cached
    m.all_local_slugs = _saved_local
_pool_ids = [str(it.get("id")) for it in _pool]
check("★ 相似候选池排除隐藏作品（否则「不感兴趣」白点）",
      "vis1" in _pool_ids and "hid1" not in _pool_ids, str(_pool_ids))

# —— 在线：真实详情页要真的渲染出这一块 ——
_sim_wid = None
for _c in (json.loads(get("/api/recs")).get("items") or []):
    if _c.get("tags"):
        _sim_wid = str(_c.get("id"))
        break
if _sim_wid:
    _pg = get(f"/book?id={urllib.parse.quote(_sim_wid)}")
    check("★ 详情页有「同标签的相似作品」", "同标签的相似作品" in _pg)
    _sims = re.findall(r'class="simrow" href="/book\?id=([^"]+)"', _pg)
    check("★ 渲染出相似作品条目", len(_sims) > 0, f"{len(_sims)} 条")
    check("★ 不把自己列进去", _sim_wid not in _sims, f"self={_sim_wid}")
    check("★ 每条都写了共有标签", _pg.count("共同标签 ·") >= len(_sims),
          f"共有标签 {_pg.count('共同标签 ·')} / 条目 {len(_sims)}")
    # ★ 位置：必须在目录**之前**。目录动辄几百话（有作品 400+），
    # 放到目录后面就等于藏起来，读者根本看不到"还有类似的吗"。
    _i_sim = _pg.find("同标签的相似作品")
    _i_toc = _pg.find('class="toc"')
    check("★ 相似作品排在目录之前（目录可能几百话，放后面等于藏起来）",
          _i_sim >= 0 and (_i_toc < 0 or _i_sim < _i_toc),
          f"相似@{_i_sim} 目录@{_i_toc}")
else:
    print("  （推荐缓存为空，跳过在线相似作品检查）")

for _c in ("simrow", "simlist", "simtag", "simp"):
    check(f".{_c} 有样式定义", f".{_c}" in _css3)

print()
print("=" * 66)
print("C. 详情页用到的 class 必须有样式（否则页面会很难看）")
print("=" * 66)
_html = get(f"/book?id={urllib.parse.quote(WID)}") if WID else ""
if _html:
    _css = re.search(r"<style>(.*?)</style>", _html, re.S)
    _css = _css.group(1) if _css else ""
    # 详情页自己新增的这些 class，漏了任何一个都会让页面走形
    for _cls in ("chip", "chip.tag", "lnkbtn", "back", "syn", "toc", "tocch",
                 "chips", "jp-sub", "orig", "hint", "resume"):
        check(f".{_cls} 有样式定义", f".{_cls}" in _css)
else:
    print("  （没有作品可测，跳过）")

print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("✅ 详情页测试全部通过")
