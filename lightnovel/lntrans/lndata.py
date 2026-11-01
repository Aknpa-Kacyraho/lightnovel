#!/usr/bin/env python3
"""Data-root contract, migration, and cross-process ownership for v5.

The application code is replaceable.  Everything that cannot be reconstructed
from the upstream source lives below one data home:

    /data/
      .lntrans-state.json
      .lntrans.lock
      backups/
      generations/
        gen-.../
          novels/
          data/
          profile/
      staging/

Legacy v4 layouts remain supported when ``LNTRANS_HOME`` is not set.  A
generation switch is one atomic pointer update in ``.lntrans-state.json``;
individual novels/data/profile directories are never switched independently.
"""

from __future__ import annotations

import contextlib
import ctypes
import hashlib
import json
import os
import secrets
import shutil
import sys
import time
from dataclasses import dataclass
from typing import Callable, Iterator

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
STATE_FILE = ".lntrans-state.json"
LOCK_FILE = ".lntrans.lock"
GENERATIONS_DIR = "generations"
STAGING_DIR = "staging"
BACKUPS_DIR = "backups"
SCHEMA_VERSION = 1

_PROFILE_NAMES = {
    "taste_profile.json",
    "candidates.json",
    "history.jsonl",
    "recommend-latest.md",
}
_SKIP_DIRS = {"__pycache__", ".git", ".idea", ".vscode"}
_SKIP_NAMES = {
    LOCK_FILE,
    STATE_FILE,
    ".DS_Store",
    "Thumbs.db",
}
_SKIP_SUFFIX = (".log", ".tmp", ".part", ".pyc")


class DataRootError(RuntimeError):
    """The configured data home is invalid or uses a newer schema."""


class LockBusy(DataRootError):
    """Another process owns the canonical data root."""


def app_version() -> str:
    try:
        with open(os.path.join(APP_ROOT, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "0.0.0-dev"
    except OSError:
        return "0.0.0-dev"


APP_VERSION = app_version()


@dataclass(frozen=True)
class Layout:
    mode: str
    home: str | None
    data_root: str
    finder_root: str
    lock_path: str
    state_path: str | None = None
    generations_dir: str | None = None
    staging_dir: str | None = None
    backups_dir: str | None = None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
    except (OSError, json.JSONDecodeError) as ex:
        raise DataRootError(f"无法读取数据根状态文件 {path}: {ex}") from ex
    if not isinstance(value, dict):
        raise DataRootError(f"数据根状态文件不是对象: {path}")
    return value


def _fsync_dir(path: str) -> None:
    """Persist a directory entry where the platform supports it."""
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_json(path: str, value: dict) -> None:
    """Write JSON with fsync + replace so readers never see half a document."""
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}-{secrets.token_hex(4)}"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _fsync_dir(parent)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def _validate_state(state: dict, path: str) -> dict:
    try:
        version = int(state["schema_version"])
    except (KeyError, TypeError, ValueError) as ex:
        raise DataRootError(f"状态文件缺少有效 schema_version: {path}") from ex
    if version > SCHEMA_VERSION:
        raise DataRootError(
            f"数据根 schema_version={version}，当前程序只支持 {SCHEMA_VERSION}；"
            "请升级程序，禁止用旧程序解释新数据")
    if version < 1:
        raise DataRootError(f"不支持的数据根 schema_version={version}")
    active = str(state.get("active_generation") or "")
    if not active.startswith(GENERATIONS_DIR + "/"):
        raise DataRootError(f"active_generation 必须是 {GENERATIONS_DIR}/... 相对路径")
    return state


def read_state(home: str) -> dict:
    path = os.path.join(home, STATE_FILE)
    if not os.path.isfile(path):
        raise DataRootError(
            f"数据根尚未初始化：{home}（先运行 lnmigrate.py init/migrate）")
    return _validate_state(_read_json(path), path)


def resolve_layout(
    home: str | None = None,
    data_root: str | None = None,
    finder_root: str | None = None,
) -> Layout:
    """Resolve either an initialized v5 home or a legacy v4 layout."""
    explicit_home = home
    home_env = os.environ.get("LNTRANS_HOME")
    explicit_root = data_root or os.environ.get("LNTRANS_DATA_ROOT")

    # Self-tests and explicit callers redirect the concrete data root.  That
    # must beat an inherited LNTRANS_HOME, otherwise a test launched from a v5
    # shell can unexpectedly touch the real generation.
    if explicit_home or (home_env and not explicit_root):
        resolved_home = os.path.abspath(
            os.path.expanduser(explicit_home or home_env or ""))
        home = resolved_home
        state = read_state(home)
        active = str(state["active_generation"]).replace("\\", "/")
        generation = os.path.abspath(os.path.join(home, *active.split("/")))
        generations = os.path.abspath(os.path.join(home, GENERATIONS_DIR))
        if os.path.commonpath([generation, generations]) != generations:
            raise DataRootError("active_generation 越出 generations 目录")
        if not os.path.isdir(generation):
            raise DataRootError(f"active_generation 不存在：{active}")
        return Layout(
            mode="v5",
            home=home,
            data_root=generation,
            finder_root=os.path.join(generation, "profile"),
            lock_path=os.path.join(home, LOCK_FILE),
            state_path=os.path.join(home, STATE_FILE),
            generations_dir=generations,
            staging_dir=os.path.join(home, STAGING_DIR),
            backups_dir=os.path.join(home, BACKUPS_DIR),
        )

    root = os.path.abspath(explicit_root or HERE)
    finder = os.path.abspath(
        finder_root
        or os.environ.get("LNTRANS_LNFINDER")
        or os.path.join(os.path.dirname(HERE), "lnfinder"))
    # Legacy keeps the lock beside writable data, never beside Python sources.
    return Layout(
        mode="legacy",
        home=None,
        data_root=root,
        finder_root=finder,
        lock_path=os.path.join(root, "data", LOCK_FILE),
    )


def apply_environment(layout: Layout) -> None:
    """Expose the resolved layout to modules loaded through importlib."""
    os.environ["LNTRANS_DATA_ROOT"] = layout.data_root
    os.environ["LNTRANS_LNFINDER"] = layout.finder_root
    if layout.home:
        os.environ["LNTRANS_HOME"] = layout.home


_HELD_PATHS: set[str] = set()
try:
    import fcntl  # type: ignore
except ImportError:  # Windows
    fcntl = None  # type: ignore
try:
    import msvcrt  # type: ignore
except ImportError:  # POSIX
    msvcrt = None  # type: ignore


class DataRootLock:
    """Non-blocking OS lock held for the entire process lifetime.

    The marker text is diagnostic only.  Ownership is determined solely by
    the operating system lock, never by PID/mtime/heartbeat heuristics.
    """

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self._fd = None
        self._guard_fd = None
        self._mutex = None

    def _acquire_windows_mutex(self) -> None:
        """Supplement file locks with a kernel mutex.

        Windows file-region locks are normally process-exclusive, but Store
        Python launchers can create different process isolation contexts.  A
        named kernel mutex makes the ownership rule explicit across terminals.
        """
        if os.name != "nt":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
        kernel32.ReleaseMutex.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        key = hashlib.sha256(self.path.casefold().encode("utf-8")).hexdigest()
        name = "Local\\LightnovelDataRoot-" + key
        handle = kernel32.CreateMutexW(None, 0, name)
        if not handle:
            raise OSError(
                getattr(ctypes, "get_last_error", lambda: 0)(),
                "CreateMutexW failed")
        result = kernel32.WaitForSingleObject(handle, 0)
        if result in (0x00000000, 0x00000080):  # owned / abandoned
            self._mutex = (kernel32, handle)
            return
        kernel32.CloseHandle(handle)
        if result == 0x00000102:  # WAIT_TIMEOUT
            raise OSError(13, "data-root mutex is busy")
        raise OSError(13, f"WaitForSingleObject failed: {result}")

    def _release_windows_mutex(self) -> None:
        if not self._mutex:
            return
        kernel32, handle = self._mutex
        self._mutex = None
        kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)

    def __enter__(self) -> "DataRootLock":
        if self.path in _HELD_PATHS:
            raise LockBusy(f"当前进程已持有数据根锁：{self.path}")
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if os.name == "nt":
                assert msvcrt is not None
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"\0")
                    os.fsync(fd)
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                assert fcntl is not None
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if os.name == "nt":
                self._acquire_windows_mutex()

            marker = json.dumps({
                "pid": os.getpid(),
                "app_version": APP_VERSION,
                "acquired_at": _now(),
            }, ensure_ascii=False, sort_keys=True) + "\n"
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, marker.encode("utf-8"))
            os.fsync(fd)
            # Keep a second descriptor for the lifetime of the service.  This
            # survives libraries that close/replace unrelated file objects and
            # gives the OS lock an explicit owner until release.
            guard_fd = os.dup(fd)
        except OSError as ex:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                detail = os.read(fd, 500).decode("utf-8", "replace").strip()
            except OSError:
                detail = ""
            self._release_windows_mutex()
            os.close(fd)
            if self._is_busy_error(ex):
                suffix = f"；当前持有者标记：{detail}" if detail else ""
                raise LockBusy(
                    f"数据根已有实例持有排他锁：{self.path}{suffix}") from ex
            raise

        self._fd = fd
        self._guard_fd = guard_fd
        _HELD_PATHS.add(self.path)
        return self

    @staticmethod
    def _is_busy_error(ex: OSError) -> bool:
        if os.name == "nt":
            return getattr(ex, "errno", None) in (13, 36) or getattr(ex, "winerror", None) in (
                33, 36)
        import errno
        return ex.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK)

    def __exit__(self, exc_type, exc, tb) -> None:
        if os.environ.get("LNTRANS_LOCK_DEBUG") == "1":
            import traceback
            print(f"[lock-debug] releasing {self.path}", file=sys.stderr)
            traceback.print_stack(file=sys.stderr)
        fd = self._fd
        guard_fd = self._guard_fd
        self._fd = None
        self._guard_fd = None
        if fd is None:
            return
        try:
            release_fd = guard_fd if guard_fd is not None else fd
            if os.name == "nt":
                assert msvcrt is not None
                os.lseek(release_fd, 0, os.SEEK_SET)
                msvcrt.locking(release_fd, msvcrt.LK_UNLCK, 1)
            else:
                assert fcntl is not None
                fcntl.flock(release_fd, fcntl.LOCK_UN)
        finally:
            self._release_windows_mutex()
            if guard_fd is not None:
                with contextlib.suppress(OSError):
                    os.close(guard_fd)
            with contextlib.suppress(OSError):
                os.close(fd)
            _HELD_PATHS.discard(self.path)

    def is_held(self) -> bool:
        for fd in (self._fd, self._guard_fd):
            if fd is None:
                continue
            try:
                os.fstat(fd)
                return True
            except OSError:
                continue
        return False

    def diagnostics(self) -> str:
        parts = []
        for label, fd in (("fd", self._fd), ("guard", self._guard_fd)):
            if fd is None:
                parts.append(f"{label}=None")
                continue
            try:
                os.fstat(fd)
                parts.append(f"{label}={fd}:open")
            except OSError as ex:
                parts.append(f"{label}={fd}:{type(ex).__name__}:{ex.errno}")
        return ", ".join(parts)


def acquire_lock(layout: Layout) -> DataRootLock:
    lock = DataRootLock(layout.lock_path)
    lock.__enter__()
    return lock


def _skip_rel(rel: str) -> bool:
    rel = rel.replace("\\", "/").strip("/")
    parts = rel.split("/") if rel else []
    if any(p in _SKIP_DIRS for p in parts):
        return True
    name = parts[-1] if parts else ""
    return name in _SKIP_NAMES or name.endswith(_SKIP_SUFFIX)


def _iter_files(root: str, profile_only: bool = False) -> Iterator[tuple[str, str, int]]:
    root = os.path.abspath(root)
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        for name in sorted(files):
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if _skip_rel(rel):
                continue
            if profile_only:
                top = rel.split("/", 1)[0]
                if top not in _PROFILE_NAMES and top != "reports":
                    continue
            yield path, rel, os.path.getsize(path)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_tree(
    src: str,
    dst: str,
    *,
    profile_only: bool = False,
    copy_hook: Callable[[str], None] | None = None,
) -> tuple[int, int]:
    os.makedirs(dst, exist_ok=True)
    count = 0
    total = 0
    for source, rel, size in _iter_files(src, profile_only=profile_only):
        target = os.path.join(dst, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
        count += 1
        total += size
        if copy_hook:
            copy_hook(rel)
    return count, total


def _tree_manifest(root: str, profile_only: bool = False) -> dict[str, tuple[int, str]]:
    return {
        rel: (size, _sha256(path))
        for path, rel, size in _iter_files(root, profile_only=profile_only)
    }


def _verify_tree(
    src: str,
    dst: str,
    *,
    profile_only: bool = False,
) -> dict:
    before = _tree_manifest(src, profile_only=profile_only)
    after = _tree_manifest(dst, profile_only=profile_only)
    missing = sorted(set(before) - set(after))
    extra = sorted(set(after) - set(before))
    bad = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    if missing or extra or bad:
        raise DataRootError(
            f"迁移校验失败（缺失 {len(missing)}，多出 {len(extra)}，"
            f"哈希/大小不符 {len(bad)}）")
    return {"files": len(before), "bytes": sum(v[0] for v in before.values())}


def _generation_id() -> str:
    return "gen-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4)


def _source_size(source_root: str, source_profile: str) -> tuple[int, int]:
    total = files = 0
    for name, profile in (("novels", False), ("data", False)):
        root = os.path.join(source_root, name)
        if os.path.isdir(root):
            for _, _, size in _iter_files(root, profile_only=profile):
                files += 1
                total += size
    if os.path.isdir(source_profile):
        for _, _, size in _iter_files(source_profile, profile_only=True):
            files += 1
            total += size
    return files, total


def _build_generation(
    home: str,
    source_root: str | None,
    source_profile: str | None,
    *,
    copy_hook: Callable[[str], None] | None = None,
) -> tuple[str, dict]:
    os.makedirs(home, exist_ok=True)
    staging_root = os.path.join(home, STAGING_DIR)
    os.makedirs(staging_root, exist_ok=True)
    staging = os.path.join(staging_root, _generation_id())
    os.makedirs(staging)
    summary = {"novels": 0, "data": 0, "profile": 0, "bytes": 0}
    try:
        if source_root:
            for name in ("novels", "data"):
                src = os.path.join(source_root, name)
                dst = os.path.join(staging, name)
                if os.path.isdir(src):
                    count, size = _copy_tree(src, dst, copy_hook=copy_hook)
                    summary[name] = count
                    summary["bytes"] += size
                    _verify_tree(src, dst)
                else:
                    os.makedirs(dst, exist_ok=True)
        else:
            os.makedirs(os.path.join(staging, "novels"), exist_ok=True)
            os.makedirs(os.path.join(staging, "data"), exist_ok=True)

        profile_src = source_profile
        profile_dst = os.path.join(staging, "profile")
        if profile_src and os.path.isdir(profile_src):
            count, size = _copy_tree(
                profile_src, profile_dst, profile_only=True, copy_hook=copy_hook)
            summary["profile"] = count
            summary["bytes"] += size
            _verify_tree(profile_src, profile_dst, profile_only=True)
        else:
            os.makedirs(profile_dst, exist_ok=True)

        generation_name = os.path.basename(staging)
        generations = os.path.join(home, GENERATIONS_DIR)
        os.makedirs(generations, exist_ok=True)
        final = os.path.join(generations, generation_name)
        os.rename(staging, final)
        _fsync_dir(staging_root)
        _fsync_dir(generations)
        return f"{GENERATIONS_DIR}/{generation_name}", summary
    except BaseException:
        # Keep a failed staging tree for diagnosis.  It is never referenced by
        # the active-generation pointer, and backup/migration skip it.
        raise


def migration_plan(
    home: str,
    source_root: str,
    source_profile: str | None = None,
) -> dict:
    home = os.path.abspath(os.path.expanduser(home))
    source_root = os.path.abspath(os.path.expanduser(source_root))
    source_profile = os.path.abspath(os.path.expanduser(
        source_profile or os.path.join(os.path.dirname(source_root), "lnfinder")))
    if not os.path.isdir(os.path.join(source_root, "novels")):
        raise DataRootError(f"旧数据根缺少 novels/：{source_root}")
    if not os.path.isdir(source_profile):
        raise DataRootError(f"画像数据目录不存在：{source_profile}")
    files, total = _source_size(source_root, source_profile)
    usage = shutil.disk_usage(os.path.dirname(home) or ".")
    # A generation may coexist with the old data and a previous generation.
    required = total * 2 + 32 * 1024 * 1024
    if usage.free < required:
        raise DataRootError(
            f"空间不足：需要约 {required / 1024 / 1024:.1f} MiB，"
            f"可用 {usage.free / 1024 / 1024:.1f} MiB")
    return {
        "home": home,
        "source_root": source_root,
        "source_profile": source_profile,
        "files": files,
        "bytes": total,
        "free": usage.free,
    }


def migrate_legacy(
    home: str,
    source_root: str,
    source_profile: str | None = None,
    *,
    write: bool = False,
    copy_hook: Callable[[str], None] | None = None,
) -> dict:
    plan = migration_plan(home, source_root, source_profile)
    if not write:
        return {"written": False, "plan": plan}

    home = plan["home"]
    os.makedirs(home, exist_ok=True)
    with DataRootLock(os.path.join(home, LOCK_FILE)):
        legacy_lock = os.path.join(plan["source_root"], "data", LOCK_FILE)
        with DataRootLock(legacy_lock):
            old_state = None
            state_path = os.path.join(home, STATE_FILE)
            if os.path.isfile(state_path):
                old_state = read_state(home)

            generation, summary = _build_generation(
                home,
                plan["source_root"],
                plan["source_profile"],
                copy_hook=copy_hook,
            )
            now = _now()
            state = {
                "schema_version": SCHEMA_VERSION,
                "app_version": APP_VERSION,
                "active_generation": generation,
                "previous_generation": (
                    old_state.get("active_generation") if old_state else None),
                "created_at": (
                    old_state.get("created_at") if old_state else now),
                "last_migration_at": now,
                "generations": list((old_state or {}).get("generations") or []),
                "last_backup": (old_state or {}).get("last_backup"),
            }
            state["generations"].append({
                "generation": generation,
                "created_at": now,
                "app_version": APP_VERSION,
                "source": "legacy-migration",
                "files": summary,
            })
            atomic_write_json(state_path, state)
            return {
                "written": True,
                "plan": plan,
                "generation": generation,
                "summary": summary,
                "state_path": state_path,
            }


def initialize_home(home: str, *, write: bool = False) -> dict:
    home = os.path.abspath(os.path.expanduser(home))
    if not write:
        return {"written": False, "home": home}
    os.makedirs(home, exist_ok=True)
    with DataRootLock(os.path.join(home, LOCK_FILE)):
        state_path = os.path.join(home, STATE_FILE)
        if os.path.isfile(state_path):
            raise DataRootError(f"数据根已经初始化：{state_path}")
        generation, summary = _build_generation(home, None, None)
        now = _now()
        atomic_write_json(state_path, {
            "schema_version": SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "active_generation": generation,
            "previous_generation": None,
            "created_at": now,
            "last_migration_at": now,
            "generations": [{
                "generation": generation,
                "created_at": now,
                "app_version": APP_VERSION,
                "source": "init",
                "files": summary,
            }],
            "last_backup": None,
        })
        return {
            "written": True,
            "home": home,
            "generation": generation,
            "state_path": state_path,
        }


def rollback(home: str, *, write: bool = False) -> dict:
    home = os.path.abspath(os.path.expanduser(home))
    state_path = os.path.join(home, STATE_FILE)
    if not os.path.isfile(state_path):
        raise DataRootError(f"数据根尚未初始化：{home}")
    if not write:
        state = read_state(home)
        return {
            "written": False,
            "from": state.get("active_generation"),
            "to": state.get("previous_generation"),
        }
    with DataRootLock(os.path.join(home, LOCK_FILE)):
        state = read_state(home)
        current = state.get("active_generation")
        previous = state.get("previous_generation")
        if not previous:
            raise DataRootError("没有可回滚的上一代数据")
        target = os.path.join(home, *str(previous).replace("\\", "/").split("/"))
        if not os.path.isdir(target):
            raise DataRootError(f"上一代数据不存在：{previous}")
        state["previous_generation"] = current
        state["active_generation"] = previous
        state["last_rollback_at"] = _now()
        atomic_write_json(state_path, state)
        return {
            "written": True,
            "from": current,
            "to": previous,
            "state_path": state_path,
        }


def status(home: str) -> dict:
    home = os.path.abspath(os.path.expanduser(home))
    state = read_state(home)
    layout = resolve_layout(home=home)
    return {
        "home": home,
        "app_version": APP_VERSION,
        "schema_version": state.get("schema_version"),
        "active_generation": state.get("active_generation"),
        "previous_generation": state.get("previous_generation"),
        "data_root": layout.data_root,
        "finder_root": layout.finder_root,
        "state": state,
    }


def record_backup(
    home: str | None,
    *,
    backup_sha256: str,
    backup_id: str,
    created_at: str,
    relative_hint: str = "",
) -> dict | None:
    """Record backup identity without persisting a host absolute path."""
    resolved_home = home or os.environ.get("LNTRANS_HOME")
    if not resolved_home:
        return None
    resolved_home = os.path.abspath(os.path.expanduser(resolved_home))
    state_path = os.path.join(resolved_home, STATE_FILE)
    if not os.path.isfile(state_path):
        return None
    state = read_state(resolved_home)
    state["last_backup"] = {
        "at": _now(),
        "created_at": created_at,
        "sha256": backup_sha256,
        "backup_id": backup_id,
        # 只留文件名：Windows 的 `C:\dir\x.zip` 在 POSIX 上 basename 不切分，
        # 会把宿主机绝对路径写进状态文件（自检当场红：test_data_safety）。
        "relative_hint": os.path.basename((relative_hint or "").replace("\\", "/")),
    }
    atomic_write_json(state_path, state)
    return state["last_backup"]

