"""Inline SVG icons for the new UI.

No icon package and no external asset: every icon is a tiny, local SVG path.
"""

from __future__ import annotations

_PATHS = {
    "compass": '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2.1 4.9-4.9 2.1 2.1-4.9 4.9-2.1Z"/>',
    "shelf": '<path d="M4 5.5h5v13H4zM10 5.5h4v13h-4zM15 5.5h5v13h-5z"/><path d="M6 8h1M6 11h1"/>',
    "library": '<path d="M4 19.5V7l8-3 8 3v12.5"/><path d="M8 19.5v-7h8v7M4 19.5h16"/>',
    "user": '<circle cx="12" cy="8" r="3.2"/><path d="M5.5 19.5c.7-3.2 3-5 6.5-5s5.8 1.8 6.5 5"/>',
    "search": '<circle cx="10.5" cy="10.5" r="5.5"/><path d="m15 15 4 4"/>',
    "tag": '<path d="M4 5h7l9 9-6 6-9-9V5Z"/><circle cx="8" cy="9" r="1"/>',
    "book": '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5v-16Z"/><path d="M4 18.5A2.5 2.5 0 0 1 6.5 16H20"/>',
    "play": '<path d="m9 6 9 6-9 6V6Z"/>',
    "heart": '<path d="M12 20s-7-4.4-7-9a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 4.6-7 9-7 9Z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3 2"/>',
    "chevron": '<path d="m9 6 6 6-6 6"/>',
    "close": '<path d="m6 6 12 12M18 6 6 18"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"/>',
}


def icon(name: str, cls: str = "ui-icon") -> str:
    path = _PATHS.get(name, _PATHS["book"])
    return (f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true" '
            f'fill="none" stroke="currentColor" stroke-width="1.7" '
            f'stroke-linecap="round" stroke-linejoin="round">{path}</svg>')
