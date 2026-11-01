#!/usr/bin/env python3
"""lnrender —— 把译文渲染成"能读下去"的阅读页面。

Markdown 只有一个字体一个字号，读长篇很枯燥。这里生成一个自包含 HTML：
暖色纸感背景、衬线中文正文、合适行高与行宽、章节目录、
原文⇄译文一键对照（排版保持同步）、阅读进度、深浅色自适应。

不引入任何外部依赖或 CDN，双击即可离线打开。
"""

from __future__ import annotations

import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lndata  # noqa: E402
import lncontracts  # noqa: E402
import lndedupe  # noqa: E402

# 作品根目录必须跟随 LNTRANS_DATA_ROOT（和 lnserve / lntrans / lnrecs 一样）。
# 踩过：这里写死 HERE 之后，隔离测试服务渲染章节时读的是**真实 novels/**
# → "/api/next" 永远返回 added=0（测试里表现为"翻完了却取不到"），
# 而真实环境看起来正常，所以特别难查。凡是碰 novels/ 的模块都要读这个变量。
LAYOUT = lndata.resolve_layout()
lndata.apply_environment(LAYOUT)
NOVELS = os.path.join(LAYOUT.data_root, "novels")

CSS = """
/* 主题令牌：显式类控制，不用 prefers-color-scheme——
   媒体查询只覆盖变量，赢不了 body 上的显式声明，会把暗色令牌泄漏到浅色主题
   （踩过：浅色下出现棕底棕字，几乎看不清）。 */
html{ color-scheme:light;
  --paper:#f7f5f0; --ink:#1f1d1a; --ink-soft:#6c6760; --rule:#e3dfd6;
  --accent:#7a5f33; --panel:#fffefb; --jp:#5f6f52; --jp-bg:#f1efe8;
  --ct:#6c6760;
  --shadow:0 1px 2px rgba(35,30,20,.04),0 8px 24px rgba(35,30,20,.05); }
html[data-t=dark]{ color-scheme:dark;
  --paper:#151413; --ink:#eae5dc; --ink-soft:#a29b8f;
  --rule:#2d2a26; --accent:#c6a774; --panel:#1d1b19; --jp:#9fb08c;
  --jp-bg:#242720; --ct:#b3ab9c;
  --shadow:0 1px 2px rgba(0,0,0,.35),0 8px 24px rgba(0,0,0,.3); }
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:"Noto Serif SC","Source Han Serif SC","Songti SC","SimSun",
              "Songti TC",Georgia,serif;
  font-size:18px; line-height:2.0; letter-spacing:.01em;
  -webkit-font-smoothing:antialiased;
}
#bar{position:fixed;top:0;left:0;height:3px;width:0;background:var(--accent);z-index:50;
     transition:width .1s linear}
#theme{position:fixed;right:18px;bottom:18px;z-index:50;border:1px solid var(--rule);
  background:var(--panel);color:var(--ink);border-radius:999px;padding:9px 15px;
  font-size:13px;font-family:system-ui,sans-serif;cursor:pointer;box-shadow:var(--shadow)}
main{max-width:44rem;margin:0 auto;padding:52px 22px 120px}
header.book{text-align:center;padding:34px 4px 30px;border-bottom:1px solid var(--rule);
  margin-bottom:10px}
header.book .kicker{font-size:12px;letter-spacing:.32em;color:var(--accent);
  text-transform:uppercase;font-family:system-ui,sans-serif}
header.book h1{margin:.45em 0 .3em;font-size:1.55em;line-height:1.45;font-weight:600;
  letter-spacing:.02em;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;
  overflow:hidden}
header.book .meta{max-width:26em;margin:0 auto;color:var(--ct);
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
header.book .meta{font-size:.82em;font-family:system-ui,sans-serif;letter-spacing:.04em}
.stats{display:flex;gap:26px;justify-content:center;margin:26px 0 6px;
  font-family:system-ui,sans-serif;font-size:.76em;color:var(--ink-soft)}
.stats b{display:block;font-size:1.5em;color:var(--ink);font-weight:600;font-family:Georgia,serif}
nav.toc{margin:30px 0 44px;padding:20px 24px;background:var(--panel);
  border:1px solid var(--rule);border-radius:10px;box-shadow:var(--shadow)}
nav.toc h2{margin:0 0 12px;font-size:.76em;letter-spacing:.2em;color:var(--accent);
  font-family:system-ui,sans-serif;font-weight:600;text-transform:uppercase}
nav.toc ol{margin:0;padding:0;list-style:none;counter-reset:c;
  column-gap:30px;columns:2}
@media (max-width:620px){nav.toc ol{columns:1}}
nav.toc li{counter-increment:c;margin:5px 0;font-size:.92em;break-inside:avoid}
nav.toc a{color:var(--ink);text-decoration:none;display:flex;gap:9px;align-items:baseline;
  padding:3px 0;border-bottom:1px dotted transparent}
nav.toc a:hover{border-bottom-color:var(--rule)}
nav.toc a::before{content:counter(c);color:var(--ink-soft);font-size:.78em;
  font-family:Georgia,serif;min-width:1.4em}
section.ch{margin:56px 0 0;scroll-margin-top:24px}
section.ch>h2{font-size:1.18em;font-weight:600;line-height:1.55;margin:0 0 4px;
  padding-top:26px;border-top:1px solid var(--rule)}
.chtitle-en{display:block;font-size:.72em;color:var(--ct);font-family:system-ui,sans-serif;
  font-weight:400;letter-spacing:.02em;margin-top:3px}
section.ch>h2 .no{color:var(--accent);font-family:Georgia,serif;margin-right:.5em;
  font-size:.9em}
section.ch .jp-title{color:var(--ct);font-size:.8em;font-family:system-ui,sans-serif;
  margin:0 0 22px;letter-spacing:.02em}
.body p{margin:0 0 1.45em;text-indent:2em}
.body p.blank{height:1em;margin:0}
.body p.jp{text-indent:2em;color:var(--jp);background:var(--jp-bg);
  border-left:3px solid var(--rule);padding:.5em .9em;margin:-.5em 0 1.2em;
  font-size:.9em;line-height:1.85;border-radius:0 6px 6px 0}
body.hidejp p.jp{display:none}
.tools{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin:22px 0 0}
.tools button{border:1px solid var(--rule);background:var(--panel);color:var(--ink);
  border-radius:999px;padding:8px 16px;font-size:13px;cursor:pointer;
  font-family:system-ui,sans-serif}
.tools button[aria-pressed=true]{border-color:var(--accent);color:var(--accent)}
footer{text-align:center;color:var(--ink-soft);font-size:.74em;margin-top:70px;
  padding-top:24px;border-top:1px solid var(--rule);font-family:system-ui,sans-serif;
  line-height:1.9}
"""

JS = """
// 主题：跟系统，点按钮手动切（首屏的主题已在 <head> 里定好）
const root=document.documentElement;
const mq=matchMedia('(prefers-color-scheme: dark)');
function apply(t){root.setAttribute('data-t',t);root.style.colorScheme=t;}
if(!root.getAttribute('data-t')) apply(mq.matches?'dark':'light');
mq.addEventListener('change',e=>apply(e.matches?'dark':'light'));
const tb=document.getElementById('theme');
tb.onclick=()=>{const c=root.getAttribute('data-t');
  apply(c==='dark'?'light':(c==='light'?'dark':'dark'));};
// 阅读进度条
const bar=document.getElementById('bar');
function upd(){const h=root;
  const p=h.scrollTop/(h.scrollHeight-h.clientHeight||1);
  bar.style.width=(p*100).toFixed(1)+'%';}
addEventListener('scroll',upd,{passive:true});upd();
// 原文对照：默认折叠（对不懂日语的读者，日文会盖过正文）
const bt=document.getElementById('toggle-jp');
document.body.classList.add('hidejp');
bt.textContent='显示日文原文';
bt.onclick=()=>{const hidden=document.body.classList.toggle('hidejp');
  bt.setAttribute('aria-pressed',String(!hidden));
  bt.textContent=hidden?'显示日文原文':'隐藏日文原文';};
"""


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def attrescape(s: str) -> str:
    return html.escape(s or "", quote=True)


# ---- 术语/人名悬浮标注 -------------------------------------------------
# 术语表（glossary）本来就是「日文 → 中文」的一张表，人物卡（characters）
# 里有人物简介 —— 以前它们只喂给翻译 prompt，读者一个都看不见。
# 现在在正文里把**中文译名**标出来，点一下显示原文与人物简介。
# 只标中文：读者不读日文，标日文名等于标了个看不懂的东西。
GLOSS_BUDGET = 60          # 每章最多标多少处（标太密反而干扰阅读）


def glossary_tips(meta: dict) -> list[tuple[str, str]]:
    """中文译名 → 悬浮说明。长名优先（避免短名把长名切开）。"""
    gl = meta.get("glossary") or {}
    chars = meta.get("characters") or {}
    tips: dict[str, str] = {}
    for jp, zh in gl.items():
        zh = (zh or "").strip()
        if not jp or not zh:
            continue
        # 单字译名（「澪」这种人名）也标，但 annotate_terms 里限次，
        # 否则满屏都是点线，反而看不清正文。
        info = chars.get(jp)
        desc = ""
        if isinstance(info, dict):
            desc = (info.get("desc") or "").strip()
        elif isinstance(info, str):
            desc = info.strip()
        tips[zh] = f"原文：{jp}" + (f"\n{desc}" if desc else "")
    return sorted(tips.items(), key=lambda kv: -len(kv[0]))


def annotate_terms(text: str, tips: list[tuple[str, str]],
                   budget: int = GLOSS_BUDGET,
                   used: dict[str, int] | None = None) -> str:
    """把正文里出现的中文译名包成可点的 span，其余照常转义。

    `used` 由调用方按**章**传进来（同一个 dict 跨段落累计），否则单字译名的
    限次会变成"每段 3 次"，一章照样标几十处。
    """
    if not text:
        return ""
    if not tips:
        return esc(text)
    tipmap = dict(tips)
    pat = re.compile("|".join(re.escape(zh) for zh, _ in tips))
    out, pos, n = [], 0, 0
    if used is None:
        used = {}
    for mt in pat.finditer(text):
        if n >= budget:
            break
        zh = mt.group(0)
        # 单字译名每章最多 3 处：第一次看到时告诉读者"这是谁"就够了。
        if len(zh) == 1 and used.get(zh, 0) >= 3:
            continue
        out.append(esc(text[pos:mt.start()]))
        out.append(f'<span class="gloss" data-tip="{attrescape(tipmap[zh])}">'
                   f'{esc(zh)}</span>')
        pos, n = mt.end(), n + 1
        used[zh] = used.get(zh, 0) + 1
    out.append(esc(text[pos:]))
    return "".join(out)


def jp_paragraphs(raw: str) -> list[str]:
    """把原文整理成与译文段落一一对应的列表。"""
    paras, buf = [], []
    for ln in (raw or "").split("\n"):
        if ln.strip() == "":
            if buf:
                paras.append("\n".join(buf).strip())
                buf = []
            paras.append("")
        else:
            buf.append(ln.strip())
    if buf:
        paras.append("\n".join(buf).strip())
    return paras


def zh_paragraphs(text: str) -> list[str]:
    out, buf = [], []
    for ln in (text or "").split("\n"):
        if ln.strip() == "":
            if buf:
                out.append("\n".join(buf).strip())
                buf = []
            out.append("")
        else:
            buf.append(ln.strip())
    if buf:
        out.append("\n".join(buf).strip())
    return out


def render_chapter_html(slug: str, idx: int) -> str:
    """只渲染一章的正文 HTML（供 Web 服务的阅读页动态拼接）。

    返回空串表示这一章还没有译文。
    """
    ndir = os.path.join(NOVELS, slug)
    zp = os.path.join(ndir, "chapters", f"{idx:04d}.txt")
    rp = os.path.join(ndir, "raw", f"{idx:04d}.txt")
    mp = os.path.join(ndir, "chapters", f"{idx:04d}.meta.json")
    if not lncontracts.translation_paths_available(zp, rp, mp):
        return ""
    meta_path = os.path.join(ndir, "meta.json")
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}
    eps = meta.get("episodes") or []
    title = (meta.get("zh_titles") or {}).get(str(idx + 1)) \
        or (eps[idx].get("title") if idx < len(eps) else "") or f"第{idx+1}话"
    title_jp = eps[idx].get("title") if idx < len(eps) else ""
    summary = (meta.get("summaries") or {}).get(str(idx + 1)) or ""

    zh_text = open(zp, encoding="utf-8").read()
    jp_text = open(rp, encoding="utf-8").read() if os.path.exists(rp) else ""
    zh = zh_paragraphs(lndedupe.dedupe_repeated_output(zh_text, jp_text))
    jp = jp_paragraphs(jp_text)

    out = [f'<section class="ch" id="c{idx+1}" data-ch="{idx+1}">']
    jp_sub = f'<span class="chtitle-en">{esc(title_jp)}</span>' if title_jp else ""
    out.append(f'<h2><span class="no">{idx+1}</span>{esc(title)}{jp_sub}</h2>')
    if summary:
        out.append(f'<p class="jp-title">本章提要：{esc(summary)}</p>')
    out.append('<div class="body">')
    tips = glossary_tips(meta)
    used: dict[str, int] = {}
    for i, z in enumerate(zh):
        if z == "":
            out.append('<p class="blank"></p>')
            continue
        out.append(f"<p>{annotate_terms(z, tips, used=used)}</p>")
        if i < len(jp) and jp[i]:
            out.append(f'<p class="jp">{esc(jp[i])}</p>')
    out.append("</div></section>")
    return "\n".join(out)


def render(slug: str, out_path: str | None = None, theme: str = "auto") -> str:
    ndir = os.path.join(NOVELS, slug)
    meta = json.load(open(os.path.join(ndir, "meta.json"), encoding="utf-8"))
    eps = meta["episodes"]
    titles_zh = meta.get("zh_titles") or {}
    summaries = meta.get("summaries") or {}

    chapters = []
    total_chars = 0
    for i in range(len(eps)):
        zp = os.path.join(ndir, "chapters", f"{i:04d}.txt")
        rp = os.path.join(ndir, "raw", f"{i:04d}.txt")
        mp = os.path.join(ndir, "chapters", f"{i:04d}.meta.json")
        if not lncontracts.translation_paths_available(zp, rp, mp):
            continue
        zh_text = open(zp, encoding="utf-8").read()
        jp_text = open(rp, encoding="utf-8").read() if os.path.exists(rp) else ""
        zh = zh_paragraphs(lndedupe.dedupe_repeated_output(zh_text, jp_text))
        jp = jp_paragraphs(jp_text)
        total_chars += sum(len(x) for x in zh)
        chapters.append({
            "no": i + 1,
            "title": titles_zh.get(str(i + 1)) or eps[i].get("title") or f"第{i+1}话",
            "title_jp": eps[i].get("title") or "",
            "summary": summaries.get(str(i + 1)) or "",
            "zh": zh, "jp": jp,
        })

    theme_attr = f' data-t="{theme}"' if theme in ("light", "dark") else ""
    head_bootstrap = (
        "<script>(function(){var d=matchMedia('(prefers-color-scheme: dark)')"
        ".matches?'dark':'light';document.documentElement.setAttribute('data-t',d);"
        "document.documentElement.style.colorScheme=d;})();</script>"
    )
    parts: list[str] = []
    parts.append(f"""<!doctype html>
<html lang="zh-CN"{theme_attr}><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<!-- 声明本页自带深浅色，阻止 Edge/Chrome「强制深色网页」反演配色 -->
<meta name="color-scheme" content="light dark">
{head_bootstrap}
<title>{esc(meta.get('title',''))} · 中文译本</title>
<style>{CSS}</style></head><body>
<div id="bar"></div>
<main>
<header class="book">
  <div class="kicker">中文译本</div>
  <h1>{esc(meta.get('title',''))}</h1>
  <div class="meta">原作：{esc(meta.get('author',''))} &nbsp;·&nbsp; 出处：Kakuyomu</div>
  <div class="stats">
    <div><b>{len(chapters)}</b>已译章节</div>
    <div><b>{total_chars//1000}</b>千字</div>
    <div><b>{len(meta.get('glossary') or {})}</b>术语</div>
  </div>
  <div class="tools">
    <button id="toggle-jp" aria-pressed="false">显示原文</button>
  </div>
</header>""")

    if len(chapters) > 1:
        parts.append('<nav class="toc"><h2>目录</h2><ol>')
        for c in chapters:
            parts.append(f'<li><a href="#c{c["no"]}">{esc(c["title"])}</a></li>')
        parts.append("</ol></nav>")

    for c in chapters:
        parts.append(f'<section class="ch" id="c{c["no"]}">')
        jp_sub = (f'<span class="chtitle-en">{esc(c["title_jp"])}</span>'
                  if c["title_jp"] else "")
        parts.append(f'<h2><span class="no">{c["no"]}</span>{esc(c["title"])}{jp_sub}</h2>')
        if c["summary"]:
            parts.append(f'<p class="jp-title">本章提要：{esc(c["summary"])}</p>')
        parts.append('<div class="body">')
        jp = c["jp"]
        for i, z in enumerate(c["zh"]):
            if z == "":
                parts.append('<p class="blank"></p>')
                continue
            parts.append(f"<p>{esc(z)}</p>")
            if i < len(jp) and jp[i]:
                parts.append(f'<p class="jp">{esc(jp[i])}</p>')
        parts.append("</div></section>")

    parts.append(f"""</main>
<footer>本译本仅供个人阅读使用。原作版权归 {esc(meta.get('author',''))} 所有。<br>
对照原文可点右下角按钮切换。</footer>
<button id="theme" title="切换深浅色">◐ 主题</button>
<script>{JS}</script>
</body></html>""")

    out_path = out_path or os.path.join(ndir, "read.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out_path


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="把译文渲染成阅读页面")
    ap.add_argument("slug")
    ap.add_argument("out", nargs="?", help="输出路径")
    ap.add_argument("--theme", choices=["auto", "light", "dark"], default="auto",
                    help="写死主题（默认跟系统）")
    a = ap.parse_args()
    p = render(a.slug, a.out, a.theme)
    print(f"已生成阅读页：{p}")
    print(f"大小：{os.path.getsize(p)/1024:.1f} KB")


if __name__ == "__main__":
    main()
