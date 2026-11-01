"""Shelf and library pages for the next UI.

The page module only formats rows supplied by the server.  It deliberately
stays downstream of routing/data, so the data layer can be tested without a browser.
"""

from __future__ import annotations

import json

from pathlib import Path

from .components import attr, badge, button, empty, esc
from .icons import icon
from .layout import shell
from .styles import css

_JS_PATH = Path(__file__).resolve().parent.parent / "static" / "lnui-library.js"
SOURCE_LABELS = {"local": "本地导入", "source": "源站"}
STATE_LABELS = {
    "reading": "在读",
    "want": "想读",
    "finished": "已读完",
    "dropped": "已弃文",
}


def library_js() -> str:
    text = _JS_PATH.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(f"library script is empty: {_JS_PATH}")
    return text


def _source_badge(row: dict) -> str:
    key = row.get("source_key") or "source"
    tone = "local" if key == "local" else "source"
    return badge(SOURCE_LABELS.get(key, "源站"), tone=tone)


def _state_badge(row: dict) -> str:
    state = row.get("tracking") or ""
    if state not in STATE_LABELS:
        return ""
    return badge(STATE_LABELS[state], tone=state)


def _work_card(row: dict, *, shelf: bool = False) -> str:
    title = row.get("title") or row.get("title_jp") or "未命名作品"
    jp = row.get("title_jp") or ""
    subtitle = jp if jp and jp != title else ""
    tags = "".join(
        f'<a class="ui-tag" href="/tags?q={attr(t)}">{esc(t)}</a>'
        for t in (row.get("tags") or [])[:5] if t)
    total = int(row.get("total") or 0)
    read = int(row.get("read") or 0)
    meta = " · ".join(x for x in (
        row.get("author") or "",
        f"{total} 话" if total else "",
        f"读到 {read} 话" if read else "",
    ) if x)
    href = row.get("href") or ""
    read_href = row.get("read_href") or ""
    source = row.get("source_key") or "source"
    state = row.get("tracking") or ""
    actions = []
    if read_href:
        actions.append(f'<a class="ui-btn ui-btn-primary" href="{attr(read_href)}">'
                       f'{icon("play")}<span>阅读</span></a>')
    if href:
        actions.append(f'<a class="ui-btn ui-btn-ghost" href="{attr(href)}">详情</a>')
    if not shelf and not read_href and row.get("url"):
        actions.append(button("加入书架", tone="secondary",
                              attrs=f'data-import-url="{attr(row["url"])}"'))
    title_html = (f'<a href="{attr(href)}">{esc(title)}</a>'
                  if href else esc(title))
    sub_html = f'<div class="ui-card-sub">{esc(subtitle)}</div>' if subtitle else ""
    tags_html = f'<div class="ui-tags">{tags}</div>' if tags else ""
    act_html = f'<div class="ui-card-foot">{"".join(actions)}</div>' if actions else ""
    return (
        f'<article class="ui-card ui-work-card" data-work-card '
        f'data-href="{attr(href)}" '
        f'data-source="{attr(source)}" data-state="{attr(state)}" '
        f'data-unstarted="{0 if row.get("on_shelf") or row.get("favorite") else 1}" '
        f'data-hay="{attr((title + " " + (row.get("author") or "") + " " + jp).lower())}">'
        '<div class="ui-card-body">'
        f'<div class="ui-card-top">{_source_badge(row)}{_state_badge(row)}</div>'
        f'<h3 class="ui-card-title">{title_html}</h3>{sub_html}'
        + (f'<div class="ui-card-meta">{esc(meta)}</div>' if meta else "")
        + tags_html + '</div>' + act_html + '</article>'
    )


def _placeholder(row: dict) -> str:
    title = row.get("title") or "未命名作品"
    url = row.get("url") or ""
    tags = "".join(
        f'<span class="ui-tag">{esc(t)}</span>'
        for t in (row.get("tags") or [])[:4] if t)
    return (
        '<article class="ui-card ui-work-card ui-card-placeholder" '
        f'data-work-card data-source="source" data-unstarted="1" '
        f'data-hay="{attr((title + " " + (row.get("author") or "")).lower())}">'
        '<div class="ui-card-body">'
        '<div class="ui-card-top">'
        f'{badge("未导入", tone="warn")}{badge("源站", tone="source")}'
        '</div>'
        f'<h3 class="ui-card-title">{esc(title)}</h3>'
        + (f'<div class="ui-card-meta">{esc(row.get("author") or "")}</div>'
           if row.get("author") else "")
        + (f'<div class="ui-tags">{tags}</div>' if tags else "")
        + '</div><div class="ui-card-foot">'
        + button("导入并阅读", tone="primary",
                 attrs=f'data-import-url="{attr(url)}" data-import-read="1"')
        + '</div></article>'
    )


def _tag_drawer(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'''
<div id="ui-tag-drawer" data-ui-tags data-tag-drawer hidden>
  <div class="ui-drawer-head"><h2>标签</h2>
    <button type="button" class="ui-drawer-close" data-tag-close aria-label="关闭标签">&times;</button></div>
  <div class="ui-toolbar">
    <label class="ui-search"><span class="ui-sr">搜索标签</span>
      <input type="search" data-tag-search placeholder="搜索标签"></label>
    <button type="button" class="ui-btn ui-btn-ghost" data-tag-clear hidden>清除已选</button>
    <a class="ui-btn ui-btn-ghost" href="/tags">全部标签</a>
  </div>
  <section class="ui-tag-group" data-tag-selected-wrap hidden>
    <div class="ui-group-head"><h2>已选</h2><span class="ui-count" data-tag-selected-n>0 个</span></div>
    <div class="ui-tag-list" data-tag-selected></div>
  </section>
  <section class="ui-tag-group" data-tag-recent-wrap>
    <div class="ui-group-head"><h2>最近新增</h2></div>
    <div class="ui-tag-list" data-tag-recent></div>
  </section>
  <section class="ui-tag-group">
    <div class="ui-group-head"><h2>全部标签</h2><span class="ui-count" data-tag-total></span></div>
    <div class="ui-tag-list" data-tag-all></div>
    <button type="button" class="ui-btn ui-btn-ghost" data-tag-more hidden>加载更多</button>
  </section>
  <div class="ui-tag-result">
    <p class="ui-help" data-tag-empty hidden>没有匹配的标签。</p>
    <p class="ui-help" data-tag-zeno hidden>选中的标签没有同时命中的作品，移除一个再试。</p>
    <a class="ui-btn ui-btn-primary" data-tag-open-result hidden href="/library">在书库中查看</a>
  </div>
  <script type="application/json" data-tags-json>{data}</script>
</div>'''


def _toolbar(*, source_counts: dict, search: bool, view: bool,
             tag_drawer: bool = False) -> str:
    def chip(key: str, label: str) -> str:
        n = source_counts.get(key, 0)
        extra = f'<span class="ui-chip-n">{n}</span>' if key != "all" else ""
        return (f'<button type="button" class="ui-chip on" data-source-filter="{key}">'
                f'{esc(label)}{extra}</button>' if key == "all" else
                f'<button type="button" class="ui-chip" data-source-filter="{key}">'
                f'{esc(label)}{extra}</button>')
    search_html = ('<label class="ui-search"><span class="ui-sr">搜索</span>'
                   '<input type="search" data-search placeholder="搜索书名或作者">'
                   '</label>' if search else "")
    view_html = ('<div class="ui-segmented" data-view-toggle>'
                 '<button type="button" class="on" data-view="new">未开始</button>'
                 '<button type="button" data-view="all">全部</button></div>'
                 if view else "")
    tag_html = ('<button type="button" class="ui-btn ui-btn-ghost" data-tag-open>'
                f'{icon("tag")}<span>标签</span></button>' if tag_drawer else
                f'<a class="ui-btn ui-btn-ghost" href="/tags">{icon("tag")}'
                '<span>标签</span></a>')
    return (f'<div class="ui-toolbar" data-ui-toolbar>'
            f'<div class="ui-filterbar">'
            f'{chip("all", "全部")}{chip("source", "源站")}{chip("local", "本地导入")}'
            f'</div>{search_html}{view_html}{tag_html}</div>')


def _group(title: str, rows: list[dict], note: str = "") -> str:
    if not rows:
        return ""
    cards = "".join(_work_card(r) for r in rows)
    note_html = f'<span class="ui-group-note">{esc(note)}</span>' if note else ""
    return (f'<section class="ui-shelf-group"><div class="ui-group-head">'
            f'<h2>{esc(title)}</h2><span class="ui-count">{len(rows)} 本</span>'
            f'{note_html}</div><div class="ui-work-grid">{cards}</div></section>')


def _doc(*, active: str, page: str, title: str, subtitle: str, body: str,
         pwa_head: str = "", script: str | None = None) -> str:
    wrapped = f'<div data-ui-library data-page="{attr(page)}">{body}</div>'
    return f'''<!doctype html>
<html lang="zh-CN" data-ui="next">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>{esc(title)}</title>
<link rel="icon" href="data:,">{pwa_head}
<script>(function(){{var s=null;try{{s=localStorage.getItem('ln-theme');}}catch(e){{}}
var d=(s==='dark'||s==='light')?s:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.documentElement.setAttribute('data-theme',d);}})();</script>
<style>{css()}</style>
</head>
<body class="ui-page-body">
{shell(active=active, title=title, subtitle=subtitle, content=wrapped)}
<script>{script if script is not None else (library_js() + chr(10) + tags_js())}</script>
</body></html>'''


def render_shelf(rows: list[dict], unimported: list[dict], *,
                 source_counts: dict, pwa_head: str = "",
                 tag_payload: dict | None = None) -> str:
    groups = []
    for key in ("reading", "want", "finished", "dropped"):
        groups.append(_group(STATE_LABELS[key],
                             [r for r in rows if r.get("tracking") == key]))
    if unimported:
        groups.append(
            '<section class="ui-shelf-group"><div class="ui-group-head">'
            '<h2>想读 · 未导入</h2>'
            f'<span class="ui-count">{len(unimported)} 本</span></div>'
            '<div class="ui-work-grid">'
            + "".join(_placeholder(r) for r in unimported)
            + '</div></section>')
    body = (_toolbar(source_counts=source_counts, search=False, view=False,
                     tag_drawer=bool(tag_payload))
            + "".join(groups))
    if tag_payload:
        body += _tag_drawer(tag_payload)
    if not groups:
        body += empty("书架还是空的",
                      "从发现页挑一本，或导入你自己手里的 EPUB/TXT。",
                      '<a class="ui-btn ui-btn-primary" href="/">去发现</a>'
                      '<a class="ui-btn ui-btn-ghost" href="/import">导入本地书</a>')
    return _doc(active="书架", page="shelf", title="书架",
                subtitle="在读、想读、读完和弃文；收藏不单独分组。",
                body=body, pwa_head=pwa_head)


def render_library(rows: list[dict], *, source_counts: dict,
                   selected_tags=(), pwa_head: str = "",
                   tag_payload: dict | None = None) -> str:
    cards = "".join(_work_card(r) for r in rows)
    body = _toolbar(source_counts=source_counts, search=True, view=True,
                    tag_drawer=bool(tag_payload))
    if tag_payload:
        body += _tag_drawer(tag_payload)
    if selected_tags:
        body += ('<div class="ui-selected-tags">已选标签：'
                 + "".join(f'<span class="ui-tag">{esc(t)}</span>'
                           for t in selected_tags) + '</div>')
    if cards:
        body += (f'<div class="ui-work-grid" data-work-grid>{cards}</div>'
                 '<p class="ui-help" data-filter-empty hidden>没有匹配的作品，'
                 '换一个来源或搜索词试试。</p>')
    else:
        body += empty("书库里还没有作品",
                      "可以调整筛选、重新抓取源站，或导入本地 EPUB/TXT。",
                      '<a class="ui-btn ui-btn-primary" href="/">去发现</a>'
                      '<a class="ui-btn ui-btn-ghost" href="/import">导入本地书</a>')
    return _doc(active="书库", page="library", title="书库",
                subtitle="源站和本地导入都在这里；移动端默认看还未开始的书。",
                body=body, pwa_head=pwa_head)

_TAGS_JS_PATH = Path(__file__).resolve().parent.parent / "static" / "lnui-tags.js"


def tags_js() -> str:
    text = _TAGS_JS_PATH.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(f"tags script is empty: {_TAGS_JS_PATH}")
    return text


def render_tags(tags: list[dict], recent: list[str], works: list[list[str]], *,
                pwa_head: str = "") -> str:
    import json
    payload = json.dumps({"tags": tags, "recent": recent, "works": works},
                         ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c")
    body = f'''
<div data-ui-tags>
  <div class="ui-toolbar">
    <label class="ui-search"><span class="ui-sr">搜索标签</span>
      <input type="search" data-tag-search placeholder="搜索标签"></label>
    <button type="button" class="ui-btn ui-btn-ghost" data-tag-clear hidden>清除已选</button>
    <a class="ui-btn ui-btn-ghost" href="/library">去书库</a>
  </div>
  <section class="ui-tag-group" data-tag-selected-wrap hidden>
    <div class="ui-group-head"><h2>已选</h2><span class="ui-count" data-tag-selected-n>0 个</span></div>
    <div class="ui-tag-list" data-tag-selected></div>
  </section>
  <section class="ui-tag-group" data-tag-recent-wrap>
    <div class="ui-group-head"><h2>最近新增</h2><span class="ui-group-note">按作品加入时间</span></div>
    <div class="ui-tag-list" data-tag-recent></div>
  </section>
  <section class="ui-tag-group">
    <div class="ui-group-head"><h2>全部标签</h2>
      <span class="ui-count" data-tag-total></span></div>
    <div class="ui-tag-list" data-tag-all></div>
    <div class="ui-inline-actions"><button type="button" class="ui-btn ui-btn-ghost"
      data-tag-more hidden>加载更多</button></div>
  </section>
  <div class="ui-tag-result">
    <p class="ui-help" data-tag-empty hidden>没有匹配的标签。</p>
    <p class="ui-help" data-tag-zeno hidden>选中的标签没有同时命中的作品，移除一个再试。</p>
    <a class="ui-btn ui-btn-primary" data-tag-open hidden href="/library">查看选中作品</a>
  </div>
</div>
<script type="application/json" id="ui-tags-data">{payload}</script>'''
    return _doc(active="标签", page="tags", title="标签",
                subtitle="搜索、组合标签；多选按 AND 同时满足。",
                body=body, pwa_head=pwa_head, script=tags_js())
