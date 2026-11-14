"""Shared loader for new-UI static assets.

Keeping newline handling in one place makes the byte-for-byte regression tests
independent of Git's CRLF/LF checkout settings.
"""

from __future__ import annotations

from pathlib import Path

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def read_static(name: str, *, required: bool = True) -> str:
    path = _STATIC_DIR / name
    with path.open("r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    if required and not text.strip():
        raise RuntimeError(f"static asset is empty: {path}")
    return text
