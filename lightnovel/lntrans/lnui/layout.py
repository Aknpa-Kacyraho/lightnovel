"""Application shell for the new UI."""

from __future__ import annotations

from .components import esc
from .icons import icon

NAV = (
    ("发现", "/discover", "compass"),
    ("书架", "/shelf", "shelf"),
    ("书库", "/library", "library"),
    ("我的", "/settings", "user"),
)


def _nav(active: str) -> str:
    rows = []
    for label, href, name in NAV:
        cls = "ui-nav-link on" if label == active else "ui-nav-link"
        rows.append(f'<a class="{cls}" href="{href}">{icon(name)}'
                    f'<span>{esc(label)}</span></a>')
    return "".join(rows)


def _mobile_nav(active: str) -> str:
    rows = []
    for label, href, name in NAV:
        cls = "ui-mobile-link on" if label == active else "ui-mobile-link"
        rows.append(f'<a class="{cls}" href="{href}">{icon(name)}'
                    f'<span>{esc(label)}</span></a>')
    return f'<nav class="ui-mobile-nav" aria-label="主导航">{"".join(rows)}</nav>'


def shell(*, active: str, title: str, content: str, eyebrow: str = "",
          subtitle: str = "", actions: str = "") -> str:
    sub = f'<p class="ui-page-sub">{esc(subtitle)}</p>' if subtitle else ""
    eye = f'<div class="ui-eyebrow">{esc(eyebrow)}</div>' if eyebrow else ""
    act = f'<div class="ui-page-actions">{actions}</div>' if actions else ""
    return f'''
<div class="ui-shell">
  <aside class="ui-sidebar">
    <a class="ui-brand" href="/">
      <span class="ui-brand-mark">{icon("book")}</span>
      <span><b>灯下</b><small>轻小说书架</small></span>
    </a>
    <nav class="ui-nav" aria-label="主导航">{_nav(active)}</nav>
    <div class="ui-sidebar-foot">
      <span class="ui-dot"></span>
      <span>本地书库</span>
    </div>
  </aside>
  <div class="ui-content">
    <header class="ui-topbar">
      <div class="ui-page-heading">{eye}<h1>{esc(title)}</h1>{sub}</div>
      {act}
    </header>
    <main class="ui-main">{content}</main>
  </div>
  {_mobile_nav(active)}
</div>'''
