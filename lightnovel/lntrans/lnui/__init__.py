"""Next-generation UI shell and components (zero dependencies)."""

from .preview import preview_js, render_preview
from .settings import render_settings, settings_js
from .styles import css

__all__ = ["css", "preview_js", "render_preview", "render_settings", "settings_js"]

from .library import (library_js, render_library, render_shelf, render_tags, tags_js)
from .queue import queue_js, render_queue
from .home import render_home
from .imports import render_import

__all__ += ["library_js", "render_library", "render_shelf", "render_tags", "tags_js", "queue_js", "render_queue", "render_home", "render_import"]
