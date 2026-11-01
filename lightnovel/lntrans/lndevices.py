#!/usr/bin/env python3
"""长期设备凭据：「记住这台电脑」，重启服务后不用再输口令。

为什么需要单独一层：浏览器登录拿到的会话只存在进程内存里，服务一重启就
清空 —— 用户每次重启、每次换浏览器标签都要重新输一遍局域网口令。
记忆设备发的是**独立随机值**（不是主口令），服务端只存 SHA-256；
凭据文件在数据根里（`data/devices.json`），所以重启后照样认这台设备。

安全边界：
  * Cookie 里永远不是主口令；文件里也没有明文（只有 sha256）；
  * 可撤销：设置页「退出本设备」删掉当前这条，删文件 = 全部忘掉；
  * 有有效期（默认 180 天，可按天配置），每次使用自动续期，长期不用才失效；
  * 损坏的文件不静默删除：先另存 `.bak-<时间戳>` 再重来，并打日志。
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

DEFAULT_TTL = 180 * 24 * 3600
MAX_DEVICES = 32
SCHEMA = 1

_LOCK = threading.RLock()
_CACHE: dict[str, list[dict]] = {}
_LOADED: dict[str, bool] = {}


def _digest(secret: str) -> str:
    return hashlib.sha256((secret or "").encode("utf-8")).hexdigest()


def _clean_label(label: str) -> str:
    """浏览器 UA 只用来在界面上认设备，别把整串 header 存进去。"""
    text = "".join(ch for ch in (label or "") if ch.isprintable())
    return text.strip()[:80]


def _entry_id(digest: str) -> str:
    return digest[:12]


def _read(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        # 损坏：别删用户文件，先备份再当空表（新登录会重建）。
        try:
            os.replace(path, f"{path}.bak-{int(time.time())}")
        except OSError:
            pass
        print(f"[devices] {path} 损坏，已另存备份并重建", flush=True)
        return []
    raw = obj.get("devices") if isinstance(obj, dict) else None
    if not isinstance(raw, list):
        return []
    now = time.time()
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        digest = item.get("digest")
        expires = item.get("expires")
        if not isinstance(digest, str) or len(digest) != 64:
            continue
        if not isinstance(expires, (int, float)) or expires <= now:
            continue
        out.append({
            "id": _entry_id(digest),
            "digest": digest,
            "label": _clean_label(str(item.get("label") or "")),
            "created": float(item.get("created") or now),
            "last_seen": float(item.get("last_seen") or now),
            "expires": float(expires),
        })
    return out


def _write(path: str, devices: list[dict]) -> None:
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}-{secrets.token_hex(4)}"
    doc = {"version": SCHEMA, "devices": devices}
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    try:
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def _devices(path: str) -> list[dict]:
    with _LOCK:
        if not _LOADED.get(path):
            _CACHE[path] = _read(path)
            _LOADED[path] = True
        return _CACHE[path]


def reset_cache() -> None:
    """测试用：丢掉内存缓存，强制下次从磁盘读（模拟进程重启）。"""
    with _LOCK:
        _CACHE.clear()
        _LOADED.clear()


def issue(path: str, label: str = "", ttl: float = DEFAULT_TTL,
          now: float | None = None) -> tuple[str, dict]:
    """登录成功后调用：返回 (cookie 里要放的随机值, 记录)。"""
    now = time.time() if now is None else now
    secret = secrets.token_urlsafe(32)
    digest = _digest(secret)
    entry = {
        "id": _entry_id(digest),
        "digest": digest,
        "label": _clean_label(label),
        "created": now,
        "last_seen": now,
        "expires": now + max(60.0, float(ttl)),
    }
    with _LOCK:
        devices = _devices(path)
        devices.append(entry)
        if len(devices) > MAX_DEVICES:
            # 刚发的这条不能被自己挤掉：淘汰时排除它，再按最久没用排序。
            others = [d for d in devices if d is not entry]
            others.sort(key=lambda d: d.get("last_seen") or 0)
            devices = others[len(others) - (MAX_DEVICES - 1):] + [entry]
        _CACHE[path] = devices
        _LOADED[path] = True
        _write(path, devices)
    return secret, dict(entry)


def verify(path: str, secret: str, ttl: float = DEFAULT_TTL,
           now: float | None = None) -> dict | None:
    """凭据有效就返回记录；顺手更新 last_seen，快过期时自动续期。"""
    if not secret or not isinstance(secret, str):
        return None
    now = time.time() if now is None else now
    digest = _digest(secret)
    with _LOCK:
        devices = _devices(path)
        hit = None
        for entry in devices:
            if hmac.compare_digest(entry["digest"], digest):
                hit = entry
                break
        if hit is None or hit["expires"] <= now:
            if hit is not None:
                devices.remove(hit)
                _write(path, devices)
            return None
        changed = False
        if now - hit["last_seen"] > 3600:
            hit["last_seen"] = now
            changed = True
        half = max(3600.0, float(ttl)) / 2
        if hit["expires"] - now < half:
            hit["expires"] = now + max(3600.0, float(ttl))
            changed = True
        if changed:
            _write(path, devices)
        return dict(hit)


def revoke(path: str, secret: str) -> bool:
    if not secret or not isinstance(secret, str):
        return False
    digest = _digest(secret)
    with _LOCK:
        devices = _devices(path)
        keep = [d for d in devices if not hmac.compare_digest(d["digest"], digest)]
        if len(keep) == len(devices):
            return False
        _CACHE[path] = keep
        _write(path, keep)
        return True


def revoke_all(path: str) -> int:
    with _LOCK:
        devices = _devices(path)
        count = len(devices)
        _CACHE[path] = []
        _write(path, [])
        return count


def describe(path: str) -> list[dict]:
    """给设置页看的公开字段（不含 digest/secret）。"""
    with _LOCK:
        devices = _devices(path)
        return [{"id": d["id"], "label": d["label"], "created": d["created"],
                 "last_seen": d["last_seen"], "expires": d["expires"]}
                for d in sorted(devices, key=lambda d: d.get("last_seen") or 0,
                                reverse=True)]
