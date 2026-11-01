#!/usr/bin/env python3
"""Fault tests for v5 data generations, migration, and process ownership."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lndata

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def put(base, rel, text):
    path = os.path.join(base, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_digest(root, skip_control=False):
    out = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if skip_control and (
                    name in (lndata.LOCK_FILE, lndata.STATE_FILE)
                    or name.endswith((".log", ".tmp", ".part"))):
                continue
            out[rel] = digest(path)
    return out


TMP = tempfile.mkdtemp(prefix="lndata-test-")

# ---------------------------------------------------------------- fixture
legacy = os.path.join(TMP, "legacy")
source = os.path.join(legacy, "lntrans")
profile = os.path.join(legacy, "lnfinder")
home = os.path.join(TMP, "home")

put(source, "novels/book-a/meta.json",
    '{"source_id":"a","glossary":{"猫":"猫"},"characters":{"アリス":{"voice":"短句"}}}')
put(source, "novels/book-a/chapters/0000.txt", "第一章译文")
put(source, "novels/book-a/raw/0000.txt", "第一章原文")
put(source, "novels/book-a/cache/cache.json", '{"0-1":["缓存"]}')
put(source, "data/books/book-a.json",
    '{"progress":{"chapter":1},"favorites":{"book-a":"now"}}')
put(source, "data/library.json", '{"items":{"a":{"title":"书"}}}')
put(source, "data/history.jsonl", '{"at":"2026-01-01"}\n')
put(source, "data/server.log", "不要迁移")
put(source, "data/x.part", "不要迁移")
put(source, "data/.lntrans.lock", "不要迁移")
put(profile, "taste_profile.json", '{"tag_weights":{"猫":2}}')
put(profile, "history.jsonl", '{"at":"2026-01-01"}\n')
put(profile, "reports/report.md", "画像报告")
put(profile, "lnfind.py", "# code must not migrate")

source_before = tree_digest(source, skip_control=True)
profile_before = tree_digest(profile)
profile_data_before = {
    rel: sha for rel, sha in profile_before.items()
    if rel in ("taste_profile.json", "candidates.json", "history.jsonl",
               "recommend-latest.md")
    or rel.startswith("reports/")
}

# ---------------------------------------------------------------- dry-run
plan = lndata.migrate_legacy(home, source, profile, write=False)
check("迁移默认干跑", plan.get("written") is False)
check("干跑不创建数据根", not os.path.exists(home))

# ---------------------------------------------------------------- migration
result = lndata.migrate_legacy(home, source, profile, write=True)
state = lndata.read_state(home)
layout = lndata.resolve_layout(home=home)
check("迁移写入 active_generation",
      state["active_generation"] == result["generation"])
check("状态文件没有绝对路径",
      TMP not in json.dumps(state, ensure_ascii=False))
check("v5 根解析到 generation",
      layout.data_root.endswith(result["generation"].replace("/", os.sep)))
check("novels 逐字节一致",
      tree_digest(os.path.join(source, "novels"))
      == tree_digest(os.path.join(layout.data_root, "novels")))
check("data 逐字节一致",
      tree_digest(os.path.join(source, "data"), skip_control=True)
      == tree_digest(os.path.join(layout.data_root, "data")))
check("画像只迁移数据、不迁移代码",
      profile_data_before == tree_digest(layout.finder_root)
      and not os.path.exists(os.path.join(layout.finder_root, "lnfind.py")))
migrated_all = tree_digest(layout.data_root)
check("锁、日志和临时文件不进 generation",
      not any(n.endswith((".log", ".part")) or n.endswith(lndata.LOCK_FILE)
              for n in migrated_all))
check("旧数据没有被删除", tree_digest(source, skip_control=True) == source_before)
check("旧画像没有被删除", tree_digest(profile) == profile_before)

# ---------------------------------------------------------------- second generation
put(source, "data/new-after-first.json", '{"new":true}')
result2 = lndata.migrate_legacy(home, source, profile, write=True)
state2 = lndata.read_state(home)
check("再次迁移指向新 generation",
      state2["active_generation"] == result2["generation"]
      and state2["previous_generation"] == result["generation"])
rolled = lndata.rollback(home, write=True)
state3 = lndata.read_state(home)
check("回滚只切换状态指针",
      rolled["to"] == result["generation"]
      and state3["active_generation"] == result["generation"])
check("回滚后旧 generation 可读",
      os.path.isfile(os.path.join(
          home, *result["generation"].split("/"), "novels", "book-a", "meta.json")))

# ---------------------------------------------------------------- kill during copy
home_kill = os.path.join(TMP, "home-kill")
child_code = r"""
import os, sys
sys.path.insert(0, sys.argv[1])
import lndata
n = [0]
def hook(_rel):
    n[0] += 1
    if n[0] >= 2:
        os._exit(17)
lndata.migrate_legacy(sys.argv[2], sys.argv[3], sys.argv[4], write=True, copy_hook=hook)
"""
env = dict(os.environ, PYTHONPATH=HERE, PYTHONUTF8="1",
           PYTHONDONTWRITEBYTECODE="1")
child = subprocess.run(
    [sys.executable, "-c", child_code, HERE, home_kill, source, profile],
    cwd=HERE, env=env, capture_output=True, text=True, timeout=30)
check("迁移中途被强杀", child.returncode == 17, f"{child.returncode}")
check("强杀后 active pointer 未切换",
      not os.path.exists(os.path.join(home_kill, lndata.STATE_FILE)))
check("强杀后旧数据仍完整",
      tree_digest(source, skip_control=True)["novels/book-a/meta.json"]
      == source_before["novels/book-a/meta.json"])
check("强杀后 staging 保留供诊断",
      os.path.isdir(os.path.join(home_kill, lndata.STAGING_DIR)))
retry = lndata.migrate_legacy(home_kill, source, profile, write=True)
check("强杀后重试可完整迁移",
      lndata.read_state(home_kill)["active_generation"] == retry["generation"])

# ---------------------------------------------------------------- schema gate
future_home = os.path.join(TMP, "future-home")
os.makedirs(os.path.join(future_home, "generations", "gen-future"))
lndata.atomic_write_json(os.path.join(future_home, lndata.STATE_FILE), {
    "schema_version": lndata.SCHEMA_VERSION + 1,
    "app_version": "9.0",
    "active_generation": "generations/gen-future",
})
blocked = False
try:
    lndata.resolve_layout(home=future_home)
except lndata.DataRootError:
    blocked = True
check("更高 schema_version 拒绝启动", blocked)

# Explicit isolation root must beat an inherited v5 home.
_old_env = dict(os.environ)
try:
    os.environ["LNTRANS_HOME"] = home
    os.environ["LNTRANS_DATA_ROOT"] = os.path.join(TMP, "explicit-root")
    os.environ["LNTRANS_LNFINDER"] = os.path.join(TMP, "explicit-profile")
    isolated = lndata.resolve_layout()
    check("显式 LNTRANS_DATA_ROOT 优先于继承的 LNTRANS_HOME",
          isolated.mode == "legacy"
          and isolated.data_root == os.path.join(TMP, "explicit-root"))
finally:
    os.environ.clear()
    os.environ.update(_old_env)

# ---------------------------------------------------------------- process lock
lock_path = os.path.join(TMP, "lock-root", lndata.LOCK_FILE)
holder_code = r"""
import sys
sys.path.insert(0, sys.argv[1])
import lndata
with lndata.DataRootLock(sys.argv[2]):
    print("LOCKED", flush=True)
    sys.stdin.read()
"""
holder = subprocess.Popen(
    [sys.executable, "-c", holder_code, HERE, lock_path],
    cwd=HERE, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.PIPE, text=True)
line = holder.stdout.readline().strip() if holder.stdout else ""
check("测试持锁进程启动", line == "LOCKED", line or "no output")
second_blocked = False
try:
    with lndata.DataRootLock(lock_path):
        pass
except lndata.LockBusy:
    second_blocked = True
check("第二个进程被系统锁拒绝", second_blocked)

holder.kill()
holder.wait(timeout=10)
reacquired = False
try:
    with lndata.DataRootLock(lock_path):
        reacquired = True
except lndata.LockBusy:
    pass
check("强杀持锁进程后无需删文件即可重获锁", reacquired)

# ---------------------------------------------------------------- init/status
empty_home = os.path.join(TMP, "empty-home")
fresh = lndata.initialize_home(empty_home, write=True)
empty_layout = lndata.resolve_layout(home=empty_home)
check("空数据根可初始化",
      fresh["written"] and os.path.isdir(os.path.join(
          empty_layout.data_root, "novels")))
status = lndata.status(empty_home)
check("status 返回应用与 schema 版本",
      status["app_version"] == lndata.APP_VERSION
      and status["schema_version"] == lndata.SCHEMA_VERSION)
recorded = lndata.record_backup(
    empty_home,
    backup_sha256="c" * 64,
    backup_id="backup-test",
    created_at="2026-10-21T12:00:00",
    relative_hint=r"C:\private\path\lntrans-backup.zip",
)
check("备份身份写回数据根状态",
      recorded and recorded["backup_id"] == "backup-test"
      and recorded["sha256"] == "c" * 64)
check("备份状态不泄漏宿主机绝对路径",
      recorded and recorded["relative_hint"] == "lntrans-backup.zip"
      and "C:\\private" not in json.dumps(lndata.read_state(empty_home)))

held = lndata.acquire_lock(empty_layout)
check("acquire_lock 返回已持有的锁", held.is_held())
held.__exit__(None, None, None)
check("acquire_lock 释放后状态正确", not held.is_held())

# End-to-end: two real lnserve processes must not enter with the same home.
probe = socket.socket()
probe.bind(("127.0.0.1", 0))
port1 = probe.getsockname()[1]
probe.close()
probe = socket.socket()
probe.bind(("127.0.0.1", 0))
port2 = probe.getsockname()[1]
probe.close()
env_server = {
    k: v for k, v in env.items()
    if k not in ("LNTRANS_DATA_ROOT", "LNTRANS_LNFINDER")
}
env_server.update(LNTRANS_HOME=home, LNTRANS_TEST_SERVER="1")
first = subprocess.Popen(
    [sys.executable, os.path.join(HERE, "lnserve.py"), "--port", str(port1)],
    cwd=HERE, env=env_server, stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, text=True)
started = False
for _ in range(50):
    if first.poll() is not None:
        break
    try:
        with socket.create_connection(("127.0.0.1", port1), timeout=0.25):
            started = True
            break
    except OSError:
        time.sleep(0.1)
check("真实 lnserve 启动", started, f"exit={first.poll()}")
second = subprocess.run(
    [sys.executable, os.path.join(HERE, "lnserve.py"), "--port", str(port2)],
    cwd=HERE, env=env_server, capture_output=True, text=True, timeout=20)
second_text = second.stdout + second.stderr
check("同数据根第二个 lnserve 被拒绝",
      second.returncode == 2 and "已有实例持有排他锁" in second_text,
      f"exit={second.returncode} out={second_text[-240:]}")
cli_write = subprocess.run(
    [sys.executable, os.path.join(HERE, "lntrans.py"),
     "learn", "book-a", "--term", "猫=猫"],
    cwd=HERE, env=env_server, capture_output=True, text=True, timeout=20)
cli_text = cli_write.stdout + cli_write.stderr
check("变更型翻译 CLI 与服务共用数据根锁",
      cli_write.returncode == 2 and "请先停止正在运行的书架服务" in cli_text,
      f"exit={cli_write.returncode} out={cli_text[-240:]}")
backup_write = subprocess.run(
    [sys.executable, os.path.join(HERE, "lnbackup.py"), "export",
     "--out", os.path.join(TMP, "blocked-backup")],
    cwd=HERE, env=env_server, capture_output=True, text=True, timeout=20)
backup_text = backup_write.stdout + backup_write.stderr
check("CLI 备份构建与服务共用数据根锁",
      backup_write.returncode == 1 and "请先停止正在运行的书架服务" in backup_text,
      f"exit={backup_write.returncode} out={backup_text[-240:].replace('❌', '[x]')}")
restore_write = subprocess.run(
    [sys.executable, os.path.join(HERE, "lnbackup.py"), "restore",
     os.path.join(TMP, "does-not-exist.zip"), "--write"],
    cwd=HERE, env=env_server, capture_output=True, text=True, timeout=20)
restore_text = restore_write.stdout + restore_write.stderr
check("恢复 --write 与服务共用数据根锁",
      restore_write.returncode == 1 and "请先停止正在运行的书架服务" in restore_text,
      f"exit={restore_write.returncode} out={restore_text[-240:].replace('❌', '[x]')}")
first.terminate()
try:
    first.wait(timeout=10)
except subprocess.TimeoutExpired:
    first.kill()
    first.wait(timeout=10)
migrated_lock = lndata.acquire_lock(lndata.resolve_layout(home=home))
check("迁移数据上的真实 lnserve 退出后锁可重新获取", migrated_lock.is_held())
migrated_lock.__exit__(None, None, None)

print()
if fails:
    print(f"失败 {len(fails)} 项：{fails}")
    print(f"保留现场：{TMP}")
    sys.exit(1)
shutil.rmtree(TMP, ignore_errors=True)
print("数据根迁移、代际切换、回滚和跨进程锁全部通过")

