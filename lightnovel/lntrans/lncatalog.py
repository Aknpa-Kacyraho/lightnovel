"""Catalog schema and compatibility adapter.

New shape (one file):

    {
      "schema_version": 1,
      "items": {...},        # real user-owned records
      "candidates": {...},   # rebuildable discovery cache
      "aliases": {old: final}
    }

The old flat ``{id: work}`` shape remains readable during the reset.  This
module is deliberately free of server imports; it is a pure data adapter.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = 1
SHELF_STATES = ("want", "reading", "finished", "dropped")
_CONTENT_FIELDS = (
    "title", "url", "author", "tags", "genre", "episodes", "characters",
    "points", "updated", "sources", "origins",
)
_LOCK = threading.RLock()


class CatalogError(ValueError):
    pass


class CatalogSchemaError(CatalogError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def source_slug(source: str, source_id: str) -> str:
    return f"{source}-{source_id}"


def new_local_id() -> str:
    return f"local-{uuid.uuid4().hex[:12]}"


def aliases_path(library_path: str) -> str:
    return os.path.join(os.path.dirname(library_path) or ".", "slug-aliases.json")


def load_aliases(library_path: str) -> dict:
    out = {}
    try:
        with open(library_path, encoding="utf-8") as f:
            obj = json.load(f)
        if is_catalog(obj):
            out.update({str(k): str(v) for k, v in obj.get("aliases", {}).items()})
    except (OSError, json.JSONDecodeError, CatalogError):
        pass
    sidecar = aliases_path(library_path)
    try:
        with open(sidecar, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            out.update({str(k): str(v) for k, v in data.items()})
    except (OSError, json.JSONDecodeError):
        pass
    return out


def resolve_alias(slug: str, aliases: dict) -> str:
    seen = set()
    cur = str(slug)
    while cur in aliases and cur not in seen:
        seen.add(cur)
        cur = str(aliases[cur])
    return cur


def choose_slug(candidate: str, aliases: dict, taken=(), current: str = "") -> str:
    """Pick a slug without stealing a reserved alias key.

    A→B→A revival: if the candidate is an alias key whose target is this same
    item, the caller may reuse it (and should remove that alias).
    """
    candidate = str(candidate)
    taken = {str(x) for x in taken}
    if candidate in aliases and aliases[candidate] == current:
        return candidate
    if candidate not in aliases and candidate not in taken:
        return candidate
    n = 2
    while f"{candidate}-{n}" in aliases or f"{candidate}-{n}" in taken:
        n += 1
    return f"{candidate}-{n}"


def empty_catalog() -> dict:
    return {"schema_version": SCHEMA_VERSION, "items": {},
            "candidates": {}, "aliases": {}}


def is_catalog(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    if "schema_version" in obj:
        return True
    # A flat legacy library can legitimately contain a work whose id is
    # "items"; only call it a catalog when all three zones are present.
    return all(k in obj for k in ("items", "candidates", "aliases"))


def _source_of(wid: str, entry: dict) -> str:
    src = str(entry.get("source") or "").strip()
    if src:
        return src
    if wid.startswith("local-"):
        return "local"
    if wid.startswith("kakuyomu-"):
        return "kakuyomu"
    if wid.startswith("syosetu-"):
        return "syosetu"
    if re.match(r"^n\d{4}[a-z]+$", wid):
        return "syosetu"
    return "kakuyomu"


def _source_id_of(wid: str, source: str) -> str:
    prefix = source + "-"
    if source in ("kakuyomu", "syosetu", "local") and wid.startswith(prefix):
        return wid[len(prefix):]
    return wid


def _normal_entry(wid: str, entry: dict) -> dict:
    row = dict(entry or {})
    row["id"] = str(row.get("id") or wid)
    source = _source_of(wid, row)
    row.setdefault("source", source)
    row.setdefault("source_id", _source_id_of(wid, source))
    row.setdefault("slug", wid if wid.startswith(
        ("kakuyomu-", "syosetu-", "local-")) else None)
    row.setdefault("source_first_seen", row.get("first_seen"))
    shelf = row.get("shelf")
    if shelf not in SHELF_STATES:
        shelf = "want" if row.get("want") else None
    row["shelf"] = shelf
    row["favorite"] = bool(row.get("favorite"))
    row["hidden"] = bool(row.get("hidden"))
    return row


def _is_item(entry: dict) -> bool:
    return bool(entry.get("shelf") or entry.get("favorite")
                or entry.get("hidden") or entry.get("added_at")
                or entry.get("imported"))


def from_legacy_flat(flat: dict) -> dict:
    cat = empty_catalog()
    for wid, entry in (flat or {}).items():
        if not isinstance(entry, dict):
            continue
        wid = str(wid)
        row = _normal_entry(wid, entry)
        if _is_item(row):
            row.setdefault("added_at", row.get("source_first_seen") or utc_now())
            cat["items"][wid] = row
        else:
            cat["candidates"][wid] = row
    return cat


def load_obj(obj, *, path: str = "") -> dict:
    if not isinstance(obj, dict):
        raise CatalogSchemaError(f"catalog must be an object: {path}")
    if not is_catalog(obj):
        return from_legacy_flat(obj)
    ver = obj.get("schema_version")
    if ver != SCHEMA_VERSION:
        raise CatalogSchemaError(
            f"unsupported catalog schema_version={ver!r} at {path}; "
            f"expected {SCHEMA_VERSION}")
    for key in ("items", "candidates", "aliases"):
        if not isinstance(obj.get(key), dict):
            raise CatalogSchemaError(f"catalog.{key} must be an object: {path}")
    cat = empty_catalog()
    for zone in ("items", "candidates"):
        for wid, entry in obj[zone].items():
            if not isinstance(entry, dict):
                raise CatalogSchemaError(
                    f"catalog.{zone}[{wid!r}] must be an object: {path}")
            row = _normal_entry(str(wid), entry)
            if zone == "items":
                row.setdefault("added_at", row.get("source_first_seen") or utc_now())
            cat[zone][str(wid)] = row
    for old, final in obj["aliases"].items():
        if not isinstance(old, str) or not isinstance(final, str):
            raise CatalogSchemaError(f"catalog.aliases must map strings: {path}")
        cat["aliases"][old] = final
    return cat


def load(path: str) -> dict:
    if not os.path.exists(path):
        return empty_catalog()
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    return load_obj(obj, path=path)


def save(path: str, cat: dict) -> None:
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with _LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cat, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)


def import_state(item: dict, novels_dir: str) -> str:
    """Derive the three-state import status from the book directory.

    ``imported`` requires both the real meta file and a completed checkpoint.
    An existing but incomplete checkpoint is ``importing``; no checkpoint is
    ``not_imported``.
    """
    wid = str(item.get("id") or "")
    if not wid:
        return "not_imported"
    base = os.path.join(novels_dir, wid)
    marker = os.path.join(base, ".import.json")
    meta = os.path.join(base, "meta.json")
    if not os.path.isfile(marker):
        return "not_imported"
    try:
        with open(marker, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return "not_imported"
    if data.get("complete") and os.path.isfile(meta):
        return "imported"
    return "importing"


def legacy_view(cat: dict) -> dict:
    """Flatten the catalog for old readers. Items override candidates."""
    out = {}
    for zone in ("candidates", "items"):
        for wid, entry in (cat.get(zone) or {}).items():
            row = dict(entry)
            row.setdefault("id", wid)
            if row.get("source_first_seen") and not row.get("first_seen"):
                row["first_seen"] = row["source_first_seen"]
            shelf = row.get("shelf")
            row["want"] = shelf == "want"
            row["hidden"] = bool(row.get("hidden"))
            row["favorite"] = bool(row.get("favorite"))
            out[str(wid)] = row
    return out


def merge_flat_view(cat: dict, flat: dict) -> dict:
    """Apply old flat-view mutations to a new catalog without losing zones."""
    cat = load_obj(cat)
    items, candidates = cat["items"], cat["candidates"]
    for wid, src in (flat or {}).items():
        if not isinstance(src, dict):
            continue
        wid = str(wid)
        cur = items.get(wid) or candidates.get(wid)
        if cur is None:
            cur = _normal_entry(wid, src)
        for key in _CONTENT_FIELDS:
            if key in src:
                cur[key] = src[key]
        want = bool(src.get("want"))
        hidden = bool(src.get("hidden"))
        shelf = src.get("shelf")
        if shelf not in SHELF_STATES:
            shelf = "want" if want else cur.get("shelf")
        cur["shelf"] = shelf
        cur["favorite"] = bool(src.get("favorite") or cur.get("favorite"))
        cur["hidden"] = hidden
        if (shelf or cur["favorite"] or hidden) and wid not in items:
            candidates.pop(wid, None)
            cur.setdefault("added_at", utc_now())
            items[wid] = cur
        elif wid in items:
            items[wid] = cur
        else:
            candidates[wid] = cur
    return cat
