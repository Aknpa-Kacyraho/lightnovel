#!/usr/bin/env python3
"""Dry-run scanner for the catalog reset.

It only reads ``novels/*`` and writes a report.  The actual rename/merge is a
later step; this tool produces the human-reviewable id-map first.

Usage:
    python3 migrate_reset.py [--novels DIR] [--report-dir DIR]
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lndata  # noqa: E402
import lncatalog  # noqa: E402

_NS = uuid.UUID("6f1d8f4e-6d0e-4e7d-9a1b-4e9b76a2b0d1")
_PREFIXES = ("kakuyomu-", "syosetu-", "local-")
_VOLUME_PATTERNS = (
    re.compile(r"\bvol\.?\s*(\d{1,3})\b", re.I),
    re.compile(r"第\s*(\d{1,3})\s*[巻卷]"),
    re.compile(r"[_]\s*(\d{1,3})\s*[_]"),
    re.compile(r"[（(]\s*(\d{1,3})\s*[）)]\s*$"),
    re.compile(r"[\s_](\d{1,3})\s*[～~]"),
    re.compile(r"[\s_](\d{1,3})\s*$"),
    re.compile(r"[（(]\s*(上|下|前編|後編)\s*[）)]\s*$"),
    re.compile(r"[\s_](上|下|前編|後編)\s*$"),
)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return re.sub(r"[\s_＿~～\u200b\u200c\u200d\ufeff]+", "", text)


def split_volume(title: str) -> tuple[str, str]:
    """Return (base title without volume marker, normalized volume token)."""
    text = unicodedata.normalize("NFKC", str(title or "")).strip()
    for pat in _VOLUME_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        vol = m.group(1)
        if vol.isdigit():
            vol = str(int(vol))
        base = (text[:m.start()] + text[m.end():]).strip(" _-－—")
        return base, vol
    return text, ""


def dedupe_key(meta: dict) -> str:
    base, vol = split_volume(meta.get("title") or "")
    author = _norm(meta.get("author") or "")
    if not author:
        author = "id:" + str(meta.get("source_id") or meta.get("id") or "")
    return "\x1f".join((_norm(base), author, vol))


def suspected_duplicates(rows: dict) -> list[dict]:
    pool = list(rows.get("auto") or []) + list(rows.get("conforming") or [])
    groups: list[list[dict]] = []
    for i, left in enumerate(pool):
        for right in pool[i + 1:]:
            if left.get("volume") != right.get("volume"):
                continue
            la = _norm(left.get("author") or "")
            ra = _norm(right.get("author") or "")
            if la and ra and la != ra:
                continue
            base_l, _ = split_volume(left.get("title") or "")
            base_r, _ = split_volume(right.get("title") or "")
            ratio = difflib.SequenceMatcher(None, _norm(base_l),
                                            _norm(base_r)).ratio()
            if ratio < 0.65:
                continue
            pair = {left.get("dir"), right.get("dir")}
            for group in groups:
                if pair & {x.get("dir") for x in group}:
                    group.extend([left, right])
                    break
            else:
                groups.append([left, right])
    out = []
    for group in groups:
        seen, items = set(), []
        for row in group:
            if row.get("dir") in seen:
                continue
            seen.add(row.get("dir"))
            items.append({"dir": row.get("dir"),
                          "title": row.get("title"),
                          "author": row.get("author"),
                          "volume": row.get("volume")})
        if len(items) > 1:
            out.append(items)
    return out


def _source_id(value) -> str:
    s = str(value or "").strip()
    for prefix in _PREFIXES:
        if s.startswith(prefix):
            return s[len(prefix):]
    return s


def _new_id(meta: dict) -> str:
    source = str(meta.get("source") or "").strip() or "kakuyomu"
    sid = _source_id(meta.get("source_id") or meta.get("id") or "")
    if source == "local":
        # deterministic UUID so repeated dry-runs produce the same id-map
        return "local-" + uuid.uuid5(_NS, sid).hex[:12]
    return f"{source}-{sid}"


def _read_meta(book_dir: str):
    try:
        with open(os.path.join(book_dir, "meta.json"), encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def scan(novels_dir: str) -> dict:
    try:
        names = sorted(os.listdir(novels_dir))
    except OSError:
        names = []
    rows = {"auto": [], "manual": [], "ignored": [], "conforming": []}
    for name in names:
        path = os.path.join(novels_dir, name)
        if name.startswith("."):
            rows["ignored"].append({"dir": name, "reason": "dot"})
            continue
        if not os.path.isdir(path):
            rows["ignored"].append({"dir": name, "reason": "not_dir"})
            continue
        meta = _read_meta(path)
        if meta is None:
            rows["manual"].append({"dir": name, "reason": "meta_missing_or_bad"})
            continue
        meta["slug"] = str(meta.get("slug") or name)
        new_id = _new_id(meta)
        _base, _vol = split_volume(meta.get("title") or "")
        if name.startswith(_PREFIXES) and name == new_id:
            rows["conforming"].append({
                "dir": name, "id": new_id,
                "title": meta.get("title") or "",
                "author": meta.get("author") or "",
                "volume": _vol,
                "dedupe_key": dedupe_key(meta),
            })
            continue
        if not _source_id(meta.get("source_id") or meta.get("id") or ""):
            rows["manual"].append({"dir": name, "reason": "source_id_missing"})
            continue
        old_urls = {name}
        if meta.get("slug") and meta["slug"] != name:
            old_urls.add(str(meta["slug"]))
        rows["auto"].append({
            "dir": name,
            "old_urls": sorted(old_urls),
            "new_id": new_id,
            "source": meta.get("source") or "",
            "source_id": meta.get("source_id") or "",
            "title": meta.get("title") or "",
            "author": meta.get("author") or "",
            "volume": _vol,
            "dedupe_key": dedupe_key(meta),
        })
    return rows


def id_map(rows: dict) -> dict:
    out = {}
    for key in ("auto", "conforming"):
        for row in rows.get(key) or []:
            out[row["dir"]] = row.get("new_id") or row.get("id")
    return out


def write_report(rows: dict, report_dir: str, dry_run: bool = True) -> str:
    os.makedirs(report_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(report_dir, f"reset-migration-{stamp}.json")
    payload = {
        "dry_run": dry_run,
        "generated_at": lncatalog.utc_now(),
        "counts": {k: len(v) for k, v in rows.items()},
        "id_map": id_map(rows),
        "auto": rows["auto"],
        "manual": rows["manual"],
        "ignored": rows["ignored"],
        "conforming": rows["conforming"],
        "merged": rows.get("merged") or [],
        "suspected_duplicates": suspected_duplicates(rows),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return path


def default_report_dir(novels_dir: str) -> str:
    return os.path.join(os.path.dirname(novels_dir) or ".", "reports", "reset")


def _read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: str, obj) -> None:
    lndata.atomic_write_json(path, obj)


def _item_from_meta(meta: dict, new_id: str, state: dict) -> dict:
    tracking = str(state.get("tracking") or "")
    shelf = tracking if tracking in ("want", "reading", "finished", "dropped") else None
    return {
        "id": new_id,
        "slug": new_id,
        "source": meta.get("source") or "local",
        "source_id": meta.get("source_id") or "",
        "title": meta.get("title") or "",
        "author": meta.get("author") or "",
        "tags": list(meta.get("tags") or []),
        "genre": meta.get("genre") or "",
        "episodes": len(meta.get("episodes") or []),
        "characters": meta.get("characters") or 0,
        "points": meta.get("points") or 0,
        "updated": meta.get("last_episode_at") or "",
        "sources": ([meta.get("source") or "local"]
                    if (meta.get("source") or "local") != "local"
                    else ["本地导入"]),
        "origins": ([meta.get("source") or "local"]
                    if (meta.get("source") or "local") != "local"
                    else ["本地导入"]),
        "source_first_seen": meta.get("source_first_seen")
                              or meta.get("created_at") or lncatalog.utc_now(),
        "added_at": meta.get("added_at") or meta.get("created_at")
                    or lncatalog.utc_now(),
        "shelf": shelf,
        "favorite": bool(state.get("favorites")),
        "hidden": bool(state.get("hidden")),
        "content_hash": meta.get("content_hash") or meta.get("sha256") or "",
        "hash_scheme": meta.get("hash_scheme") or "",
    }


def _merge_exact_duplicates(rows: list[dict], novels_dir: str,
                            data_dir: str, cat: dict) -> tuple[list[dict], list[dict], int]:
    """Merge only exact local/source duplicates; never fuzzy title matches."""
    by_key: dict[str, list[dict]] = {}
    for row in rows:
        key = str(row.get("dedupe_key") or "")
        if key:
            by_key.setdefault(key, []).append(row)
    keep: list[dict] = []
    merged: list[dict] = []
    removed = 0
    merged_root = os.path.join(data_dir, "merged")
    for key, group in by_key.items():
        if len(group) < 2:
            keep.extend(group)
            continue
        locals_ = [r for r in group
                   if str((_read_json(os.path.join(novels_dir, r["dir"],
                                                  "meta.json"), {}) or {}).get("source") or "") == "local"]
        remote = [r for r in group if r not in locals_]
        if not locals_ or not remote:
            keep.extend(group)
            continue
        winner = locals_[0]
        win_new = winner.get("new_id") or winner.get("id")
        keep.append(winner)
        for loser in remote:
            old = loser["dir"]
            new = loser.get("new_id") or loser.get("id")
            src = os.path.join(novels_dir, old)
            if not os.path.isdir(src):
                continue
            os.makedirs(merged_root, exist_ok=True)
            dst = os.path.join(merged_root, new)
            n = 2
            while os.path.exists(dst):
                dst = os.path.join(merged_root, f"{new}-{n}")
                n += 1
            os.rename(src, dst)
            old_state = os.path.join(data_dir, "books", f"{old}.json")
            loser_state = _read_json(old_state, {}) or {}
            if os.path.exists(old_state):
                os.replace(old_state, os.path.join(merged_root, f"{new}.json"))
            win_state = os.path.join(data_dir, "books", f"{winner['dir']}.json")
            try:
                if (str((loser_state.get("progress") or {}).get("at") or "")
                        > str((_read_json(win_state, {}) or {}).get("progress", {}).get("at") or "")):
                    shutil.copy2(os.path.join(merged_root, f"{new}.json"), win_state)
            except OSError:
                pass
            _write_json(os.path.join(dst, "MERGE.json"), {
                "schema_version": 1, "merged_into": win_new,
                "source_dir": old, "source_id": new,
                "reason": "exact dedupe_key: local wins, source archived",
                "at": lncatalog.utc_now()})
            for k in (old, new):
                if k in cat["candidates"]:
                    cat["candidates"].pop(k, None)
                    removed += 1
                if k in cat["items"]:
                    cat["items"].pop(k, None)
                    removed += 1
            for k in (old, new):
                cat["aliases"][str(k)] = win_new
            merged.append({"from": old, "to": win_new, "archived": dst,
                           "dedupe_key": key})
    return keep, merged, removed


def write_migration(rows: dict, novels_dir: str, *,
                    backup: bool = True) -> dict:
    """Apply the safe rename/catalog step. Caller must stop lnserve first."""
    if rows.get("manual"):
        raise RuntimeError(f"还有需人工项：{rows['manual']}")
    root = os.path.dirname(os.path.abspath(novels_dir))
    data_dir = os.path.join(root, "data")
    lib_path = os.path.join(data_dir, "library.json")
    id_path = os.path.join(data_dir, "reset-id-map.json")
    existing = _read_json(id_path, {})
    mapping = existing if isinstance(existing, dict) and existing else id_map(rows)
    _write_json(id_path, mapping)

    backup_dir = ""
    if backup:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup_dir = os.path.join(data_dir, f"reset-backup-{stamp}")
        os.makedirs(backup_dir, exist_ok=True)
        for name in ("library.json", "user.json"):
            src = os.path.join(data_dir, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(backup_dir, name))
        books_src = os.path.join(data_dir, "books")
        if os.path.isdir(books_src):
            shutil.copytree(books_src, os.path.join(backup_dir, "books"),
                            dirs_exist_ok=True)

    cat = lncatalog.load(lib_path)
    for old, final in lncatalog.load_aliases(lib_path).items():
        cat["aliases"].setdefault(old, final)
    old_count = len(cat["items"]) + len(cat["candidates"])

    renamed = []
    removed_candidates = 0
    added_items = 0
    rows_to_write = (list(rows.get("auto") or [])
                     + list(rows.get("conforming") or []))
    rows_to_write, merged, removed_merged = _merge_exact_duplicates(
        rows_to_write, novels_dir, data_dir, cat)
    rows["merged"] = merged
    for row in rows_to_write:
        old = row["dir"]
        new = row.get("new_id") or row.get("id")
        if not new:
            raise RuntimeError(f"迁移行缺少 new_id/id：{old}")
        src_dir = os.path.join(novels_dir, old)
        dst_dir = os.path.join(novels_dir, new)
        if old != new and os.path.isdir(src_dir):
            if os.path.isdir(dst_dir):
                raise RuntimeError(f"目标目录已存在：{dst_dir}")
            os.rename(src_dir, dst_dir)
            renamed.append((old, new))
        if not os.path.isdir(dst_dir):
            raise RuntimeError(f"迁移后目录不存在：{dst_dir}")

        meta_path = os.path.join(dst_dir, "meta.json")
        meta = _read_json(meta_path, None)
        if not isinstance(meta, dict):
            raise RuntimeError(f"迁移后 meta 不可读：{meta_path}")
        meta["id"] = new
        meta["slug"] = new
        meta["source"] = meta.get("source") or "local"
        meta["source_first_seen"] = (meta.get("source_first_seen")
                                     or meta.get("created_at")
                                     or lncatalog.utc_now())
        meta["added_at"] = meta.get("added_at") or lncatalog.utc_now()
        _write_json(meta_path, meta)

        old_state = os.path.join(data_dir, "books", f"{old}.json")
        new_state = os.path.join(data_dir, "books", f"{new}.json")
        if old != new and os.path.exists(old_state) and not os.path.exists(new_state):
            os.replace(old_state, new_state)
        state = _read_json(new_state, {}) or {}
        if new not in cat["items"]:
            added_items += 1
        if old in cat["candidates"]:
            removed_candidates += 1
            cat["candidates"].pop(old, None)
        cat["items"][new] = _item_from_meta(meta, new, state)
        for old_url in row.get("old_urls") or [old]:
            if str(old_url) != new:
                cat["aliases"][str(old_url)] = new

    new_count = len(cat["items"]) + len(cat["candidates"])
    expected = old_count - removed_merged - removed_candidates + added_items
    if new_count != expected:
        raise RuntimeError(
            f"catalog 条目守恒失败：{old_count} - {removed_candidates} + "
            f"{added_items} != {new_count}")
    lncatalog.save(lib_path, cat)
    sidecar = lncatalog.aliases_path(lib_path)
    if os.path.exists(sidecar):
        os.remove(sidecar)
    return {"id_map": mapping, "backup": backup_dir,
            "renamed": renamed, "merged": merged, "catalog": lib_path}


def main() -> None:
    ap = argparse.ArgumentParser(description="Catalog reset dry-run scanner")
    ap.add_argument("--novels", default="")
    ap.add_argument("--report-dir", default="")
    ap.add_argument("--write", action="store_true",
                    help="not implemented here; use the later migration step")
    args = ap.parse_args()
    novels = args.novels or os.path.join(os.path.dirname(HERE), "novels")
    if not os.path.isdir(novels):
        print(f"找不到作品目录：{novels}", file=sys.stderr)
        sys.exit(2)
    rows = scan(novels)
    report_dir = args.report_dir or default_report_dir(novels)
    if args.write:
        if rows.get("manual"):
            print(f"仍有需人工项，拒绝写入：{rows['manual']}", file=sys.stderr)
            sys.exit(2)
        result = write_migration(rows, novels)
        path = write_report(rows, report_dir, dry_run=False)
        print(f"写入完成：重命名 {len(result['renamed'])} 本")
        print(f"备份：{result['backup']}")
        print(f"id-map：{os.path.join(os.path.dirname(novels), 'data', 'reset-id-map.json')}")
        print(f"报告：{path}")
        return
    path = write_report(rows, report_dir, dry_run=True)
    print(f"扫描完成：自动 {len(rows['auto'])} / 需人工 {len(rows['manual'])} / "
          f"已规范 {len(rows['conforming'])} / 忽略 {len(rows['ignored'])}")
    print(f"dry-run 报告：{path}")
    _dups = suspected_duplicates(rows)
    if _dups:
        print(f"疑似重复组：{len(_dups)}（只报告，不自动合并）")
        for group in _dups:
            print("  DUP " + " | ".join(
                f"{x.get('dir')} · {x.get('volume') or '-'} · "
                f"{(x.get('title') or '')[:38]}" for x in group))
    if not rows["auto"] and not rows["manual"]:
        print("没有需要迁移的作品：零迁移。")


if __name__ == "__main__":
    main()
