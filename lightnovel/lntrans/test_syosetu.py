"""syosetu（成为小说家吧）适配器：纯解析回归，不联网。

页面结构来自 2026-10 实测：作品页 `p-novel__title` / `p-novel__author` /
`id="novel_ex" class="p-novel__summary"` / `p-eplist__sublist`；章节页
`p-novel__body` → `p-novel__text` 里一串 `<p id="L<n>">`。
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lnfinder"))

fails = []


def check(name, cond, extra=""):
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def _err(fn):
    try:
        fn()
    except Exception:
        return True
    return False


_spec = importlib.util.spec_from_file_location(
    "lnlib", os.path.join(os.path.dirname(HERE), "lnfinder", "lnlib.py"))
lnlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lnlib)

WORK_HTML = """
<h1 class="p-novel__title p-novel__title--rensai">無職転生 - 異世界行ったら本気だす -</h1>
<div class="p-novel__author">作者：<a href="https://mypage.syosetu.com/288399/">理不尽な孫の手</a> </div>
<div id="novel_ex" class="p-novel__summary">３４歳職歴無し。<br /> 異世界に転生したらしい。<br /> <br /> 完結しました。</div>
<div class="p-eplist">
  <div class="p-eplist__chapter-title">第１章 幼年期</div>
  <div class="p-eplist__sublist">
    <a href="/n9669bk/1/" class="p-eplist__subtitle"> プロローグ </a>
    <div class="p-eplist__update"> 2012/11/22 17:00 </div>
  </div>
  <div class="p-eplist__sublist">
    <a href="/n9669bk/2/" class="p-eplist__subtitle"> 第一話「もしかして：異世界」 </a>
    <div class="p-eplist__update"> 2012/11/22 18:15 </div>
  </div>
  <div class="p-eplist__chapter-title">第２章 少年期</div>
  <div class="p-eplist__sublist">
    <a href="/n9669bk/3/" class="p-eplist__subtitle"> 第二話 </a>
  </div>
</div>
"""

EP_HTML = """
<div class="p-novel__body">
  <div class="js-novel-text p-novel__text p-novel__text--preface">
    <p id="Lp1">前書きは取らない</p>
  </div>
  <div class="js-novel-text p-novel__text">
    <p id="L1"> 俺は34歳住所不定無職。</p>
    <p id="L2"><ruby>漢字<rt>かんじ</rt></ruby>のテスト。</p>
    <p id="L3"><br /></p>
    <p id="L4"> 三行目 </p>
  </div>
  <div class="js-novel-text p-novel__text p-novel__text--afterword">
    <p id="La1">後書きは取らない</p>
  </div>
</div>
"""

check("URL 识别：一般向",
      lnlib.syosetu_source("https://ncode.syosetu.com/n9669bk/") == ("syosetu", "N9669BK"))
check("URL 识别：R18",
      lnlib.syosetu_source("https://novel18.syosetu.com/n9598df/") == ("novel18", "N9598DF"))
check("裸 ncode 默认一般向",
      lnlib.syosetu_source("n9669bk") == ("syosetu", "N9669BK"))
check("非 syosetu 链接不误判",
      lnlib.syosetu_source("https://kakuyomu.jp/works/123") is None)

w = lnlib.syosetu_parse_work(WORK_HTML, "N9669BK")
check("标题", w["title"] == "無職転生 - 異世界行ったら本気だす -", w["title"])
check("作者（去掉「作者：」前缀）", w["author"] == "理不尽な孫の手", w["author"])
check("简介保留换行且不夹标签",
      "３４歳職歴無し。" in w["synopsis"] and "<br" not in w["synopsis"]
      and "\n" in w["synopsis"])
check("目录分章", [g["title"] for g in w["toc"]] == ["第１章 幼年期", "第２章 少年期"])
check("章节顺序与数量", [e["id"] for e in w["episodes"]] == ["1", "2", "3"])
check("章节标题", w["episodes"][1]["title"] == "第一話「もしかして：異世界」")
check("source_id 大写、url 小写",
      w["source_id"] == "N9669BK" and w["url"].endswith("/n9669bk/"))
check("一般向不带 R18", not w["r18"])

r = lnlib.syosetu_parse_work(WORK_HTML, "N9598DF", "novel18")
check("R18 标记与域名",
      r["r18"] and r["url"].startswith("https://novel18.syosetu.com/"))

text = lnlib.syosetu_parse_episode(EP_HTML)
check("正文按段分行", text.splitlines()[0] == "俺は34歳住所不定無職。", repr(text[:20]))
check("ruby 注音不进正文", "漢字のテスト。" in text and "かんじ" not in text)
check("空段落保留为空行", "\n\n" in text, repr(text))
check("不抓前書き/後書き", "前書き" not in text and "後書き" not in text)
check("空 HTML 抛错", _err(lambda: lnlib.syosetu_parse_episode("<html></html>")))


print()
if fails:
    print(f"失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("全部通过 ✓")
