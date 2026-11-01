"""Translation queue page for the next UI."""

from __future__ import annotations

from pathlib import Path

from .components import badge, esc
from .icons import icon
from .layout import shell
from .styles import css

_JS_PATH = Path(__file__).resolve().parent.parent / "static" / "lnui-queue.js"


def queue_js() -> str:
    text = _JS_PATH.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(f"queue script is empty: {_JS_PATH}")
    return text


def _progress(row: dict) -> int:
    total = int(row.get("total") or 0)
    have = int(row.get("have") or 0)
    return round(have / total * 100) if total else 0


def _row(row: dict) -> str:
    slug = row.get("slug") or ""
    title = row.get("title") or slug
    pct = _progress(row)
    reason = row.get("reason") or "queue"
    why = {"reading": "在读 · 持续翻译", "queue": "翻译队列",
           "paused": "已暂停"}.get(reason, "翻译队列")
    if row.get("read"):
        why += f" · 读到 {row['read']} 话"
    if reason == "paused":
        ops = ('<button type="button" class="ui-btn ui-btn-ghost" '
               f'data-q-action="resume" data-slug="{esc(slug)}">继续</button>'
               '<button type="button" class="ui-btn ui-btn-ghost" '
               f'data-q-action="forget" data-slug="{esc(slug)}">移出</button>')
    else:
        ops = ('<button type="button" class="ui-btn ui-btn-ghost" '
               f'data-q-action="pause" data-slug="{esc(slug)}">暂停</button>'
               + (f'<button type="button" class="ui-btn ui-btn-ghost" '
                  f'data-q-action="up" data-slug="{esc(slug)}">上移</button>'
                  f'<button type="button" class="ui-btn ui-btn-ghost" '
                  f'data-q-action="down" data-slug="{esc(slug)}">下移</button>'
                  if reason == "queue" else ""))
    return (f'<li class="ui-qrow" data-qrow data-slug="{esc(slug)}">'
            f'<div class="ui-qmain"><a href="/read/{esc(slug)}">{esc(title)}</a>'
            f'<span class="ui-qwhy">{esc(why)}</span></div>'
            f'<div class="ui-qops">{ops}</div>'
            f'<div class="ui-qbar"><i style="width:{pct}%"></i></div>'
            f'<div class="ui-qmeta"><span>已译 {row.get("have") or 0}/'
            f'{row.get("total") or 0} 话</span><span>{pct}%</span></div></li>')


def _group(title: str, rows: list[dict], note: str = "") -> str:
    if not rows:
        return ""
    note_html = f'<span class="ui-group-note">{esc(note)}</span>' if note else ""
    return (f'<section class="ui-queue-group"><div class="ui-group-head">'
            f'<h2>{esc(title)}</h2><span class="ui-count">{len(rows)} 本</span>'
            f'{note_html}</div><ul class="ui-qlist">'
            + "".join(_row(r) for r in rows) + '</ul></section>')


def _history_row(row: dict, *, failed: bool) -> str:
    slug = row.get("slug") or ""
    title = row.get("title") or slug
    status = row.get("status") or ""
    label = {"provider_error": "失败", "error": "失败",
             "interrupted": "中断", "budget_exhausted": "预算暂停",
             "partial": "部分完成", "done": "已完成",
             "cancelled": "已取消"}.get(status, status)
    tone = "warn" if failed else "ok"
    err = row.get("error") or ""
    return (f'<li class="ui-qrow ui-qrow-history" data-qrow>'
            f'<div class="ui-qmain"><a href="/read/{esc(slug)}">{esc(title)}</a>'
            f'<span class="ui-qwhy">{badge(label, tone=tone)} '
            f'已译 {row.get("have") or 0}/{row.get("total") or 0} 话</span>'
            + (f'<div class="ui-help">{esc(err[:160])}</div>' if err and failed else "")
            + '</div><div class="ui-qops">'
            f'<a class="ui-btn ui-btn-ghost" href="/read/{esc(slug)}">打开</a>'
            '</div></li>')


def _history_group(title: str, rows: list[dict], *, failed: bool,
                   collapsed: bool = False) -> str:
    if not rows:
        return ""
    body = '<ul class="ui-qlist">' + "".join(
        _history_row(r, failed=failed) for r in rows) + '</ul>'
    if collapsed:
        return (f'<details class="ui-queue-group ui-history"><summary>'
                f'{esc(title)} <span class="ui-count">{len(rows)} 本</span></summary>'
                f'{body}</details>')
    return (f'<section class="ui-queue-group"><div class="ui-group-head">'
            f'<h2>{esc(title)}</h2><span class="ui-count">{len(rows)} 本</span></div>'
            f'{body}</section>')


def _doc(body: str, *, pwa_head: str = "") -> str:
    return f'''<!doctype html>
<html lang="zh-CN" data-ui="next">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>翻译列表</title>
<link rel="icon" href="data:,">{pwa_head}
<script>(function(){{var s=null;try{{s=localStorage.getItem('ln-theme');}}catch(e){{}}
var d=(s==='dark'||s==='light')?s:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.documentElement.setAttribute('data-theme',d);}})();</script>
<style>{css()}</style>
</head>
<body class="ui-page-body">{shell(active="我的", title="翻译列表",
  subtitle="在读就一直翻；也可以把书加进来提前翻。", content=body)}
<script>{queue_js()}</script></body></html>'''


def render_queue(view: dict, *, pwa_head: str = "") -> str:
    rows = list(view.get("rows") or []) + list(view.get("paused_rows") or [])
    reading = [r for r in view.get("rows") or [] if r.get("reason") == "reading"]
    queued = [r for r in view.get("rows") or [] if r.get("reason") == "queue"]
    paused = list(view.get("paused_rows") or [])
    have = sum(int(r.get("have") or 0) for r in rows)
    total = sum(int(r.get("total") or 0) for r in rows)
    pct = round(have / total * 100) if total else 0
    status = ("已全局暂停" if view.get("paused") else
              ("今日超出预算（仍在继续）" if view.get("over_budget") else "运行中"))
    body = f'''
<div data-ui-queue>
  <div class="ui-queue-summary">
    <div class="ui-qstat"><b>{len(rows)}</b><span>本在列表</span></div>
    <div class="ui-qstat"><b>{len(reading)}</b><span>在读自动翻</span></div>
    <div class="ui-qstat"><b>{len(queued)}</b><span>排队提前翻</span></div>
    <div class="ui-qstat"><b>{len(paused)}</b><span>已暂停</span></div>
    <div class="ui-qstat ui-qstat-wide"><b>{pct}%</b><span>全部进度 · 已译 {have}/{total} 话</span></div>
  </div>
  <div class="ui-queue-status">
    <span>状态 <b data-q-status>{esc(status)}</b> · 今日云端已用
      <b>{int(view.get("used_today") or 0):,}</b> token · 剩余
      <b>{max(0, int(view.get("budget_left") or 0)):,}</b></span>
    <button type="button" class="ui-btn ui-btn-ghost" data-q-pause-all>
      {"继续全部" if view.get("paused") else "全部暂停"}</button>
    <a class="ui-btn ui-btn-ghost" href="/settings">我的</a>
  </div>
  <p class="ui-help" data-q-live>队列每 7 秒刷新；页面不可见时停止轮询。</p>
  <p class="ui-help">本地模型 0 元，不计入 token；预算只是提醒，超了仍在读的书会继续翻。</p>
  {_group("正在读", reading, "自动持续翻译")}
  {_group("翻译队列", queued, "按顺序提前翻")}
  {_group("已暂停", paused, "不会自动继续")}
  {_history_group("失败/中断", list(view.get("failed") or []), failed=True)}
  {_history_group("已完成", list(view.get("completed") or []), failed=False, collapsed=True)}
  {"" if rows or view.get("failed") or view.get("completed") else '<div class="ui-empty"><h3>翻译列表是空的</h3><p>去书架打开一本书，或在书库点「加入书架」。</p><a class="ui-btn ui-btn-primary" href="/shelf">去书架</a></div>'}
</div>'''
    return _doc(body, pwa_head=pwa_head)
