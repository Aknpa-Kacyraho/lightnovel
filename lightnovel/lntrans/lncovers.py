#!/usr/bin/env python3
"""lncovers —— 封面：从源站抓 og:image、落盘、给页面与 EPUB 用。

为什么值得做：没有封面的书在书架里长得一模一样 —— 一屏十本卡片，全是纯文字，
读者只能逐个读标题。封面是"一眼认出是哪本"的东西，也是 EPUB 的门面。

三条设计约束（都是踩过的坑推出来的）：

1. **页面渲染绝不联网**。渲染路径只读本地文件：有就 <img>，没有就占位块。
   抓取进后台单线程队列（限速），下次打开就有 —— 打开页面等 3 秒 = "卡死"，
   这条在 `check_on_open_bounded` 上已经付过一次学费。
2. **自检里绝不抓图**。`LNTRANS_TEST_SERVER` / `LNTRANS_NO_NET` 一置位就整条关闭，
   否则自检会打源站（慢、且等于拿用户的钱包做测试）。
3. **文件名只认相对 key**：`data/covers/<source>-<source_id>.<ext>`。
   带 slug 的话换机器/换数据根就找不回来了（slug 是标题生成的，会撞车、会变）。
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lnfinder"))
import lndata  # noqa: E402

LAYOUT = lndata.resolve_layout()
lndata.apply_environment(LAYOUT)
DATA = os.path.join(LAYOUT.data_root, "data")
COVERS = os.path.join(DATA, "covers")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# 只收这三种：EPUB 阅读器普遍认 JPEG/PNG，WebP 只有一部分认（EPUB 里会跳过）。
EXTS = ("jpg", "png", "webp")
MAGIC = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
}
MYTYPE = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}

MIN_BYTES = 2_000          # 太小 = 占位图/错误页
MAX_BYTES = 3_000_000      # 太大 = 不是封面（原尺寸插画）

_enabled = not (os.environ.get("LNTRANS_TEST_SERVER")
                or os.environ.get("LNTRANS_NO_NET"))
_lock = threading.Lock()
_pending: set[str] = set()
_queue: list[tuple[str, str]] = []
_worker: threading.Thread | None = None


def key_for(source: str, source_id: str) -> str:
    """data/covers 下的文件名主干。只保留 ASCII 安全字符。"""
    raw = f"{source or 'kakuyomu'}-{source_id or ''}"
    return re.sub(r"[^A-Za-z0-9._-]", "_", raw)[:120]


def path_of(key: str) -> str | None:
    for ext in EXTS:
        p = os.path.join(COVERS, f"{key}.{ext}")
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None


def url_of(key: str) -> str:
    """给 HTML 用的地址（没有封面时也返回，前端 onerror 自己藏）。"""
    return f"/cover/{key}"


def _ext_of(data: bytes) -> str | None:
    for magic, ext in MAGIC.items():
        if data.startswith(magic):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _save(key: str, data: bytes) -> str | None:
    ext = _ext_of(data)
    if not ext:
        return None
    os.makedirs(COVERS, exist_ok=True)
    dst = os.path.join(COVERS, f"{key}.{ext}")
    tmp = dst + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dst)
    return dst


def og_image(page_url: str, timeout: int = 20) -> str | None:
    """从作品页抓 og:image。两种属性顺序都要认（有的站是 content 在前）。"""
    try:
        import lnlib
        hdr = None
        sy = lnlib.syosetu_source(page_url) if hasattr(lnlib, "syosetu_source") else None
        if sy:
            hdr = lnlib.syosetu_headers(sy[0] == "novel18")
        html = lnlib.fetch(page_url, headers=hdr, timeout=timeout)
    except Exception:
        return None
    pats = (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
    )
    for pat in pats:
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    return None


_PRIVATE_HOST = re.compile(
    r"^(?:localhost|localhost\.localdomain|0\.|127\.|10\.|192\.168\.|169\.254\.|"
    r"172\.(?:1[6-9]|2\d|3[01])\.)")


def _looks_private(host: str) -> bool:
    """目标是不是本机/内网。只做字面判断（不为了判域名去解析 DNS）。"""
    h = host.strip("[]").lower()
    return h == "::1" or bool(_PRIVATE_HOST.match(h))


def safe_img_url(page_url: str, img_url: str) -> str | None:
    """把 og:image 补成绝对 URL；只放行 http/https，且不指向本机/内网。

    `og:image` 可能是相对路径（`/img/a.jpg`），先按 page_url 补全再判 ——
    直接判 scheme 会把相对路径也一起拒掉。`file://` / `data:` / 空主机名一律
    拒绝：那些是"构造一个 og:image 就能读本地文件"的口子。不限制与 page_url
    同 host，因为源站封面常放在 CDN 上；但本机/内网地址不放行（防 SSRF）。
    """
    if not img_url:
        return None
    try:
        full = urllib.parse.urljoin(page_url or "", img_url.strip())
        parts = urllib.parse.urlsplit(full)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    if not parts.hostname or _looks_private(parts.hostname):
        return None
    return full


def fetch_one(source: str, source_id: str, page_url: str,
              timeout: int = 25) -> bool:
    """抓一本的封面。已有就跳过；任何失败都只是"这次没有"，不抛。"""
    key = key_for(source, source_id)
    if path_of(key):
        return True
    img_url = og_image(page_url, timeout=timeout)
    if not img_url:
        return False
    img_url = safe_img_url(page_url, img_url)
    if not img_url:
        return False
    req = urllib.request.Request(img_url, headers={
        "User-Agent": UA,
        "Referer": page_url,
        "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(MAX_BYTES + 1)
    except Exception:
        return False
    if not (MIN_BYTES <= len(data) <= MAX_BYTES):
        return False
    return _save(key, data) is not None


def _worker_loop() -> None:
    while True:
        with _lock:
            if not _queue:
                _pending.clear()
                _worker_local = True
            else:
                item = _queue.pop(0)
                _worker_local = False
        if _worker_local:
            return
        source, source_id, page_url = item
        try:
            fetch_one(source, source_id, page_url)
        except Exception:
            pass
        time.sleep(0.8)          # 限速：别把源站 CDN 打崩，也别被当成爬虫


def ensure_async(source: str, source_id: str, page_url: str) -> None:
    """把一本排进后台队列（幂等）。页面渲染路径只调这个，绝不在这里联网。"""
    global _worker
    if not _enabled or not source_id or not page_url:
        return
    key = key_for(source, source_id)
    if path_of(key):
        return
    with _lock:
        if key in _pending:
            return
        _pending.add(key)
        _queue.append((source, source_id, page_url))
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_worker_loop, name="covers",
                                       daemon=True)
            _worker.start()


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="封面：抓取 / 查看本地有哪些")
    ap.add_argument("--all-shelf", action="store_true", help="给书架里每本书抓封面")
    ap.add_argument("--slug", default="", help="只抓某一本（目录名）")
    ap.add_argument("--list", action="store_true", help="列出已落盘的封面")
    a = ap.parse_args()
    if a.list:
        if not os.path.isdir(COVERS):
            print("还没有封面。")
            return 0
        for f in sorted(os.listdir(COVERS)):
            print(f, os.path.getsize(os.path.join(COVERS, f)))
        return 0
    import json
    import glob
    metas = []
    for p in sorted(glob.glob(os.path.join(DATA, "..", "novels", "*", "meta.json"))):
        m = json.load(open(p, encoding="utf-8"))
        if a.slug and os.path.basename(os.path.dirname(p)) != a.slug:
            continue
        metas.append(m)
    if not metas:
        print("没有找到作品。")
        return 1
    ok = 0
    for m in metas:
        sid = str(m.get("source_id") or "")
        url = m.get("url") or ""
        print(f"  {m.get('title') or sid} …", end="", flush=True)
        if fetch_one(str(m.get("source") or "kakuyomu"), sid, url):
            ok += 1
            print(" ok")
        else:
            print(" 跳过（没抓到 og:image）")
    print(f"完成：{ok}/{len(metas)} 本有封面 → {COVERS}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
