#!/usr/bin/env python3
"""回归：分享包必须由白名单构建，且不含个人数据/字节码。

以前包是手工 zip，排除清单只活在 README 里：真实口味画像和 11 个 `.pyc`
就这么进了评审包。这里直接构建一次包，按条目审计；`make_share.py` 里
任何“新加个目录忘了排除”的错误都会在这里变红。
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


_s = importlib.util.spec_from_file_location(
    "make_share", os.path.join(ROOT, "make_share.py"))
ms = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ms)

tmp = tempfile.mkdtemp(prefix="ln-share-")
try:
    dest, files = ms.build(os.path.join(tmp, "share.zip"))
    with zipfile.ZipFile(dest) as z:
        names = set(z.namelist())
        blobs = {n: z.read(n) for n in names}

    prefix = ms.PREFIX + "/"
    check("所有条目都在同一顶层目录下",
          bool(names) and all(n.startswith(prefix) for n in names))
    check("路径不含绝对路径/盘符/..",
          all(not n.startswith(("/", "\\")) and ".." not in n.split("/")
              and not (len(n) > 1 and n[1] == ":") for n in names))

    forbidden = [n for n in names
                 if any(part in ms.FORBIDDEN_NAMES
                        for part in n.split("/"))
                 or n.lower().endswith(ms.FORBIDDEN_SUFFIX)
                 or "lightnovel/lntrans/novels/" in n
                 or "lightnovel/lntrans/data/" in n
                 or "lightnovel/lnfinder/reports/" in n
                 or n.endswith("-中文.md")]
    check("不含画像/候选池/历史/报告/novels/data/pyc",
          not forbidden, str(forbidden[:5]))

    required = {prefix + rel for rel in (
        "VERSION", "SECURITY.md", "make_share.py",
        "lntrans/lnserve.py", "lntrans/lncatalog.py",
        "lntrans/migrate_reset.py", "lntrans/run_selftests.py",
        "lntrans/lnui/__init__.py", "lntrans/lnui/components.py",
        "lntrans/lnui/icons.py", "lntrans/lnui/layout.py",
        "lntrans/lnui/preview.py", "lntrans/lnui/settings.py",
        "lntrans/lnui/styles.py",
        "lntrans/static/app.css", "lntrans/static/lnui.css",
        "lntrans/static/lnui-preview.js", "lntrans/static/lnui-settings.js",
        "lntrans/static/reader.js",
        "lntrans/static/icon-192.png", "lntrans/static/icon-512.png",
        "lntrans/contracts/chapter-meta-v1.schema.json",
        "skills/lightnovel/SKILL.md",
        "skills/lightnovel/references/finder.md",
    )}
    check("必备文件齐全（少 app.css 服务直接起不来）",
          required <= names, str(sorted(required - names)[:5]))

    css_rel = "lntrans/static/app.css"
    src_css = open(os.path.join(ROOT, css_rel), "rb").read()
    check("包内 app.css 与源码逐字节一致",
          blobs.get(prefix + css_rel) == src_css)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
_all = not fails
print("回归结果：", "全部通过 ✅" if _all else f"仍有失败 ❌ {fails}")
if not _all:
    sys.exit(1)
