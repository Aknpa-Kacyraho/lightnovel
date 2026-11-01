#!/usr/bin/env python3
"""回归：书库分页（点「下一页」没反应的那个 bug）。

根因是路由分支只认 `q` / `want` 两个参数：
    if "q" in q or "want" in q:
而「下一页」只发 `?page=N`，于是落到书架分支，页码从未保存。

这个测试直接打真实的 HTTP 服务（不是内部函数），
因为 bug 就出在**路由分发**这一层，绕开它测不出来。
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def get(path: str) -> str:
    with urllib.request.urlopen(BASE + path, timeout=25) as r:
        return r.read().decode("utf-8")


def pager_of(html: str) -> str:
    m = re.search(r'<div class="pager">(.*?)</div>', html, re.S)
    if not m:
        return ""
    return " ".join(re.sub(r"<[^>]+>", " ", m.group(1)).split())


def cards_of(html: str) -> int:
    """数**书库分页卡**的数量。

    不能用 `data-lib=` 计数：推荐卡/标签页卡也带这个属性，
    会把它们算进来（踩过：加了详情页跳转后这里就开始误报）。
    书库分页卡在 #pane-lib 里面，先切出那一段再数。
    """
    i = html.find('id="pane-lib"')
    if i < 0:
        return html.count("data-lib=")
    seg = html[i:]
    # 到下一个 pane 为止
    j = seg.find('class="pane"', 10)
    if j > 0:
        seg = seg[:j]
    return seg.count("data-lib=")


print("=" * 62)
print("书库分页（真实 HTTP，覆盖路由分发）")
print("=" * 62)

PAGE_SIZE = 15

cfg_raw = get("/api/modelcfg")
cfg = json.loads(cfg_raw)
check("模型配置接口可用且给三角色",
      cfg.get("roles", {}).get("translate")
      and cfg.get("roles", {}).get("auxiliary")
      and cfg.get("roles", {}).get("review"))
check("模型配置接口不回传密钥", "api_key" not in cfg_raw.lower())

# 先清空筛选，回到"全部"，并**从服务端推导**期望值
# （不写死 8 页/107 项：书库大小和筛选状态都会变，写死必然某天误报）
get("/api/library?q=&want=0&page=1")
total = json.loads(get("/api/booklib"))["total"]
exp_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
print(f"  （书库共 {total} 本 → 预计 {exp_pages} 页，每页 {PAGE_SIZE}）")

h1 = get("/classic")
p1 = pager_of(h1)
check(f"第 1 页：显示 1/{exp_pages}", f"1 / {exp_pages}" in p1, p1[:64])
check("第 1 页：渲染 15 张卡片", cards_of(h1) == min(PAGE_SIZE, total), f"{cards_of(h1)}")

if exp_pages >= 2:
    # 关键回归：只带 page 参数（这正是「下一页」发出的请求）
    get("/api/library?page=2")
    h2 = get("/classic")
    p2 = pager_of(h2)
    check(f"只发 ?page=2 时页码被保存（1/{exp_pages} → 2/{exp_pages}）",
          f"2 / {exp_pages}" in p2, p2[:64])
    check("第 2 页仍是 15 张卡片", cards_of(h2) == PAGE_SIZE, f"{cards_of(h2)}")

    mid = max(2, exp_pages - 2)
    get(f"/api/library?page={mid}")
    p6 = pager_of(get("/classic"))
    check(f"跳到第 {mid} 页生效", f"{mid} / {exp_pages}" in p6, p6[:64])

    get("/api/library?page=999")
    p9 = pager_of(get("/classic"))
    check(f"越界页码被夹到最后一页（{exp_pages}）", f"{exp_pages} / {exp_pages}" in p9, p9[:64])
else:
    print("  （书库不足 2 页，跳过多页断言）")

# 搜索 + 翻页组合
get("/api/library?q=%E3%81%96%E3%81%BE%E3%81%81&page=1")   # ざまぁ
hs = get("/classic")
ps = pager_of(hs)
m = re.search(r"共 (\d+) 项", ps)
n_hit = int(m.group(1)) if m else 0
check("搜索后总项数变小", 0 < n_hit < total, f"{total} → {n_hit}")
exp_s = max(1, (n_hit + PAGE_SIZE - 1) // PAGE_SIZE)
check(f"搜索后页数按命中数算（{n_hit} 项 → {exp_s} 页）",
      f"1 / {exp_s}" in ps, ps[:64])
if exp_s >= 2:
    get("/api/library?page=2")
    check("搜索状态下也能翻到第 2 页",
          f"2 / {exp_s}" in pager_of(get("/classic")), pager_of(get("/classic"))[:64])

# 标签 facet：点标签只看该类 —— 数量必须与真正渲染的卡同源（数字不能骗人）
get("/api/library?q=&want=0&tag=&page=1")
h0 = get("/classic")
chips = re.findall(r'data-libtag="([^"]+)"', h0)
check("标签 facet：书库渲染出可点标签", bool(chips), f"{len(chips)} 个")
check("★ 标签 facet 单行横向滚动（不铺满手机首屏）",
      'class="facetrow"' in h0 and "overflow-x:auto" in h0)
check("★ 标签 facet 最多 20 个（长尾不挤占首屏）",
      len(chips) <= 20, f"{len(chips)} 个")
if chips:
    tag0 = html.unescape(chips[0])
    get("/api/library?tag=" + urllib.parse.quote(tag0))
    hf = get("/classic")
    check(f"标签 facet：选中「{tag0}」后 chip 进入 on 态", "libtag on" in hf)
    esc = re.escape(html.escape(tag0, quote=True))
    mch = re.search(r'data-libtag="' + esc + r'"[^>]*>.*?<span class="s">(\d+)</span>',
                    hf, re.S)
    chip_n = int(mch.group(1)) if mch else -1
    mnote = re.search(r"筛选出 (\d+) 本", hf)
    note_n = int(mnote.group(1)) if mnote else -1
    check("标签 facet：chip 频次 == 筛选数（两个函数同源）",
          chip_n > 0 and chip_n == note_n, f"chip={chip_n} note={note_n}")
    check(f"标签 facet：首页卡片数 == min({note_n}, {PAGE_SIZE})",
          cards_of(hf) == min(PAGE_SIZE, note_n),
          f"{cards_of(hf)} vs {min(PAGE_SIZE, note_n)}")
    get("/api/library?tag=")                    # 取消标签筛选
    hc = get("/classic")
    check("标签 facet：取消后回到全量（无「筛选出」且标签行不变）",
          "筛选出" not in hc and len(re.findall(r'data-libtag="', hc)) == len(chips))

    # ★ 标签多选（用户报「书库标签为什么不能多选」）：AND 语义，同时满足。
    if len(chips) >= 2:
        t1, t2 = html.unescape(chips[0]), html.unescape(chips[1])
        def _single(tag):
            get("/api/library?want=0&tag=" + urllib.parse.quote(tag))
            mm = re.search(r"筛选出 (\d+) 本", get("/classic"))
            return int(mm.group(1)) if mm else 0
        n1 = _single(t1)
        n2 = _single(t2)
        # 同时选两个 → 只留两者都带的书
        get("/api/library?want=0&tag=" + urllib.parse.quote(t1)
            + "&tag=" + urllib.parse.quote(t2))
        hm = get("/classic")
        mm = re.search(r"筛选出 (\d+) 本", hm)
        nboth = int(mm.group(1)) if mm else 0
        check("★ 标签多选：两个 chip 都进入 on 态",
              hm.count("libtag on") >= 2, f"{hm.count('libtag on')} 个 on")
        check("★ 标签多选按 AND（同时满足），不是 OR 相加",
              0 <= nboth <= min(n1, n2), f"{t1}({n1}) & {t2}({n2}) → {nboth}")
        check("标签多选：卡片数与联合命中数同源",
              cards_of(hm) == min(PAGE_SIZE, nboth),
              f"{cards_of(hm)} vs {min(PAGE_SIZE, nboth)}")
        check("标签多选：给出「清除标签」按钮",
              'id="libtagclear"' in hm)
        get("/api/library?want=0&tag=")         # 清除全部标签
        check("清除标签后回到全量（无「筛选出」）",
              "筛选出" not in get("/classic"))
    else:
        check("标签多选：隔离库里应存在 ≥2 个可点标签（否则是环境问题）", False)
else:
    check("标签 facet：隔离库里应存在频次≥2 的标签（否则是环境问题）", False)

get("/api/library?q=&want=0&page=1")   # 恢复

print()
print("=" * 62)
print("/api/booklib 的截断必须自报（数字不能骗人）")
print("=" * 62)
# 这个接口默认只回 300 条，而书库可能更大。以前只回 items+total，
# 拿到 300 条的人会以为"书库只有 300 本"。现在必须带上 limit/offset/more。
d = json.loads(get("/api/booklib?limit=2&offset=1"))
check("?limit=2&offset=1 真的只回 2 条", len(d.get("items") or []) == 2,
      f"{len(d.get('items') or [])} 条")
check("回包自报 limit / offset",
      d.get("limit") == 2 and d.get("offset") == 1,
      str({k: d.get(k) for k in ("limit", "offset")}))
check("total 不受 limit 影响（= 书库可浏览本数）", d.get("total") == total,
      f"{d.get('total')} vs 面板 {total}")
check("more 如实反映后面还有没有", d.get("more") is (1 + 2 < total), f"more={d.get('more')}")
d2 = json.loads(get("/api/booklib?limit=9999"))
check("limit 有硬上限（不许一次拉爆整个库）",
      d2.get("limit") == 1000 and len(d2.get("items") or []) <= 1000,
      f"limit={d2.get('limit')} 条数={len(d2.get('items') or [])}")
d3 = json.loads(get("/api/booklib?limit=abc&offset=-5"))
check("坏参数回落到默认值、不抛 500",
      d3.get("limit") == 300 and d3.get("offset") == 0,
      f"{d3.get('limit')}/{d3.get('offset')}")
print()
print("=" * 62)
print("设置页 / PWA：偏好集中一处，manifest 与图标可访问")
print("=" * 62)
s = get("/settings")
check("设置页可打开", "<title>设置</title>" in s and "阅读与应用" in s)
check("设置页走新 UI 壳（data-ui=next / ui-settings-page）",
      'data-ui="next"' in s and 'ui-settings-page' in s)
check("设置页加载外置设置脚本（主题/字号偏好仍在 localStorage）",
      "ln-theme" in s and "ln-fs" in s and "ln-lh" in s)
check("主题三态齐全（浅色/深色/跟随系统）",
      all(f'data-theme="{m}"' in s for m in ("light", "dark", "system")))
check("字号/行距可选", 'data-fs-set="s"' in s and 'data-lh-set="loose"' in s)
check("日文原文三态（隐藏/混排/对照）",
      all(f'data-jp="{m}"' in s for m in ("hide", "mix", "show")))
check("翻页手势三态", all(f'data-tap="{m}"' in s for m in ("off", "lr", "ud")))
check("朗读语言可选", 'data-speak="jp"' in s and 'data-speak="zh"' in s)
check("本地导入入口在设置页", 'href="/import"' in s)
check("备份下载在设置页", 'href="/api/backup"' in s)
man = json.loads(get("/manifest.webmanifest"))
check("PWA manifest 声明 standalone 与 start_url",
      man.get("display") == "standalone" and man.get("start_url") == "/discover")
check("manifest 带 192/512 图标",
      {i.get("sizes") for i in man.get("icons") or []} >= {"192x192", "512x512"})
with urllib.request.urlopen(BASE + "/icon-192.png", timeout=10) as r:
    check("PWA 图标可访问（PNG 魔数）", r.read(8) == b"\x89PNG\r\n\x1a\n")
check("首页 head 引入 manifest 与主题色",
      'rel="manifest"' in get("/classic") and 'name="theme-color"' in get("/classic"))
check("主题初始化覆盖首页/设置/翻译列表（data-t + ln-theme）",
      all('data-t' in get(p) and 'ln-theme' in get(p)
          for p in ("/", "/settings", "/queue")))

print()
print("=" * 62)
print("本地导入：真实上传 → 自动上架 → 阅读页（结束后删掉探针书）")
print("=" * 62)
_root = os.environ.get("LNTRANS_SERVER_ROOT") or ""
check("隔离数据根可用（导入会写书，绝不能打真实书架）",
      bool(_root) and os.path.isdir(os.path.join(_root, "novels")), _root)
_page = get("/import")
check("导入页可打开且带文件控件",
      "<h1>导入本地 EPUB / TXT</h1>" in _page and 'id="imp-file"' in _page)
_probe = ""
try:
    if _root:
        _body = "第1話　始まり\n自检导入探针。\n".encode("utf-8")
        _url = (BASE + "/api/import?name="
                + urllib.parse.quote("自检导入探针.txt"))
        _req = urllib.request.Request(
            _url, data=_body, method="POST",
            headers={"Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(_req, timeout=30) as r:
            _d = json.loads(r.read().decode("utf-8"))
        _probe = _d.get("slug") or ""
        check("真实上传：ok / created / 章数",
              bool(_d.get("ok")) and bool(_d.get("created"))
              and _d.get("chapters") == 1, str(_d)[:160])
        check("导入后自动进书架",
              bool(_probe) and f"/read/{_probe}" in get("/classic"))
        _rp = get(f"/read/{_probe}")
        check("导入的书能打开阅读页（落地章待译占位）",
              'id="need-1"' in _rp and "自检导入探针" in _rp)
        _req2 = urllib.request.Request(
            _url, data=_body, method="POST",
            headers={"Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(_req2, timeout=30) as r:
            _d2 = json.loads(r.read().decode("utf-8"))
        check("同一文件重复导入返回原书（不建第二本）",
              bool(_d2.get("ok")) and not _d2.get("created")
              and _d2.get("slug") == _probe, str(_d2)[:160])
        _meta_path = os.path.join(_root, "novels", _probe, "meta.json")
        with open(_meta_path, encoding="utf-8") as _mf:
            _meta = json.load(_mf)
        _sid = str(_meta.get("source_id") or "")
        _alias_path = os.path.join(_root, "data", "slug-aliases.json")
        os.makedirs(os.path.dirname(_alias_path), exist_ok=True)
        with open(_alias_path, "w", encoding="utf-8") as _af:
            json.dump({"old-probe": _probe,
                       "missing-alias": "does-not-exist"}, _af)

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        def _redirect_of(path):
            try:
                urllib.request.build_opener(_NoRedirect).open(
                    BASE + path, timeout=10)
                return 0, ""
            except urllib.error.HTTPError as e:
                return e.code, e.headers.get("Location") or ""

        _c, _loc = _redirect_of(f"/book?id={urllib.parse.quote(_sid)}")
        check("旧 /book?id= 301 到 /book/<slug>",
              _c == 301 and _loc.rstrip("/").endswith("/book/" + _probe),
              f"{_c} {_loc}")
        _c2, _loc2 = _redirect_of("/read/old-probe?from=2")
        check("旧 /read/<alias> 301 且保留 query（Location 不带 fragment）",
              _c2 == 301 and _loc2.endswith(f"/read/{_probe}?from=2")
              and "#" not in _loc2, f"{_c2} {_loc2}")
        _c3, _loc3 = _redirect_of("/book/old-probe")
        check("旧 /book/<alias> 301 到最终 slug",
              _c3 == 301 and _loc3.rstrip("/").endswith("/book/" + _probe),
              f"{_c3} {_loc3}")
        _c4, _loc4 = _redirect_of("/read/missing-alias")
        check("alias 目标不存在时不 301，直接 404", _c4 == 404, f"{_c4} {_loc4}")
finally:
    if _probe and _root:
        shutil.rmtree(os.path.join(_root, "novels", _probe),
                      ignore_errors=True)
        try:
            os.remove(os.path.join(_root, "data", "books", _probe + ".json"))
        except OSError:
            pass

_tags_html = get("/tags")
check("新标签页 200 且带搜索/已选/全部标签",
      'data-ui-tags' in _tags_html and 'data-tag-search' in _tags_html
      and 'data-tag-selected' in _tags_html and 'data-tag-all' in _tags_html)
check("新标签页带可计算的标签数据",
      'ui-tags-data' in _tags_html and 'works' in _tags_html
      and 'count' in _tags_html)
check("旧 /tags?q= 直达链接仍可用", get("/tags?q=__no_such_tag__") != "")


# P3.4: async import must return a job id, expose progress, and finish.
_async_slug = ""
try:
    if _root:
        _abody = "第1話 開始\nテスト本文です。\n".encode("utf-8")
        _aurl = (BASE + "/api/import_async?name="
                 + urllib.parse.quote("异步导入探测.txt"))
        _areq = urllib.request.Request(
            _aurl, data=_abody, method="POST",
            headers={"Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(_areq, timeout=30) as r:
            _aj = json.loads(r.read().decode("utf-8"))
        _jid = _aj.get("id") or ""
        _ajob = {}
        for _ in range(30):
            with urllib.request.urlopen(
                    BASE + "/api/import_job?id=" + urllib.parse.quote(_jid),
                    timeout=10) as r:
                _ajob = json.loads(r.read().decode("utf-8"))
            if _ajob.get("status") in ("done", "error"):
                break
            time.sleep(0.2)
        _async_slug = _ajob.get("slug") or ""
        check("异步导入任务完成并有 slug", _ajob.get("status") == "done"
              and bool(_async_slug), str(_ajob)[:160])
        check("异步导入写入 .import.json schema", bool(_async_slug) and os.path.exists(
            os.path.join(_root, "novels", _async_slug, ".import.json")))
finally:
    if _async_slug and _root:
        shutil.rmtree(os.path.join(_root, "novels", _async_slug),
                      ignore_errors=True)


_preview = get("/preview")
check("新 UI /preview 200 且挂 data-ui=next",
      'data-ui="next"' in _preview and 'class="ui-shell"' in _preview
      and 'data-preview-stage' in _preview)
check("新 UI /preview 有卡片/表单/空状态/主题与视口控件",
      all(x in _preview for x in ('ui-card', 'ui-form-grid', 'ui-empty',
                                  'data-ui-theme', 'data-reading-theme',
                                  'data-viewport')))
_home_new = get("/")
check("新首页 200 且挂 shell/发现",
      'data-ui="next"' in _home_new and 'data-page="home"' in _home_new
      and '今天适合读什么' in _home_new)
check("新首页没有 Traceback", 'Traceback' not in _home_new)

_discover = get("/discover")
check("新发现页 200 且挂 shell/直接阅读",
      'data-ui="next"' in _discover and 'data-page="home"' in _discover
      and '直接阅读' in _discover)
check("新发现页没有 Traceback", 'Traceback' not in _discover)

_shelf = get("/shelf")
check("新书架 200 且挂 shell/来源筛选", 
      'data-ui="next"' in _shelf and 'data-page="shelf"' in _shelf
      and 'data-source-filter="local"' in _shelf)
_library = get("/library")
check("新书库 200 且挂来源筛选/搜索/未开始切换",
      'data-page="library"' in _library and 'data-search' in _library
      and 'data-view="new"' in _library and 'data-source-filter="source"' in _library)
check("新书架/书库没有 Traceback", 'Traceback' not in _shelf + _library)

check("旧页面不挂 data-ui=next（新令牌不泄漏）",
      'data-ui="next"' not in get("/classic"))
_ui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lnui")
_ui_bad = []
for _name in sorted(os.listdir(_ui_dir)):
    if not _name.endswith(".py"):
        continue
    _src = open(os.path.join(_ui_dir, _name), encoding="utf-8").read()
    if "import lnserve" in _src or "from lnserve" in _src:
        _ui_bad.append(_name)
check("UI 组件层不反向 import 服务入口", not _ui_bad, str(_ui_bad))

print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("✅ 分页回归全部通过")
