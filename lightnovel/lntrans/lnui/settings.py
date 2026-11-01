"""Settings page for the next UI.

The page owns presentation only.  Server data (PWA head, model summary, LAN
visibility) is passed in as plain strings/booleans.
"""

from __future__ import annotations

from pathlib import Path

from .layout import shell
from .styles import css

_JS_PATH = Path(__file__).resolve().parent.parent / "static" / "lnui-settings.js"


def settings_js() -> str:
    text = _JS_PATH.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(f"settings script is empty: {_JS_PATH}")
    return text


def _choice(label: str, attr_name: str, value: str, *,
            active: bool = False, extra: str = "") -> str:
    cls = "ui-btn ui-btn-choice on" if active else "ui-btn ui-btn-choice"
    return (f'<button type="button" class="{cls}" '
            f'{attr_name}="{value}"{(" " + extra) if extra else ""}>'
            f'{label}</button>')


def _lan_block(remembered: int) -> str:
    return f'''
<div class="ui-settings-lan">
  <h3>局域网访问</h3>
  <p class="ui-help">其他设备访问地址：<b id="lanurl">正在获取…</b></p>
  <p class="ui-help">首次打开输一次口令；之后这台电脑会被记住，重启服务也不用再输。
    已记住 {remembered} 台设备。</p>
  <form method="post" action="/logout">
    <button class="ui-btn ui-btn-ghost" type="submit">退出本设备</button>
  </form>
  <p id="lanpeers" class="ui-help">正在获取已连接设备…</p>
</div>'''


def render_settings(*, pwa_head: str, translation_summary: str,
                    lan_enabled: bool, remembered: int = 0,
                    queue_summary: str = "") -> str:
    # Keep data-theme on the buttons for the existing page-level assertion;
    # JS binds to data-set-theme so the root data-theme is not selected too.
    theme = (
        '<div class="ui-choices" id="set-theme">'
        + _choice("浅色", "data-set-theme", "light",
                  extra='data-theme="light"')
        + _choice("深色", "data-set-theme", "dark",
                  extra='data-theme="dark"')
        + _choice("跟随系统", "data-set-theme", "system",
                  extra='data-theme="system"')
        + '</div>'
    )

    fs = ('<div class="ui-choices" id="set-fs">'
          + _choice("小", "data-fs-set", "s")
          + _choice("标准", "data-fs-set", "m")
          + _choice("大", "data-fs-set", "l") + '</div>')
    lh = ('<div class="ui-choices" id="set-lh">'
          + _choice("紧凑", "data-lh-set", "tight")
          + _choice("标准", "data-lh-set", "normal")
          + _choice("宽松", "data-lh-set", "loose") + '</div>')
    jp = ('<div class="ui-choices" id="set-jp-mode">'
          + _choice("只显示中文", "data-jp", "hide")
          + _choice("混排（半透明）", "data-jp", "mix")
          + _choice("对照（整段显示）", "data-jp", "show") + '</div>')
    tap = ('<div class="ui-choices" id="set-tap">'
           + _choice("关闭", "data-tap", "off")
           + _choice("左右点击", "data-tap", "lr")
           + _choice("上下点击", "data-tap", "ud") + '</div>')
    speak = ('<div class="ui-choices" id="set-speak">'
             + _choice("中文", "data-speak", "zh")
             + _choice("日文", "data-speak", "jp") + '</div>')

    content = f'''
<div class="ui-settings-page">
  <div class="ui-stack">
    {queue_summary}
    <section class="ui-settings-grid">
      <div class="ui-panel">
        <div class="ui-section-head"><div><span class="ui-kicker">APPEARANCE</span>
          <h2>外观</h2><p>管理页和阅读器各自记住偏好。</p></div></div>
        <div class="ui-settings-group"><span class="ui-label">主题</span>{theme}</div>
        <div class="ui-settings-group"><span class="ui-label">阅读字号</span>{fs}</div>
        <div class="ui-settings-group"><span class="ui-label">行距</span>{lh}</div>
        <div class="ui-settings-preview" id="fs-preview">
          雨声落在窗沿上，像有人在很轻地敲门。她把书翻到下一页，却没有看进去。
        </div>
      </div>
      <div class="ui-panel">
        <div class="ui-section-head"><div><span class="ui-kicker">READING</span>
          <h2>阅读</h2><p>这些偏好在阅读页立即生效。</p></div></div>
        <div class="ui-settings-group"><span class="ui-label">日文原文</span>{jp}
          <p class="ui-help">混排：日文以小字半透明跟在译文后。</p></div>
        <div class="ui-settings-group"><span class="ui-label">翻页手势</span>{tap}
          <p class="ui-help">左右/上下区域翻页；按钮、链接和术语气泡不受影响。</p></div>
        <div class="ui-settings-group"><span class="ui-label">朗读</span>{speak}
          <p class="ui-help">使用设备自带语音，不花钱、不联网。</p></div>
      </div>
    </section>

    <section class="ui-settings-grid">
      <div class="ui-panel">
        <div class="ui-section-head"><div><span class="ui-kicker">TRANSLATION</span>
          <h2>翻译</h2><p>模型角色与今日花费。</p></div></div>
        <div class="ui-settings-summary">{translation_summary}</div>
        <p class="ui-help">预算与暂停在阅读页的「阅读与翻译设置」里；
          <a href="/queue">打开翻译列表</a>。</p>
      </div>
      <div class="ui-panel">
        <div class="ui-section-head"><div><span class="ui-kicker">DATA</span>
          <h2>数据</h2><p>译文、术语表、书架状态只在这台机器上保存。</p></div></div>
        <div class="ui-inline-actions">
          <a class="ui-btn ui-btn-primary" href="/api/backup" download>下载备份 zip</a>
          <a class="ui-btn" href="/import">导入本地 EPUB/TXT</a>
        </div>
        <p class="ui-help" style="margin-top:10px">换机或重置前先下载备份；备份会落到手机「下载」目录。</p>
      </div>
    </section>

    <section class="ui-panel">
      <div class="ui-section-head"><div><span class="ui-kicker">HELP</span>
        <h2>使用说明</h2></div></div>
      <div class="ui-settings-help">
        · 推荐与书库里的作品点开是详情页；加入书架后可直接阅读，向下滚动会自动续译<br>
        · 加入书架只决定能否阅读，不代表收藏，也不影响偏好画像<br>
        · 收藏用于记录偏好：参与口味学习，并始终检查更新<br>
        · 已读完/已弃文不再自动翻译；弃文同时取消收藏<br>
        · 默认仅在打开作品时检查更新；需要全量检查时用书架顶部的「检查全部更新」
      </div>
    </section>

    {_lan_block(remembered) if lan_enabled else ""}
  </div>
</div>'''

    body = shell(
        active="我的",
        eyebrow="设置",
        title="阅读与应用",
        subtitle="主题、阅读、翻译与数据都在这里。",
        content=content,
        actions='<a class="ui-btn ui-btn-ghost" href="/">返回书架</a>',
    )
    return f'''<!doctype html>
<html lang="zh-CN" data-ui="next" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>设置</title>
<link rel="icon" href="data:,">{pwa_head}
<script>(function(){{var s=null;try{{s=localStorage.getItem('ln-theme');}}catch(e){{}}
var d=(s==='dark'||s==='light')?s:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.documentElement.setAttribute('data-theme',d);}})();</script>
<style>{css()}</style>
</head>
<body class="ui-settings-body">
{body}
<script>{settings_js()}</script>
</body></html>'''
