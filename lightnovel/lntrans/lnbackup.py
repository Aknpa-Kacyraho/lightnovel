#!/usr/bin/env python3
"""lnbackup —— 备份 / 校验 / 恢复：把「钱买不到的东西」搬出这台手机。

为什么需要它：译文、术语表 / 人物卡 / 梗概、书架状态、口味画像，**只有容器里一份**。
容器被重置，十几万 token 的翻译和几个月的口味记录会一起消失；而译文能重译，
花的是钱和时间，画像能重建，但「什么时候喜欢过什么」找不回来。

三条铁律（想清楚才写的，不是照抄 checklist）：

1. **同盘 zip 不算备份**。容器文件系统会被重置，写在同一棵树里的 zip 跟着一起没。
   真正的第二份必须离开容器：浏览器下载（落到 /sdcard/Download）或导出到别的设备。
   所以服务端提供 `/api/backup` 下载接口，`export` 命令行只是补充手段。
2. **没验过的备份等于没有备份**。每个文件带 sha256，`restore` **先校验再动盘**，
   坏一个字节就整包拒绝 —— 宁可恢复不了，也不能把好数据覆盖成坏的。
3. **恢复只增不删**。本地多出来的文件不动；同名但内容不同的，先把本地那份挪成
   `.bak-<时间戳>` 再写。误操作最多多几个 .bak，不会丢东西。默认干跑，`--write` 才写。

装什么：`novels/`（译文 + meta + raw + cache）、`data/`（书架 / 书库 / 阅读历史）、
`lnfinder/`（口味画像）。不含 `*.log`、`*.tmp`、`__pycache__` —— 都是噪音，
而且日志里带路径。`--no-raw` / `--no-cache` 可以瘦身（raw 能重抓，cache 重译要花钱，
所以默认都装）。

manifest 里**只写相对路径**：备份包换一台机器、换一个数据根都能直接恢复。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lndata  # noqa: E402

KIND = "lntrans-backup"
# 格式版本：改了目录结构 / manifest 字段就 +1，并让 restore 拒绝未来版本。
FORMAT = 1
MANIFEST = "manifest.json"
ROOT_NAMES = ("novels", "data", "lnfinder")

_SKIP_DIRS = {
    "__pycache__", ".git", ".idea", ".vscode",
    lndata.STAGING_DIR, lndata.BACKUPS_DIR, lndata.GENERATIONS_DIR,
}
_SKIP_SUFFIX = (".log", ".tmp", ".part", ".zip", ".pyc")
_SKIP_INFIX = (".bak-", ".restore-tmp")
_SKIP_NAMES = {
    ".DS_Store", "Thumbs.db", lndata.LOCK_FILE, lndata.STATE_FILE,
}
# lnfinder/ 是代码与数据混居目录：只有这些才是“钱买不到的用户数据”。
# 源码/自检/README 永远不进备份，恢复也就永远不可能把 lnfind.py 回退。
_FINDER_DATA_FILES = {
    "taste_profile.json", "candidates.json", "history.jsonl",
}
_FINDER_DATA_DIRS = ("reports",)
_CODE_SUFFIX = (".py", ".pyc", ".pyo", ".pyd")
# 恢复时允许出现的根名前缀（同时也是路径穿越的防线：未知根一律拒绝）
_SAFE_PART = re.compile(r"^[^/\\\0]+$")
_CONTROL_NAMES = {
    lndata.LOCK_FILE,
    lndata.STATE_FILE,
}
_CONTROL_DIRS = {
    lndata.STAGING_DIR,
    lndata.BACKUPS_DIR,
    lndata.GENERATIONS_DIR,
}


class BackupError(RuntimeError):
    """备份包不可用（损坏 / 版本不对 / 路径可疑）。"""


# ---------------------------------------------------------------- 路径解析

def roots(data_root: str | None = None, finder_root: str | None = None) -> dict[str, str]:
    """三个根目录。**一律读环境变量**，不写死路径（AGENTS.md 的硬规则）。"""
    if not data_root and not finder_root and os.environ.get("LNTRANS_HOME"):
        layout = lndata.resolve_layout()
        dr, fr = layout.data_root, layout.finder_root
    else:
        dr = os.path.abspath(
            data_root or os.environ.get("LNTRANS_DATA_ROOT") or HERE)
        fr = os.path.abspath(
            finder_root or os.environ.get("LNTRANS_LNFINDER")
            or os.path.join(os.path.dirname(HERE), "lnfinder"))
    return {"novels": os.path.join(dr, "novels"),
            "data": os.path.join(dr, "data"),
            "lnfinder": fr}


def _data_entry_allowed(root_name: str, rel: str) -> bool:
    """按根白名单判断一个相对路径能不能进备份。

    * 任何 ``*.py`` / 字节码永久排除（代码不是用户数据）；
    * ``lnfinder/`` 只收画像/候选池/历史/报告，其余一律当代码；
    * ``novels/`` 与 ``data/`` 是纯数据目录，保持递归收集。
    """
    rel = (rel or "").replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return False
    if rel.endswith(_CODE_SUFFIX) or any(x in rel for x in _SKIP_INFIX):
        return False
    if root_name == "lnfinder":
        first, _, rest = rel.partition("/")
        if rest:
            return first in _FINDER_DATA_DIRS
        return first in _FINDER_DATA_FILES
    return True


def _forbidden_entry(arc: str) -> bool:
    """备份条目是否越界（路径穿越 / 未知根 / 代码或运行控制文件）。"""
    if not _safe_rel(arc) or _runtime_control(arc) or "/" not in arc:
        return True
    root, rel = arc.split("/", 1)
    if root not in ROOT_NAMES:
        return True
    return not _data_entry_allowed(root, rel)


def _iter_files(base: str, root_name: str, skip_raw: bool = False,
                skip_cache: bool = False):
    """按稳定顺序产出 (绝对路径, 相对路径)。稳定顺序 = 同样输入产出同样字节。"""
    for dirpath, dirnames, filenames in os.walk(base):
        keep = [d for d in dirnames if d not in _SKIP_DIRS]
        if skip_raw:
            keep = [d for d in keep if d not in ("raw",)]
        if skip_cache:
            keep = [d for d in keep if d not in ("cache",)]
        dirnames[:] = sorted(keep)
        for fn in sorted(filenames):
            if fn in _SKIP_NAMES or fn.endswith(_SKIP_SUFFIX):
                continue
            if any(x in fn for x in _SKIP_INFIX):
                continue
            p = os.path.join(dirpath, fn)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            rel = os.path.relpath(p, base).replace(os.sep, "/")
            if not _data_entry_allowed(root_name, rel):
                continue
            yield p, rel


def _iter_dirs(base: str, root_name: str, skip_raw: bool = False,
               skip_cache: bool = False):
    """空目录也要记下来。zip 只存文件，`chapters/` 一个空目录在恢复后会消失 ——
    恢复出来的树和原来不完全一样，那就不叫"恢复"了。（实际踩到：演练时 diff 报
    `Only in novels/xxx: chapters`，文件一个不差，但目录少了。）"""
    for dirpath, dirnames, _ in os.walk(base):
        keep = [d for d in dirnames if d not in _SKIP_DIRS]
        if skip_raw:
            keep = [d for d in keep if d not in ("raw",)]
        if skip_cache:
            keep = [d for d in keep if d not in ("cache",)]
        dirnames[:] = sorted(keep)
        if dirpath != base:
            rel = os.path.relpath(dirpath, base).replace(os.sep, "/")
            if _data_entry_allowed(root_name, rel):
                yield rel


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_rel(rel: str) -> bool:
    """备份包里的相对路径必须是「干净的相对路径」：不许绝对、不许 ..、不许盘符。"""
    if not rel or rel.startswith(("/", "\\")) or "\\" in rel:
        return False
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    if re.match(r"^[A-Za-z]:", parts[0]):
        return False
    return True


def _runtime_control(rel: str) -> bool:
    parts = str(rel).replace("\\", "/").split("/")
    return any(p in _CONTROL_NAMES for p in parts) or any(
        p in _CONTROL_DIRS for p in parts)


# ---------------------------------------------------------------- 导出

def default_name(now: float | None = None) -> str:
    return "lntrans-backup-" + time.strftime("%Y%m%d-%H%M%S",
                                             time.localtime(now or time.time())) + ".zip"


def build(dest: str, data_root: str | None = None, finder_root: str | None = None,
          include_raw: bool = True, include_cache: bool = True) -> dict:
    """把三棵树打进 `dest`（原子写：先 .part 再 replace）。返回 manifest。"""
    rs = roots(data_root, finder_root)
    dest = os.path.abspath(dest)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    files: list[dict] = []
    dirs: list[str] = []
    counts: dict[str, int] = {}
    total = 0
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name in ROOT_NAMES:
                base = rs[name]
                if not os.path.isdir(base):
                    counts[name] = 0
                    continue
                n = 0
                for rel in _iter_dirs(base, name, skip_raw=not include_raw,
                                      skip_cache=not include_cache):
                    dirs.append(f"{name}/{rel}")
                for p, rel in _iter_files(base, name, skip_raw=not include_raw,
                                          skip_cache=not include_cache):
                    with open(p, "rb") as f:
                        blob = f.read()
                    arc = f"{name}/{rel}"
                    # 固定时间戳：同样输入 → 同样条目字节，便于比对与复现。
                    zi = zipfile.ZipInfo(arc, date_time=(1980, 1, 1, 0, 0, 0))
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    zi.external_attr = 0o644 << 16
                    z.writestr(zi, blob)
                    files.append({"path": arc, "size": len(blob),
                                  "sha256": hashlib.sha256(blob).hexdigest()})
                    total += len(blob)
                    n += 1
                counts[name] = n
            manifest = {
                "kind": KIND,
                "format": FORMAT,
                "backup_id": (
                    "backup-" + time.strftime("%Y%m%d-%H%M%S")
                    + "-" + secrets.token_hex(4)),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "counts": counts,
                "files": len(files),
                "bytes": total,
                "include_raw": bool(include_raw),
                "include_cache": bool(include_cache),
                "dirs": dirs,
                "entries": files,
            }
            z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
        os.replace(tmp, dest)
        try:
            lndata.record_backup(
                os.environ.get("LNTRANS_HOME"),
                backup_sha256=_sha256(dest),
                backup_id=manifest["backup_id"],
                created_at=manifest["created_at"],
                relative_hint=dest,
            )
        except (OSError, lndata.DataRootError):
            # A backup is still valid if its convenience metadata cannot be
            # written; never discard or mutate the completed archive for this.
            pass
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return manifest


def export(out_dir: str | None = None, name: str | None = None,
           data_root: str | None = None, finder_root: str | None = None,
           include_raw: bool = True, include_cache: bool = True) -> tuple[str, dict]:
    out_dir = os.path.abspath(out_dir or os.getcwd())
    path = os.path.join(out_dir, name or default_name())
    if os.path.exists(path):  # 同一秒内点两次也不覆盖
        stem, ext = os.path.splitext(path)
        i = 2
        while os.path.exists(f"{stem}-{i}{ext}"):
            i += 1
        path = f"{stem}-{i}{ext}"
    layout = lndata.resolve_layout(
        data_root=data_root, finder_root=finder_root)
    lock = lndata.acquire_lock(layout)
    try:
        return path, build(path, data_root=data_root, finder_root=finder_root,
                           include_raw=include_raw, include_cache=include_cache)
    finally:
        lock.__exit__(None, None, None)


# ---------------------------------------------------------------- 校验

def verify(path: str) -> dict:
    """逐文件核 sha256。返回报告，不抛异常（调用方自己看 ok）。"""
    path = os.path.abspath(path)
    rep: dict = {"ok": False, "path": path, "files": 0, "bytes": 0,
                 "missing": [], "bad": [], "unsafe": [], "counts": {},
                 "created_at": "", "error": ""}
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if MANIFEST not in names:
                rep["error"] = "缺少 manifest.json（不是本工具产的备份？）"
                return rep
            man = json.loads(z.read(MANIFEST))
            if man.get("kind") != KIND:
                rep["error"] = f"kind 不是 {KIND}：{man.get('kind')!r}"
                return rep
            if int(man.get("format") or 0) > FORMAT:
                rep["error"] = (f"备份格式 v{man.get('format')} 比本工具支持的新 "
                                f"(v{FORMAT})，请用更新的代码恢复")
                return rep
            if int(man.get("format") or 0) <= 0:
                rep["error"] = "manifest.format 非法"
                return rep
            rep["created_at"] = man.get("created_at") or ""
            rep["counts"] = man.get("counts") or {}
            for ent in man.get("entries") or []:
                arc = ent.get("path") or ""
                if _forbidden_entry(arc):
                    rep["unsafe"].append(arc)
                    continue
                if arc not in names:
                    rep["missing"].append(arc)
                    continue
                blob = z.read(arc)
                if len(blob) != int(ent.get("size") or 0) or \
                        hashlib.sha256(blob).hexdigest() != (ent.get("sha256") or ""):
                    rep["bad"].append(arc)
                    continue
                rep["files"] += 1
                rep["bytes"] += len(blob)
            # 目录条目也要过路径检查（否则 `novels/../../x` 能借 makedirs 造目录）
            for d in man.get("dirs") or []:
                if _forbidden_entry(d):
                    rep["unsafe"].append(d)
            rep["ok"] = not (rep["missing"] or rep["bad"] or rep["unsafe"])
    except (zipfile.BadZipFile, json.JSONDecodeError, OSError, ValueError) as e:
        rep["error"] = f"{type(e).__name__}: {e}"
    return rep


def info(path: str) -> dict:
    """只读 manifest（不核校验和，用来"先看看包里有什么"）。"""
    with zipfile.ZipFile(os.path.abspath(path)) as z:
        man = json.loads(z.read(MANIFEST))
    if man.get("kind") != KIND:
        raise BackupError(f"不是本工具的备份包（kind={man.get('kind')!r}）")
    return man


# ---------------------------------------------------------------- 恢复

def restore(path: str, data_root: str | None = None,
            finder_root: str | None = None, write: bool = False) -> dict:
    """Restore with the data-root lock held for real writes.

    Dry-run is read-only and intentionally works without the lock.  The actual
    merge takes the same lock as ``lnserve`` and mutating translation CLI
    commands.
    """
    if not write:
        return _restore_unlocked(
            path, data_root=data_root, finder_root=finder_root, write=False)
    layout = lndata.resolve_layout(
        data_root=data_root, finder_root=finder_root)
    lock = lndata.acquire_lock(layout)
    try:
        return _restore_unlocked(
            path, data_root=data_root, finder_root=finder_root, write=True)
    finally:
        lock.__exit__(None, None, None)


def _restore_unlocked(path: str, data_root: str | None = None,
                      finder_root: str | None = None,
                      write: bool = False) -> dict:
    """把备份合并回数据根。默认干跑。

    * 只增不删：本地有、包里没有的文件原样保留。
    * 同名且内容相同 → 跳过（重复恢复是幂等的）。
    * 同名但内容不同 → 本地那份改名为 `X.bak-<时间戳>`，再写入包里的版本。
    * 整包校验不过 → 一个文件都不动。
    """
    rep = verify(path)
    if not rep["ok"]:
        detail = []
        if rep["error"]:
            detail.append(rep["error"])
        if rep["missing"]:
            detail.append(f"缺 {len(rep['missing'])} 个文件")
        if rep["bad"]:
            detail.append(f"{len(rep['bad'])} 个文件 hash 不符（包已损坏）")
        if rep["unsafe"]:
            detail.append(f"{len(rep['unsafe'])} 个路径可疑")
        raise BackupError("备份校验失败，拒绝恢复：" + "；".join(detail or ["未知原因"]))

    rs = roots(data_root, finder_root)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out: dict = {"path": os.path.abspath(path), "created_at": rep["created_at"],
                 "created": 0, "updated": 0, "unchanged": 0, "dirs": 0,
                 "bak": [], "plan": [], "written": bool(write)}
    with zipfile.ZipFile(os.path.abspath(path)) as z:
        man = json.loads(z.read(MANIFEST))
        # 先把目录补回来（空目录 zip 存不下，manifest 单独记了一份）。
        # 干跑只数不做：用户要先看到"会建几个目录"。
        for d in man.get("dirs") or []:
            root, _, sub = d.partition("/")
            dp = os.path.join(rs[root], *sub.split("/"))
            if os.path.isdir(dp):
                continue
            out["dirs"] += 1
            if write:
                os.makedirs(dp, exist_ok=True)
        for ent in man.get("entries") or []:
            arc = ent["path"]
            if _forbidden_entry(arc):
                raise BackupError(
                    f"备份包含不该恢复的路径（代码/控制文件/越界）：{arc}")
            root, _, sub = arc.partition("/")
            dest = os.path.join(rs[root], *sub.split("/"))
            if os.path.isfile(dest) and _sha256(dest) == ent["sha256"]:
                out["unchanged"] += 1
                continue
            action = "overwrite" if os.path.isfile(dest) else "create"
            out["plan"].append((action, arc))
            if not write:
                out["created" if action == "create" else "updated"] += 1
                continue
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            if action == "overwrite":
                bak = f"{dest}.bak-{stamp}"
                i = 2
                while os.path.exists(bak):
                    bak = f"{dest}.bak-{stamp}-{i}"
                    i += 1
                os.replace(dest, bak)
                # Manifest/API paths are always POSIX-style.  Windows otherwise
                # leaks backslashes into the restore report and downstream tools
                # can no longer match the backup entry they refer to.
                out["bak"].append(
                    os.path.relpath(bak, rs[root]).replace(os.sep, "/"))
            tmp = dest + ".restore-tmp"
            with z.open(arc) as src, open(tmp, "wb") as f:
                shutil.copyfileobj(src, f)
            if _sha256(tmp) != ent["sha256"]:
                os.remove(tmp)
                raise BackupError(f"恢复过程中校验失败：{arc}（已中止，后续文件未动）")
            os.replace(tmp, dest)
            out["created" if action == "create" else "updated"] += 1

    if write:
        # 留一张审计单：什么时候、从哪个包、恢复了多少、覆盖了谁。
        logdir = os.path.join(rs["data"])
        try:
            os.makedirs(logdir, exist_ok=True)
            with open(os.path.join(logdir, f"restore-{stamp}.json"), "w",
                      encoding="utf-8") as f:
                json.dump({k: out[k] for k in
                           ("path", "created_at", "created", "updated",
                            "unchanged", "bak")} | {"at": stamp},
                          f, ensure_ascii=False, indent=1)
        except OSError:
            pass
    return out


# ---------------------------------------------------------------- CLI

def _fmt(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="lnbackup", description="备份 / 校验 / 恢复轻小说数据（译文、书架、画像）")
    sub = ap.add_subparsers(dest="cmd")

    e = sub.add_parser("export", help="导出备份 zip")
    e.add_argument("--out", default="", help="输出目录（默认当前目录）")
    e.add_argument("--name", default="", help="文件名（默认 lntrans-backup-<时间>.zip）")
    e.add_argument("--no-raw", action="store_true", help="不装原文（能重抓，省体积）")
    e.add_argument("--no-cache", action="store_true", help="不装翻译缓存（重译会花钱，慎用）")

    v = sub.add_parser("verify", help="校验备份包（逐文件 sha256）")
    v.add_argument("file")

    i = sub.add_parser("info", help="看备份里有什么（不核校验和）")
    i.add_argument("file")

    r = sub.add_parser("restore", help="恢复（默认干跑，--write 才真写）")
    r.add_argument("file")
    r.add_argument("--write", action="store_true", help="真的写盘")

    a = ap.parse_args(argv)
    if a.cmd == "export":
        try:
            path, man = export(
                out_dir=a.out or None, name=a.name or None,
                include_raw=not a.no_raw, include_cache=not a.no_cache)
        except lndata.DataRootError as ex:
            print(f"❌ {ex}；请先停止正在运行的书架服务")
            return 1
        print(f"✅ 已导出 {path}")
        print(f"   {man['files']} 个文件 / {_fmt(man['bytes'])}"
              f"（" + " · ".join(f"{k} {n}" for k, n in man["counts"].items()) + "）")
        print("   ⚠ 同一块盘上的 zip 不算备份：请把它拷到别的设备，"
              "或从网页「数据备份」下载（落到手机存储）。")
        return 0

    if a.cmd == "info":
        man = info(a.file)
        print(f"备份时间 {man['created_at']} · {man['files']} 个文件 / {_fmt(man['bytes'])}")
        print("   " + " · ".join(f"{k} {n}" for k, n in (man.get("counts") or {}).items()))
        return 0

    if a.cmd == "verify":
        rep = verify(a.file)
        if rep["ok"]:
            print(f"✅ 校验通过：{rep['files']} 个文件 / {_fmt(rep['bytes'])}"
                  f"（{rep['created_at']}）")
            return 0
        print("❌ 校验失败：" + (rep["error"] or ""))
        for key, label in (("missing", "缺失"), ("bad", "损坏"), ("unsafe", "路径可疑")):
            for x in rep[key][:10]:
                print(f"   {label}：{x}")
        return 1

    if a.cmd == "restore":
        try:
            out = restore(a.file, write=a.write)
        except (BackupError, lndata.DataRootError) as ex:
            print(f"❌ {ex}")
            if isinstance(ex, lndata.DataRootError):
                print("❌ 请先停止正在运行的书架服务")
            return 1
        verb = "已恢复" if out["written"] else "【干跑】将要恢复"
        print(f"{verb}：新建 {out['created']} · 覆盖 {out['updated']} · "
              f"未变 {out['unchanged']} · 补目录 {out['dirs']}")
        if out["bak"]:
            print(f"   原文件已备份 {len(out['bak'])} 个（.bak-*）")
        if not out["written"]:
            print("   （干跑不写盘；确认无误后加 --write 真恢复）")
        else:
            print("   ⚠ 恢复后请重启 lnserve，进程内缓存才会重新读盘。")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
