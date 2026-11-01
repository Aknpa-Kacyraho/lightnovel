#!/usr/bin/env python3
"""Versioned contracts for v5 task logs and chapter sidecars.

The parsers remain independent from scheduling so the durable record shapes and
the crash-recovery implementation cannot silently drift apart.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

JOB_SCHEMA_VERSION = 1
CHAPTER_META_SCHEMA_VERSION = 1

JOB_STATUSES = frozenset({
    "queued",
    "running",
    "interrupted",
    "cancelled",
    "budget_exhausted",
    "provider_error",
    "partial",
    "done",
})

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")


class ContractError(ValueError):
    """A persisted record is malformed or belongs to a newer schema."""


def _need(obj: dict, key: str, typ: type | tuple[type, ...], where: str):
    if key not in obj:
        raise ContractError(f"{where} 缺少字段 {key}")
    value = obj[key]
    if not isinstance(value, typ):
        raise ContractError(f"{where}.{key} 类型错误：{type(value).__name__}")
    return value


def _check_schema(obj: dict, expected: int, where: str) -> None:
    version = _need(obj, "schema_version", int, where)
    if version > expected:
        raise ContractError(
            f"{where}.schema_version={version}，当前只支持 {expected}")
    if version != expected:
        raise ContractError(
            f"{where}.schema_version={version}，应为 {expected}")


def _check_usage(value: Any, where: str) -> None:
    if not isinstance(value, dict):
        raise ContractError(f"{where} 必须是对象")
    for key in ("input", "output"):
        n = value.get(key, 0)
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise ContractError(f"{where}.{key} 必须是非负整数")


def _check_cost(value: Any, where: str) -> None:
    if not isinstance(value, dict):
        raise ContractError(f"{where} 必须是对象")
    amount = value.get("amount", 0)
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 0:
        raise ContractError(f"{where}.amount 必须是非负数")
    if not isinstance(value.get("currency"), str) or not value["currency"].strip():
        raise ContractError(f"{where}.currency 不能为空")
    if not isinstance(value.get("estimated"), bool):
        raise ContractError(f"{where}.estimated 必须是布尔值")


def validate_job_record(obj: dict) -> dict:
    """Validate and return a v1 durable job record."""
    if not isinstance(obj, dict):
        raise ContractError("job record 必须是对象")
    _check_schema(obj, JOB_SCHEMA_VERSION, "job")
    for key in ("job_id", "idempotency_key", "slug", "created_at", "updated_at"):
        if not isinstance(_need(obj, key, str, "job"), str) or not obj[key].strip():
            raise ContractError(f"job.{key} 不能为空")
    status = _need(obj, "status", str, "job")
    if status not in JOB_STATUSES:
        raise ContractError(f"未知 job.status: {status}")
    target = _need(obj, "target", dict, "job")
    for key in ("from_chapter", "to_chapter"):
        n = _need(target, key, int, "job.target")
        if n < 1:
            raise ContractError(f"job.target.{key} 必须 >= 1")
    if target["to_chapter"] < target["from_chapter"]:
        raise ContractError("job.target.to_chapter 不能小于 from_chapter")
    if "usage" in obj:
        _check_usage(obj["usage"], "job.usage")
    if "cost" in obj:
        _check_cost(obj["cost"], "job.cost")
    return obj


def translation_config_hash(
    *,
    source_sha256: str,
    model_provider: str,
    model_id: str,
    prompt_version: str,
    glossary_revision: str | int,
    characters_revision: str | int,
    style_revision: str | int,
) -> str:
    """Hash every input that can change the meaning of a translation."""
    payload = {
        "source_sha256": source_sha256,
        "model_provider": model_provider,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "glossary_revision": str(glossary_revision),
        "characters_revision": str(characters_revision),
        "style_revision": str(style_revision),
    }
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_chapter_meta(obj: dict) -> dict:
    """Validate the final-content sidecar ``chapters/NNNN.meta.json``."""
    if not isinstance(obj, dict):
        raise ContractError("chapter meta 必须是对象")
    _check_schema(obj, CHAPTER_META_SCHEMA_VERSION, "chapter_meta")
    status = _need(obj, "status", str, "chapter_meta")
    if status not in ("complete", "partial"):
        raise ContractError("chapter_meta.status 必须是 complete 或 partial")
    sha = _need(obj, "source_sha256", str, "chapter_meta")
    if not _HEX64.fullmatch(sha):
        raise ContractError("chapter_meta.source_sha256 必须是 64 位小写 sha256")
    content_sha = _need(obj, "content_sha256", str, "chapter_meta")
    if not _HEX64.fullmatch(content_sha):
        raise ContractError("chapter_meta.content_sha256 必须是 64 位小写 sha256")
    cfg = _need(obj, "translation_config_hash", str, "chapter_meta")
    if not _HEX64.fullmatch(cfg):
        raise ContractError("chapter_meta.translation_config_hash 必须是 sha256")
    for key in ("model_provider", "model_role", "model_id", "prompt_version",
                "translated_at"):
        if not _need(obj, key, str, "chapter_meta").strip():
            raise ContractError(f"chapter_meta.{key} 不能为空")
    if obj["model_role"] != "translate":
        raise ContractError("章节旁车的 model_role 必须是 translate")
    _check_usage(_need(obj, "tokens", dict, "chapter_meta"), "chapter_meta.tokens")
    _check_cost(_need(obj, "cost", dict, "chapter_meta"), "chapter_meta.cost")
    incomplete = _need(obj, "incomplete_paragraphs", list, "chapter_meta")
    if any(not isinstance(x, int) or isinstance(x, bool) or x < 0 for x in incomplete):
        raise ContractError("chapter_meta.incomplete_paragraphs 必须是非负整数数组")
    if status == "complete" and incomplete:
        raise ContractError(
            "chapter_meta.status=complete 时 incomplete_paragraphs 必须为空")
    if status == "partial" and not incomplete:
        raise ContractError(
            "chapter_meta.status=partial 时 incomplete_paragraphs 不能为空")
    if "incomplete_reason" in obj:
        reason = obj["incomplete_reason"]
        if reason not in ("budget_exhausted", "provider_incomplete"):
            raise ContractError("chapter_meta.incomplete_reason 非法")
        if status != "partial":
            raise ContractError(
                "chapter_meta.incomplete_reason 只能出现在 partial 状态")
    if "glossary_revision" in obj:
        rev = obj["glossary_revision"]
        if not isinstance(rev, str) or not _HEX32.fullmatch(rev):
            raise ContractError(
                "chapter_meta.glossary_revision 必须是 32 位小写 sha 前缀")
    return obj


def content_available(
    meta: dict | None,
    *,
    translation_exists: bool,
    current_source_sha256: str,
    current_content_sha256: str | None = None,
) -> bool:
    """Whether readers may use the existing chapter translation.

    A model/prompt config change is not invalidation.  Only missing content or a
    changed source makes the translation unavailable.
    """
    if not translation_exists or not meta:
        return False
    try:
        validate_chapter_meta(meta)
    except ContractError:
        return False
    if meta["source_sha256"] != current_source_sha256:
        return False
    if (current_content_sha256 is not None
            and meta["content_sha256"] != current_content_sha256):
        return False
    return True


def current_config_satisfied(meta: dict | None, config_hash: str) -> bool:
    return bool(meta and meta.get("translation_config_hash") == config_hash)


def load_record(path: str, kind: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError) as ex:
        raise ContractError(f"无法读取 {kind} 记录 {path}: {ex}") from ex
    if kind == "job":
        return validate_job_record(obj)
    if kind == "chapter_meta":
        return validate_chapter_meta(obj)
    raise ContractError(f"未知契约类型：{kind}")


# 文件哈希缓存：`translation_paths_state` 每次校验都会算 原文+译文 两个
# SHA-256，而 `rebuild_novel_md` 每译完一章就要校验全书 —— 不缓存就是
# O(章数²) 的全书重哈希（185 章时累计上 GB 读取）。签名含 mtime/size/inode，
# 文件真变了才重算，判定语义不变。
_FILE_HASH_CACHE: dict[str, tuple[tuple[int, int, int], str]] = {}
_FILE_HASH_CACHE_MAX = 1024


def file_sig(path: str) -> tuple[int, int] | None:
    """(mtime_ns, size)，文件不存在或不可读时 None。"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def dir_sigs(path: str) -> dict[str, tuple[int, int, int]] | None:
    """一次 scandir 取整个目录下普通文件的 (mtime_ns, size, inode)。

    目录不存在时返回 ``None``。存在的理由是可复用的性能护栏：逐章
    ``os.stat`` 会让"这本译了几章"在 30 本书上变成 1.8 万次系统调用
    （实测首页 320ms 里的 92%）；scandir 一次拿回目录项，Windows 上
    mtime/size 直接来自目录列表，Linux 上最多每文件一次 fstatat，
    而且**不必为不存在的文件发失败 stat**（未译章是常态）。

    签名必须带 inode：exFAT / sdcardfs 的 mtime 只有 2 秒粒度，而用
    ``save_text`` / ``save_json``（先写临时文件再 ``os.replace``）落盘的内容
    大小也可能不变（引号对齐、错字修正）。此时 (mtime, size) 与旧版本完全
    相同，跨进程（命令行维护脚本 → 服务进程）就会命中旧缓存。原子替换一定
    换 inode，所以 inode 能可靠地把这种"同签名不同内容"区分开；不提供
    inode 的文件系统返回 0，此时行为与只有 (mtime, size) 相同（写端显式
    失效仍是兜底）。
    """
    try:
        it = os.scandir(path)
    except OSError:
        return None
    out: dict[str, tuple[int, int, int]] = {}
    with it:
        for e in it:
            try:
                if not e.is_file(follow_symlinks=False):
                    continue
                st = e.stat()
                # Windows 上 DirEntry.stat() 不填 st_ino（恒 0），但 DirEntry
                # 自带 inode() 能从目录项直接取到文件索引，且不额外 stat。
                ino = e.inode()
            except OSError:
                continue
            out[e.name] = (st.st_mtime_ns, st.st_size,
                           ino or getattr(st, "st_ino", 0))
    return out


def invalidate_file_hash(path: str | None = None) -> None:
    """Drop cached digests after this process writes a file.

    mtime granularity is not a correctness guarantee: exFAT / sdcardfs report
    two-second mtimes, so a freshly rewritten chapter can carry the *same*
    signature as the version we hashed a moment ago.  Writers therefore
    invalidate explicitly instead of hoping ``os.stat`` moved.
    """
    if path is None:
        _FILE_HASH_CACHE.clear()
    else:
        _FILE_HASH_CACHE.pop(os.path.abspath(path), None)


def file_sha256(path: str) -> str:
    key = os.path.abspath(path)
    try:
        st = os.stat(path)
    except OSError:
        _FILE_HASH_CACHE.pop(key, None)
        raise
    sig = (st.st_mtime_ns, st.st_size, getattr(st, "st_ino", 0))
    hit = _FILE_HASH_CACHE.get(key)
    if hit is not None and hit[0] == sig:
        return hit[1]
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    digest = h.hexdigest()
    if len(_FILE_HASH_CACHE) >= _FILE_HASH_CACHE_MAX:
        _FILE_HASH_CACHE.clear()
    _FILE_HASH_CACHE[key] = (sig, digest)
    return digest


def translation_paths_state(zh_path: str, raw_path: str,
                            sidecar_path: str) -> str:
    """Return ``missing|invalid|legacy|complete|partial`` for one chapter."""
    if not os.path.exists(zh_path) or os.path.getsize(zh_path) <= 0:
        return "missing"
    if not os.path.exists(sidecar_path):
        return "legacy"                # v4 content predates sidecars
    try:
        meta = load_record(sidecar_path, "chapter_meta")
        raw_sha = file_sha256(raw_path)
        content_sha = file_sha256(zh_path)
    except (ContractError, OSError):
        return "invalid"
    if not content_available(
        meta, translation_exists=True,
        current_source_sha256=raw_sha,
        current_content_sha256=content_sha,
    ):
        return "invalid"
    return "complete" if meta["status"] == "complete" else "partial"


def translation_paths_available(zh_path: str, raw_path: str,
                                sidecar_path: str) -> bool:
    """Validate a chapter using explicit paths, independent of data-root globals."""
    return translation_paths_state(
        zh_path, raw_path, sidecar_path) in (
            "legacy", "complete", "partial")


def translation_paths_complete(zh_path: str, raw_path: str,
                               sidecar_path: str) -> bool:
    """Whether the chapter has no known incomplete paragraphs."""
    return translation_paths_state(
        zh_path, raw_path, sidecar_path) in ("legacy", "complete")

