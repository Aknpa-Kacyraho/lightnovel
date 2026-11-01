"""Small, dependency-free render helpers for the new UI.

They accept plain data and return strings.  This module must not import the
server module: the UI layer is downstream of routing/data, never the reverse.
"""

from __future__ import annotations

import html

from .icons import icon


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def attr(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def button(label: str, *, tone: str = "default", attrs: str = "",
           icon_name: str = "", disabled: bool = False) -> str:
    cls = f"ui-btn ui-btn-{tone}"
    if icon_name:
        lead = icon(icon_name, "ui-btn-icon")
    else:
        lead = ""
    dis = " disabled" if disabled else ""
    return (f'<button type="button" class="{cls}"{dis}{(" " + attrs) if attrs else ""}>'
            f'{lead}<span>{esc(label)}</span></button>')


def badge(label: str, *, tone: str = "default") -> str:
    return f'<span class="ui-badge ui-badge-{attr(tone)}">{esc(label)}</span>'


def tag(label: str, *, href: str = "") -> str:
    body = esc(label)
    if href:
        return f'<a class="ui-tag" href="{attr(href)}">{body}</a>'
    return f'<span class="ui-tag">{body}</span>'


def card(*, title: str, subtitle: str = "", synopsis: str = "",
         meta: str = "", tags=(), actions: str = "",
         href: str = "", tone: str = "") -> str:
    tag_html = "".join(tag(t) for t in tags)
    body = (
        f'<article class="ui-card{" ui-card-" + attr(tone) if tone else ""}">'
        f'<div class="ui-card-body">'
        f'<h3 class="ui-card-title">{esc(title)}</h3>'
        + (f'<div class="ui-card-sub">{esc(subtitle)}</div>' if subtitle else "")
        + (f'<p class="ui-card-syn">{esc(synopsis)}</p>' if synopsis else "")
        + (f'<div class="ui-card-meta">{esc(meta)}</div>' if meta else "")
        + (f'<div class="ui-tags">{tag_html}</div>' if tag_html else "")
        + '</div>'
        + (f'<div class="ui-card-foot">{actions}</div>' if actions else "")
        + '</article>'
    )
    if href:
        return f'<a class="ui-card-link" href="{attr(href)}">{body}</a>'
    return body


def field(label: str, name: str, *, value: str = "", kind: str = "text",
          placeholder: str = "", help_text: str = "") -> str:
    help_html = f'<p class="ui-help">{esc(help_text)}</p>' if help_text else ""
    return (
        f'<label class="ui-field" for="{attr(name)}">'
        f'<span class="ui-label">{esc(label)}</span>'
        f'<input class="ui-input" id="{attr(name)}" name="{attr(name)}" '
        f'type="{attr(kind)}" value="{attr(value)}" '
        f'placeholder="{attr(placeholder)}">'
        f'{help_html}</label>'
    )


def select(label: str, name: str, options, *, selected: str = "") -> str:
    opts = "".join(
        f'<option value="{attr(v)}"{" selected" if v == selected else ""}>'
        f'{esc(t)}</option>' for v, t in options)
    return (
        f'<label class="ui-field" for="{attr(name)}">'
        f'<span class="ui-label">{esc(label)}</span>'
        f'<select class="ui-input" id="{attr(name)}" name="{attr(name)}">'
        f'{opts}</select></label>'
    )


def empty(title: str, body: str = "", action: str = "") -> str:
    return (
        '<div class="ui-empty">'
        f'<div class="ui-empty-mark">{icon("book", "ui-empty-icon")}</div>'
        f'<h3>{esc(title)}</h3>'
        + (f'<p>{esc(body)}</p>' if body else "")
        + (f'<div class="ui-empty-action">{action}</div>' if action else "")
        + '</div>'
    )
