"""New UI stylesheet loader.

The new UI lives behind ``data-ui="next"``.  Keeping the stylesheet in its own
file makes the migration boundary explicit: old pages never load this file.
"""

from __future__ import annotations

from .static import read_static


def css() -> str:
    return read_static("lnui.css")
