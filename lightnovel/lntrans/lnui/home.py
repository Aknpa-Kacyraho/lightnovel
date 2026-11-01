"""Discovery home for the next UI."""

from __future__ import annotations

from .components import attr, badge, button, empty, esc
from .icons import icon
from .library import _work_card, library_js
from .layout import shell
from .styles import css


def _home_card(row: dict) -> str:
    if row.get("read_href"):
        return _work_card(row)
    title = row.get("title") or row.get("title_jp") or "未命名作品"
    jp = row.get("title_jp") or ""
    tags = "".join(
        f'<span class="ui-tag">{esc(t)}</span>'
        for t in (row.get("tags") or [])[:5] if t)
    meta = " · ".join(x for x in (
        row.get("author") or "",
        f"{int(row.get('total') or 0)} 话" if row.get("total") else "",
    ) if x)
    actions = ""
    if row.get("url"):
        actions = (
            button("继续导入" if row.get("want") else "直接阅读", tone="primary",
                   attrs=f'data-import-url="{attr(row["url"])}" data-import-read="1"')
            + button("加入书架", tone="secondary",
                     attrs=f'data-import-url="{attr(row["url"])}"'))
    return (
        f'<article class="ui-card ui-work-card" data-work-card '
        f'data-href="/book?id={attr(row.get("id") or "")}" data-source="source" '
        f'data-unstarted="1" data-hay="{attr((title + " " + jp).lower())}">'
        '<div class="ui-card-body">'
        f'<div class="ui-card-top">{badge("待导入", tone="warn") if row.get("want") else badge("源站", tone="source")}</div>'
        f'<h3 class="ui-card-title">{esc(title)}</h3>'
        + (f'<div class="ui-card-sub">{esc(jp)}</div>' if jp and jp != title else "")
        + (f'<div class="ui-card-meta">{esc(meta)}</div>' if meta else "")
        + (f'<div class="ui-tags">{tags}</div>' if tags else "")
        + '</div>'
        + (f'<div class="ui-card-foot">{actions}</div>' if actions else "")
        + '</article>'
    )


def render_home(candidates: list[dict], continue_reading: dict | None = None,
                *, pwa_head: str = "", notice: str = "") -> str:
    cards = "".join(_home_card(r) for r in candidates[:12])
    cont = ""
    if continue_reading:
        r = continue_reading
        cont = (f'<section class="ui-continue"><div>'
                f'<div class="ui-kicker">CONTINUE</div>'
                f'<h2>{esc(r.get("title") or "")}</h2>'
                f'<p>上次读到第 {r.get("chapter") or 0} 话 · '
                f'已译 {r.get("have") or 0} 话</p></div>'
                f'<a class="ui-btn ui-btn-primary" href="/read/'
                f'{esc(r.get("slug") or "")}?from={r.get("next") or 1}">'
                f'{icon("play")}<span>接着读</span></a></section>')
    body = f'''
<div class="ui-home" data-ui-library data-page="home" data-home>
  {notice}
  {cont}
  <section class="ui-section">
    <div class="ui-section-head">
      <div><span class="ui-kicker">DISCOVER</span><h2>今天适合读什么</h2>
        <p>先直接读，加入书架只决定能不能继续读，不代表收藏。</p></div>
      <a class="ui-btn ui-btn-ghost" href="/library">去书库</a>
    </div>
    {f'<div class="ui-work-grid" data-work-grid>{cards}</div>' if cards else
     empty("暂时没有候选", "去书库看看存量作品，或稍后再刷新推荐。",
           '<a class="ui-btn ui-btn-primary" href="/library">打开书库</a>')}
    <p class="ui-help" data-filter-empty hidden>没有匹配的作品。</p>
  </section>
</div>'''
    return f'''<!doctype html>
<html lang="zh-CN" data-ui="next">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>发现</title>
<link rel="icon" href="data:,">{pwa_head}
<script>(function(){{var s=null;try{{s=localStorage.getItem('ln-theme');}}catch(e){{}}
var d=(s==='dark'||s==='light')?s:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.documentElement.setAttribute('data-theme',d);}})();</script>
<style>{css()}</style>
</head>
<body class="ui-page-body">{shell(active="发现", title="发现",
  subtitle="从还没读过的作品里挑一本；加入书架不等于收藏。", content=body)}
<script>{library_js()}</script></body></html>'''
