"""New UI stylesheet loader.

The new UI lives behind ``data-ui="next"``.  Keeping the stylesheet in its own
file makes the migration boundary explicit: old pages never load this file.
"""

from __future__ import annotations

from pathlib import Path

_CSS_PATH = Path(__file__).resolve().parent.parent / "static" / "lnui.css"


def css() -> str:
    text = _CSS_PATH.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(f"new UI stylesheet is empty: {_CSS_PATH}")
    return text
