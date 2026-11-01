#!/usr/bin/env python3
"""Build a clean share package from an allowlist.

Why an allowlist: the previous package was assembled by hand with a list of
"things to exclude" that lived only in documentation.  Personal data and
`__pycache__` silently slipped in.  Anything not named here is simply not
packed, so a new runtime file can never leak by accident.

Usage:
    python make_share.py [--out PATH]
"""

from __future__ import annotations

import argparse
import fnmatch
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREFIX = ROOT.name

ROOT_FILES = {
    "AGENTS.md",
    "CONTRIBUTING.md",
    "Dockerfile.ci",
    "LICENSE",
    "NOTICE",
    "README.md",
    "README-FOR-REVIEW.md",
    "REVIEW-ROUND2-FOLLOWUP.md",
    "SECURITY.md",
    "SHARE-README.md",
    "VERSION",
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "make_share.py",
    "pyproject.toml",
}

# (directory, patterns).  Directories are recursive unless a pattern is a
# literal relative path.
INCLUDE = (
    ("lnfinder", ("*.py", "README.md")),
    ("lntrans", ("*.py", "*.md", "test_click_dom.js")),
    ("lntrans/static", ("*.js", "*.css", "*.png")),
    ("lntrans/contracts", ("*.json", "*.md")),
    ("skills", ("*.md",)),
    ("docs", ("*.md",)),
    (".github/workflows", ("*.yml", "*.yaml")),
)

FORBIDDEN_NAMES = {
    "taste_profile.json",
    "candidates.json",
    "history.jsonl",
    "recommend-latest.md",
    "recommend-latest.json",
    "__pycache__",
    ".env",
    ".credentials.yaml",
}
FORBIDDEN_SUFFIX = (".pyc", ".pyo", ".pyd", ".log", ".tmp", ".part", ".zip")

# 个人/运行时数据目录：前缀匹配。`lntrans` 的白名单是递归 `*.md`，而
# `lntrans/novels/<slug>/novel.md` 正是**整本译文的汇总** —— 只按文件名/
# 后缀排除会把它打进分享包（真实发生过）。数据目录一律按前缀排除。
EXCLUDE_PREFIXES = (
    "lntrans/novels/",
    "lntrans/data/",
    "lnfinder/reports/",
)


def _forbidden(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if any(rel.startswith(p) for p in EXCLUDE_PREFIXES):
        return True
    parts = rel.split("/")
    if any(p in FORBIDDEN_NAMES for p in parts):
        return True
    if any(p.startswith(".bak-") for p in parts):
        return True
    if rel.lower().endswith(FORBIDDEN_SUFFIX):
        return True
    # 工作区导出的译文摘要（`<书名>-中文.md`）也是个人数据。
    if parts[-1].endswith("-中文.md"):
        return True
    return False


def _iter_files():
    seen: set[str] = set()
    for name in sorted(ROOT_FILES):
        p = ROOT / name
        if p.is_file():
            rel = name
            if not _forbidden(rel):
                seen.add(rel)
                yield p, rel
    for directory, patterns in INCLUDE:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT).as_posix()
            if _forbidden(rel):
                continue
            if not any(fnmatch.fnmatch(p.name, pat) for pat in patterns):
                continue
            if rel not in seen:
                seen.add(rel)
                yield p, rel


def build(out: str | Path | None = None,
          prefix: str | None = None) -> tuple[Path, list[str]]:
    """打包。`prefix` 是包内顶层目录名（默认取 checkout 目录名）。

    为什么要能改：顶层目录名不该取决于"你把仓库克隆到哪个文件夹"——
    在 `Andoroid/` 下打包会得到 `Andoroid/...`，而发布物一直是 `lightnovel/...`。
    """
    name = prefix or PREFIX
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if out is None:
        out = ROOT.parent / (
            f"{name}-share-{time.strftime('%Y-%m-%d')}-v{version}.zip")
    dest = Path(out).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    files = list(_iter_files())
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p, rel in files:
            z.write(p, arcname=f"{name}/{rel}")
    return dest, [rel for _, rel in files]


def main() -> int:
    ap = argparse.ArgumentParser(description="打包干净的分享 zip（白名单）")
    ap.add_argument("--out", default="")
    ap.add_argument("--prefix", default="", help="包内顶层目录名（默认当前目录名）")
    a = ap.parse_args()
    dest, files = build(a.out or None, a.prefix or None)
    print(f"已生成 {dest}")
    print(f"条目 {len(files)} 个（个人数据/字节码/备份目录一律未入包）")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
