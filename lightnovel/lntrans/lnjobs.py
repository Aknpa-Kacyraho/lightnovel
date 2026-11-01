#!/usr/bin/env python3
"""Durable translation-job records and crash recovery helpers.

The archive is deliberately file based: one JSON object per job under
``data/jobs``.  A malformed record never gets silently discarded.  Instead the
whole job subsystem becomes read-only until the user quarantines or repairs the
bad file, while chapter files remain readable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sys
import threading
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lndata  # noqa: E402
import lncontracts  # noqa: E402

LAYOUT = lndata.resolve_layout()
ROOT = LAYOUT.data_root
ACTIVE_STATUSES = frozenset({"queued", "running"})
TERMINAL_STATUSES = lncontracts.JOB_STATUSES - ACTIVE_STATUSES


class JobError(RuntimeError):
    pass


class RecoveryRequired(JobError):
    pass


class JobRecordCorrupt(RecoveryRequired):
    """One existing record is unreadable or violates the contract.

    Treated like the whole log being read-only: the job subsystem stops
    scheduling and asks for confirmation, while reading keeps working.  It is
    deliberately *not* a plain ``JobError`` — the worker maps plain errors to
    ``provider_error``, which would tell the user the model failed.
    """


class JobRecordMissing(RecoveryRequired):
    """An active record disappeared while the worker still owned it.

    This is an external deletion (or a restore that dropped the file), not a
    model failure.  It must stop that one job and say so; it must neither mark
    the whole log read-only (there is nothing to repair) nor leave a
    "translation failed" badge on the book.
    """


class ActiveJobExists(JobError):
    def __init__(self, record: dict):
        super().__init__(f"{record.get('slug')} 已有有效翻译任务")
        self.record = record


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _canonical_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def idempotency_key(*, slug: str, target: dict, sources: list[dict],
                    translation_config_hash: str) -> str:
    """Stable identity for "the same paid work", not for a scheduler event."""
    return _canonical_hash({
        "slug": slug,
        "target": {
            "from_chapter": int(target["from_chapter"]),
            "to_chapter": int(target["to_chapter"]),
        },
        "sources": sources,
        "translation_config_hash": translation_config_hash,
    })


def composite_config_hash(*, source_hashes: list[str], model_provider: str,
                          model_id: str, prompt_version: str,
                          glossary_revision: str,
                          characters_revision: str,
                          style_revision: str) -> str:
    aggregate_source = _canonical_hash(sorted(source_hashes))
    return lncontracts.translation_config_hash(
        source_sha256=aggregate_source,
        model_provider=model_provider,
        model_id=model_id,
        prompt_version=prompt_version,
        glossary_revision=glossary_revision,
        characters_revision=characters_revision,
        style_revision=style_revision,
    )


class JobStore:
    def __init__(self, root: str | None = None):
        self.root = os.path.join(root or ROOT, "data", "jobs")
        self.quarantine_root = os.path.join(self.root, "quarantine")
        self._lock = threading.RLock()
        self._last_health: dict | None = None
        self._last_count: int | None = None

    def _ensure_dir(self) -> None:
        os.makedirs(self.root, exist_ok=True)

    def path_for(self, job_id: str) -> str:
        if not job_id or os.path.basename(job_id) != job_id:
            raise JobError("非法 job_id")
        return os.path.join(self.root, f"{job_id}.json")

    def _json_count(self) -> int:
        """Cheap change detector: number of records, without parsing them."""
        try:
            return sum(1 for name in os.listdir(self.root)
                       if name.endswith(".json") and not name.startswith("."))
        except OSError:
            return 0

    def _health_payload(self, corrupt: list[dict]) -> dict:
        return {
            "ok": not corrupt,
            "read_only": bool(corrupt),
            "corrupt": corrupt,
            "jobs_root": self.root,
            "repair_command": (
                "python lntrans/lnjobs.py quarantine <job-id> --write"),
        }

    def _scan(self) -> tuple[list[dict], list[dict]]:
        if not os.path.isdir(self.root):
            return [], []
        records: list[dict] = []
        corrupt: list[dict] = []
        for name in sorted(os.listdir(self.root)):
            if not name.endswith(".json") or name.startswith("."):
                continue
            path = os.path.join(self.root, name)
            if not os.path.isfile(path):
                continue
            try:
                rec = lncontracts.load_record(path, "job")
            except (lncontracts.ContractError, OSError) as ex:
                corrupt.append({"file": name, "error": str(ex)})
                continue
            records.append(rec)
        records.sort(key=lambda r: (r.get("created_at", ""),
                                    r.get("job_id", "")))
        return records, corrupt

    def health(self, refresh: bool = True) -> dict:
        """Report whether the job log is writable.

        ``refresh=False`` reuses the cached verdict unless the number of record
        files changed.  Updates rewrite existing files, so polling and per
        paragraph progress reports stay O(1) instead of parsing every job on
        every write; a newly appeared record (the only way an outside process
        can corrupt the log without replacing a known file) still triggers a
        full rescan.
        """
        with self._lock:
            count = self._json_count()
            if (refresh or self._last_health is None
                    or count != self._last_count):
                _, corrupt = self._scan()
                self._last_health = self._health_payload(corrupt)
                self._last_count = self._json_count()
            return dict(self._last_health)

    def assert_writable(self, refresh: bool = False) -> None:
        h = self.health(refresh=refresh)
        if h["read_only"]:
            names = ", ".join(x["file"] for x in h["corrupt"])
            raise RecoveryRequired(
                f"任务日志损坏，已进入只读恢复模式：{names}。"
                f"修复命令：{h['repair_command']}")

    def records(self) -> list[dict]:
        with self._lock:
            records, _ = self._scan()
            return records

    def get(self, job_id: str) -> dict | None:
        path = self.path_for(job_id)
        if not os.path.isfile(path):
            return None
        try:
            return lncontracts.load_record(path, "job")
        except lncontracts.ContractError as ex:
            # 损坏的活动任务记录必须走「只读恢复」这条路，而不是把
            # ContractError（ValueError 子类）漏给 HTTP 层变成 500，也不是
            # 让写入路径把它当成普通模型错误（那会显示「翻译中止」）。
            raise JobRecordCorrupt(str(ex)) from ex

    def active(self, slug: str) -> dict | None:
        with self._lock:
            records, corrupt = self._scan()
            if corrupt:
                return None
            active = [
                r for r in records
                if r.get("slug") == slug and r.get("status") in ACTIVE_STATUSES
            ]
            return active[-1] if active else None

    def latest(self, slug: str) -> dict | None:
        with self._lock:
            records, _ = self._scan()
            rows = [r for r in records if r.get("slug") == slug]
            if not rows:
                return None
            rows.sort(key=lambda r: (r.get("updated_at", ""),
                                     r.get("created_at", ""),
                                     r.get("job_id", "")))
            return rows[-1]

    def _new_id(self) -> str:
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        return f"job-{stamp}-{secrets.token_hex(4)}"

    def create(self, *, slug: str, target: dict, model_provider: str,
               model_role: str, model_id: str,
               translation_config_hash: str,
               idempotency_key: str,
               requested: dict,
               source_entries: list[dict] | None = None) -> dict:
        with self._lock:
            # Creating a task is rare: pay for a full scan so an already
            # corrupted log blocks new paid work before anything is written.
            self.assert_writable(refresh=True)
            current = self.active(slug)
            if current:
                raise ActiveJobExists(current)
            self._ensure_dir()
            stamp = now_iso()
            rec = {
                "schema_version": lncontracts.JOB_SCHEMA_VERSION,
                "job_id": self._new_id(),
                "idempotency_key": idempotency_key,
                "slug": slug,
                "status": "queued",
                "target": {
                    "from_chapter": int(target["from_chapter"]),
                    "to_chapter": int(target["to_chapter"]),
                },
                "model_provider": model_provider,
                "model_role": model_role,
                "model_id": model_id,
                "translation_config_hash": translation_config_hash,
                "usage": {"input": 0, "output": 0},
                "cost": {"amount": 0, "currency": "CNY", "estimated": True},
                "created_at": stamp,
                "updated_at": stamp,
                "heartbeat_at": stamp,
                "error": None,
                "requested": dict(requested),
                "sources": list(source_entries or []),
                "chapter_numbers": [],
                "completed_chapters": [],
                "remaining_chapters": [],
                "partial_chapters": [],
            }
            lncontracts.validate_job_record(rec)
            lndata.atomic_write_json(self.path_for(rec["job_id"]), rec)
            # The scan above proved the log healthy; remember it instead of
            # forcing the next poll/progress write to rescan everything.
            self._last_health = self._health_payload([])
            self._last_count = self._json_count()
            return rec

    def update(self, job_id: str, **changes) -> dict:
        with self._lock:
            # Fast path: the cached verdict plus the target record's own
            # validation.  Per-paragraph progress callbacks run through here,
            # so a full-directory scan on every write would be O(records) per
            # paragraph and grow with the archive.
            self.assert_writable(refresh=False)
            path = self.path_for(job_id)
            rec = self.get(job_id)
            if rec is None:
                # 活跃任务记录被外部删除：这不是「参数错了」，更不是模型失败。
                # 让调用方按恢复处理（停这个任务、说明原因），但不锁整站。
                raise JobRecordMissing(
                    f"任务记录已被删除：{job_id}；任务已停止，已译章节可读")
            rec.update(changes)
            rec["updated_at"] = now_iso()
            rec["heartbeat_at"] = rec["updated_at"]
            lncontracts.validate_job_record(rec)
            lndata.atomic_write_json(path, rec)
            return rec

    def reconcile_startup(self) -> dict:
        """Turn in-flight records into explicit interrupted work.

        The in-memory queue dies with the process, so ``queued`` is no more
        truthful than ``running`` after a restart.  Both become ``interrupted``
        and require a user-confirmed resume.
        """
        with self._lock:
            records, corrupt = self._scan()
            self._last_health = self._health_payload(corrupt)
            self._last_count = self._json_count()
            if corrupt:
                return {"ok": False, "read_only": True, "corrupt": corrupt,
                        "changed": 0}
            changed = 0
            active_by_slug: dict[str, list[dict]] = {}
            for rec in records:
                if rec.get("status") in ACTIVE_STATUSES:
                    active_by_slug.setdefault(rec["slug"], []).append(rec)
            for slug, rows in active_by_slug.items():
                rows.sort(key=lambda r: (r.get("created_at", ""),
                                         r.get("job_id", "")))
                for rec in rows:
                    reason = "服务重启或进程中断；已停止调度，等待用户确认恢复"
                    if len(rows) > 1:
                        reason = ("启动时检测到同一本书有多个有效任务；"
                                  "全部停止，等待用户确认恢复")
                    self.update(
                        rec["job_id"],
                        status="interrupted",
                        error=reason,
                        interrupted_at=now_iso(),
                    )
                    changed += 1
            # Keep the healthy verdict computed above: every update in this
            # loop already ran through the fast path without a rescan.
            return {"ok": not corrupt, "read_only": bool(corrupt),
                    "changed": changed, "corrupt": corrupt}

    def quarantine(self, job_id: str, *, write: bool = False) -> dict:
        path = self.path_for(job_id)
        if not os.path.isfile(path):
            raise JobError(f"找不到任务文件：{path}")
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(self.quarantine_root,
                            f"{job_id}.{stamp}.bad.json")
        result = {"source": path, "destination": dest, "written": bool(write)}
        if not write:
            return result
        os.makedirs(self.quarantine_root, exist_ok=True)
        if os.path.exists(dest):
            raise JobError(f"隔离目标已存在：{dest}")
        shutil.move(path, dest)
        self._last_health = None
        return result

    def public_view(self, record: dict | None) -> dict:
        if not record:
            return {"status": "idle"}
        completed = list(record.get("completed_chapters") or [])
        remaining = list(record.get("remaining_chapters") or [])
        return {
            "status": record.get("status"),
            "job_id": record.get("job_id"),
            "slug": record.get("slug"),
            "target": dict(record.get("target") or {}),
            "completed_chapters": completed,
            "remaining_chapters": remaining,
            "partial_chapters": list(record.get("partial_chapters") or []),
            "completed": len(completed),
            "remaining": len(remaining),
            "requested": dict(record.get("requested") or {}),
            "usage": dict(record.get("usage") or {}),
            "cost": dict(record.get("cost") or {}),
            "error": record.get("error"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
        }


STORE = JobStore()


def _main() -> int:
    ap = argparse.ArgumentParser(description="检查与隔离持久翻译任务日志")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="列出任务记录")
    sub.add_parser("verify", help="校验全部任务记录")
    q = sub.add_parser("quarantine", help="把损坏记录移到 quarantine/")
    q.add_argument("job_id")
    q.add_argument("--write", action="store_true", help="真正移动；默认干跑")
    a = ap.parse_args()

    h = STORE.health(refresh=True)
    if a.cmd == "verify":
        print("任务日志正常" if h["ok"] else
              "任务日志损坏，已进入只读恢复模式")
        for item in h["corrupt"]:
            print(f"  - {item['file']}: {item['error']}")
        if not h["ok"]:
            print(f"修复命令：{h['repair_command']}")
            return 1
        return 0

    if a.cmd == "quarantine":
        result = STORE.quarantine(a.job_id, write=a.write)
        print(("已隔离：" if a.write else "将隔离：") + result["source"])
        print("目标：" + result["destination"])
        if not a.write:
            print("这是干跑；确认后加 --write")
        return 0

    rows = STORE.records()
    for rec in rows:
        print(f"{rec['job_id']}  {rec['slug']}  {rec['status']}  "
              f"{rec['target']['from_chapter']}-{rec['target']['to_chapter']}  "
              f"完成 {len(rec.get('completed_chapters') or [])} / "
              f"剩余 {len(rec.get('remaining_chapters') or [])}")
    if not rows:
        print("（没有任务记录）")
    if not h["ok"]:
        print("损坏记录：")
        for item in h["corrupt"]:
            print(f"  - {item['file']}: {item['error']}")
        print(f"修复命令：{h['repair_command']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
