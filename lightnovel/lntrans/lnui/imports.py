"""Local EPUB/TXT import page with a resumable job view."""

from __future__ import annotations

from pathlib import Path

from .layout import shell
from .styles import css

_JS_PATH = Path(__file__).resolve().parent.parent / "static" / "lnui-import.js"


def import_js() -> str:
    text = _JS_PATH.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(f"import script is empty: {_JS_PATH}")
    return text


def render_import(*, pwa_head: str = "") -> str:
    body = '''
<div data-ui-import>
  <div class="ui-panel ui-import-panel">
    <div class="ui-section-head"><div><span class="ui-kicker">IMPORT</span>
      <h2>选择文件</h2>
      <p>支持日文 EPUB（按 spine 拆章）与 TXT（按第 N 话/序章/闲话拆章）。
        导入只建书，不花 token。</p></div></div>
    <div class="ui-form-grid">
      <label class="ui-field"><span class="ui-label">文件</span>
        <input id="imp-file" type="file" accept=".epub,.txt,application/epub+zip,text/plain"></label>
      <label class="ui-field"><span class="ui-label">书名（可选）</span>
        <input id="imp-title" class="ui-input" autocomplete="off"
          placeholder="留空则用 EPUB 元数据或文件名"></label>
      <label class="ui-field"><span class="ui-label">作者（可选）</span>
        <input id="imp-author" class="ui-input" autocomplete="off"></label>
    </div>
    <div class="ui-inline-actions">
      <button id="imp-go" type="button" class="ui-btn ui-btn-primary">导入</button>
      <button id="imp-retry" type="button" class="ui-btn ui-btn-ghost" hidden>继续导入</button>
      <a class="ui-btn ui-btn-ghost" href="/shelf">返回书架</a>
    </div>
    <p id="imp-status" class="ui-help">选择文件后开始；离开页面也会继续。</p>
    <div class="ui-import-progress" id="imp-progress" hidden>
      <div class="ui-qbar"><i id="imp-fill" style="width:0%"></i></div>
      <div class="ui-qmeta"><span id="imp-pct">0%</span><span id="imp-step"></span></div>
    </div>
  </div>
</div>'''
    return f'''<!doctype html>
<html lang="zh-CN" data-ui="next">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>导入本地书</title>
<link rel="icon" href="data:,">{pwa_head}
<script>(function(){{var s=null;try{{s=localStorage.getItem('ln-theme');}}catch(e){{}}
var d=(s==='dark'||s==='light')?s:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.documentElement.setAttribute('data-theme',d);}})();</script>
<style>{css()}</style>
</head>
<body class="ui-page-body">{shell(active="书库", title="导入本地 EPUB / TXT",
  subtitle="导入任务会在后台继续；完成后自动打开阅读。", content=body)}
<script>{import_js()}</script></body></html>'''
