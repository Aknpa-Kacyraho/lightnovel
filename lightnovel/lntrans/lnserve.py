#!/usr/bin/env python3
"""lnserve —— 轻小说「点开就读、读到哪翻到哪」的本地服务。

设计要点（为什么这样拆）：

* 你在浏览器里的**阅读进度是服务端知道的**（前端上报），
  所以只翻你正在看的那几章，不预翻整本。
* 翻译在**后台线程**跑，前端轮询 /api/job 看进度，
  读到章末自动续译下一章——不用你点任何按钮。
* 收藏和反馈落到 `data/user.json`，反馈带章节号与时间，
  下一次对话我可以直接读它来调整画像/术语表。
* 单进程 ThreadingHTTPServer + 一个翻译 worker，无外部依赖。

启动：python3 lnserve.py --port 8099
"""

from __future__ import annotations

import argparse
import atexit
try:  # Linux/Android 用它读网卡地址；Windows 没有 fcntl，退回到 socket 查询
    import fcntl
except ImportError:  # pragma: no cover - 只在非 POSIX 平台走到
    fcntl = None
import faulthandler
import hashlib
import html
import hmac
import importlib.util
import json
import math
import os
import queue
import re
import secrets
import signal
import socket
import struct
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lndata  # noqa: E402
import lncontracts  # noqa: E402
import lnjobs as jobstore  # noqa: E402
import lnmodels  # noqa: E402
import lncatalog  # noqa: E402
import lnimport  # noqa: E402
import lndevices as devstore  # noqa: E402
import lnui  # noqa: E402

# LNTRANS_HOME 是 v5 的单一数据根；未设置时仍兼容 v4 的
# LNTRANS_DATA_ROOT / 代码目录布局。先解析，再让 importlib 加载的模块
# 从同一组环境变量读取，避免不同模块各自算出不同数据根。
LAYOUT = lndata.resolve_layout()
lndata.apply_environment(LAYOUT)
_ROOT = LAYOUT.data_root
NOVELS = os.path.join(_ROOT, "novels")
DATA = os.path.join(_ROOT, "data")

# 前端脚本放在真实文件 `static/*.js`（曾经是内嵌在 Python 三引号字符串里的大段 JS）。
# 搬到文件里，编辑器/语法高亮/node --check 才能直接作用其上 —— 改错一个引号不会再
# 把整个 Python 模块搞崩。页面仍是把它们**内联**注入 <script>（读进来直接用），
# 所以渲染结果与旧版逐字节一致，前端两层自检（test_ui / test_detail / test_click）无需改。
_STATIC = os.path.join(HERE, "static")


def _read_static(name: str) -> str:
    with open(os.path.join(_STATIC, name), encoding="utf-8", newline="") as f:
        return f.read()


def _js_json(value) -> str:
    """内联进 <script> 的 JSON：额外挡掉 `</script>` 提前闭合。"""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _header_items(headers):
    """响应头可以是 dict，也可以是 [(key, value), ...]。

    后者是必需的：登录成功要同时种会话和设备两个 Cookie，而 HTTP 的
    Set-Cookie 不能合并成一行（合并只有第一个生效）。
    """
    if not headers:
        return ()
    return headers.items() if hasattr(headers, "items") else headers


# 绑定的 host（main 里设置）。页面要在"局域网模式"下显示平板该用哪个地址，
# 所以得让渲染层知道 —— 只在回环上就完全不显示，不给用户看没用的东西。
BIND_HOST = "127.0.0.1"

# 局域网访问口令（main 里设置）。绑**非回环**地址、显式配置了外部 Host
# 白名单，或传了 --require-auth 时必须鉴权：
# 同一 Wi-Fi/热点下任何人都能读书架、写状态、甚至触发翻译（那是真花钱）。
# 回环免登录**只对本机浏览器成立**：peer 是回环、Host 也是回环、且没有代理头。
# 反代/隧道部署时 peer 同样是 127.0.0.1，不能再拿 peer 单独当“自己人”。
# 口令来源：环境变量 LNTRANS_TOKEN 或 LNTRANS_TOKEN_FILE；都没有时每次启动
# 随机生成并打到终端。浏览器登录后拿到的是随机会话，不把主口令存进 Cookie。
AUTH_REQUIRED = False
AUTH_LOCAL_BYPASS = True
AUTH_TOKEN = ""
AUTH_COOKIE = "ln_session"
AUTH_SESSION_TTL = 7 * 24 * 3600
AUTH_SESSION_MAX = 128

# 「记住这台电脑」：登录成功后另发一个长期随机凭据（不是主口令），
# 存进数据根，所以服务重启后也不用再输口令。
AUTH_DEVICE_COOKIE = "ln_device"
AUTH_DEVICE_FILENAME = "devices.json"


def _device_days() -> int:
    try:
        days = int(os.environ.get("LNTRANS_DEVICE_DAYS") or 180)
    except ValueError:
        days = 180
    return max(1, min(3650, days))


AUTH_DEVICE_TTL = _device_days() * 24 * 3600


def device_store_path() -> str:
    return os.path.join(DATA, AUTH_DEVICE_FILENAME)

_SESSION_LOCK = threading.Lock()
_SESSIONS: dict[str, float] = {}


def _positive_env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


LOGIN_FAIL_LIMIT = _positive_env_int("LNTRANS_LOGIN_LIMIT", 5)
LOGIN_FAIL_WINDOW = _positive_env_int("LNTRANS_LOGIN_WINDOW", 600, minimum=60)
TRANSLATE_RATE_LIMIT = _positive_env_int("LNTRANS_TRANSLATE_LIMIT", 12)
TRANSLATE_RATE_WINDOW = _positive_env_int("LNTRANS_TRANSLATE_WINDOW", 300, minimum=10)
_RATE_LOCK = threading.Lock()
_RATE_EVENTS: dict[tuple[str, str], list[float]] = {}
_HOST_NAMES_LOCK = threading.Lock()
_HOST_NAMES_CACHE: tuple[float, set[str]] = (0.0, set())
REQUEST_BODY_LIMIT = 2 * 1024 * 1024
IMPORT_BODY_LIMIT = 32 * 1024 * 1024     # EPUB 常有插图，别卡在 2MB


def _peer_is_loopback(peer: str) -> bool:
    """回环地址（手机自己）免鉴权 —— --lan 绑 0.0.0.0 时本地浏览不受影响。"""
    p = (peer or "").strip()
    return p in ("127.0.0.1", "localhost", "::1") or p.startswith("127.")


def _token_ok(presented, expected: str) -> bool:
    """常数时间比较，避免按字符逐位试出口令。expected 为空 = 不需要口令。"""
    if not expected:
        return True
    if presented is None:
        return False
    return hmac.compare_digest(str(presented), str(expected))


def auth_verdict(peer, required: bool, expected: str, presented, host: str = "",
                 *, forwarded: bool = False, allow_local: bool = True) -> bool:
    """纯判据：这一请求能不能放行。Handler 与自检共用同一份逻辑，避免两处漂移。

    回环免登录必须同时满足：peer 回环、Host 回环、请求没有代理头。
    反代通常保留原 Host，但 peer 会是 127.0.0.1；只看 peer 就会把外部访问
    当成“本机”，所以 Host 与代理头必须一起参与判断。
    """
    if not required:
        return True
    if allow_local and allow_without_auth(peer, host, forwarded):
        return True
    return _token_ok(presented, expected)


def _norm_hostname(value: str) -> str:
    return (value or "").strip().lower().rstrip(".")


def _host_parts(value: str) -> tuple[str, int | None]:
    raw = (value or "").strip()
    if not raw:
        return "", None
    try:
        parsed = (urllib.parse.urlsplit(raw) if "://" in raw
                  else urllib.parse.urlsplit("//" + raw))
        return _norm_hostname(parsed.hostname or ""), parsed.port
    except ValueError:
        return "", None


def host_verdict(host: str, allowed: set[str]) -> bool:
    hostname, _ = _host_parts(host)
    if not hostname:
        return False
    if hostname.startswith("127."):
        return True
    return hostname in {_norm_hostname(x) for x in allowed if x}


def host_is_loopback(host: str) -> bool:
    """Host 头是否是“本机”名字（不含代理转发来的外部域名）。"""
    hostname, _ = _host_parts(host)
    return hostname in ("localhost", "::1") or hostname.startswith("127.")


def has_proxy_headers(headers) -> bool:
    """标准反代头一旦出现，就不再把回环 peer 当成本机浏览器。"""
    for key in ("X-Forwarded-For", "X-Forwarded-Host", "X-Real-IP", "Forwarded"):
        if (headers.get(key) or "").strip():
            return True
    return False


def allow_without_auth(peer: str, host: str, forwarded: bool = False) -> bool:
    return (not forwarded and _peer_is_loopback(peer)
            and host_is_loopback(host))


def explicit_allowed_hosts() -> set[str]:
    """只返回用户显式写进 LNTRANS_ALLOWED_HOSTS 的名字。

    自动探测的网卡 IP / 主机名不算“对外形态”，否则本机回环启动也会被
    误判成需要口令。
    """
    out: set[str] = set()
    for item in (os.environ.get("LNTRANS_ALLOWED_HOSTS") or "").split(","):
        name = _host_parts(item)[0] or _norm_hostname(item)
        if name:
            out.add(name)
    return out


def auth_required_for(bind_host: str, explicit_allowed: set[str] | None = None,
                      *, force: bool = False) -> bool:
    """绑定地址 / 显式外部 Host / --require-auth 任一成立即需口令。"""
    if force:
        return True
    if not _peer_is_loopback(bind_host) and _norm_hostname(bind_host) != "localhost":
        return True
    return any(not host_is_loopback(x) for x in (explicit_allowed or set()))


def same_origin(origin: str, host: str) -> bool:
    if not origin or origin == "null":
        return False
    try:
        op = urllib.parse.urlsplit(origin)
        origin_host = _norm_hostname(op.hostname or "")
        origin_port = op.port
    except ValueError:
        return False
    hostname, host_port = _host_parts(host)
    return (
        bool(origin_host)
        and origin_host == hostname
        and origin_port == host_port
    )


def origin_verdict(origin: str, host: str, fetch_site: str = "") -> bool:
    if (fetch_site or "").strip().lower() == "cross-site":
        return False
    # Non-browser clients normally omit Origin.  Some Android browsers /
    # privacy proxies send the literal "null" for a same-page form POST even
    # though the Host is ours; the session cookie (SameSite=Lax) and the
    # access token are still the real gates, so accept it.
    if not origin or origin.strip().lower() == "null":
        return True
    return same_origin(origin, host)


def _safe_next(value: str) -> str:
    value = (value or "").strip()
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    if any(ch in value for ch in ("\r", "\n")):
        return "/"
    if urllib.parse.urlsplit(value).path == "/login":
        return "/"
    return value


def load_access_token(env_token: str = "", token_file: str = "") -> tuple[str, str]:
    direct = (env_token or "").strip()
    if direct:
        return direct, "环境变量 LNTRANS_TOKEN"
    raw_path = (token_file or "").strip()
    if not raw_path:
        return "", ""
    path = os.path.abspath(os.path.expanduser(raw_path))
    try:
        with open(path, "rb") as f:
            raw = f.read(4097)
    except OSError as ex:
        raise OSError(f"无法读取 LNTRANS_TOKEN_FILE={path}: {ex}") from ex
    if len(raw) > 4096:
        raise OSError("LNTRANS_TOKEN_FILE 过长（上限 4096 字节）")
    try:
        value = raw.decode("utf-8-sig", "strict").strip()
    except UnicodeDecodeError as ex:
        raise OSError("LNTRANS_TOKEN_FILE 必须是 UTF-8 文本") from ex
    return value, (f"密钥文件 {path}" if value else "")


def _session_digest(session_id: str) -> str:
    return hashlib.sha256((session_id or "").encode("utf-8")).hexdigest()


def issue_session() -> str:
    sid = secrets.token_urlsafe(32)
    now = time.time()
    with _SESSION_LOCK:
        expired = [k for k, until in _SESSIONS.items() if until <= now]
        for k in expired:
            _SESSIONS.pop(k, None)
        while len(_SESSIONS) >= AUTH_SESSION_MAX:
            _SESSIONS.pop(min(_SESSIONS, key=_SESSIONS.get), None)
        _SESSIONS[_session_digest(sid)] = now + AUTH_SESSION_TTL
    return sid


def session_valid(session_id: str) -> bool:
    if not session_id:
        return False
    key = _session_digest(session_id)
    now = time.time()
    with _SESSION_LOCK:
        until = _SESSIONS.get(key)
        if until is None:
            return False
        if until <= now:
            _SESSIONS.pop(key, None)
            return False
        return True


def revoke_session(session_id: str) -> None:
    if not session_id:
        return
    with _SESSION_LOCK:
        _SESSIONS.pop(_session_digest(session_id), None)


def clear_auth_state() -> None:
    """清掉内存里的登录状态（测试用）。设备凭据在磁盘上，不清 —— 那正是重点。"""
    global _HOST_NAMES_CACHE
    with _SESSION_LOCK:
        _SESSIONS.clear()
    with _RATE_LOCK:
        _RATE_EVENTS.clear()
    with _HOST_NAMES_LOCK:
        _HOST_NAMES_CACHE = (0.0, set())
    devstore.reset_cache()


def _rate_retry(scope: str, peer: str, limit: int, window: int) -> int:
    key = (scope, peer or "")
    now = time.monotonic()
    with _RATE_LOCK:
        events = [t for t in _RATE_EVENTS.get(key, []) if now - t < window]
        _RATE_EVENTS[key] = events
        if len(events) < max(1, limit):
            return 0
        return max(1, int(window - (now - events[0])) + 1)


def _rate_hit(scope: str, peer: str, window: int) -> None:
    key = (scope, peer or "")
    now = time.monotonic()
    with _RATE_LOCK:
        events = [t for t in _RATE_EVENTS.get(key, []) if now - t < window]
        events.append(now)
        _RATE_EVENTS[key] = events[-1000:]


def _rate_clear(scope: str, peer: str) -> None:
    with _RATE_LOCK:
        _RATE_EVENTS.pop((scope, peer or ""), None)


def _allowed_host_names() -> set[str]:
    global _HOST_NAMES_CACHE
    now = time.monotonic()
    with _HOST_NAMES_LOCK:
        cached_at, cached = _HOST_NAMES_CACHE
        if cached and now - cached_at < 15:
            return set(cached)
    names = {
        "127.0.0.1", "localhost", "::1",
        _norm_hostname(socket.gethostname()),
        _norm_hostname(socket.gethostname()) + ".local",
    }
    if BIND_HOST not in ("0.0.0.0", "::", ""):
        names.add(_norm_hostname(BIND_HOST))
    for entry in lan_ipv4():
        names.add(_norm_hostname(entry.get("ip") or ""))
    for item in (os.environ.get("LNTRANS_ALLOWED_HOSTS") or "").split(","):
        names.add(_norm_hostname(item))
    names.discard("")
    with _HOST_NAMES_LOCK:
        _HOST_NAMES_CACHE = (now, set(names))
    return names


def _auth_page(next_path: str = "/", error: str = "") -> str:
    nxt = html.escape(_safe_next(next_path), quote=True)
    err = (f'<p class="err">{html.escape(error)}</p>' if error else "")
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>登录轻小说书架</title>
<style>
:root{{color-scheme:light dark}}
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:32em;
margin:8vh auto;padding:0 1.2em;line-height:1.65}}
.card{{border:1px solid #8884;border-radius:16px;padding:1.3em;
background:color-mix(in srgb,Canvas 96%,CanvasText 4%)}}
h1{{font-size:1.45em;margin:.1em 0 .6em}} .hint,.err{{font-size:.92em}}
.err{{color:#c33}} label{{display:block;margin:.8em 0 .35em;font-weight:600}}
input{{font-size:1em;padding:.72em;width:100%;box-sizing:border-box;
border:1px solid #8888;border-radius:10px;background:Canvas;color:CanvasText}}
button{{margin-top:.9em;font-size:1em;padding:.68em 1.25em;border:0;
border-radius:999px;background:#356ae6;color:white;font-weight:650}}
</style></head><body><main class="card"><h1>登录轻小说书架</h1>
<p class="hint">这是私人阅读库。口令只填在这里，不会出现在网址或浏览器历史中。</p>
{err}<form method="post" action="/login"><input type="hidden" name="next" value="{nxt}">
<label for="access-token">访问口令</label>
<input id="access-token" name="token" type="password" autocomplete="current-password"
autofocus required><button type="submit">进入书架</button></form>
<p class="hint">口令在启动服务的终端里。<b>这台电脑会被记住</b>：登录一次之后，重启服务、
关掉浏览器都不用再输；想解除就在书架「设置 → 退出本设备」。</p>
</main></body></html>"""


def lan_ipv4() -> list[dict]:
    """本机所有非回环 IPv4（局域网访问用）。

    不用 `ip`/`ss`/`netstat`：这台设备上要么没有、要么读 /proc/net 被拒。
    用 `socket.if_nameindex()` 拿网卡名 + `SIOCGIFADDR` ioctl 拿地址，
    纯标准库。实测能列出几块网卡（Wi-Fi 与移动数据都会被列出来）。

    Windows 没有 fcntl/SIOCGIFADDR，改用 socket.getaddrinfo 查本机地址：
    能拿到局域网 IPv4，但无法像 Android 那样可靠识别"哪张是热点网卡"，
    所以 `ap` 恒为 False（--lan 的访问口令仍然照常生效）。
    """
    out: list[dict] = []
    if fcntl is None:
        seen: set[str] = set()
        try:
            infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        except OSError:
            infos = []
        for info in infos:
            ip = info[4][0]
            if ip.startswith("127.") or ip in seen:
                continue
            seen.add(ip)
            out.append({"if": "lan", "ip": ip, "ap": False})
        return out

    try:
        names = [n for _, n in socket.if_nameindex()]
    except OSError:
        return out
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for n in names:
            if n == "lo":
                continue
            try:
                raw = fcntl.ioctl(s.fileno(), 0x8915,  # SIOCGIFADDR
                                  struct.pack("256s", n[:15].encode()))
                ip = socket.inet_ntoa(raw[20:24])
            except OSError:
                continue
            if ip.startswith("127."):
                continue
            out.append({"if": n, "ip": ip,
                        # 名字像热点，**或者**实测它上面有热点的 DNS 代理
                        "ap": _looks_like_hotspot(n, ip) or _is_tethering_addr(ip)})
    finally:
        s.close()
    return out


# 最近来过的**外部**设备（ip → 最后访问时间）。回环不算。
# 为什么要有它：`--lan` 模式下面板和手机在同一个局域网里，"平板连上了没"这件事
# 服务端本来完全看不见 —— 用户只能反复试地址。有这张表就能当场回答
# "刚有一台别的设备打开过首页"，也能反过来确认地址到底对不对。
PEERS: dict = {}
PEERS_LOCK = threading.Lock()
PEERS_MAX = 20


def note_peer(addr: str) -> None:
    if not addr or addr.startswith("127.") or addr in ("::1", "localhost"):
        return
    with PEERS_LOCK:
        PEERS[addr] = time.time()
        if len(PEERS) > PEERS_MAX:
            for k, _ in sorted(PEERS.items(), key=lambda kv: kv[1])[:-PEERS_MAX]:
                PEERS.pop(k, None)


def peer_list() -> list:
    """按"最近来过"排序的外部设备。只给 ip 和时间，不存任何请求内容。"""
    with PEERS_LOCK:
        rows = sorted(PEERS.items(), key=lambda kv: -kv[1])
    now = time.time()
    return [{"ip": ip, "ago": round(now - ts, 1),
             "at": time.strftime("%H:%M:%S", time.localtime(ts))}
            for ip, ts in rows]


_TETHER_CACHE: dict = {}


def _is_tethering_addr(ip: str) -> bool:
    """这个地址上是不是跑着热点的 DNS 代理？（= 它是不是热点那张网卡的地址）

    为什么要**实测**而不是看名字：名字猜法（`ap*` / `wlan1` / 地址以 .1 结尾）
    在真机上会**猜错** —— 有的系统里热点网卡既不叫 `ap*` 也不叫 `wlan1`，
    地址也不以 .1 结尾，于是页面把真正的地址排在后面、还不打 ★，
    平板那边就只能靠试。

    判据：**只有热点接口上才会有本地监听的 53 端口**（netd/dnsmasq 给连上来的
    设备提供 DNS）。手机自己连的 Wi-Fi 不会在本地开 53。
    连不上一般会立刻 ConnectionRefused，所以常态下没有额外耗时；结果缓存 15 秒。
    """
    if not ip:
        return False
    hit = _TETHER_CACHE.get(ip)
    now = time.time()
    if hit and now - hit[0] < 15:
        return hit[1]
    ok = False
    s = socket.socket()
    s.settimeout(0.25)
    try:
        s.connect((ip, 53))
        ok = True
    except OSError:
        ok = False
    finally:
        s.close()
    _TETHER_CACHE[ip] = (now, ok)
    return ok


def _looks_like_hotspot(ifname: str, ip: str) -> bool:
    """这像是「手机自己开的热点」那张网卡吗？

    平板连的是手机热点，**只能**走热点那张网卡（通常是 ap0 / wlan1 / swlan0，
    网关形如 192.168.x.1）。手机**自己连的** Wi-Fi 对平板没用，
    不区分的话用户会照着错地址输，怎么都打不开 —— 所以给个 ★ 提示，
    但两个都列出来，免得猜错时无路可走。
    """
    n = ifname.lower()
    if n.startswith(("ap", "softap", "swlan", "wlan1", "rndis", "bt-pan", "eth")):
        return True
    return ip.endswith(".1") and ip.startswith(("192.168.", "10.", "172."))

# ============ 重要 ============
# 下面加载子模块时会把 sys.argv 改成假值（那些模块的 main 也用 argv），
# 结果 main() 里的 argparse 读到的是假 argv —— 表现是**命令行参数全部失效**
# （踩过：`--port 8237` 被忽略，永远绑 8099，导致测试服务起不来）。
# 所以在改动前先把真实 argv 存下来，最后用它解析。
_REAL_ARGV = list(sys.argv)

_spec = importlib.util.spec_from_file_location("lntrans", os.path.join(HERE, "lntrans.py"))
lt = importlib.util.module_from_spec(_spec)
sys.argv = ["lntrans"]
_spec.loader.exec_module(lt)
# lnreview 会在函数里 `import lntrans`。不登记到 sys.modules 的话它会再加载
# 一份模块，两份 _NOVEL_LOCKS 互不相识，校对和翻译可能同时写同一本。
sys.modules.setdefault("lntrans", lt)

_specrev = importlib.util.spec_from_file_location(
    "lnreview", os.path.join(HERE, "lnreview.py"))
rview = importlib.util.module_from_spec(_specrev)
sys.argv = ["lnreview"]
_specrev.loader.exec_module(rview)
sys.modules.setdefault("lnreview", rview)

_specrec = importlib.util.spec_from_file_location("lnrecs", os.path.join(HERE, "lnrecs.py"))
recs = importlib.util.module_from_spec(_specrec)
sys.argv = ["lnrecs"]
_specrec.loader.exec_module(recs)

_spec2 = importlib.util.spec_from_file_location("lnrender", os.path.join(HERE, "lnrender.py"))
lr = importlib.util.module_from_spec(_spec2)
sys.argv = ["lnrender"]
_spec2.loader.exec_module(lr)

# 备份模块：/api/backup 直接把数据下载到手机存储（容器外的第二份）。
_specbk = importlib.util.spec_from_file_location(
    "lnbackup", os.path.join(HERE, "lnbackup.py"))
bk = importlib.util.module_from_spec(_specbk)
sys.argv = ["lnbackup"]
_specbk.loader.exec_module(bk)

# 封面：抓 og:image、落盘到 data/covers/，页面只读本地文件（渲染路径不联网）。
_speccv = importlib.util.spec_from_file_location(
    "lncovers", os.path.join(HERE, "lncovers.py"))
lc = importlib.util.module_from_spec(_speccv)
sys.argv = ["lncovers"]
_speccv.loader.exec_module(lc)

# 翻译调度：决定"下一个翻哪本书的哪一章"（在读持续翻 / 翻译列表 / 预算）。
_specsc = importlib.util.spec_from_file_location(
    "lnsched", os.path.join(HERE, "lnsched.py"))
sched_mod = importlib.util.module_from_spec(_specsc)
sys.argv = ["lnsched"]
_specsc.loader.exec_module(sched_mod)

# EPUB 导出：把已译作品打包成能带走的书（标准库实现，见 lnepub.py 的取舍说明）。
_speceb = importlib.util.spec_from_file_location(
    "lnepub", os.path.join(HERE, "lnepub.py"))
epub = importlib.util.module_from_spec(_speceb)
sys.argv = ["lnepub"]
_speceb.loader.exec_module(epub)

# --- 复用 lnfinder 的取页工具（带缓存、gzip、错站 Referer）--------------
_speclib = importlib.util.spec_from_file_location(
    "lnlib", os.path.join(os.path.dirname(HERE), "lnfinder", "lnlib.py"))
try:
    sys.argv = ["lnlib"]
    lnlib = importlib.util.module_from_spec(_speclib)
    _speclib.loader.exec_module(lnlib)
except Exception:  # noqa: BLE001
    lnlib = None


DETAIL_DIR = os.path.join(DATA, "details")


def detail_path(work_id: str) -> str:
    return os.path.join(DETAIL_DIR, f"{str(work_id).replace('/', '_')}.json")


DETAIL_LOCK = threading.Lock()


def load_detail(work_id: str) -> dict:
    try:
        with open(detail_path(work_id), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_detail(work_id: str, d: dict) -> None:
    try:
        os.makedirs(DETAIL_DIR, exist_ok=True)
        with open(detail_path(work_id), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except OSError:
        pass


def extract_work_page(page: str) -> dict:
    """从 kakuyomu 作品页抽出**简介 + 目录**。

    合格的作品页必须有这两样，否则用户点进去看到"只有标题"是没法判断
    要不要读的（用户报的就是这个）。

    · 简介  ← og:description（kakuyomu 把 あらすじ 放在这里）
    · 目录  ← __NEXT_DATA__ 的 Apollo 缓存：
              Chapter(章) + TableOfContentsChapter(章下的話) + Episode(話)
    """
    out: dict = {"synopsis": "", "toc": []}
    m = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]*)"',
                  page)
    if not m:
        m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', page)
    if m:
        out["synopsis"] = html.unescape(m.group(1)).strip()
    # Kakuyomu 的完整あらすじ在 __NEXT_DATA__ 的 introduction 字段；
    # og:description 往往只有第一句。取更长的那个。
    m_intro = re.search(r'"introduction"\s*:\s*"((?:\\.|[^"\\])*)"', page)
    if m_intro:
        try:
            intro = json.loads('"' + m_intro.group(1) + '"')
        except (ValueError, TypeError):
            intro = ""
        if len(intro or "") > len(out["synopsis"]):
            out["synopsis"] = html.unescape(str(intro)).strip()

    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return out
    try:
        data = json.loads(m.group(1))
        ap = (data.get("props", {}).get("pageProps", {})
              .get("__APOLLO_STATE__") or {})
    except (json.JSONDecodeError, AttributeError):
        return out

    # id -> (标题, 发布时间)
    eps = {}
    for k, v in ap.items():
        if k.startswith("Episode:"):
            eps[k.split(":", 1)[1]] = (v.get("title") or "",
                                       (v.get("publishedAt") or "")[:10])
    # 章标题
    chaps = {}
    for k, v in ap.items():
        if k.startswith("Chapter:"):
            chaps[k.split(":", 1)[1]] = v.get("title") or ""
    # 顺序：TableOfContentsChapter 里 episodeUnions 的顺序就是目录顺序
    toc = []
    for k, v in ap.items():
        if not k.startswith("TableOfContentsChapter:"):
            continue
        ref = (v.get("chapter") or {}).get("__ref") or ""
        cid = ref.split(":", 1)[1] if ":" in ref else ""
        ctitle = chaps.get(cid) or ""
        items = []
        for u in (v.get("episodeUnions") or []):
            eid = (u.get("__ref") or "").split(":", 1)[1] if u else ""
            if not eid or eid not in eps:
                continue
            t, at = eps[eid]
            items.append({"id": eid, "title": t, "at": at})
        if items:
            toc.append({"title": ctitle, "episodes": items})
    if not toc and eps:
        # 没有分章的作品：直接按 Episode 排列
        toc = [{"title": "", "episodes": [
            {"id": i, "title": t, "at": a} for i, (t, a) in eps.items()]}]
    out["toc"] = toc
    out["episode_count"] = len(eps)
    return out


def refresh_detail(work_id: str, url: str, force: bool = False) -> dict:
    """按需抓取作品详情并缓存（打开详情页时才抓，省流量）。"""
    d = load_detail(work_id)
    if (len(str(d.get("synopsis") or "")) >= 80
            and d.get("toc") and not force):
        return d
    if lnlib is None or not url:
        return d
    try:
        if lnlib.syosetu_source(url):
            w = lnlib.syosetu_work(url)
            got = {"synopsis": w["synopsis"], "toc": w["toc"],
                   "episode_count": w["episode_count"]}
        else:
            html = lnlib.fetch(url, headers={"Referer": "https://kakuyomu.jp/"},
                               timeout=25, use_cache=False)
            got = extract_work_page(html)
    except Exception:  # noqa: BLE001
        return d
    if got.get("synopsis"):
        d["synopsis"] = got["synopsis"]
    if got.get("toc"):
        d["toc"] = got["toc"]
    if got.get("episode_count"):
        d["episode_count"] = got["episode_count"]
    d["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_detail(work_id, d)
    return d


def refresh_work_detail(work_id: str, force: bool = False) -> dict:
    """抓取作品简介/目录并返回结果，GET 与 POST `/api/detail` 共用。

    前端详情页「重抓简介/目录」发的是 POST。踩过：这段逻辑一度只挂在
    do_GET 上、还误用了 do_POST 作用域里的 `d` —— 结果 GET 直接 NameError，
    而前端发的 POST 落到兜底分支返回 unknown，按钮显示"抓取中…"却根本没重抓。
    """
    wid = str(work_id or "")
    item = None
    try:
        for cand in recs.cached(include_hidden=True) or []:
            if str(cand.get("id")) == wid:
                item = cand
                break
    except Exception:  # noqa: BLE001
        pass
    if item is None:
        try:
            item = (recs._load_lib() or {}).get(wid)
        except Exception:  # noqa: BLE001
            item = None
    url = (item or {}).get("url") or ""
    # 先清空缓存再抓，确保"重试"真的会重抓
    if force and wid:
        try:
            os.remove(detail_path(wid))
        except OSError:
            pass
    got = refresh_detail(wid, url, force=True) if url else {}
    return {"ok": True, "has_synopsis": bool(got.get("synopsis")),
            "chapters": len(got.get("toc") or [])}


LOCK = threading.RLock()
LIB_VIEW = {"q": "", "want": False, "tags": []}   # 书库的搜索/筛选状态（标签可多选）
PAGE_SIZE = 15                            # 每页卡片数（用户：全放一页怕卡）
SHELF_PAGE_MAX_KEYS = 256
SHELF_PAGE: dict[str, int] = {}
LIB_PAGE = {"n": 1}
JOBS: dict[str, dict] = {}
JOBS_Q: "queue.Queue[tuple[str, int, int, int]]" = queue.Queue()
STOP = threading.Event()
JOBS_READ_ONLY = False
JOBS_RECOVERY_INFO: dict = {
    "ok": True, "read_only": False, "corrupt": [],
    "repair_command": "python lntrans/lnjobs.py quarantine <job-id> --write",
}


def _shelf_key(value) -> str:
    return str(value or "")[:64]


def _shelf_page(key: str) -> int:
    if not key:
        return 1
    with LOCK:
        return int(SHELF_PAGE.get(key) or 1)


def _remember_shelf_page(key: str, page: int) -> None:
    if not key:
        return
    with LOCK:
        if key not in SHELF_PAGE and len(SHELF_PAGE) >= SHELF_PAGE_MAX_KEYS:
            SHELF_PAGE.pop(next(iter(SHELF_PAGE)), None)
        SHELF_PAGE[key] = max(1, int(page))


def _job_recovery_block() -> dict | None:
    """Return a 503 payload only for operations that must write job state."""
    health = jobstore.STORE.health(refresh=True)
    if not health.get("read_only"):
        return None
    return {
        "ok": False,
        "read_only": True,
        "error": "任务日志损坏；翻译任务相关写入已暂停，"
                 "阅读、进度、书架和备份仍可用。修复后重启服务。",
        "corrupt": health.get("corrupt") or [],
        "repair_command": health.get("repair_command"),
    }


# ------------------------------------------------------------------ 状态

def state_path() -> str:
    os.makedirs(DATA, exist_ok=True)
    return os.path.join(DATA, "user.json")


# 每本书的状态目录只建一次。踩过（性能）：`book_state_path()` 原来每次都
# `os.makedirs(exist_ok=True)`，而渲染首页会读同一本书的状态 7 次（trans_cfg /
# auto_ceiling / stale_days / is_dormant / read_tracking…）→ 11 本书 = 82 次
# makedirs + 82 次 stat，光这一项就 0.17s（首页 1.0s 里的大头）。
_BOOKS_DIR_READY = [False]


def _valid_slug(value) -> bool:
    """slug 是目录名：拒绝空、控制字符、路径分隔符与 `..`。

    所有数据路径都由 slug 拼出来（`novels/<slug>`、`data/books/<slug>.json`），
    而 `/read/<slug>`、`/export/<slug>.epub` 直接吃 URL 里的 slug。不校验就能
    用 `..%2F` 逃出数据根：读路径能读到根外的 meta.json/章节，写路径能在
    其它目录落文件。允许非 ASCII（历史目录名可能含中文），只掐掉危险形态。
    """
    v = str(value or "")
    # 只拒绝「整段就是 . 或 ..」和路径分隔符；`a..b` 这类子串是合法的
    # 目录名（源站标题可能长这样），拒绝它属于误伤 —— 没有分隔符时 `..`
    # 只是普通字符，无法逃出数据根。
    if not v or len(v) > 140 or v in (".", ".."):
        return False
    if any(c in v for c in ("/", "\\", "\x00")):
        return False
    if any(ord(c) < 32 for c in v):
        return False
    return not os.path.isabs(v)


def book_state_path(slug: str) -> str:
    if not _valid_slug(slug):
        raise ValueError("非法 slug")
    d = os.path.join(DATA, "books")
    if not _BOOKS_DIR_READY[0]:
        os.makedirs(d, exist_ok=True)
        _BOOKS_DIR_READY[0] = True
    return os.path.join(d, f"{slug}.json")


EMPTY = {"progress": {}, "favorites": {}, "feedback": [], "opened": {}}


def _migrate_global() -> dict:
    """旧版把所有书塞在 data/user.json 里；这里拆成每书一个文件。

    书多了之后单文件有三个问题：每读一章就整体重写、写坏一本书的进度
    不影响别人、文件无限增长。迁移是幂等的。
    """
    p = state_path()
    if not os.path.exists(p):
        return EMPTY
    try:
        old = json.load(open(p, encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return EMPTY
    touched = False
    for slug, pr in (old.get("progress") or {}).items():
        bs = _read_book(slug)
        if not bs.get("progress"):
            bs["progress"] = pr
            _write_book(slug, bs)
            touched = True
    for slug, at in (old.get("favorites") or {}).items():
        bs = _read_book(slug)
        if not bs.get("favorites"):
            bs["favorites"] = at
            _write_book(slug, bs)
            touched = True
    for fb in (old.get("feedback") or []):
        slug = fb.get("slug") or "_unknown"
        bs = _read_book(slug)
        bs.setdefault("feedback", []).append(fb)
        _write_book(slug, bs)
        touched = True
    if touched:
        os.rename(p, p + ".migrated")
    return EMPTY


# 状态文件读缓存：key=slug，值=(mtime_ns, size, dict)。
# 首页一棵书架要问 N 次"这本的状态"（trans_cfg / auto_ceiling / read_tracking…），
# 缓存前同一本要 open+json.load 七遍。写路径（_write_book / update_book）都是
# tmp+replace，mtime 必然变 → 缓存自动失效，不需要手工清。
# 返回的是 **deepcopy**：调用方会就地改这份 dict 再写回，共享对象会互相污染。
_BOOK_CACHE: dict[str, tuple[int, int, dict]] = {}


def _read_book(slug: str) -> dict:
    import copy
    try:
        p = book_state_path(slug)
    except ValueError:
        return {"progress": {}, "favorites": {}, "feedback": [], "opened": {}}
    try:
        st = os.stat(p)
    except OSError:
        return {"progress": {}, "favorites": {}, "feedback": [], "opened": {}}
    hit = _BOOK_CACHE.get(slug)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return copy.deepcopy(hit[2])
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"progress": {}, "favorites": {}, "feedback": [], "opened": {}}
    for k, v in (("progress", {}), ("favorites", {}), ("feedback", []), ("opened", {})):
        d.setdefault(k, v)
    _BOOK_CACHE[slug] = (st.st_mtime_ns, st.st_size, d)
    return copy.deepcopy(d)


def _write_book(slug: str, d: dict) -> None:
    _BOOK_CACHE.pop(slug, None)
    try:
        p = book_state_path(slug)
    except ValueError:
        return
    # 统一走 lndata 的原子写（fsync + 唯一临时名 + 目录 fsync）：
    # 书架状态是用户唯一的进度/收藏来源，掉电时不能出现半截 JSON。
    with LOCK:
        lndata.atomic_write_json(p, d)


def save_state(s: dict) -> None:
    """⚠ 仅用于兼容旧调用，**不要在请求路径里用**。

    它会把传入的聚合状态整体写回，而聚合状态包含所有书的历史数据，
    用于"追加"语义时会重复写入。新的写入请用
    set_progress / toggle_favorite / append_feedback / set_opened。
    """
    for slug, pr in (s.get("progress") or {}).items():
        d = _read_book(slug)
        d["progress"] = pr
        _write_book(slug, d)
    for slug, at in (s.get("favorites") or {}).items():
        d = _read_book(slug)
        d["favorites"] = at
        _write_book(slug, d)
    seen = set()
    for fb in (s.get("feedback") or []):
        slug = fb.get("slug") or "_unknown"
        key = (slug, fb.get("at"), fb.get("chapter"), fb.get("note"))
        if key in seen:
            continue
        seen.add(key)
        d = _read_book(slug)
        if key not in {(x.get("at"), x.get("chapter"), x.get("note"))
                       for x in d.get("feedback", [])}:
            d.setdefault("feedback", []).append(fb)
            _write_book(slug, d)
    for slug, at in (s.get("opened") or {}).items():
        d = _read_book(slug)
        d["opened"] = at
        _write_book(slug, d)


# 分类语义（按用户的原话定的，别乱改）：
#   favorite —— 用户主动收藏的书堆。**只有它**用于画像学习、也优先查更新。
#   reading  —— 在读。要查更新（书更新了我们得告诉用户），但**不进画像**：
#               用户说"我看的不代表我喜欢，可能只看一点点就放弃了"。
#   finished —— 看完的。单独一堆，不混进"想看的书"里。
#   dropped  —— 明确放弃。不查更新、不进画像。


TRACKING = ("want", "reading", "finished", "dropped")
TRACKING_LABEL = {"want": "想读", "reading": "在读",
                  "finished": "看完", "dropped": "弃文"}


def _tracking_of(d: dict) -> str | None:
    t = d.get("tracking")
    if t in TRACKING:
        return t
    if d.get("finished"):
        return "finished"
    if d.get("dropped"):
        return "dropped"
    return None


def read_tracking(slug: str) -> str | None:
    """读 tracking 状态。**不在书架上返回 None**，不再伪造 "want"。

    兼容旧数据（旧版用 finished/dropped 两个独立字段）。

    为什么必须返回 None（用户报的 bug，2026-10-16）：
      以前没有 tracking 时这里返回 "want"，于是**"不在书架"和"想读"变成同一个值**。
      而阅读页有一条规则「打开阅读页 = 开始看 → want 自动转 reading」——
      它只该对**已经在书架上的书**生效，却因为伪造的 "want" 对
      "已经移出书架"的书也生效了：
        用户点「✕ 移出」→ tracking=None → 打开书接着读 → 又被写回 reading →
        书回到书架。用户连点三次「移出」都"没反应"（server.log 有三次 off=True）。
      用户的原话是「我加入书架不等于收藏，因为我不加看不了」——
      他只是在读一本书，不该因此被塞进书架。
    """
    return _tracking_of(_read_book(slug))


def _clear_update_flags(d: dict) -> None:
    """清掉「源站有更新」的标记。

    用在三处：复查确认没有新章、弃文、移出书架 —— 这些情况下
    再亮着「更新了 +N 话 · 点我翻译」都是在骗人。
    """
    for k in ("has_update", "new_episodes", "update_at"):
        d.pop(k, None)


def apply_action(slug: str, action: str, value: bool | None = None) -> dict:
    """所有状态变更的**唯一入口**（转换表见 STATE-MACHINE.md）。

    · drop 会**自动清除收藏**（用户明确要求）
    · favorite 与 tracking 正交，互不影响
    """
    box: dict = {}

    def fn(d):
        def set_tracking(new):
            d["tracking"] = new
            # 兼容旧读法：同步老字段，避免两套数据打架
            d["finished"] = time.strftime("%Y-%m-%d %H:%M:%S") if new == "finished" else None
            d["dropped"] = time.strftime("%Y-%m-%d %H:%M:%S") if new == "dropped" else None

        if action == "favorite":
            new_fav = (not d.get("favorites")) if value is None else bool(value)
            d["favorites"] = time.strftime("%Y-%m-%d %H:%M:%S") if new_fav else None
            box["favorite"] = new_fav
        elif action == "reading":
            set_tracking("reading" if (value is None or value) else "want")
        elif action == "finished":
            set_tracking("finished" if (value is None or value) else "reading")
        elif action == "dropped":
            if value is None or value:
                set_tracking("dropped")
                d["favorites"] = None          # ★ 弃文自动移出收藏
                _clear_update_flags(d)         # 弃文不再查更新，徽标也该消失
                box["cleared_favorite"] = True
            else:
                set_tracking("want")
        elif action == "want":
            set_tracking("want")
        elif action in ("off", "remove", "shelf_off"):
            # 移出书架：**清空状态**，而不是退回 want。
            # 踩过：原来"移除"只是退回 want，而书架按 tracking 分组，
            # 于是书永远留在「想读」里删不掉（用户报的 bug）。
            d["tracking"] = None
            d["finished"] = None
            d["dropped"] = None
            d["favorites"] = None
            _clear_update_flags(d)             # 移出书架后不再查更新
            box["removed"] = True
        box["tracking"] = d.get("tracking")

    update_book(slug, fn)
    box["favorites"] = bool(_read_book(slug).get("favorites"))
    return box


def book_status(slug: str, it: dict | None = None) -> str:
    """一本书归到哪一堆。

    **收藏是独立维度，优先级最高**：用户可以"收藏了并且看完了"，
    这种书必须同时留在收藏堆里（否则收藏夹会随着读完而变空，
    而收藏恰恰是唯一用来学画像的信号）。
    看完/放弃只作为附加标记，不把书从收藏堆抢走。
    """
    d = _read_book(slug)
    if d.get("favorites"):
        return "favorite"
    if d.get("dropped"):
        return "dropped"
    if d.get("finished"):
        return "finished"
    read = d.get("progress") or {}
    if it is None:
        meta = novel_meta(slug) or {}
        total = len(meta.get("episodes") or [])
        have = zh_chapters(slug, total)
        ch = int(read.get("chapter") or 0)
        # 读到最后一章（或已译全部且读到末尾）→ 看完
        if total and ch >= total:
            return "finished"
    else:
        if it.get("total") and it.get("read", 0) >= it["total"]:
            return "finished"
    # 注意：**不能**把"很久没打开"自动判成放弃。
    # 搁置 ≠ 放弃，自动挪走会让用户找不到书，而且会平白停掉更新检查。
    # 只在书架上标一个"搁置 N 天"，去留由用户自己决定。
    return "reading"


def _stale_days_of(d: dict) -> int:
    """距上次阅读多少天（0 表示读过或没记录）。"""
    at = (d.get("progress") or {}).get("at") or ""
    if not at:
        return 0
    try:
        t = time.mktime(time.strptime(at, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return 0
    days = int((time.time() - t) / 86400)
    return days if days > 7 else 0


def stale_days(slug: str) -> int:
    return _stale_days_of(_read_book(slug))


DORMANT_DAYS = 60
AUTO_AHEAD_DEFAULT = 3        # 默认只自动翻到"读到的位置 + 3 章"


def _trans_cfg_of(d: dict) -> dict:
    cfg = d.get("translate") or {}
    return {
        "enabled": bool(cfg.get("enabled")),
        "ahead": int(cfg.get("ahead") or AUTO_AHEAD_DEFAULT),
        "max_chapters": cfg.get("max_chapters"),
    }


def trans_cfg(slug: str) -> dict:
    """这本书的翻译策略。

    用户要求（原话）：
      · 「不要自动翻译没看过的小说」→ 没手动开启就不自动翻
      · 「看过的最多自动翻译到看到的后面第三章」
      · 「除非玩家主动开启这本小说的翻译」「可以选择翻译到多少多少」
    """
    return _trans_cfg_of(_read_book(slug))


def set_trans_cfg(slug: str, **kw) -> dict:
    def fn(d):
        t = d.setdefault("translate", {})
        for k in ("enabled", "ahead", "max_chapters"):
            if k in kw:
                t[k] = kw[k]
    update_book(slug, fn)
    return trans_cfg(slug)


def read_chapter(slug: str) -> int:
    return int((_read_book(slug).get("progress") or {}).get("chapter") or 0)


def _auto_ceiling_of(d: dict, meta: dict) -> int:
    """自动翻译允许翻到的最大章号。

    没开启翻译 → 0（一章都不自动翻）。
    开启了 → min(读到 + ahead, max_chapters, 总章数)。
    """
    cfg = _trans_cfg_of(d)
    if not cfg["enabled"]:
        return 0
    total = len(meta.get("episodes") or [])
    ceiling = int((d.get("progress") or {}).get("chapter") or 0) + max(0, cfg["ahead"])
    if cfg.get("max_chapters"):
        ceiling = min(ceiling, int(cfg["max_chapters"]))
    return max(0, min(ceiling, total))


def auto_ceiling(slug: str, meta: dict) -> int:
    return _auto_ceiling_of(_read_book(slug), meta)


def allowed_targets(slug: str, meta: dict, want: int,
                    after: int | None = None,
                    explicit_ceiling: int | None = None) -> tuple[list[int], int]:
    """按策略算出"允许翻哪几章"，返回 (章号列表, 天花板)。

    这是**唯一**决定"翻什么"的入口：自动续译和手动补译都走它，
    保证策略只有一处、不会两条路径行为不一致。

    `explicit_ceiling`：用户手动点「翻到第 N 章」时传进来，
    用来**突破**"读到 + ahead"的自动上限（那是自动行为的上限，
    用户明确要求的不该被它挡住）。
    """
    total = len(meta.get("episodes") or [])
    ceiling = auto_ceiling(slug, meta)
    if explicit_ceiling is not None:
        # 手动请求：天花板不能低于"已经翻好的章数"（已花钱译出来的内容
        # 不该被自己的策略挡住；踩过：读到 0 章时 ceiling=0，连已译的 20 章
        # 都被判"超限"）。
        # 只有手动请求才需要全书已译数；自动请求在 ceiling<=0 时直接返回，
        # 不必为它扫一遍全部章节（阅读页每轮 tick 都会打这个接口）。
        have_n = len(zh_chapters(slug, total))
        ceiling = max(ceiling, have_n, min(int(explicit_ceiling), total))
    # 自动续译：上限**只看"读到哪"**，绝不因为"已经翻了多少章"往上爬。
    # 踩过（用户报「我还没开始看，怎么就第二话了」那次之后发现的）：
    # 原来是 max(auto, have_n)，而已译章数会随翻译增长 → 上限自己往上跑，
    # 一本从没读过的书在几分钟里被从头翻到尾（23/23），白花用户的钱。
    # 原话：「我没看的你就不要浪费 token」。
    if ceiling <= 0:
        return [], ceiling
    targets = next_targets(slug, meta, want, after)
    return [t for t in targets if t <= ceiling], ceiling


def _dormant_of(d: dict) -> bool:
    if d.get("favorites"):
        return False          # 收藏的书永远不判休眠
    if d.get("finished") or d.get("dropped"):
        return False
    at = (d.get("progress") or {}).get("at") or ""
    if not at:
        return False
    try:
        t = time.mktime(time.strptime(at, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return False
    return (time.time() - t) / 86400 > DORMANT_DAYS


def is_dormant(slug: str) -> bool:
    """久未打开且没收藏 → 休眠。休眠的书不自动查更新，省掉无谓请求。

    取舍：用户说过"我没看的你就不要浪费 token"。但"搁置"长期累积
    会让检查列表无限膨胀，所以划一条线：**收藏的永远查**；
    没收藏的只有在近期读过时才查，一旦再打开就自动恢复。
    """
    return _dormant_of(_read_book(slug))


def should_watch(status: str, slug: str | None = None) -> bool:
    """要不要查更新。

    **收藏永远查**（用户说过：「我看的书就加个收藏」，收藏=他在乎的书），
    即使已经标记看完——完结作品也可能出番外/续篇。
    非收藏：只在读且未休眠时查。
    """
    if status == "favorite":
        return True
    if slug and (_read_book(slug).get("favorites")):
        return True
    if status != "reading":
        return False
    return not (slug and is_dormant(slug))


def should_learn(status: str, slug: str | None = None) -> bool:
    """要不要用这本书学画像：**只有收藏**（看完的收藏照样算，那是真爱）。"""
    if status == "favorite":
        return True
    return bool(slug and _read_book(slug).get("favorites"))


def set_flag(slug: str, flag: str, value: bool) -> dict:
    """设置 finished / dropped / favorites 标记（锁内读改写）。"""
    def fn(d):
        if flag == "favorites":
            d["favorites"] = time.strftime("%Y-%m-%d %H:%M:%S") if value else None
        else:
            d[flag] = time.strftime("%Y-%m-%d %H:%M:%S") if value else None
        # 看完 与 放弃 互斥
        if value and flag in ("finished", "dropped"):
            other = "dropped" if flag == "finished" else "finished"
            d[other] = None

    out = update_book(slug, fn)
    # 「看完 / 弃文」是**停止花钱**的语义，不能只写在书状态里：
    # 调度器还记着"这本书在读"，30 分钟内会继续翻（踩过：14:04 标弃文，
    # 14:25 还在翻 51/54，钱一直花）。这里同时暂停调度并停掉进行中的任务；
    # 之后要恢复就读，显式点「继续翻译」即可（不自动解除，和"停止"一致）。
    if value and flag in ("finished", "dropped"):
        try:
            SCHED.set_paused(slug, True)
        except Exception:  # noqa: BLE001 - 调度状态损坏不影响状态标记
            pass
        try:
            cancel_job(slug, disable=False)
        except Exception:  # noqa: BLE001
            pass
    return out


def update_book(slug: str, fn) -> dict:
    """在锁内做"读-改-写"，避免并发丢更新。

    append_feedback 等函数是 `_read_book` → 改 → `_write_book`，
    中间没有锁：两个请求同时提交反馈会丢一条（最后一个写入者胜）。
    _write_book 内部那把锁只保护"写"本身，保护不了整个读改写序列。
    """
    with LOCK:
        try:
            p = book_state_path(slug)
        except ValueError:
            return {}
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
            except (json.JSONDecodeError, OSError):
                d = {}
        else:
            d = {}
        for k, v in (("progress", {}), ("favorites", None), ("feedback", []),
                     ("opened", None)):
            d.setdefault(k, v)
        fn(d)
        # 与 _write_book 同一套原子写：原地 tmp+replace 没有 fsync，
        # 掉电/强杀可能留下空文件或旧内容，而这正是用户唯一的一份进度。
        lndata.atomic_write_json(p, d)
        _BOOK_CACHE.pop(slug, None)      # 写完立刻失效（别等 mtime 精度）
        return d


HISTORY_PATH = os.path.join(DATA, "history.jsonl")


def set_progress(slug: str, chapter: int, scroll: float | None = None) -> None:
    """记录阅读进度。

    `scroll`（章节内百分比 0~1）来自 Kavita 的 `BookScrollId` 思路：
    只记"读到第几章"的话，一章几千字，回来只能从章首重读。
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    prev = (_read_book(slug).get("progress") or {})

    def fn(d):
        p = {"chapter": int(chapter), "at": ts}
        # 双轨进度，学自 LightNovelReader 的
        # currentChapterReadingProgressMap / maxChapterReadingProgressMap：
        #   scroll     —— 你**实际停在哪**（下次从这里继续）
        #   max_scroll —— 你在本章**读到过的最远位置**（用于算整体进度）
        # 只存一个"最大值"是错的：往回翻一点再退出，下次会被送到最远处，
        # 而不是你真正停下的地方。
        same_ch = prev.get("chapter") == int(chapter)
        if scroll is not None:
            cur = max(0.0, min(1.0, float(scroll)))
            p["scroll"] = cur
            old_max = float(prev.get("max_scroll") or 0) if same_ch else 0.0
            p["max_scroll"] = round(max(cur, old_max), 3)
        elif same_ch:
            if prev.get("scroll") is not None:
                p["scroll"] = prev["scroll"]
            if prev.get("max_scroll") is not None:
                p["max_scroll"] = prev["max_scroll"]
        d["progress"] = p

    update_book(slug, fn)
    log_history(slug, chapter, scroll)


def log_history(slug: str, chapter: int, scroll: float | None = None) -> None:
    """追加一条阅读历史（学自 Kavita 的 AppUserReadingSession）。

    只追加不修改，用于算"连续阅读天数 / 每天读了多少"。
    同一分钟内重复上报会合并，避免每次滚动都写一行。
    """
    ts = time.time()
    rec = {"t": int(ts), "slug": slug, "chapter": int(chapter)}
    if scroll is not None:
        rec["scroll"] = round(float(scroll), 3)
    try:
        os.makedirs(DATA, exist_ok=True)
        # 同小时同一本书只留一条，日志不会爆
        last = None
        if os.path.exists(HISTORY_PATH):
            with open(HISTORY_PATH, "rb") as f:
                try:
                    f.seek(-4096, os.SEEK_END)
                except OSError:
                    f.seek(0)
                tail = f.read().decode("utf-8", "replace").strip().split("\n")
            if tail and tail[-1]:
                try:
                    last = json.loads(tail[-1])
                except json.JSONDecodeError:
                    last = None
        if last and last.get("slug") == slug and (int(ts) - int(last.get("t") or 0)) < 1800:
            return
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def reading_stats() -> dict:
    """从历史日志算：连续阅读天数 / 最近 7 天阅读章数。"""
    days: dict[str, int] = {}
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    d = time.strftime("%Y-%m-%d", time.localtime(int(r.get("t") or 0)))
                    days[d] = days.get(d, 0) + 1
        except OSError:
            pass
    if not days:
        return {"streak": 0, "today": 0, "last7": 0, "days": 0}

    # 连续天数：从今天（或昨天）往前数
    today = time.strftime("%Y-%m-%d")
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    cur = today if today in days else (yesterday if yesterday in days else None)
    streak = 0
    if cur:
        t = time.mktime(time.strptime(cur, "%Y-%m-%d"))
        while time.strftime("%Y-%m-%d", time.localtime(t)) in days:
            streak += 1
            t -= 86400
    last7 = sum(v for k, v in days.items()
                if k >= time.strftime("%Y-%m-%d", time.localtime(time.time() - 6 * 86400)))
    return {"streak": streak, "today": days.get(today, 0),
            "last7": last7, "days": len(days)}


def toggle_favorite(slug: str) -> bool:
    box = {}

    def fn(d):
        if d.get("favorites"):
            d["favorites"] = None
            box["fav"] = False
        else:
            d["favorites"] = time.strftime("%Y-%m-%d %H:%M:%S")
            box["fav"] = True

    update_book(slug, fn)
    return box.get("fav", False)


def append_feedback(slug: str, rec: dict) -> None:
    """只追加到这一本书的反馈里（锁内读改写，避免并发丢反馈）。

    **不要**用 save_state(整份聚合状态) 来写反馈：
    load_state() 会把所有书的历史反馈聚合起来，再整体写回，
    于是每次提交都把旧反馈重复追加一遍（自检抓到同一条被写了 4 次）。
    """
    update_book(slug, lambda d: d["feedback"].append(rec))


def set_opened(slug: str) -> None:
    update_book(slug, lambda d: d.__setitem__(
        "opened", time.strftime("%Y-%m-%d %H:%M:%S")))


def migrate_shelf_state() -> int:
    """老数据里"有阅读进度但没有 tracking/favorites"的书，按"在读"补上。

    否则改成"看标记才上架"之后，用户原来的书会全部从书架消失。
    （只跑一次：补过 tracking 就不会再命中。）
    """
    # 只跑一次：否则用户"主动移出书架"的书会被反复自动加回去
    # （踩过：用户移出后重启服务，迁移又把它标成 reading 放回书架）
    marker = os.path.join(DATA, ".shelf-migrated")
    if os.path.exists(marker):
        return 0
    n = 0
    if not os.path.isdir(NOVELS):
        return 0
    for slug in os.listdir(NOVELS):
        if slug.startswith(".") or not os.path.isdir(os.path.join(NOVELS, slug)):
            continue
        d = _read_book(slug)
        if d.get("tracking") in TRACKING or d.get("favorites"):
            continue
        pr = d.get("progress") or {}
        if pr.get("chapter"):
            def fn(dd, _c=pr.get("chapter")):
                dd["tracking"] = "reading"
                dd["finished"] = None
                dd["dropped"] = None
            update_book(slug, fn)
            n += 1
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + f"（迁移 {n} 本）\n")
    except OSError:
        pass
    return n


def dedupe_feedback() -> int:
    """清理历史重复反馈（幂等，启动时跑一次）。"""
    n = 0
    bd = os.path.join(DATA, "books")
    if not os.path.isdir(bd):
        return 0
    for fn in os.listdir(bd):
        if not fn.endswith(".json"):
            continue
        slug = fn[:-5]
        d = _read_book(slug)
        seen, out = set(), []
        for fb in d.get("feedback") or []:
            k = (fb.get("at"), fb.get("chapter"), fb.get("vote"), fb.get("note"))
            if k in seen:
                n += 1
                continue
            seen.add(k)
            out.append(fb)
        if len(out) != len(d.get("feedback") or []):
            d["feedback"] = out
            _write_book(slug, d)
    return n


def load_state() -> dict:
    """汇总所有书的状态（读多写少，聚合视图够用）。"""
    if not os.path.isdir(NOVELS):
        return dict(EMPTY)
    if os.path.exists(state_path()):
        _migrate_global()
    agg = {"progress": {}, "favorites": {}, "feedback": [], "opened": {}}
    bd = os.path.join(DATA, "books")
    if os.path.isdir(bd):
        for fn in os.listdir(bd):
            if not fn.endswith(".json"):
                continue
            slug = fn[:-5]
            d = _read_book(slug)
            if d.get("progress"):
                agg["progress"][slug] = d["progress"]
            if d.get("favorites"):
                agg["favorites"][slug] = d["favorites"]
            if d.get("opened"):
                agg["opened"][slug] = d["opened"]
            agg["feedback"].extend(d.get("feedback") or [])
    agg["feedback"].sort(key=lambda x: (x.get("at") or ""))
    return agg


def attrescape(s: str) -> str:
    """转义要放进 HTML 属性值里的文本。

    踩过大坑：卡片 onclick 里写了 `location.href='/read/x'`，
    嵌在双引号属性里时那个单引号会提前结束属性，
    整个 DOM 结构被浏览器重解析 → 按钮脱离 .card 容器 →
    `b.closest('.card')` 返回 null → 所有状态按钮点了没反应。
    """
    return html.escape(str(s), quote=True)


# meta.json 的按 (mtime, size) 缓存。
# 踩过（性能）：列表页每张卡都要问一次"这本书的 meta"，一个书架页就会把同两个
# meta.json 解析几百遍（实测 747 次 / 页面，占首页 5 秒里的 1.4 秒）。
# 只缓存**文件没变**的那份，worker 写完 save_json 后 mtime 变了自然失效。
_META_CACHE: dict[str, tuple] = {}


def novel_meta(slug: str) -> dict | None:
    if not _valid_slug(slug):
        return None
    p = os.path.join(NOVELS, slug, "meta.json")
    try:
        st = os.stat(p)
        # inode 也进缓存键：save_json 用临时文件 + os.replace，原子替换会换
        # inode，而 exFAT/sdcardfs 的 mtime 只有 2 秒粒度 —— 只比 mtime/size
        # 的话，「命令行改了 meta.json、服务进程在同一秒内读到」会拿到旧内容。
        key = (st.st_mtime_ns, st.st_size, getattr(st, "st_ino", 0))
    except OSError:
        _META_CACHE.pop(slug, None)
        return None
    hit = _META_CACHE.get(slug)
    if hit and hit[0] == key:
        return hit[1]
    try:
        with open(p, encoding="utf-8") as f:
            meta = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if len(_META_CACHE) > 64:            # 书架不会同时有 64 本在渲染
        _META_CACHE.clear()
    _META_CACHE[slug] = (key, meta)
    return meta


def has_zh(slug: str, idx: int) -> bool:
    # v5 validates the sidecar's source/content hashes.  A new text file with
    # an old sidecar (or vice versa) must not become readable merely because
    # the .txt exists.
    base = os.path.join(NOVELS, slug, "chapters")
    return lt.translation_available(
        os.path.join(base, f"{idx:04d}.txt"),
        os.path.join(NOVELS, slug, "raw", f"{idx:04d}.txt"),
        os.path.join(base, f"{idx:04d}.meta.json"),
    )


def _dir_sigs(path: str) -> dict[str, tuple[int, int, int]] | None:
    """一次 scandir 取整个目录的 (mtime_ns, size, inode)；目录不存在则 ``None``。

    实现在契约层（`lncontracts.dir_sigs`），`lntrans.rebuild_novel_md` 也用
    同一份 —— 两套目录扫描必然漂移。性能背景见那里的 docstring。
    """
    return lncontracts.dir_sigs(path)


def _chapter_sigs(slug: str):
    """(chapters 目录签名, raw 目录签名)；chapters 目录不存在时 (None, None)。"""
    c = _dir_sigs(os.path.join(NOVELS, slug, "chapters"))
    if c is None:
        return None, None
    return c, (_dir_sigs(os.path.join(NOVELS, slug, "raw")) or {})


def _prune_chapter_cache(cache: dict, total: int) -> None:
    # 章节数缩小时清掉越界项，避免缓存只增不减。
    for key in [k for k in cache if k >= total]:
        cache.pop(key, None)


def has_complete_zh(slug: str, idx: int, c_sigs=None, r_sigs=None) -> bool:
    """章译文是否**译全**（partial 旁车不算）。

    `next_targets` 会为全书每章问一次，而 worker 每译完一章又会重算一次
    targets —— 不做签名缓存就是 O(章数²) 次 sidecar 解析。与 `zh_chapters`
    同一套「只重算签名变化的那一章」策略，并可复用一次目录扫描的结果。
    """
    if c_sigs is None:
        c_sigs, r_sigs = _chapter_sigs(slug)
        if c_sigs is None:
            return False
    name = f"{idx:04d}"
    zh = os.path.join(NOVELS, slug, "chapters", f"{name}.txt")
    sidecar = os.path.join(NOVELS, slug, "chapters", f"{name}.meta.json")
    raw = os.path.join(NOVELS, slug, "raw", f"{name}.txt")
    sig = (c_sigs.get(f"{name}.txt"), c_sigs.get(f"{name}.meta.json"),
           r_sigs.get(f"{name}.txt"))
    cache = _ZH_COMPLETE_CACHE.setdefault(slug, {})
    hit = cache.get(idx)
    if hit is not None and hit[0] == sig:
        return hit[1]
    ok = lncontracts.translation_paths_complete(zh, raw, sidecar)
    cache[idx] = (sig, ok)
    return ok


# 每章缓存 (zh 签名, sidecar 签名, raw 签名) -> 是否有可读译文。
# 不再把 `have` 写进 state：那是纯写放大（GET 渲染路径写盘），而且旧读端
# 已被删除，写进去也没人消费。缓存命中路径只查表，不重算 SHA-256。
_ZH_CHAPTER_CACHE: dict[str, dict[int, tuple[tuple, bool]]] = {}
_ZH_COMPLETE_CACHE: dict[str, dict[int, tuple[tuple, bool]]] = {}


def zh_chapters(slug: str, total: int) -> list[int]:
    """已译章号（1-based）。**不看是否有空洞**。

    增量缓存：只有 zh/sidecar/raw 的文件签名（mtime + size）变了才重算
    该章的哈希。翻译完一章只会让那一章失效，不再整本重哈希；也不在渲染
    路径写 state 文件。签名来自一次目录扫描（见 `_dir_sigs`）。
    """
    c_sigs, r_sigs = _chapter_sigs(slug)
    if c_sigs is None:
        return []
    cache = _ZH_CHAPTER_CACHE.setdefault(slug, {})
    _prune_chapter_cache(cache, total)
    _prune_chapter_cache(_ZH_COMPLETE_CACHE.setdefault(slug, {}), total)
    out: list[int] = []
    for i in range(total):
        name = f"{i:04d}"
        sig = (c_sigs.get(f"{name}.txt"),
               c_sigs.get(f"{name}.meta.json"),
               r_sigs.get(f"{name}.txt"))
        hit = cache.get(i)
        if hit is not None and hit[0] == sig:
            ok = hit[1]
        else:
            ok = has_zh(slug, i)
            cache[i] = (sig, ok)
        if ok:
            out.append(i + 1)
    return out


def invalidate_cache(slug: str | None = None, idx: int | None = None) -> None:
    """丢弃章节可读性缓存；`idx`（0-based）给定时只丢那一章。

    写端必须显式失效：exFAT / sdcardfs 的 mtime 只有 2 秒粒度，刚写完的
    章节可能与旧版本签名完全相同。只靠签名比对的话，新译章要等下一次
    签名变化（甚至重启）才会在书架上亮起来。
    """
    if slug and idx is not None:
        for cache in (_ZH_CHAPTER_CACHE, _ZH_COMPLETE_CACHE):
            cache.get(slug, {}).pop(idx, None)
        return
    if slug:
        _ZH_CHAPTER_CACHE.pop(slug, None)
        _ZH_COMPLETE_CACHE.pop(slug, None)
    else:
        _ZH_CHAPTER_CACHE.clear()
        _ZH_COMPLETE_CACHE.clear()


def translated_count(slug: str, meta: dict) -> int:
    """从第 1 章起的最长连续已译前缀。

    用途：前端"下一页从哪取"、进度显示。
    自检发现：老实现遇到第一个空洞就 break 并返回，导致
    「1,2 译好、3 失败、4~8 译好」时认为只译了 2 章 ——
    后面 6 章直接不可见，而且续译会重翻，白花 token。
    """
    total = len(meta.get("episodes") or [])
    # 必须走 zh_chapters()（带 mtime 缓存）。
    # 踩过：这里直接调 has_zh() 逐章 stat，绕过了缓存 ——
    # 30 本书 × 200 章 = 1.2 万次 stat，3.4 秒（profile 实测）。
    have = set(zh_chapters(slug, total))
    n = 0
    while (n + 1) in have:
        n += 1
    return n


def have_count(slug: str, meta: dict) -> int:
    """**真有译文**的章数（带空洞也算）。

    显示一律用它，不用 translated_count：后者是"从第 1 章起的连续前缀"，
    拿它当"已译"会骗人 —— 踩过：第 2~7 章译好了、第 1 章没译，
    书架和阅读页都显示「已译 0 章 / 已有 0/23 章译文」，
    而下面明明列着已译章节（用户当场就问「我第一话呢？」）。
    """
    return len(zh_chapters(slug, len(meta.get("episodes") or [])))


def ensure_zh_titles(slug: str, upto: int | None = None) -> int:
    """把书名/章节名翻成中文（复用 CLI 的 titles，一次请求搞定）。

    为什么必须做：正文翻了、目录和章节大标题还是日文，中文读者扫不了
    （用户要求：「你汉化完了显示汉化章节，我点进去来看，这样清晰明了」）。
    返回翻好的条数；`upto` 限定只翻前 N 章 —— 别为一本 200 章的书
    在只读前 3 章时把 200 个标题全翻了。
    """
    ns = argparse.Namespace(slug=slug, model=lt.AUX_MODEL, no_book=False)
    meta = novel_meta(slug) or {}
    before = len((meta.get("zh_titles") or {}))
    lt.cmd_titles(ns, upto=upto)
    # cmd_titles 只重写 meta.json 的 zh_titles，不动章节文件 —— 章节可读性
    # 缓存无需整本失效（那会让每次译标题都重扫全书）。只丢 meta 缓存。
    _META_CACHE.pop(slug, None)
    after = len(((novel_meta(slug) or {}).get("zh_titles") or {}))
    return max(0, after - before)


def zh_title_of(meta: dict, ch: int, fallback: str = "") -> str:
    """第 ch 章的中文标题（没翻过就退回日文原名）。"""
    eps = meta.get("episodes") or []
    jp = (eps[ch - 1].get("title") if 0 < ch <= len(eps) else "") or fallback
    return (meta.get("zh_titles") or {}).get(str(ch)) or jp or f"第{ch}话"


def toc_list(slug: str, meta: dict, have, shown) -> str:
    """「已译章节」列表：**全部**已译章（不只本页那几章），带中文标题。

    用户要求：「你应该学习章节划分，你汉化完了显示汉化章节，我点进去来看」。
    所以这里当**目录**用：本页内的章走锚点（不重新加载），
    本页外的章走 /read/<slug>?from=N（从那一章开始渲染）。
    """
    eps = meta.get("episodes") or []
    zh = meta.get("zh_titles") or {}
    # 「未译全」要标出来：这一章有段落翻译失败过（原文暂时留着）。
    # 章数照算，但不能让人以为它和别的章一样是整篇中文。
    # 标记写在 meta.progress.incomplete（见 lntrans.translate_chapter）。
    inc = set((meta.get("progress") or {}).get("incomplete") or [])
    items = []
    for i in sorted(have):
        jp = (eps[i - 1].get("title") if i - 1 < len(eps) else "") or ""
        t = zh_title_of(meta, i)
        if i in inc:
            t += (' <span class="part" title="这一章有段落没译出来（留着日文原文），'
                  '再点一次翻译可以补齐">未译全</span>')
        sub = f'<span class="epd">{lr.esc(jp)}</span>' if (jp and zh.get(str(i))) else ""
        # 不在本页的章节也带 `#c<N>`：翻过去直接落在正文，不再回页面顶部
        # 让读者自己翻过标题和折叠目录。
        href = (f"#c{i}" if i in shown
                else f"/read/{attrescape(slug)}?from={i}#c{i}")
        cur = ' class="cur"' if i in shown else ""
        items.append(f'<li{cur}><a href="{href}">'
                     f'<span class="epnum">{i}</span>'
                     f'<span class="epn">{lr.esc(t)}</span>{sub}</a></li>')
    return "".join(items)


def next_targets(slug: str, meta: dict, want: int,
                 after: int | None = None) -> list[int]:
    """该翻哪几章：优先补空洞，其次从末尾往后。

    `after` 给定时（读者当前所在章），优先翻它后面的内容，
    这样"读到哪翻到哪"在有空洞时也成立。

    **但当前这一章本身没译文时，它必须排第一个**。
    踩过（用户报「我还没开始看，怎么就第二话了，我第一话呢？」）：
    新书 after=1，原来把"当前章之后的"排在前面，于是第 2、3 章先被翻，
    第 1 章要等 later 用完才轮到 —— 读者一进来看到的就是第 2 章，
    而且因为阅读页渲染了第 2 章，进度还被记成"读到第 2 章"。
    """
    total = len(meta.get("episodes") or [])
    # 走 zh_chapters()（带签名缓存），不要逐章 has_zh() 直接 stat —— 那是本项目
    # 记录在案的反模式。这里额外只扫一次目录，把签名传给每章判定，避免
    # `next_targets` 自己变成 O(章数) 次目录扫描。
    # Partial sidecars are readable but still count as unfinished work.  This
    # lets "补齐" resume the missing paragraphs instead of skipping the chapter.
    c_sigs, r_sigs = _chapter_sigs(slug)
    if c_sigs is None:
        complete = set()
    else:
        complete = {i + 1 for i in range(total)
                    if has_complete_zh(slug, i, c_sigs, r_sigs)}
    missing = [c for c in range(1, total + 1) if c not in complete]
    if not missing:
        return []
    if after is None:
        return missing[:want]
    later = [c for c in missing if c > after]
    earlier = [c for c in missing if c <= after]
    if after in earlier:                    # 正在看的这一章还没翻 → 先翻它
        earlier = [c for c in earlier if c != after]
        return ([after] + later + earlier)[:want]
    return (later + earlier)[:want]


CHECK_MIN_INTERVAL_H = 6   # 同一本书多久最多查一次（避免反复打开就反复请求）


def check_on_open(slug: str, force: bool = False) -> dict:
    """用户**打开这本书**时才查它的更新。

    为什么改成按需（用户要求）：定时轮询会在用户根本不看书的日子里
    也一直打源站，纯属浪费。改成"打开才查"以后：
      · 不打开 → 零请求
      · 打开 → 这一次查最新，而且书架上的标记也是最新的
    去重：同一天（默认 6 小时内）重复打开不重复请求，点"强制"才绕过。
    """
    _m = novel_meta(slug) or {}
    if (_m.get("source") or "") == "local":
        # 本地导入的书没有源站。别拿空 url 去打 fetch_work（会写成 check_error，
        # 卡片上看着像源站抽风，其实是我们自己在瞎查）。
        return {"slug": slug, "checked": False, "reason": "本地书不检查更新",
                "has_update": False, "new_episodes": 0}
    d = _read_book(slug)
    # 用「上次尝试时间」而不是「上次成功时间」去重：源站宕机时成功时间不更新，
    # 若只认 checked_at，每次打开书都会重新起后台线程、页面白等 1 秒、
    # 反复去打一个已经挂掉的源站。失败也要退避，恢复后最多等一个间隔。
    last = d.get("check_attempt_at") or d.get("checked_at") or ""
    if not force and last:
        try:
            t = time.mktime(time.strptime(last, "%Y-%m-%d %H:%M:%S"))
            if (time.time() - t) < CHECK_MIN_INTERVAL_H * 3600:
                return {"slug": slug, "checked": False, "reason": "不久前刚查过",
                        "has_update": bool(d.get("has_update")),
                        "new_episodes": d.get("new_episodes") or 0,
                        "last_episode_at": d.get("last_episode_at") or ""}
        except ValueError:
            pass
    res = check_updates([slug], verbose=False)
    if not res:
        return {"slug": slug, "checked": False, "reason": "查询失败"}
    r = res[0]
    r["checked"] = True
    return r


def check_on_open_bounded(slug: str, timeout: float = 1.0) -> None:
    """打开阅读页时的更新检查：**最多耽搁 timeout 秒**，超时就让它后台跑完。

    踩过（导出时被自检抓到）：源站慢的时候，整个阅读页请求会卡在这一次网络
    请求上（十几秒白屏）—— 用户看到的就是"页面打不开 / 得自己刷新一下"。
    实测一次真实的源站查询要 **3.1 秒**（kakuyomu 作品页），所以不能同步等。
    这里挪进后台线程只等 1 秒：查得快就顺手把"更新了 +N 话"标出来，
    查得慢（或源站抽风）页面立刻出来，结果写进状态，下次打开/回书架就能看到。
    """
    done = threading.Event()

    def run() -> None:
        try:
            check_on_open(slug)
        except Exception:  # noqa: BLE001
            pass          # 查更新失败绝不能挡住阅读
        finally:
            done.set()

    threading.Thread(target=run, daemon=True, name=f"chk-{slug}").start()
    done.wait(timeout)


def check_updates(slugs: list[str] | None = None, verbose: bool = False) -> list[dict]:
    """查这些书有没有更新（只看作品页的章节列表，**不花翻译 token**）。

    记录：episodes_latest（源站最新话数）、last_episode_at（最新话时间）、
          new_episodes（比上次多几话）、checked_at。
    """
    out = []
    for slug in (slugs or []):
        meta = novel_meta(slug)
        if not meta:
            continue
        if (meta.get("source") or "") == "local":
            # 本地书没有源站目录可查，别发无意义的请求。
            continue
        # ⚠ 抓取（`fetch_work`）要花好几秒（实测 3.1s），**绝不能**
        # 在抓取前 `_read_book` 一份快照、抓完再整体 `_write_book` 回写 ——
        # 那会把抓取期间用户/测试改的 tracking / favorites / progress 一起覆盖掉
        # （`update_book` docstring 警告的"丢一次写"）。踩过：后台 `chk-<slug>`
        # 线程用旧快照回写，把刚点的「弃文」冲回旧值（test_ui 偶发红）。
        # 正确做法：抓取放锁外，字段合并走 `update_book`（LOCK 内基于最新状态）。
        try:
            info = lt.fetch_work(meta["url"])
        except (Exception, SystemExit) as e:  # noqa: BLE001
            if verbose:
                print(f"  {slug}: 查询失败 {type(e).__name__}")
            msg = f"{type(e).__name__}: {e}"
            _now = time.strftime("%Y-%m-%d %H:%M:%S")
            # 失败也写「尝试时间」：去重/退避只看它（见 check_on_open）。
            # checked_at 保持"上次成功检查"的语义，书架不显示失败时间。
            update_book(slug, lambda d: d.update(
                {"check_error": msg, "check_attempt_at": _now}))
            continue
        eps = info.get("episodes") or []
        newest = max((e.get("publishedAt") or "" for e in eps), default="")
        box: dict = {}

        def fn(d):
            prev_n = d.get("episodes_latest")
            prev_at = d.get("last_episode_at") or ""
            delta = 0
            if prev_n is not None:
                delta = max(0, len(eps) - int(prev_n))
            new_flag = bool(prev_n is not None and (delta > 0 or newest > prev_at))
            d.update({
                "episodes_latest": len(eps),
                "last_episode_at": newest,
                "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "check_attempt_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            d.pop("check_error", None)
            if new_flag:
                d["new_episodes"] = delta
                d["has_update"] = True
                d["update_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            elif eps:
                # 本次检查确认**没有**新内容 → 清掉过期的「更新了」徽标。
                # 踩过：has_update 一旦置位就再没人清，读者把更新处理完
                # （翻好、读掉）以后徽标仍永远亮着，点进去根本没有新章 ——
                # 按钮名字就成了谎话。`elif eps` 是护栏：源站偶发返回空列表
                # 不能被当成"删章了"而误清掉真正的更新。
                _clear_update_flags(d)
            box["delta"] = delta
            box["new_flag"] = new_flag

        update_book(slug, fn)
        delta, new_flag = box["delta"], box["new_flag"]
        out.append({"slug": slug, "title": meta.get("title"),
                    "episodes": len(eps), "new": delta, "newest": newest,
                    "has_update": new_flag})
        if verbose:
            mark = f"有更新 +{delta} 话" if new_flag else "无更新"
            print(f"  {slug}: {len(eps)} 话 · 最新 {newest or '-'} · {mark}")
        time.sleep(0.6)
    return out


def watch_list() -> list[str]:
    """该定时查更新的书：收藏 + 在读。放弃/看完不查。"""
    out = []
    for it in library():
        if it.get("local"):
            continue          # 本地书没有源站，不入定时查更新队列
        if should_watch(book_status(it["slug"], it), it["slug"]):
            out.append(it["slug"])
    return out


def update_daemon(every_hours: float = 12.0) -> None:
    """后台定时查更新。只查 watch_list()，不做免费的翻译。

    为什么要定时：源站不会推送，我们只能轮询。轮询的是作品页
    （章节列表），成本远低于翻译；发现更新后只在书架打个标记，
    翻译与否由用户决定——这样不会因为"某某更新了"就白烧 token。
    """
    while not STOP.is_set():
        try:
            wl = watch_list()
            if wl:
                print(f"[更新检查] {time.strftime('%H:%M:%S')} 查 {len(wl)} 本：{', '.join(wl)}")
                check_updates(wl, verbose=True)
        except (Exception, SystemExit) as e:  # noqa: BLE001
            print(f"[更新检查] 出错：{type(e).__name__}: {e}")
        # 分片睡眠，保证能及时响应退出
        for _ in range(int(every_hours * 3600 / 5)):
            if STOP.is_set():
                return
            time.sleep(5)


def _tags_by_source() -> dict[str, list[str]]:
    """书库留档里的标签（source_id → tags）；书架卡与阅读页共用。"""
    out: dict[str, list[str]] = {}
    try:
        raw = recs._load_lib() or {}
    except Exception:  # noqa: BLE001
        raw = {}
    for k, v in raw.items():
        tags = [str(t) for t in (v.get("tags") or []) if t]
        if tags:
            out[str(k)] = tags
    # 书库留档缺失/被迁移时，推荐缓存仍可能是同一本书的标签来源。
    try:
        for it in recs.cached(include_hidden=True) or []:
            wid = str(it.get("id") or "")
            tags = [str(t) for t in (it.get("tags") or []) if t]
            if wid and tags:
                out.setdefault(wid, tags)
    except Exception:  # noqa: BLE001
        pass
    return out


def library() -> list[dict]:
    st = load_state()
    out = []
    if not os.path.isdir(NOVELS):
        return out
    tag_map = _tags_by_source()
    for slug in sorted(os.listdir(NOVELS)):
        if slug.startswith(".") or not os.path.isdir(os.path.join(NOVELS, slug)):
            continue
        meta = novel_meta(slug)
        if not meta:
            continue
        eps = meta.get("episodes") or []
        done = have_count(slug, meta)
        prog = st["progress"].get(slug) or {}
        zh = meta.get("zh_titles") or {}
        bd = _read_book(slug)
        # 中文书名的**唯一来源**：章节译文缓存（meta.zh_titles.book）与
        # 详情缓存（data/details/<id>.json 的 zh_title）**两处合并**。
        # 踩过（用户报「书架里的书标题没翻译」）：详情页/推荐卡的中文书名写进详情缓存，
        # 而书架卡只读 meta.zh_titles.book —— 后者要**开始翻章节**才写。
        # 于是同一本书：推荐卡上是中文，书架上还是日文（用户以为坏了）。
        wid = str(meta.get("source_id") or "")
        det = load_detail(wid) if wid else {}
        zh_book = zh.get("book") or det.get("zh_title") or ""
        item = {
            "slug": slug,
            "id": wid,
            "title": zh_book or meta.get("title") or slug,
            "title_zh": zh_book,
            "title_jp": meta.get("title") or "",
            "author": meta.get("author") or "",
            "total": len(eps),
            "translated": done,
            "read": prog.get("chapter") or 0,
            "favorite": bool(bd.get("favorites")),
            "finished": bool(bd.get("finished")),
            "dropped": bool(bd.get("dropped")),
            "last_read": prog.get("at") or "",
            "updated": prog.get("at") or meta.get("created_at") or "",
            "has_update": bool(bd.get("has_update")),
            "new_episodes": bd.get("new_episodes") or 0,
            "checked_at": bd.get("checked_at") or "",
            "last_episode_at": bd.get("last_episode_at") or "",
            # 翻译失败痕迹（持久化，服务重启后仍能提示重试）
            "trans_error": bd.get("trans_error") or "",
            "trans_error_at": bd.get("trans_error_at") or "",
            # 本地导入的书（没有源站）：卡片不显示「检查更新」。
            "local": ((meta.get("source") or "") == "local"
                      or str(wid).startswith("local-") or not meta.get("url")),
            "want": bool(bd.get("want")),
            # 源站标签在 data/library.json（按 source_id 存）；novel meta 里没有。
            # 不 join 的话书架卡永远看不到标签（用户报「收集了很多书却没有标签」）。
            "tags": (tag_map.get(wid) if wid else None)
                    or [str(t) for t in (meta.get("tags") or []) if t],
        }
        item["on_shelf"] = bool(bd.get("favorites")) or (bd.get("tracking") in TRACKING)
        item["tracking"] = _tracking_of(bd)
        item["status"] = (item["tracking"] if item["tracking"] in ("finished", "dropped")
                          else ("favorite" if item["favorite"] else item["tracking"]))
        item["stale"] = _stale_days_of(bd)
        item["dormant"] = _dormant_of(bd)
        # 整体进度用于"这本书我读了多少"
        _p = bd.get("progress") or {}
        try:
            _ch = int(_p.get("chapter") or 0)
            _mx = float(_p.get("max_scroll") or 0)
            item["book_progress"] = round(
                max(0.0, min(1.0, ((_ch - 1) + _mx) / max(len(eps), 1))), 4)
        except (TypeError, ValueError):
            item["book_progress"] = 0.0
        cfg = _trans_cfg_of(bd)
        item["t_enabled"] = cfg["enabled"]
        item["t_ahead"] = cfg["ahead"]
        item["t_ceiling"] = _auto_ceiling_of(bd, meta)
        item["read"] = item["read"] or 0
        out.append(item)
    out.sort(key=lambda x: (x["last_read"], x["last_episode_at"]), reverse=True)
    return out


# ------------------------------------------------------------------ 翻译任务

def job_key(slug: str) -> str:
    return slug


# 这些字段是 **UI 的内存态**，没有恢复价值：`message`（提示文案）、
# `done`（本次任务翻了几段）、`translated`/`total`（全书累计，重启后重算）、
# `targets`（与持久化的 chapter_numbers 重复）。不写进持久任务记录有两个
# 好处：任务日志不被内存态污染；段级进度回调只更新内存，**不再每段一次
# fsync**（手机闪存上几十毫秒级，一章十几段就是几百毫秒的无谓写放大）。
_VOLATILE_JOB_FIELDS = frozenset({"message", "done", "translated", "total",
                                  "targets"})


RESTART_ERROR_MARK = "服务重启或进程中断"


def _auto_resume_plan(rec: dict, *, auto_translate: bool,
                      total: int, max_chapters: int = 10) -> dict | None:
    """服务重启后要不要自动把这个中断任务接着跑？返回 start_job 的参数。

    背景（2026-10-21 的真实事故）：我在第 30-31 章翻译跑到一半时重启服务，
    启动时 `reconcile_startup` 按设计把 running 改成 interrupted —— 用户眼里
    就是「翻译又卡了」，而实际上**是我把任务掐了**。
    单用户自用站里，重启（升级、改配置、容器重启）是常态；每次都让用户
    回来手点一次「继续」，等于每次部署都白丢一次点击。

    但自动续跑必须窄：
      ① 只认「因重启而中断」这一种原因（error 精确匹配），provider_error /
         cancelled / 预算耗尽都不碰；
      ② 书必须**开着自动翻译**（用户已经授权这本书花钱）；
      ③ 只补原来的剩余章节，最多 max_chapters 章；
      ④ 不连续套娃：上一条自己就是自动续跑的任务，再中断就不再自动续（防无限花钱）。

    这些条件放在一个纯函数里，是为了能被测试直接钉住（见 test_state）。
    """
    if not isinstance(rec, dict):
        return None
    if rec.get("status") != "interrupted":
        return None
    if RESTART_ERROR_MARK not in (rec.get("error") or ""):
        return None
    remaining = [int(x) for x in (rec.get("remaining_chapters") or [])
                 if str(x).isdigit()]
    if not remaining:
        # worker 刚启动、还没算出 targets 就被重启：记录里只有 create 时写下的
        # `target` 范围（remaining 仍是空数组）。这不是「没有剩余章节」，而是
        # 「还没登记」——必须从 target 派生，否则这条任务永远等不到自动续跑，
        # 用户看到的就是「一重启就卡住」。
        tgt = rec.get("target") or {}
        try:
            lo = int(tgt.get("from_chapter") or 0)
            hi = int(tgt.get("to_chapter") or 0)
        except (TypeError, ValueError):
            lo = hi = 0
        done = {int(x) for x in (rec.get("completed_chapters") or [])
                if str(x).isdigit()}
        if lo and hi >= lo:
            remaining = [c for c in range(lo, hi + 1) if c not in done]
    if not remaining or not auto_translate:
        return None
    if len(remaining) > max_chapters or (total and max(remaining) > total):
        return None
    requested = rec.get("requested") or {}
    if requested.get("reason") == "resume-after-restart":
        return None
    return {
        "count": len(remaining),
        "after": max(1, min(remaining) - 1),
        "ceiling": max(remaining),
        "reason": "resume-after-restart",
        "resume_of": rec.get("job_id"),
    }


def _resume_interrupted_after_restart() -> int:
    """启动时把「因重启中断」的任务接回去（条件见 `_auto_resume_plan`）。

    `LNTRANS_NO_AUTO_RESUME=1` 可关掉（例如你想先看看中断原因再决定要不要花钱）。
    """
    if os.environ.get("LNTRANS_NO_AUTO_RESUME"):
        return 0
    try:
        recs = jobstore.STORE.records()
    except Exception:  # noqa: BLE001 - 坏日志由只读恢复模式处理，这里不抢戏
        return 0
    n = 0
    # 每本书只看**最新一条**记录。踩过：按"第一次见到的 slug"去重，而 records()
    # 的顺序不是最新的在前 —— 于是先碰到一条旧的 done，把后面的 interrupted 全
    # 跳过了，函数静默返回 0（日志里什么都没有，像没装这个功能）。
    latest: dict[str, dict] = {}
    for rec in recs:
        slug = rec.get("slug") or ""
        if not slug:
            continue
        prev = latest.get(slug)
        if prev is None or (rec.get("created_at") or "") >= (prev.get("created_at") or ""):
            latest[slug] = rec
    for slug, rec in latest.items():
        try:
            if jobstore.STORE.active(slug):
                continue          # 已有活动任务（或刚被别的路径接手）
        except Exception:  # noqa: BLE001
            continue
        meta = novel_meta(slug) or {}
        # 注意：**不能**再用废弃的 translate.enabled 当闸门（v5.1 起调度器根本
        # 不看它，于是用调度器翻的书 enabled 恒为 false → 重启后永远不续跑，
        # 用户看到的就是"重启一下又卡住"）。真正的授权信号是：这本书没弃文/
        # 没看完、也没被用户「暂停」。
        bd = _read_book(slug)
        auto = not (bd.get("finished") or bd.get("dropped")) \
            and not SCHED.is_paused(slug)
        plan = _auto_resume_plan(
            rec, auto_translate=bool(auto),
            total=len(meta.get("episodes") or []))
        if not plan:
            continue
        try:
            start_job(slug, plan["count"], plan["reason"], after=plan["after"],
                      ceiling=plan["ceiling"], resume_of=plan["resume_of"])
        except (jobstore.JobError, RuntimeError) as e:  # noqa: BLE001
            print(f"[恢复] {slug} 自动续跑失败：{e}")
            continue
        n += 1
        _zh = (meta.get("zh_titles") or {}).get("book") or meta.get("title") or slug
        print(f"[恢复] 服务重启：自动继续《{_zh}》"
              f"第 {plan['after'] + 1}-{plan['ceiling']} 章"
              f"（{plan['count']} 章；不想自动续跑可设 LNTRANS_NO_AUTO_RESUME=1）")
    return n


def _close_own_record(job_id: str, completed: list[int],
                      remaining: list[int],
                      reason: str = "已被新任务取代，已停止") -> bool:
    """关掉「已经没人负责」的耐久任务记录（幂等，只动自己那条）。

    为什么需要它：worker 收尾时用 `_sync_job`，而它对 token 不匹配的情况是
    **静默返回 {}**（防止旧任务覆盖新任务）。于是被取代/超时后重试的旧任务，
    它自己的记录会永远停在 `running` —— 界面上就是「翻译一直进行中」，直到
    240 秒超时才被收尸。这里按 job_id 补上最后一次收尾写入；只动自己这条，
    不碰新任务（新任务有自己的 job_id）。
    """
    if not job_id:
        return False
    try:
        rec = jobstore.STORE.get(job_id) or {}
        if rec.get("status") not in ("queued", "running"):
            return False
        jobstore.STORE.update(
            job_id, status="interrupted", message=reason, error=None,
            completed_chapters=list(completed),
            remaining_chapters=list(remaining))
        return True
    except jobstore.JobError:
        return False


def _sync_job(slug: str, token: int, **changes) -> dict:
    """Update in-memory and durable job state as one logical operation."""
    global JOBS_READ_ONLY, JOBS_RECOVERY_INFO
    with LOCK:
        j = JOBS.get(slug)
        if not j or j.get("token") != token:
            return {}
        job_id = j.get("job_id")
        persisted = {k: v for k, v in changes.items()
                     if k not in _VOLATILE_JOB_FIELDS}
        if job_id and persisted:
            try:
                rec = jobstore.STORE.update(job_id, **persisted)
            except jobstore.JobRecordMissing as ex:
                # 记录被外部删除：只停这一个任务，**不**锁定整站任务写入
                # （没有坏文件需要隔离），也不写「翻译失败」痕迹（见 worker）。
                j["status"] = "interrupted"
                j["message"] = "任务记录丢失，已停止调度（可重新开始翻译）"
                j["error"] = str(ex)
                raise
            except jobstore.RecoveryRequired as ex:
                JOBS_READ_ONLY = True
                JOBS_RECOVERY_INFO = jobstore.STORE.health(refresh=True)
                j["status"] = "interrupted"
                j["error"] = str(ex)
                raise
            changes.update({k: rec.get(k) for k in persisted})
        j.update(changes)
        j["heartbeat"] = time.time()
        return dict(j)


def _initial_job_identity(slug: str, meta: dict, after: int | None,
                          count: int, fill: bool,
                          ceiling: int | None) -> dict:
    total = len(meta.get("episodes") or [])
    start = max(1, min(int(after or 1), total))
    if fill:
        stop = min(total, int(ceiling or total))
        chapters = list(range(start, stop + 1))
    else:
        stop = min(total, int(ceiling or total), start + max(1, count) - 1)
        chapters = list(range(start, stop + 1))
    if not chapters:
        chapters = [start]
    args = argparse.Namespace(model=DEFAULT_MODEL, temperature=0.3)
    return lt.job_identity(slug, chapters, meta, args)


def forced_targets(after: int, want: int, ceiling: int, total: int) -> list[int]:
    """force 重翻时明确指定要翻的章节（绕开 next_targets 的「只补缺译」）。

    术语表过期重翻针对的是**已有译文**的章节；`next_targets` 永远跳过它们，
    所以这里必须按 `after/count/ceiling` 直接给范围，并夹在全书内。
    """
    a = max(1, int(after))
    w = max(1, int(want))
    c = int(ceiling or a)
    return list(range(a, min(int(total), c, a + w - 1) + 1))


def start_job(slug: str, count: int = 2, reason: str = "auto",
              after: int | None = None, fill: bool = False,
              ceiling: int | None = None,
              resume_of: str | None = None,
              force: bool = False) -> dict:
    meta_for_total = novel_meta(slug) or {}
    if not ceiling:
        # 持续翻译模型里没有"读到 + N 章"上限：不给 ceiling 就翻到全书。
        # 踩过：阅读页 tick 不带 ceiling → allowed_targets 用旧的 auto_ceiling，
        # 而 enabled 已废弃 → 返回空 → worker 建一条"未开启翻译"的 done 任务，
        # 界面上就是"点了没反应/卡住"。
        ceiling = len(meta_for_total.get("episodes") or [])
    with LOCK:
        j = JOBS.get(slug)
        if j and j["status"] in ("queued", "running"):
            return j
        durable = jobstore.STORE.active(slug)
        if durable:
            view = jobstore.STORE.public_view(durable)
            JOBS[slug] = dict(view, at=time.time(), heartbeat=time.time(),
                              token=time.time_ns(), job_id=durable["job_id"])
            return JOBS[slug]
        meta = novel_meta(slug)
        if not meta:
            raise RuntimeError("作品不存在")
        identity = _initial_job_identity(slug, meta, after, count, fill, ceiling)
        try:
            rec = jobstore.STORE.create(
                slug=slug,
                target=identity["target"],
                model_provider=identity["model_provider"],
                model_role=identity["model_role"],
                model_id=identity["model_id"],
                translation_config_hash=identity["translation_config_hash"],
                idempotency_key=identity["idempotency_key"],
                requested={
                    "count": int(count), "reason": reason, "after": after,
                    "fill": bool(fill), "ceiling": ceiling,
                    "resume_of": resume_of, "force": bool(force),
                },
                source_entries=identity["sources"],
            )
        except jobstore.ActiveJobExists as ex:
            rec = ex.record
            JOBS[slug] = dict(jobstore.STORE.public_view(rec),
                              at=time.time(), heartbeat=time.time(),
                              token=time.time_ns(), job_id=rec["job_id"])
            return JOBS[slug]
        JOBS[slug] = {
            "slug": slug, "status": "queued", "done": 0, "count": count,
            "reason": reason, "after": after, "fill": fill,
            "ceiling": ceiling, "force": bool(force), "message": "排队中",
            "at": time.time(), "heartbeat": time.time(), "error": None,
            "job_id": rec["job_id"], "reset_status": "idle",
            # token：识别"这次任务"。心跳超时被判 error 后用户重试会建新 JOBS，
            # 旧任务靠它认出自己已被取代（见 worker）。
            "token": time.time_ns(),
        }
        JOBS_Q.put((slug, count, int(time.time()), JOBS[slug]["token"]))
        return JOBS[slug]


# ---------------------------------------------------------------- 翻译调度
# 状态单独放 data/sched.json（不塞进每本书的 books/*.json）：
# 调度是"全局"概念（队列顺序、每日预算、谁在读），按书写状态会让它四散。
SCHED = sched_mod.Scheduler()


def note_reading(slug: str, persist: bool = False) -> None:
    """读者在读这本书：刷新"最近在读"时间，调度器据此持续翻它。

    已读完 / 已弃文的不算"在读"：那是"我不看了"的明确信号，
    再自动翻就是替用户花钱（踩过：标了读完还会继续译）。
    `persist=False` 给高频路径（轮询/渲染）用：只更新内存，
    减少手机闪存上的 fsync；进程重启后最多丢 30 秒的"正在读"。
    """
    if not slug:
        return
    try:
        _bd = _read_book(slug)
        if _bd.get("finished") or _bd.get("dropped"):
            return
        # 打开页面但**还没读**（进度为 0 且从未读过）→ 不自动开翻。
        # 否则"点开看一眼"就会让调度器开始翻整本（一本 133 章 ≈ 45 万 token）。
        # 真正读起来（进度上报 ≥1 章）才开始，这是"我在读"的最小证据。
        _pr = _bd.get("progress") or {}
        if int(_pr.get("chapter") or 0) <= 0 and not _pr.get("at"):
            _q = (SCHED.state["books"].get(slug) or {}).get("queued_at")
            if not _q:
                return
        SCHED.note_read(slug, persist=persist)
    except Exception:  # noqa: BLE001 - 调度状态坏了也不能影响阅读
        pass


def _first_missing_chapter(slug: str) -> int:
    """下一章翻哪：第一个缺译的章。

    但**反复失败的章不许堵住整本**：翻译失败会把它写进
    `meta.progress.incomplete`（见 lntrans._translate_chapter_impl）。如果永远
    只挑"第一个缺的"，一个模型死活翻不动的毒章会让这本书永久卡在那一章
    （踩过：第 49 章某段连续失败 → 每轮重试同一章 → 界面「已译 48/54」一动不动，
    GPU 一直忙）。所以先跳过已知失败的章，把后面的补完；只剩毒章时才回头重试。
    成功落盘会把它从 incomplete 里移除（lntrans 成功分支），跳过自然是临时的。
    """
    meta = novel_meta(slug) or {}
    total = len(meta.get("episodes") or [])
    targets = next_targets(slug, meta, max(1, total), None)
    if not targets:
        return 0
    inc = set((meta.get("progress") or {}).get("incomplete") or [])
    for c in targets:
        if c not in inc:
            return int(c)
    return int(targets[0])


def _any_job_active() -> bool:
    with LOCK:
        return any((j or {}).get("status") in ("queued", "running")
                   for j in JOBS.values())


def _translation_dispatcher() -> None:
    """唯一的"下一步翻什么"决策者。

    旧模型把策略写在阅读页和 worker 里（读到 + N 章），结果是：
      · 读者连读几章必然断粮（用户原话"翻译跟不上我阅读的速度"）；
      · 想提前攒书没有入口；
      · 策略一改就要真跑一遍模型才能验证。
    现在策略全在 lnsched（纯函数、有单元测试），这里只做三件事：
    问调度器要一本书 → 用现有 start_job 翻一批 → 循环。
    """
    # 自检的隔离服务里**不跑**调度线程：测试用 fixture 精确控制"哪一章被翻"，
    # 后台自动开翻会把断言变成竞态（踩过：fill 测试撞上一个自动任务，
    # 拿到的是别人的 after=0）。真实服务不受影响。
    if os.environ.get("LNTRANS_TEST_SERVER"):
        return
    while not STOP.is_set():
        STOP.wait(2.0)
        try:
            if JOBS_READ_ONLY:
                # 任务日志损坏 → 只读恢复模式：翻译写入会被拒（503）。
                # 这里也要停手，否则每 30 秒刷一条异常日志，还会掩盖真问题。
                STOP.wait(60)
                continue
            if SCHED.blocked_globally():
                continue
            if _any_job_active():
                continue
            act = SCHED.pick(_first_missing_chapter_wrap)
            if not act:
                continue
            meta = novel_meta(act.slug)
            if not meta:
                continue
            total = len(meta.get("episodes") or [])
            first = _first_missing_chapter(act.slug)
            if not first:
                continue
            start_job(act.slug, act.count, act.reason,
                      after=max(0, first - 1), ceiling=total)
        except (Exception, SystemExit) as _e:  # noqa: BLE001
            # 每 2 秒刷一次栈会把日志淹掉（而且掩盖真正的问题）。打一次、退避。
            print(f"[调度] 本轮出错（30 秒后重试）：{type(_e).__name__}: {_e}",
                  flush=True)
            STOP.wait(30)


def _first_missing_chapter_wrap(slug: str) -> list:
    n = _first_missing_chapter(slug)
    return [n] if n else []


JOB_STALE_SEC = int(os.environ.get("LNTRANS_JOB_STALE_SEC", "240"))  # 任务超过这个时间没更新，判定为卡死
# 心跳在每段/每章都会更新（model 调用本身一般 < 60s），所以 240s 没动静
# 一定是真卡了。原来写 900s：用户看着「正在翻译」发呆 15 分钟 —— 太长了。
JOB_STALL_LOG_SEC = int(os.environ.get("LNTRANS_JOB_STALL_LOG_SEC", "120"))  # 只打诊断不判死


# SIGUSR1 → 把全部线程栈写进日志（`kill -USR1 <pid>`），不杀进程。
# 为什么要它：翻译"卡住"时，进程还活着、接口也回 200，但 worker 线程卡在某把锁上 ——
# 没有栈就只能猜。faulthandler 是标准库里唯一能在不重启的前提下拿到栈的工具。
try:
    if hasattr(signal, "SIGUSR1"):
        faulthandler.register(signal.SIGUSR1, all_threads=True)
except Exception:  # noqa: BLE001 - 注册失败不影响服务
    pass


def _job_watchdog() -> None:
    """卡死自诊断：心跳停了 JOB_STALL_LOG_SEC 秒就 dump 一次全线程栈。

    只诊断、不判死（判定仍由 JOB_STALE_SEC 走 job_view 的收尸逻辑）：
    提前把栈打进日志，事后能看出卡在拿锁、写盘还是模型请求上。
    每个任务只 dump 一次，避免刷屏。
    """
    dumped: set[str] = set()
    while not STOP.is_set():
        STOP.wait(30)
        try:
            now = time.time()
            with LOCK:
                snap = [(slug, dict(j)) for slug, j in JOBS.items()
                        if j.get("status") in ("queued", "running")]
            for slug, j in snap:
                hb = float(j.get("heartbeat") or j.get("at") or 0)
                jid = str(j.get("job_id") or slug)
                if now - hb > JOB_STALL_LOG_SEC and jid not in dumped:
                    dumped.add(jid)
                    print(f"[诊断] 任务 {jid}（{slug}）心跳已停 "
                          f"{int(now - hb)}s，dump 全线程栈：", flush=True)
                    faulthandler.dump_traceback(all_threads=True)
        except Exception:  # noqa: BLE001 - 看门狗自己不许把服务搞挂
            pass


def cancel_job(slug: str, disable: bool = True) -> dict:
    """停止本书的翻译：换掉 token（worker 下一次检查就停手）+ 关掉自动翻译。

    为什么必须关掉自动翻译：worker 一停，阅读页的 `tick()` 下一轮还会按
    「读到哪翻到哪」再排一次 —— 用户点"停止"后它自己又转起来，等于按钮骗人。
    LLM 调用本身不可中断，正在译的那一章会译完才停，文案要说清楚。
    """
    with LOCK:
        j = JOBS.setdefault(slug, {})
        j["token"] = time.time_ns()
        j["status"] = "cancelled"
        j["message"] = "已停止"
        j["error"] = None
        j["heartbeat"] = time.time()
        job_id = j.get("job_id")
        if job_id:
            try:
                jobstore.STORE.update(
                    job_id, status="cancelled", error=None,
                    message="已停止")
            except jobstore.JobError as ex:
                j["error"] = str(ex)
    if disable:
        try:
            set_trans_cfg(slug, enabled=False)
        except Exception as e:  # noqa: BLE001
            print(f"  停止时关闭自动翻译失败：{type(e).__name__}: {e}", flush=True)
    return {"ok": True, "status": "cancelled", "enabled": False}


def _note_trans_error(slug: str, msg: str) -> None:
    """把翻译失败**落到书上**，不只留在 JOBS 内存里。

    踩过（互评指出）：卡片上的「翻译失败 / 重试」原来只读 `JOBS` 内存态，
    服务一重启痕迹全无，用户下次打开书架看不出哪本失败过 —— 与 README 承诺不符。
    这里只写两个字段，卡片读 item（零 I/O），不进 history。
    """
    if JOBS_READ_ONLY:
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    text = (msg or "翻译失败").strip()[:300]

    def fn(d: dict) -> None:
        d["trans_error"] = text
        d["trans_error_at"] = ts

    try:
        update_book(slug, fn)
    except Exception as e:  # noqa: BLE001
        print(f"  记录翻译失败痕迹失败：{type(e).__name__}: {e}", flush=True)


def _clear_trans_error(slug: str) -> None:
    """任务成功结束时清掉失败痕迹（置位/清除必须成对，否则徽标永远亮着）。"""
    if JOBS_READ_ONLY:
        return
    def fn(d: dict) -> None:
        d.pop("trans_error", None)
        d.pop("trans_error_at", None)

    try:
        update_book(slug, fn)
    except Exception as e:  # noqa: BLE001
        print(f"  清除翻译失败痕迹失败：{type(e).__name__}: {e}", flush=True)


def job_view(slug: str) -> dict:
    """给前端看的任务状态，带"卡死"兜底。

    踩过：worker 若在翻译中途异常退出，JOBS[slug] 会永远停在 running，
    前端就会一直轮询、永远等下去。这里按时间戳把僵尸任务标成 error，
    前端收到 error 会停下来并让用户重试。
    """
    with LOCK:
        j = dict(JOBS.get(slug) or {})
    if not j:
        latest = jobstore.STORE.latest(slug)
        view = jobstore.STORE.public_view(latest)
        view["pending_confirmation"] = view.get("status") == "interrupted"
        # 轮询路径（前端每 2.5s 一次）不许反复全目录扫描任务日志；
        # 缓存由 create/reconcile/显式 health(refresh=True) 维护。
        view["read_only"] = jobstore.STORE.health(refresh=False).get("read_only", False)
        return view
    if j.get("job_id"):
        try:
            rec = jobstore.STORE.get(j["job_id"])
        except jobstore.JobError as ex:
            # 活动任务自己的记录损坏：按「任务日志损坏」处理 —— 停止调度、
            # 让前端进入「等待确认恢复」，而不是把 500 抛给 /api/job。
            rec = None
            j["error"] = str(ex)
            j["read_only"] = True
            j["status"] = "interrupted"
            j["message"] = "任务记录损坏，已停止调度；阅读与书架不受影响"
        if rec:
            view = jobstore.STORE.public_view(rec)
            for key in ("message", "done", "count", "reason", "after",
                        "fill", "ceiling", "targets", "translated", "total",
                        "heartbeat", "token", "at"):
                if key in j:
                    view[key] = j[key]
            j = view
    if j.get("status") in ("queued", "running"):
        if time.time() - float(j.get("heartbeat") or j.get("at") or 0) > JOB_STALE_SEC:
            with LOCK:
                if slug in JOBS:
                    JOBS[slug]["status"] = "interrupted"
                    JOBS[slug]["error"] = "任务超时（可能翻译中断），等待确认恢复"
                    job_id = JOBS[slug].get("job_id")
                    if job_id:
                        try:
                            jobstore.STORE.update(
                                job_id, status="interrupted",
                                error="任务超时（可能翻译中断），等待确认恢复")
                        except jobstore.JobError:
                            pass
            j["status"] = "interrupted"
            j["error"] = "任务超时（可能翻译中断），等待确认恢复"
            # worker 线程可能已经死了，这里是唯一的"收尸"点 → 顺手落到书上。
            _note_trans_error(slug, j["error"])
    if not j.get("job_id"):
        latest = jobstore.STORE.latest(slug)
        if latest:
            j["job_id"] = latest["job_id"]
    j["pending_confirmation"] = j.get("status") == "interrupted"
    # 目标记录本身损坏时上面已把 read_only 置 True：别被缓存里的
    # 「其他记录都健康」覆盖掉。
    j["read_only"] = bool(j.get("read_only")) or \
        jobstore.STORE.health(refresh=False).get("read_only", False)
    return j


def worker() -> None:
    while not STOP.is_set():
        try:
            slug, count, _, q_token = JOBS_Q.get(timeout=0.5)
        except queue.Empty:
            continue
        my_token = None
        with LOCK:
            # token 用来识别"我还是当前这个任务吗"。任务被判超时后用户重试，
            # 会为同一 slug 建一份新 JOBS；旧任务每次更新前先核对 token，
            # 不是自己就停手 —— 否则两个任务会重复翻译同一章、互相覆盖状态。
            # 排队项也要带 token：否则"刚入队就点停止"时，worker 会把新 token
            # 当成自己的 → 把 cancelled 改回 running，停止按钮等于没按。
            cur = JOBS.get(slug) or {}
            if cur.get("token") != q_token or cur.get("status") == "cancelled":
                # 这个队列项已经被取走；不 task_done 会让 unfinished_tasks
                # 永久留下一个幽灵任务。
                JOBS_Q.task_done()
                continue
            my_token = q_token
            JOBS.setdefault(slug, {})["status"] = "running"
            JOBS[slug]["message"] = "准备中"
            JOBS[slug]["heartbeat"] = time.time()
            my_job_id = JOBS[slug].get("job_id")
        try:
            _sync_job(slug, my_token, status="running", message="准备中")
            meta = novel_meta(slug)
            if not meta:
                raise RuntimeError("作品不存在")
            total = len(meta.get("episodes") or [])
            existing = zh_chapters(slug, total)
            # `done` 是**本次任务**翻了几章，`translated` 是全书累计已译。
            # 进度条必须用后者；否则从第 50 章补译时，进度会从 50 掉到 1。
            with LOCK:
                JOBS[slug]["translated"] = len(existing)
                JOBS[slug]["total"] = total
            try:
                after = int(JOBS[slug].get("after") or 0) or None
            except (TypeError, ValueError):
                after = None
            want = 9999 if JOBS[slug].get("fill") else max(1, count)

            # 顺手把章节名翻成中文（一次请求、极便宜）。
            # 不做的话目录和章节大标题永远是日文 ——
            # 用户要求「你汉化完了显示汉化章节，我点进去来看，这样清晰明了」。
            # 放在**算 targets 之前**：整本都翻完的书（targets 为空）也得能补标题，
            # 否则"章节名翻译"永远不会触发。只翻到"读得到的范围"，
            # 200 章的书不必为读前 3 章就把 200 个标题全翻了。
            try:
                if trans_cfg(slug)["enabled"]:      # 没开翻译的书一个 token 都不花
                    ensure_zh_titles(slug, upto=min(
                        total, max(auto_ceiling(slug, meta), len(existing) + 5)))
                    meta = novel_meta(slug) or meta
            except Exception as e:  # noqa: BLE001
                print(f"  章节名翻译失败（不影响正文）：{type(e).__name__}: {e}",
                      flush=True)

            # 受翻译策略约束：未开启 → 空；已开启 → 读到 + ahead 为上限。
            # force（术语表过期重翻）是用户对**已有译文**的明确指令，
            # 必须绕过 next_targets（它只挑"缺译"的章）。
            _force = bool(JOBS[slug].get("force"))
            if _force and after:
                _ceil = int(JOBS[slug].get("ceiling") or after)
                targets = forced_targets(after, want, _ceil, total)
                ceiling = _ceil
            else:
                targets, ceiling = allowed_targets(
                    slug, meta, want, after,
                    explicit_ceiling=JOBS[slug].get("ceiling"))
            if not targets:
                cfg = trans_cfg(slug)
                why = ("没有可翻的章节（已全部译完，或目标都已有译文）")
                _sync_job(
                    slug, my_token, status="done", message=why,
                    done=len(existing), idle_reason=why,
                    remaining_chapters=[], completed_chapters=[])
                continue

            args = argparse.Namespace(
                slug=slug, count=1, from_chapter=targets[0], force=_force,
                summary=False, dry_run=False, allow_missing=False,
                model=DEFAULT_MODEL, temperature=0.3,
            )
            identity = lt.job_identity(slug, targets, meta, args)
            _sync_job(
                slug, my_token, status="running",
                target=identity["target"],
                chapter_numbers=targets,
                remaining_chapters=targets,
                completed_chapters=[],
                partial_chapters=[],
                sources=identity["sources"],
                model_provider=identity["model_provider"],
                model_role=identity["model_role"],
                model_id=identity["model_id"],
                translation_config_hash=identity["translation_config_hash"],
                idempotency_key=identity["idempotency_key"],
                targets=targets, done=0,
            )
            completed: list[int] = []
            remaining: list[int] = list(targets)
            partials: list[int] = []
            terminal_status = None
            terminal_error = None

            # 原文**按需逐章抓**（就在下面循环里、紧挨着翻译前抓这一章）。
            # 踩过：原先把整本原文一次抓完再翻 —— 「翻到第 185 章」时先静默下载
            # ~9 分钟、期间已译恒为 0、界面没有任何进度，看着就像卡死。
            # 逐章抓之后，第一段译文几秒内就出现，进度随章推进。
            for _n, i in enumerate([t - 1 for t in targets], 1):
                cur = _sync_job(
                    slug, my_token, message=f"抓取第 {i+1} 章原文")
                if not cur:
                    break        # 已被新任务取代：停手，别再花 token
                meta = novel_meta(slug) or meta
                try:
                    lt.ensure_raw(slug, meta, i + 1, quiet=True)
                except Exception as e:  # noqa: BLE001
                    terminal_status = "provider_error"
                    terminal_error = (
                        f"抓取第 {i+1} 章原文失败：{type(e).__name__}: {e}")
                    _sync_job(
                        slug, my_token, status=terminal_status,
                        error=terminal_error,
                        message=f"抓取第 {i+1} 章原文失败")
                    break
                cur = _sync_job(
                    slug, my_token,
                    message=f"正在翻译第 {i+1} 章")
                if not cur:
                    break
                meta = novel_meta(slug) or meta
                # 抓到原文后身份从 episode-id 升级为真实 source hash。
                identity = lt.job_identity(slug, targets, meta, args)
                _sync_job(
                    slug, my_token,
                    sources=identity["sources"],
                    translation_config_hash=identity["translation_config_hash"],
                    idempotency_key=identity["idempotency_key"])
                ok = False

                def _prog(ci, n, _i=i, _tok=my_token):
                    """章内进度：长章一次要十几段，只写"正在翻译第 N 章"会像卡死。"""
                    try:
                        _sync_job(
                            slug, _tok,
                            message=f"第 {_i+1} 章 · 段 {ci}/{n}")
                    except jobstore.JobError:
                        # 进度上报失败不能反过来打断正在进行的模型请求；真正的
                        # 只读状态会在请求返回后的落盘阶段被检查。
                        pass

                try:
                    ok = lt.translate_chapter(slug, i, meta, args, progress=_prog)
                except SystemExit:
                    raise
                except Exception as e:  # noqa: BLE001
                    terminal_status = (
                        "budget_exhausted"
                        if isinstance(e, lt.lnmodels.BudgetExceeded)
                        else "provider_error")
                    terminal_error = f"{type(e).__name__}: {e}"
                    _sync_job(
                        slug, my_token, status=terminal_status,
                        error=terminal_error, message=f"第 {i+1} 章失败")
                    break
                with LOCK:
                    call_still_current = (
                        (JOBS.get(slug) or {}).get("token") == my_token)
                # 写端显式失效（成功/停止/失败都要）：低精度文件系统上
                # mtime 可能没变；本章的 raw 与译文都是 worker 刚写过的。
                invalidate_cache(slug, i)
                _META_CACHE.pop(slug, None)
                if not call_still_current:
                    # 中途点了「停止」：模型请求不可中断，本章可能已译完。
                    # 不覆盖 cancelled 状态，但把实际可读的章节补进已取消任务，
                    # 这样任务日志仍能准确说明"停在哪、哪些已可用"。
                    if ok:
                        chapter_result = lt.last_chapter_result()
                        completed.append(i + 1)
                        if i + 1 in remaining:
                            remaining.remove(i + 1)
                        if chapter_result.get("partial"):
                            partials.append(i + 1)
                        _rec = jobstore.STORE.get(my_job_id) or {}
                        if _rec.get("status") == "cancelled":
                            _u = dict(_rec.get("usage") or {
                                "input": 0, "output": 0})
                            _t = chapter_result.get("tokens") or {}
                            _c = dict(_rec.get("cost") or {
                                "amount": 0, "currency": "CNY",
                                "estimated": True})
                            jobstore.STORE.update(
                                my_job_id,
                                completed_chapters=completed,
                                remaining_chapters=remaining,
                                partial_chapters=partials,
                                usage={
                                    "input": int(_u.get("input", 0))
                                    + int(_t.get("input", 0) or 0),
                                    "output": int(_u.get("output", 0))
                                    + int(_t.get("output", 0) or 0),
                                },
                                cost={
                                    "amount": round(
                                        float(_c.get("amount", 0))
                                        + float((chapter_result.get("cost") or {})
                                                .get("amount", 0) or 0), 8),
                                    "currency": _c.get("currency") or "CNY",
                                    "estimated": True,
                                },
                                message=f"已停止；第 {i+1} 章已译完")
                    break
                with LOCK:
                    # done = 本次任务**已完成段数**（不是章号：补译从第 5 章起时，
                    # 章号 5 并不等于"译了 5 段"）。前端按"已译 N 章"显示。
                    JOBS[slug]["done"] = _n
                if not ok:
                    # 失败也花了 token（日志/`_CHAPTER_RESULT` 里记着）。
                    # 不记账的话，连续失败时预算永远"还有钱"，会一直重试下去。
                    try:
                        _cf = lt.last_chapter_result() or {}
                        _ct = _cf.get("tokens") or {}
                        _ctok = int(_ct.get("input", 0) or 0) + int(_ct.get("output", 0) or 0)
                        _ccost = float((_cf.get("cost") or {}).get("amount", 0) or 0)
                        if _ctok:
                            SCHED.add_usage(_ctok, cost=_ccost)
                    except Exception:  # noqa: BLE001
                        pass
                    # 有分段失败：**不登记为已译**（否则"已译 N 章"会虚报），
                    # 给用户明确错误 + 可重试提示，而不是静默 done。
                    terminal_status = "provider_error"
                    terminal_error = (
                        f"第 {i+1} 章有段落翻译失败（原文保留，可重试）")
                    _sync_job(
                        slug, my_token, status=terminal_status,
                        error=terminal_error, message=f"第 {i+1} 章失败")
                    break
                chapter_result = lt.last_chapter_result()
                # 不用手工失效整本：zh_chapters 按章比对文件签名，新章
                # 只会让那一章重算，其余章节命中缓存。
                completed.append(i + 1)
                if i + 1 in remaining:
                    remaining.remove(i + 1)
                if chapter_result.get("partial"):
                    partials.append(i + 1)
                rec = jobstore.STORE.get(my_job_id) or {}
                usage = dict(rec.get("usage") or {"input": 0, "output": 0})
                tokens = chapter_result.get("tokens") or {}
                old_cost = dict(rec.get("cost") or {
                    "amount": 0, "currency": "CNY", "estimated": True})
                chapter_cost = float((chapter_result.get("cost") or {}).get(
                    "amount", 0) or 0)
                new_usage = {
                    "input": int(usage.get("input", 0))
                    + int(tokens.get("input", 0) or 0),
                    "output": int(usage.get("output", 0))
                    + int(tokens.get("output", 0) or 0),
                }
                new_cost = {
                    "amount": round(float(old_cost.get("amount", 0))
                                    + chapter_cost, 8),
                    "currency": old_cost.get("currency") or "CNY",
                    "estimated": True,
                }
                _job_limit = lnmodels.job_budget()
                try:
                    _tok = (tokens.get("input", 0) or 0) + (tokens.get("output", 0) or 0)
                    if _tok:
                        SCHED.add_usage(int(_tok), cost=chapter_cost)
                except Exception:  # noqa: BLE001 - 记账失败不该影响翻译
                    pass
                with LOCK:
                    # 翻完一章就更新全书累计数，轮询期间进度只会前进。
                    JOBS[slug]["translated"] = len(zh_chapters(slug, total))
                if (chapter_result.get("budget_exhausted")
                        or (_job_limit > 0
                            and new_cost["amount"] >= _job_limit)):
                    terminal_status = "budget_exhausted"
                    if (_job_limit > 0
                            and new_cost["amount"] >= _job_limit):
                        terminal_error = (
                            f"本任务费用已达 {new_cost['amount']:.4f} "
                            f"{new_cost['currency']}（上限 {_job_limit:.2f}）；"
                            "已完成章节可读")
                    else:
                        terminal_error = (
                            f"第 {i+1} 章触发 token 预算上限；已有译文可读，"
                            "等待确认后继续")
                _sync_job(
                    slug, my_token, status=terminal_status or "running",
                    error=terminal_error,
                    message=(terminal_error or
                             f"已译第 {i+1} 章，继续"),
                    completed_chapters=completed,
                    remaining_chapters=remaining,
                    partial_chapters=partials,
                    usage=new_usage,
                    cost=new_cost,
                    done=_n)
                if terminal_status:
                    break
                time.sleep(0.4)
            # 失败的痕迹要落到书上（卡片在重启后仍能显示「翻译失败 / 重试」）。
            # 这里的 `_outcome` 在锁内算好、**锁外**写盘 —— update_book 也用 LOCK，
            # 持锁调用会自锁死。
            _outcome = None
            n_have = len(existing)
            final_status = "interrupted"
            final_message = "任务已停止"
            _superseded = False
            with LOCK:
                if (JOBS.get(slug) or {}).get("token") != my_token:
                    _superseded = True
                else:
                    j = JOBS[slug]
                    n_have = len(zh_chapters(slug, total))
                    final_status = terminal_status
                    if final_status is None:
                        final_status = "partial" if partials else "done"
                    if final_status in ("provider_error", "budget_exhausted"):
                        _outcome = ("error",
                                    terminal_error or j.get("error") or "翻译中止")
                    else:
                        if completed:
                            _outcome = ("ok", "")
                    j["status"] = final_status
                    j["message"] = (
                        terminal_error if terminal_error else
                        ("部分译完，可稍后补齐" if final_status == "partial"
                         else f"已译 {n_have}/{total} 章"))
                    final_message = j["message"]
                    j["error"] = terminal_error
                    j["translated"] = n_have
                    j["total"] = total
            if _superseded:
                # 被取代的 worker 走到收尾时 token 已不匹配，`_sync_job` 会静默
                # 跳过 —— 必须按 job_id 自己把记录关掉，否则永远停在 running。
                _close_own_record(my_job_id, completed, remaining)
            _sync_job(
                slug, my_token,
                status=final_status,
                message=final_message,
                error=terminal_error,
                completed_chapters=completed,
                remaining_chapters=remaining,
                partial_chapters=partials,
                translated=n_have,
                total=total)
            if _outcome:
                if _outcome[0] == "ok":
                    _clear_trans_error(slug)
                else:
                    _note_trans_error(slug, _outcome[1])
        except (Exception, SystemExit) as e:  # noqa: BLE001
            # 连 SystemExit 一起接住：lt.die()（如缺 API key）会 sys.exit，
            # 只 catch Exception 接不住 —— worker 线程会直接死掉，之后所有翻译
            # 任务都没人跑、永远卡在 running（踩过：缺 key 时整条队列瘫痪）。
            _emsg = ""
            with LOCK:
                if (JOBS.get(slug) or {}).get("token") == my_token:
                    if isinstance(e, lt.lnmodels.BudgetExceeded):
                        JOBS.setdefault(slug, {})["status"] = "budget_exhausted"
                        _emsg = str(e)
                        JOBS[slug]["error"] = _emsg
                    elif isinstance(e, jobstore.JobRecordMissing):
                        # 记录被删 ≠ 模型失败：停这个任务，写清原因，但**不**把
                        # 「翻译失败」徽标落到书上（那会误导用户去查模型/网络），
                        # 也不把整站任务写入锁死（没有坏文件要隔离）。
                        JOBS.setdefault(slug, {})["status"] = "interrupted"
                        JOBS[slug]["message"] = (
                            "任务记录丢失，已停止调度（可重新开始翻译）")
                        JOBS[slug]["error"] = str(e)
                    elif isinstance(e, jobstore.RecoveryRequired):
                        JOBS.setdefault(slug, {})["status"] = "interrupted"
                        _emsg = str(e)
                        JOBS[slug]["error"] = _emsg
                    elif isinstance(e, SystemExit):
                        code = getattr(e, "code", None)
                        detail = f"退出码 {code}" if code not in (None, 0) else "已退出"
                        JOBS.setdefault(slug, {})["status"] = "provider_error"
                        _emsg = f"翻译中止（{detail}）"
                        JOBS[slug]["error"] = _emsg
                    else:
                        JOBS.setdefault(slug, {})["status"] = "provider_error"
                        _emsg = f"{type(e).__name__}: {e}"
                        JOBS[slug]["error"] = _emsg
            if _emsg:
                try:
                    _estatus = (JOBS.get(slug) or {}).get(
                        "status", "provider_error")
                    _sync_job(
                        slug, my_token, status=_estatus,
                        error=_emsg, message="翻译中止")
                except jobstore.JobError:
                    pass
            if _emsg:
                _note_trans_error(slug, _emsg)
        finally:
            JOBS_Q.task_done()


# ------------------------------------------------------------------ 页面

CSS = lr.CSS + _read_static("app.css")
# New UI stylesheet is intentionally separate and scoped to [data-ui="next"].
# Reading it at startup makes a missing/empty file fail fast instead of silently
# serving an unstyled preview.
LNUI_CSS = lnui.css()
LNUI_PREVIEW_JS = lnui.preview_js()
LNUI_SETTINGS_JS = lnui.settings_js()
LNUI_READER_JS = _read_static("lnui-reader.js")

# 主题初始化：所有页面都必须有（漏一页就是「这一页不跟设置」）。
# 放进 PWA_HEAD，任何使用 PWA_HEAD 的页面自动获得；页面里已有的更早同类脚本
# 重复执行是幂等的（同样的 localStorage 值算出同样的 data-t），还能防首屏闪烁。
THEME_BOOT = ('<script>(function(){var s=null,f=null,h=null;'
              'try{s=localStorage.getItem(\'ln-theme\');'
              'f=localStorage.getItem(\'ln-fs\');'
              'h=localStorage.getItem(\'ln-lh\');}catch(e){}'
              'var d=(s===\'dark\'||s===\'light\')?s:'
              '(matchMedia(\'(prefers-color-scheme: dark)\').matches?\'dark\':\'light\');'
              'var r=document.documentElement;r.setAttribute(\'data-t\',d);'
              'r.style.colorScheme=d;'
              'if(f===\'s\'||f===\'l\')r.setAttribute(\'data-fs\',f);'
              'if(h===\'tight\'||h===\'loose\')r.setAttribute(\'data-lh\',h);})();</script>')

# PWA：加到主屏后像 App（standalone），主题色跟**用户选的主题**（不只是系统）。
# 每页 head 的 inline 脚本先写好 data-t，这里跟着它更新 theme-color；
# 设置页切换主题会触发 MutationObserver，不需要额外接口。
# Service Worker 故意不做：本站是本地单用户、离线读不了正文，缓存旧页面反而更糟。
PWA_HEAD = (THEME_BOOT +
            '<link rel="manifest" href="/manifest.webmanifest">'
            '<meta name="theme-color" content="#f7f5f0">'
            '<link rel="apple-touch-icon" href="/icon-192.png">'
            '<script>(function(){var m=document.querySelector(\'meta[name="theme-color"]\');'
            'if(!m)return;function u(){m.setAttribute("content",'
            'document.documentElement.getAttribute("data-t")==="dark"?"#151413":"#f7f5f0");}'
            'u();if(typeof MutationObserver==="function"){new MutationObserver(u).observe('
            'document.documentElement,'
            '{attributes:true,attributeFilter:["data-t"]});}'
            'try{matchMedia("(prefers-color-scheme: dark)").addEventListener("change",u);}'
            'catch(e){}'
            '})();</script>')

ACTION_JS = _read_static("action.js")

LIB_JS = _read_static("lib.js")

# 「不感兴趣」：推荐页 / 书库页 / 标签页共用同一段脚本
# （这三个页面都会渲染带 data-dislike 的卡片；只写一遍，避免漏改某处）
DISLIKE_JS = _read_static("dislike.js")

READER_JS = _read_static("reader.js")
REVIEW_JS = _read_static("review.js")
QUEUE_JS = _read_static("queue.js")
META_JS = _read_static("meta.js")


def _item_watches(it: dict) -> bool:
    """这张卡对应的书现在还会被查更新吗（与 watch_list() 同判定，零 I/O）。

    watch_list() 走 book_status()；卡片已经拿着同一份 item，所以这里用
    item 里的 favorite/finished/dropped/read/total/dormant 直接判断，
    避免每张卡再读一次书状态文件（卡片路径的性能红线）。
    """
    if it.get("favorite"):
        return True
    if it.get("dropped") or it.get("finished"):
        return False
    if it.get("total") and it.get("read", 0) >= it["total"]:
        return False
    return not it.get("dormant")


def _card(it: dict, jobs: dict) -> str:
    js = jobs.get(it["slug"]) or {}
    running = js.get("status") in ("queued", "running")
    if it["translated"] >= it["total"]:
        pill, cls = "已全译", "pill ok"
    elif running:
        pill, cls = "翻译中", "pill run"
    else:
        pill, cls = f"{it['translated']}/{it['total']} 章", "pill"
    pct = it["translated"] / max(it["total"], 1) * 100
    fav = "★ " if it["favorite"] else ""
    read = f"读到第 {it['read']} 章" if it["read"] > 1 else ""
    # 徽标 = 「收藏」（正交维度）+ 一个 tracking 状态；两者可同时出现
    tk = it.get("tracking") or "want"
    badge = ""
    if it["favorite"]:
        badge += '<span class="badge fav">收藏</span>'
    if tk == "finished":
        badge += '<span class="badge fin">看完</span>'
    elif tk == "dropped":
        badge += '<span class="badge drop">弃文</span>'
    elif tk == "reading":
        badge += '<span class="badge">在读</span>'
    upd = ""
    # 上次任务失败：给一个**就在卡片上**的重试入口。
    # 失败痕迹优先读**书状态里的持久字段**（服务重启后仍在），内存里的 JOBS
    # 只用来兜住"刚失败还没落盘"的一瞬。
    err_msg = (it.get("trans_error") or "").strip()
    if not err_msg and js.get("status") in ("provider_error", "error"):
        err_msg = (js.get("error") or "上次翻译失败").strip()
    if err_msg:
        upd += (f'<span class="badge drop" title="{attrescape(err_msg)}">翻译失败</span>')
    # 旧数据可能留下「弃文/看完/移出后 has_update 仍为 True」的残留；
    # 这张卡不该再承诺「点我翻译」——它已经不进 watch_list() 了。
    if it.get("has_update") and _item_watches(it):
        n = it.get("new_episodes") or 0
        # 把"这次要翻几话"显式带给服务端：按钮上写 +N 话，就只翻 N 话
        # （服务端还会再夹到 ≤10，避免一次点击把几十话的欠账全翻完）。
        upd += (f'<button class="badge new act" data-act="fill" data-n="{max(1, min(n or 2, 10))}" '
               f'title="翻译本次新增的章节">新增{f" {n} 话" if n else ""} · 翻译'
               f'</button>')
    go = it["read"] if it["read"] > 1 else 1
    if it["translated"] >= it["total"]:
        trans_btn = ('<button type="button" data-act="autotrans" disabled '
                     'title="全书已译完">已全译</button>')
    elif running:
        trans_btn = ('<button type="button" data-act="autotrans" class="on" disabled '
                     'title="正在翻译">翻译中…</button>')
    else:
        trans_btn = ('<button type="button" data-act="autotrans" '
                     'title="加入翻译列表并开始翻译">开启翻译</button>')
    hay = f"{it['title']} {it['title_zh']} {it['title_jp']} {it['author']}".lower()
    # 日文原名只在中日不同时显示第二行。
    # 踩过（用户报「书架里的书标题没翻译」）：没中文名时大标题已经是日文，
    # 下面又原样重复一遍日文 → 看着像渲染卡住了，也看不出是"没翻"。
    jp_line = (f'  <div class="jp">{lr.esc(it["title_jp"])}</div>\n'
               if it['title_jp'] and it['title_jp'] != it['title'] else '')
    _tags = [str(t) for t in (it.get("tags") or []) if t]
    tag_html = (('<div class="card-tags">'
                 + "".join(
                     f'<a class="chip tag" href="/tags?q='
                     f'{attrescape(urllib.parse.quote(t))}">{lr.esc(t)}</a>'
                     for t in _tags[:5])
                 + '</div>') if _tags else '')
    # 没中文名：给一句**准确**的状态说明 + 一个能自己做主的按钮
    name_note = ""
    if not it["title_zh"]:
        _st = batch_state(it.get("id") or "")
        if _st in ("queued", "running"):
            name_note = ('  <div class="tr-note">中文书名翻译中，完成后自动刷新</div>\n')
        elif load_detail(it.get("id") or "").get("zh_title_failed"):
            name_note = ('  <div class="tr-note">书名疑似生造词，未能翻译（保留原名）'
                         '<button class="lnkbtn" data-act="trname" style="margin-left:6px;'
                         'padding:1px 8px;font-size:.9em">重试</button></div>\n')
        else:
            name_note = ('  <div class="tr-note">中文书名尚未翻译'
                         '<button class="lnkbtn" data-act="trname" style="margin-left:6px;'
                         'padding:1px 8px;font-size:.9em">翻译书名</button></div>\n')
    return f'''<div class="card" data-slug="{attrescape(it['slug'])}" data-wid="{attrescape(it['id'])}" data-fav="{int(it['favorite'])}"
   data-read="{attrescape(it['last_read'])}" data-status="{attrescape(tk)}" data-hay="{attrescape(hay)}"
   onclick="if(!event.target.closest(&quot;button,a,summary,.moremenu&quot;))location.href=&quot;/read/{attrescape(it['slug'])}?from={go}#c{go}&quot;">
   <div class="t">{fav}{lr.esc(it['title'])}<span class="{cls}">{pill}</span>{badge}{upd}</div>
{jp_line}{name_note}  <div class="s">{lr.esc(it['author'])}{(' · ' + read) if read else ''}{(' · 搁置 ' + str(it['stale']) + ' 天') if it.get('stale') else ''}{' · 不自动查更新（再打开即恢复）' if it.get('dormant') else ''}</div>
{tag_html}
  <div class="pbar"><i style="width:{pct:.1f}%"></i></div>
  <div class="ctrls card-actions">
    <a class="lnkbtn primary" href="/read/{attrescape(it['slug'])}?from={go}#c{go}">继续阅读</a>
    {trans_btn}
    <details class="moremenu">
      <summary title="更多操作" aria-label="更多操作">⋯</summary>
      <div class="morelist">
        <button type="button" data-act="favorite" class="{'on' if it['favorite'] else ''}"
          title="收藏表示偏好：用于学习阅读口味，并始终检查更新。与能否阅读无关。">{'★ 已收藏' if it['favorite'] else '☆ 收藏'}</button>
        <button type="button" data-act="reading" class="{'on' if tk=='reading' else ''}"
          title="标记为正在阅读（不参与偏好打分）">在读</button>
        <button type="button" data-act="finished" class="{'on' if tk=='finished' else ''}"
          title="归入已读完分组，不再占用待读列表">读完</button>
        <button type="button" data-act="dropped" class="{'on' if tk=='dropped' else ''}"
          title="不再检查更新，也不参与偏好学习（会同时取消收藏）">弃文</button>
        <button type="button" data-act="off" title="从书架移除（译文保留，可随时加回）">移出书架</button>
        {'' if it.get('local') else '<button type="button" data-act="check" title="立即检查源站是否有新章节">检查更新</button>'}
        {('<button type="button" data-act="retry" title="重试上次失败的翻译">重试翻译</button>'
          if err_msg else '')}
      </div>
    </details>
  </div>
</div>'''


def ln_fmt(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0"
    return f"{n/10000:.1f}万" if n >= 10000 else str(n)


def _finding_card(it: dict) -> str:
    """推荐卡片：中文标题优先 + 简介摘要 + 我的状态 + 标签 + 加入书架。"""
    tag_list = [str(x) for x in (it.get("tags") or []) if x]
    hit_list = [str(x) for x in (it.get("hits") or []) if x]
    tags = "、".join(tag_list[:4]) + ("…" if len(tag_list) > 4 else "")
    # 「命中」经常就是标签列表的重复拷贝，单独占一行只会把卡片拉长。
    # 只有命中理由里有标签外的新信息时才显示。
    extra_hits = [x for x in hit_list if x not in tag_list]
    wid = str(it.get("id") or "")
    det = load_detail(wid) if wid else {}
    _stats = (f'<div class="s rec-stats">{lr.esc(it.get("author") or "")} · '
              f'{lr.esc(it.get("genre") or "")} · {it.get("episodes") or 0} 话</div>')
    # 标签/来源不再单独占行：卡片只回答「这是什么、我读到哪」，
    # 完整标签在详情页（手机上一条卡少两行）。
    _extra = (f'<div class="s rec-hit">命中：'
              f'{lr.esc("、".join(extra_hits[:4]))}</div>'
              if extra_hits else '')
    _ops = ('<div class="ctrls"><span class="chip ok">已在书架</span></div>'
            if it.get("on_shelf") else
            '<div class="ctrls">'
            f'<button class="primary" data-add="{attrescape(it.get("url") or "")}"'
            ' title="加入书架后可阅读与翻译；这不是收藏，也不影响偏好画像。">'
            '加入书架</button>'
            + dislike_button(wid)
            + '</div>')
    return (
        f'<div class="card rec" data-rid="{attrescape(wid)}"'
        f' data-lib="{attrescape(wid)}"'
        f' onclick="if(event.target.tagName!=&quot;BUTTON&quot;)location.href=&quot;/book?id={attrescape(wid)}&quot;">'
        + work_head(it, det)
        + work_status_chips(it)
        + f'<div class="card-foot">{_stats}{_extra}{_ops}</div></div>'
    )


def _book_zh_title(it: dict) -> str:
    """章节翻译写进 novels/<slug>/meta.json 的 zh_titles.book（仅书架上的书有）。

    列表/详情页翻译写的是 data/details/<id>.json 的 zh_title；两处都要读，
    否则同一本书在推荐卡是中文、在书库/书架上是日文（用户报过）。
    """
    slug = it.get("slug") or ""
    if not slug:
        wid = str(it.get("id") or "")
        slug = slug_for_source(wid) if wid else ""
    if not slug:
        return ""
    return ((novel_meta(slug) or {}).get("zh_titles") or {}).get("book") or ""


def cover_html(it: dict) -> str:
    """详情页顶部的作品横幅（源站 og:image）。**只读本地文件**，没有就不渲染。

    为什么只放在详情页、不放在卡片上：Kakuyomu 的 og:image 是 1200×630 的
    宣传图（大字标题 + 简介，不是插画封面），塞进卡片那种 58×80 的竖版缩略框
    会被 object-fit 切掉大半，看着像坏了。详情页是 16:9 的横向版式，正合适。

    抓取走 lncovers 的后台队列（限速、去重）：渲染路径一旦联网，打开页面就要
    等源站 3 秒 —— 这就是"页面卡住/得刷新"的老病（见 check_on_open_bounded）。
    """
    wid = str(it.get("id") or "")
    slug = it.get("slug") or _slug_index().get(wid) or ""
    meta = novel_meta(slug) if slug else None
    source = (meta or {}).get("source") or it.get("source") or "kakuyomu"
    sid = str((meta or {}).get("source_id") or wid)
    key = lc.key_for(source, sid)
    if lc.path_of(key):
        return (f'<div class="hero"><img src="{lc.url_of(key)}" alt="" '
                f'loading="lazy" decoding="async"></div>')
    if meta:
        lc.ensure_async(source, sid, meta.get("url") or "")
    return ""


def work_head(it: dict, det: dict | None = None) -> str:
    """作品卡片的「标题区」：中文大 + 日文小 + 中文简介摘要。

    抽成共用函数是有原因的：推荐卡与书库卡是两处独立渲染，
    上次只改了一处就成了 bug（用户报「书库点了没用」时我只修了书库卡，
    推荐卡又漏了）。共用一处，改一次两处都生效。

    `det` 可传已读好的详情缓存，避免重复读盘。
    """
    wid = str(it.get("id") or "")
    if det is None:
        det = load_detail(wid) if wid else {}
    # 中文书名有两个来源，**必须合并读**（踩过：同一本书推荐卡中文、书架日文）：
    #   ① data/details/<id>.json 的 zh_title（列表/详情页翻译写的）
    #   ② novels/<slug>/meta.json 的 zh_titles.book（章节翻译写的）
    zh_title = det.get("zh_title") or it.get("title_zh") or _book_zh_title(it)
    jp_title = it.get("title_jp") or it.get("title") or ""

    if zh_title:
        head = (f'<div class="t">{lr.esc(zh_title)}</div>'
                f'<div class="jp-sub">{lr.esc(jp_title)}</div>')
    else:
        st = batch_state(wid)
        if st in ("queued", "running"):
            note = "翻译中…"
        elif det.get("zh_title_failed"):
            note = "书名是造词，模型译不出（保留原名）"
        else:
            note = "未翻译"
        head = (f'<div class="t">{lr.esc(jp_title)}</div>'
                f'<div class="tr-note">{note}</div>')

    zh_syn = det.get("zh_synopsis") or ""
    syn_html = ""
    if zh_syn:
        cut = zh_syn.strip().replace("\n", " ")
        if len(cut) > 80:
            cut = cut[:80] + "…"
        syn_html = f'<div class="card-syn">{lr.esc(cut)}</div>'
    elif det.get("synopsis"):
        syn_html = '<div class="card-syn jp">（简介待翻译）</div>'
    return head + syn_html


def work_status_chips(it: dict) -> str:
    """显示"我和这本书的关系"：收藏 / 在读 / 看完 / 弃文 / 已译多少章。

    用户扫列表时最想知道的是"这本我是不是已经在跟了"，
    以前只有一句「✓ 已在书架」，看不出进度。
    """
    wid = str(it.get("id") or "")
    # 走反查表，别每张卡都"遍历所有作品 + 读每个 meta.json"
    # （372 张卡 × 全表 = 首页 5 秒的主因）。
    slug = _slug_index().get(wid)
    chips = []
    if "R18" in (it.get("tags") or []):
        chips.append(("R18", "r18"))
    if slug:
        tk = read_tracking(slug)
        if _read_book(slug).get("favorites"):
            chips.append(("已收藏", "fav"))
        label = {"reading": "在读", "finished": "已读完",
                 "dropped": "已弃文", "want": "想读"}.get(tk)
        if label:
            chips.append((label, "tk"))
        have = have_count(slug, novel_meta(slug) or {})
        if have:
            chips.append((f"已译 {have} 章", "tr"))
        pr = (_read_book(slug).get("progress") or {}).get("chapter")
        if pr and int(pr) > 1:
            chips.append((f"读到第 {pr} 章", ""))
    elif it.get("on_shelf"):
        chips.append(("已在书架", "ok"))
    # 来源（「流派:奇幻」/ 关键词）不再放进卡片：它和标签、类型高度重复，
    # 手机上一行只够放几个，反而把「我与这本书的关系」挤没了。
    # 需要看来源时去详情页（标签完整列在那里）。
    inner = "".join(f'<span class="chip {c}">{lr.esc(t)}</span>' for t, c in chips)
    if not inner:
        return ""
    return f'<div class="chips" style="margin-top:8px">{inner}</div>'


def shelf_source_ids() -> set[str]:
    """**在书架上**的作品源站 id。

    判定必须和 `library()` 的 `on_shelf` 完全一致：
      on_shelf = favorites 或 tracking in TRACKING
    踩过（用户抱怨「加入书架不等于收藏」的那一串）：
      这里原来只判断"本地有没有这个作品目录"，于是
      ①「移出书架」之后，推荐卡/书库卡还写「✓ 已在书架」，而且**没有加回来的按钮**；
      ② 详情页/推荐卡说"已在书架"，书架页里却找不到这本书 —— 同一件事两套判定，
         用户完全没法自己判断到底在不在书架。
    """
    out = set()
    for s in all_local_slugs():
        m = novel_meta(s) or {}
        sid = str(m.get("source_id") or "")
        if not sid:
            continue
        d = _read_book(s)
        if d.get("favorites") or d.get("tracking") in TRACKING:
            out.add(sid)
    return out


# source_id → slug 的反查表。见 _slug_index()：不能每张卡都扫一遍全表。
_SLUG_IDX: list = [None, {}]


def _slug_index() -> dict:
    """source_id → slug 的**反查表**（按 novels 目录状态缓存）。

    踩过（性能）：`work_head()` 每渲染一张卡就会问一次"这本的中文书名在 meta 里吗"，
    而原来 slug_for_source() 是"遍历所有本地作品 + 逐个读 meta.json" ——
    书库 372 张卡 = 372 × N 次文件读，首页实测 **5.0 秒**（用户一直在抱怨慢）。
    这里整张表只建一次，novels 目录变了（加书/删书）才重建。
    """
    try:
        st = os.stat(NOVELS)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _SLUG_IDX[0] != key:
        idx: dict[str, str] = {}
        for s in all_local_slugs():
            sid = str((novel_meta(s) or {}).get("source_id") or "")
            if sid and sid not in idx:
                idx[sid] = s
        _SLUG_IDX[0] = key
        _SLUG_IDX[1] = idx
    return _SLUG_IDX[1]


def slug_for_source(work_id: str) -> str:
    """按源站作品 id 找本地 slug（找不到返回空串）。"""
    return _slug_index().get(str(work_id or ""), "")


def ensure_on_shelf(slug: str) -> bool:
    """「加入书架」= 放进书架并标为**想读**。

    关键：**这不是收藏**。`favorites` 一动不动 —— 用户明确要求两条轴分开
    （「我加入书架不等于收藏，因为我（不加）看不了」= 他加进来只是为了能读，
    不代表他喜欢这本书，更不该拿它去学口味）。

    踩过：以前 `/api/add` 什么都不写，于是"加进来了、书架里却没有这本书"
    （book 目录在，但 on_shelf 为假）—— 用户只能靠按 ★收藏 或 ▸在读 才让它出现，
    而详情页的 ★收藏 当时还是坏的，所以怎么点都"没反应"。
    """
    if not slug:
        return False
    d = _read_book(slug)
    if d.get("favorites") or d.get("tracking") in TRACKING:
        return False                      # 已经在书架上了，别动用户的状态
    apply_action(slug, "want", True)
    return True


def findings_html(limit: int = recs.RECS_PAGE) -> str:
    """推荐位：让用户有个"我该看什么"的入口（之前完全没有）。

    这里读的是 `recs.window()` 而不是 `cached()` —— 推荐位是**分屏**的，
    「换一批」只挪本地游标（秒回），「重新抓取」才是那个要等三分半的慢操作。
    两个按钮分开，是因为把两件事塞进一个按钮就必然骗人：
    要么撒谎说"约 1 分钟"，要么让用户以为换了其实没换。
    """
    try:
        win = recs.window(limit)
    except Exception:  # noqa: BLE001
        return ""
    items = win["items"]
    if not win["total"]:
        return ('<div class="fb" style="margin:22px 0"><h3>为你推荐</h3>'
                '<div class="s" style="font-family:var(--ui);font-size:13px;line-height:1.75">'
                '暂无推荐内容。可先从书库中挑选，或重新抓取源站获取新作品'
                f'（{recs.scan_q_note()}）。</div>'
                '<div class="ctrls" style="margin-top:12px">'
                '<button id="recs-topup">从书库生成</button>'
                '<button id="recs-refresh" class="ghost">重新抓取源站</button>'
                '</div></div>')
    have = shelf_source_ids()
    cards = []
    shown = items
    for it in shown:
        it2 = dict(it)
        it2["on_shelf"] = str(it.get("id") or "") in have
        cards.append(_finding_card(it2))
    cards = "".join(cards)
    stale_badge = '<span class="badge" title="推荐缓存已有一段时间，可在下方重新抓取源站">缓存较旧</span>' if win["stale"] else ""
    # 数字必须等于**实际渲染的卡片数**：宁可写"第 1–12 本"也不要写"共 60 本"
    # 却只给 6 张（踩过）。这里 start/end 直接来自 window()。
    if win["total"] > len(shown):
        pos = f'第 {win["start"] + 1}–{win["end"]} 本 / 共 {win["total"]} 本'
    else:
        pos = f'共 {win["total"]} 本'
    # 抓取在服务端后台跑：刷新页面也要看得见它还在动（否则又是"点了没反应"）
    try:
        _sc = recs.scan_state()
    except Exception:  # noqa: BLE001
        _sc = {}
    run_html = ""
    if _sc.get("running"):
        run_html = (f'<div class="s" id="recs-run" style="padding:0 2px 10px;'
                    f'font-family:var(--ui);font-size:12px;color:var(--accent)">'
                    f'正在抓取 {_sc.get("done", 0)}/{_sc.get("total", 0)} 个关键词</div>')
    # 翻到最后一批时给出下一步：再点「换一批」只会回到开头（本地轮换到顶了），
    # 只有「重新抓取源站」能带来新书 —— 不说清楚用户会以为按钮又坏了
    tail_hint = ""
    if win["total"] > len(shown) and win["end"] >= win["total"]:
        tail_hint = ' 已到最后一页，继续翻页会回到开头；如需新作品，请重新抓取源站。'
    return (f'<details class="shelf" id="recstop" open><summary><span class="arrow">▸</span>'
            f'为你推荐 <span class="n">{len(shown)} 本</span>'
            f'{stale_badge}</summary>'
            f'{run_html}'
            f'<div class="cards">{cards}</div>'
            f'<div class="ctrls" style="padding:0 2px 8px">'
            f'<button id="recs-next">换一批</button>'
            f'<span class="s" style="align-self:center;color:var(--ct)">{pos}</span>'
            f'<button id="recs-refresh" class="ghost">重新抓取源站</button>'
            f'</div>'
            f'<details class="minihelp" style="margin:0 2px 14px">'
            f'<summary>换一批与重新抓取的区别</summary>'
            f'<div>「换一批」从本地书库轮换，立即返回，不访问源站；'
            f'「重新抓取源站」会按当前偏好搜索新作品{recs.scan_q_note()}，'
            f'耗时较长，抓取结果会存入书库。{tail_hint}</div></details></details>')


def pager(total: int, page: int, size: int, anchor: str, compact: bool = False) -> str:
    """简单分页控件。只渲染当前页，避免一次塞几百张卡片。

    `compact=True` 给"列表**顶部**"用的精简版（上一页/下一页 + 页码信息）：
    用户报过"翻到最下面点下一页，新页停在底部，还得从下往上看"，所以列表顶部
    也要能翻页、且翻完回到顶部。注意 compact 的 class 是 `pager compact`，
    以免和底部完整版（`class="pager"`）被测试的正则混为一谈。
    """
    pages = max(1, (total + size - 1) // size)
    page = max(1, min(page, pages))
    if pages <= 1:
        return ""
    def btn(p, label, cur=False):
        cls = ' class="on"' if cur else ""
        return (f'<button data-gopage="{p}" data-anchor="{anchor}"{cls}>{label}</button>')
    pinfo = f'<span class="pinfo">{page} / {pages} 页 · 共 {total} 项</span>'
    if compact:
        parts = []
        if page > 1:
            parts.append(btn(page - 1, "‹ 上一页"))
        parts.append(pinfo)
        if page < pages:
            parts.append(btn(page + 1, "下一页 ›"))
        return '<div class="pager compact">' + "".join(parts) + '</div>'
    parts = []
    if page > 1:
        parts.append(btn(page - 1, "‹ 上一页"))
    lo, hi = max(1, page - 2), min(pages, page + 2)
    if lo > 1:
        parts.append(btn(1, "1"))
        if lo > 2:
            parts.append('<span style="color:var(--ct)">…</span>')
    for p in range(lo, hi + 1):
        parts.append(btn(p, str(p), p == page))
    if hi < pages:
        if hi < pages - 1:
            parts.append('<span style="color:var(--ct)">…</span>')
        parts.append(btn(pages, str(pages)))
    if page < pages:
        parts.append(btn(page + 1, "下一页 ›"))
    return '<div class="pager">' + "".join(parts) + pinfo + '</div>'


def library_pane(query: str = "", want_only: bool = False, tags=None) -> str:
    """书库面板：爬过的书都在这里，可搜、可标「想看」、可按标签筛选、可加入书架。

    页数/数字与真正渲染的卡**必须来自同一次过滤**：以前总数用整库条数
    （含隐藏、不受筛选影响），渲染却用 limit 截断后的前 400 本 —— 库一大
    末尾就多出翻不到的空页（用户报过"共 28 页却只翻到 27"）。
    标签支持**多选**（AND，同时满足）：`tags` 为已选标签列表。
    """
    sel = recs._norm_tags("", tags)
    try:
        view_total = recs.library_count(query=query, want_only=want_only, tags=sel)
        total = recs.library_count()             # 全库可浏览本数
        hidden = recs.hidden_count()
        page = LIB_PAGE["n"]
        pages = max(1, (view_total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(1, min(page, pages))
        LIB_PAGE["n"] = page
        rows = recs.library_items(query=query, want_only=want_only, tags=sel,
                                  limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
    except Exception as e:  # noqa: BLE001
        return f'<div class="fb">书库暂时不可用：{lr.esc(type(e).__name__)}</div>'
    have = shelf_source_ids()
    cards = []
    for r in rows:
        on = str(r.get("id")) in have
        want = bool(r.get("want"))
        _wid = str(r.get("id") or "")
        _det = load_detail(_wid) if _wid else {}
        cards.append(
            f'<div class="card" data-hay="{attrescape((r.get("title") or "") + " " + (r.get("author") or "") + " " + (r.get("title_zh") or ""))}"'
            f' data-lib="{attrescape(_wid)}"'
            f' onclick="if(event.target.tagName!=&quot;BUTTON&quot;)location.href=&quot;/book?id={attrescape(_wid)}&quot;">'
            # 中文优先：与推荐卡共用同一套渲染，避免两处各写一遍再漏改
            + work_head(r, _det)
            + work_status_chips(r)
            + f'<div class="s">{lr.esc(r.get("author") or "")} · {lr.esc(r.get("genre") or "")} · '
            + f'{r.get("episodes") or 0} 话 · '
            + f'更新 {lr.esc(r.get("updated") or "-")}</div>'
            + ('<div class="ctrls" style="margin-top:12px">'
               '<span class="chip ok">已在书架</span></div>'
               if on else
               '<div class="ctrls" style="margin-top:12px">'
               f'<button class="primary" data-add="{attrescape(r.get("url") or "")}"'
               f' title="加入书架后可阅读与翻译；这不是收藏，也不影响偏好画像。">'
               f'加入书架</button></div>')
            + '<div class="ctrls">'
            + f'<button data-want="{attrescape(_wid)}" class="{"on" if want else ""}"'
            + ' title="仅在书库中标记，暂不阅读；标记不等于加入书架，'
            + ' 要阅读请点击上方「加入书架」。">'
            + f'{"已标记想读" if want else "标记想读"}</button>'
            + dislike_button(_wid)
            + '</div>'
            + '</div>')
    if not rows:
        cards = ['<p style="color:var(--ct);text-align:center;font-family:var(--ui);'
                 'font-size:13px;padding:24px 0">没有匹配的作品。'
                 '可调整筛选条件，或重新抓取源站扩充书库。</p>']
    # 分页：cards 已经是**这一页**的卡（页数在开头按 view_total 算好）
    # 顶部也放一条精简分页，翻页后回到列表顶部即可继续翻（用户报过"要从下往上看"）。
    pg = pager(view_total, page, PAGE_SIZE, "lib")
    pg_top = pager(view_total, page, PAGE_SIZE, "lib", compact=True)
    # 可点标签 facet：频次最高的若干标签（含本书数），点了只看该标签；可多选（同时满足）。
    # 只渲染交互元素，数字用真实频次（不能骗人）；无标签时整行不出现。
    facet = ""
    try:
        # 手机首屏不能铺满一整屏标签：只取前 20 个，并放在单行横向滚动条里。
        # min_count=1：小书库（十几本）里很多标签只出现一次，按 2 过滤会看起来
        # “明明有书却没有标签”。
        _tags = recs.library_tags(top=20, min_count=1)
    except Exception:  # noqa: BLE001
        _tags = []
    _tag_names = {t for t, _ in _tags}
    for _st in sel:
        if _st not in _tag_names:
            try:
                _tags.append((_st, recs.library_count(tags=[_st])))
            except Exception:  # noqa: BLE001
                _tags.append((_st, 0))
    if sel:
        # 已选标签按**选择顺序**排最前，刷新后不用横向找它。
        _tags.sort(key=lambda tn: (sel.index(tn[0]) if tn[0] in sel else 9999,
                                   0 if tn[0] in sel else -tn[1], tn[0]))
    if _tags:
        _chips = []
        for _t, _n in _tags:
            _on = (_t in sel)
            _title = ("取消「" + _t + "」筛选（可多选，同时满足）" if _on
                      else "只看带「" + _t + "」的作品（可多选，同时满足）")
            _chips.append(
                f'<button class="libtag{" on" if _on else ""}"'
                f' data-libtag="{attrescape(_t)}"'
                f' title="{attrescape(_title)}">'
                f'{lr.esc(_t)} <span class="s">{_n}</span></button>')
        _label = "标签" + (f" · 已选 {len(sel)}" if sel else "")
        _clear = ('<button class="libtag clear" id="libtagclear"'
                  ' title="清除全部标签筛选">清除筛选</button>' if sel else "")
        facet = ('<div class="facetrow">'
                 f'<span class="facetlabel">{_label}</span>'
                 + "".join(_chips) + _clear + '</div>')
    return (f'<div class="fb" id="libtop" style="margin:18px 0 6px">'
            f'<div class="row lib-search" style="display:flex;gap:8px;flex-wrap:wrap;margin:0">'
            f'<input id="libq" placeholder="搜索书名、作者或标签" '
            f'style="flex:1;min-width:150px" value="{attrescape(query)}">'
            f'<button id="libwant" class="{"on" if want_only else ""}">仅看想读</button>'
            f'<button id="libapply">搜索</button></div>'
            + f'<div class="s" style="font-family:var(--ui);font-size:12px;'
            f'color:var(--ct);margin-top:8px">书库共 {total} 本'
            f'{"（已隐藏 " + str(hidden) + " 本）" if hidden else ""}'
            f'{"，筛选出 " + str(view_total) + " 本" if query or want_only or sel else ""}'
            f'</div>'
            + facet
            + '</div>'
            + pg_top
            + f'<div class="cards">{"".join(cards)}</div>{pg}')


def all_local_slugs() -> list[str]:
    """本地已有作品目录的 slug 列表。"""
    if not os.path.isdir(NOVELS):
        return []
    return [s for s in sorted(os.listdir(NOVELS))
            if not s.startswith(".") and os.path.isdir(os.path.join(NOVELS, s))
            and os.path.exists(os.path.join(NOVELS, s, "meta.json"))]


GENRE_ZH = {
    "ROMANCE": "恋爱", "FANTASY": "奇幻", "ACTION": "动作", "SF": "科幻",
    "MYSTERY": "悬疑", "HORROR": "恐怖", "HISTORY": "历史", "NONFICTION": "纪实",
    "DRAMA": "剧情", "COMEDY": "喜剧", "LITERARY": "文学", "POETRY": "诗歌",
    "BL": "BL", "GL": "GL", "OTHER": "其他",
}


DEFAULT_MODEL = lt.TRANSLATE_MODEL
AUX_MODEL = lt.AUX_MODEL
REVIEW_MODEL = lt.REVIEW_MODEL

_TITLE_SYS = (
    "你是轻小说标题翻译。把日文作品名译成简体中文。"
    "保留原有的语气与人称，专有名词意译为主。"
    "**只输出译文本身**，不要引号、不要解释、不要加书名号。"
)
_SYNO_SYS = (
    "你是轻小说简介翻译。把日文简介译成简体中文，保留原文段落。"
    "语气自然、口语化一点，符合中文网文读者习惯。"
    "**只输出译文本身**，不要前后加任何说明。"
)


def _clean_line(s: str) -> str:
    """模型有时会加引号/书名号/前缀，去掉它们。"""
    t = (s or "").strip()
    t = t.strip("\"'“”‘’")
    t = t.strip("《》〈〉")
    for pre in ("译文：", "翻译：", "中文标题：", "标题："):
        if t.startswith(pre):
            t = t[len(pre):].strip()
    return t.strip()


def _worker_err_msg(e: BaseException) -> str:
    """把后台线程的异常转成给用户看的错误串。

    SystemExit 单列：lt.die()（如缺 API key）走的是 sys.exit()，不是普通异常，
    只 `except Exception` 接不住 —— 线程会直接死掉、任务永卡 running（踩过）。
    """
    if isinstance(e, SystemExit):
        code = getattr(e, "code", None)
        return (f"翻译中止（退出码 {code}）"
                if code not in (None, 0) else "翻译中止（已退出）")
    return f"{type(e).__name__}: {e}"


TR_JOBS: dict = {}          # work_id -> {status, at, err}
TR_LOCK = threading.Lock()


# 校对任务按 (书, 章) 隔离。不能让“甲书第 3 章”的状态覆盖“乙书第 3 章”。
REVIEW_JOBS: dict = {}
REVIEW_LOCK = threading.Lock()
REVIEW_STALE_SEC = 900


def _review_key(slug: str, chapter: int) -> str:
    return f"{slug}:{int(chapter)}"


def review_state(slug: str, chapter: int) -> dict:
    key = _review_key(slug, chapter)
    with REVIEW_LOCK:
        j = dict(REVIEW_JOBS.get(key) or {})
    if not j:
        return {"status": "idle", "slug": slug, "chapter": int(chapter)}
    if j.get("status") in ("queued", "running"):
        if time.time() - float(j.get("heartbeat") or j.get("at") or 0) > REVIEW_STALE_SEC:
            with REVIEW_LOCK:
                if key in REVIEW_JOBS:
                    REVIEW_JOBS[key]["status"] = "error"
                    REVIEW_JOBS[key]["error"] = "校对超时，请重试"
            j.update(status="error", error="校对超时，请重试")
    return j


def start_review(slug: str, chapter: int, *, use_llm: bool = False,
                 fix: bool = False, learn: bool = True) -> dict:
    """后台校对一章。报告按书落盘，状态按 (slug, chapter) 隔离。"""
    key = _review_key(slug, chapter)
    with REVIEW_LOCK:
        j = REVIEW_JOBS.get(key)
        if j and j.get("status") in ("queued", "running"):
            return dict(j)
        token = time.time_ns()
        REVIEW_JOBS[key] = {
            "status": "queued", "slug": slug, "chapter": int(chapter),
            "use_llm": bool(use_llm), "fix": bool(fix), "learn": bool(learn),
            "at": time.time(), "heartbeat": time.time(), "token": token,
            "message": "排队中", "error": None,
        }

    def work() -> None:
        with REVIEW_LOCK:
            REVIEW_JOBS[key].update(status="running", message="规则检查中",
                                    heartbeat=time.time())
        try:
            meta = lt.load_meta(slug)
            total = len(meta.get("episodes") or [])
            if not (1 <= int(chapter) <= total):
                raise ValueError(f"章号超出范围：{chapter}/{total}")
            rep = rview.review_chapter(
                slug, int(chapter) - 1, meta, use_llm=use_llm,
                model=REVIEW_MODEL, temperature=0.2,
                fix=fix, learn=learn, quiet=False)
            with REVIEW_LOCK:
                if (REVIEW_JOBS.get(key) or {}).get("token") == token:
                    REVIEW_JOBS[key].update(
                        status="done", heartbeat=time.time(),
                        message="校对完成", report=rep,
                        counts=rep.get("counts"),)
        except (Exception, SystemExit) as e:  # noqa: BLE001
            with REVIEW_LOCK:
                if (REVIEW_JOBS.get(key) or {}).get("token") == token:
                    REVIEW_JOBS[key].update(
                        status="error", heartbeat=time.time(),
                        message="校对失败", error=_worker_err_msg(e))

    threading.Thread(target=work, daemon=True,
                     name=f"review-{slug}-{chapter}").start()
    with REVIEW_LOCK:
        return dict(REVIEW_JOBS[key])


def tr_job_state(work_id: str) -> str:
    return (TR_JOBS.get(str(work_id)) or {}).get("status") or "idle"


def start_translation(work_id: str, title: str, synopsis: str) -> str:
    """后台翻译标题+简介（LLM 慢，不能卡住页面响应）。"""
    wid = str(work_id)
    with TR_LOCK:
        j = TR_JOBS.get(wid) or {}
        if j.get("status") in ("queued", "running"):
            return "running"
        TR_JOBS[wid] = {"status": "queued",
                        "at": time.strftime("%Y-%m-%d %H:%M:%S")}

    def work():
        TR_JOBS[wid] = dict(TR_JOBS.get(wid) or {}, status="running")
        try:
            ensure_translation(wid, title, synopsis)
            TR_JOBS[wid] = {"status": "done",
                            "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        except (Exception, SystemExit) as e:  # noqa: BLE001
            TR_JOBS[wid] = {"status": "error", "err": _worker_err_msg(e)[:120],
                            "at": time.strftime("%Y-%m-%d %H:%M:%S")}

    threading.Thread(target=work, daemon=True).start()
    return "queued"


def tr_title(jp: str, model: str = AUX_MODEL) -> str:
    if not jp:
        return ""
    for attempt in range(2):
        try:
            out, _ = lt.call_llm(
                _TITLE_SYS, jp, model, 0.3, role="auxiliary")
        except Exception:  # noqa: BLE001
            return ""
        got = _clean_line((out or "").splitlines()[0] if out else "")
        # 译名不该和日文一模一样；也不该长得像一段解释
        if got and got != jp and len(got) <= max(40, len(jp) * 2):
            return got
        if attempt == 0:
            continue
    return ""


def tr_synopsis(jp: str, model: str = AUX_MODEL) -> str:
    if not jp:
        return ""
    try:
        out, _ = lt.call_llm(
            _SYNO_SYS, jp, model, 0.4, role="auxiliary")
    except Exception:  # noqa: BLE001
        return ""
    got = (out or "").strip()
    # 校验：必须确实翻成了中文，且**与原日文不同**（复用 lntrans 的检测防回抄；
    # 纯汉字简介中日同形，补一条"不等于原文"更保险）
    if got and lt.detect_chinese(got) and got != jp:
        return got
    return ""


def ensure_translation(work_id: str, title: str, synopsis: str,
                       model: str = AUX_MODEL) -> dict:
    """按需翻译标题与简介并缓存。只翻一次，之后直接读缓存。"""
    d = load_detail(work_id)
    changed = False
    if title and not d.get("zh_title"):
        got = tr_title(title, model)
        if got:
            d["zh_title"] = got
            changed = True
    if synopsis and not d.get("zh_synopsis"):
        got = tr_synopsis(synopsis, model)
        if got:
            d["zh_synopsis"] = got
            changed = True
    if changed:
        save_detail(work_id, d)
    return d


_BATCH_SYS = (
    "你是轻小说信息翻译。给你日文作品标题和简介，输出简体中文。"
    "严格按下面格式输出两行，不要任何额外文字：\n"
    "T: <中文标题>\n"
    "S: <中文简介>\n"
    "标题保留原有语气和标点风格；简介保留段落，语气自然口语化。"
    "若某一段缺失就留空。"
)


def _parse_batch(text: str) -> tuple[str, str]:
    """解析 T:/S: 两行。模型偶尔会加多余行，只认这两行。"""
    title, syn = "", ""
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("T:"):
            title = _clean_line(s[2:])
        elif s.startswith("S:"):
            syn = s[2:].strip()
    return title, syn


def translate_one(work_id: str, title: str, synopsis: str,
                  model: str = AUX_MODEL) -> dict:
    """一次请求同时翻标题+简介，写进详情缓存。已翻过就跳过。

    ⚠ 必须在锁里做 **读-改-写**：列表页会并发翻很多本，
    不锁的话两个线程各自读到旧文件、各自写回，后写的把先写的覆盖掉
    （踩过：某本标题翻译凭空丢失，一直显示"未翻译"）。
    """
    wid = str(work_id)
    with DETAIL_LOCK:
        d = load_detail(wid)
        need_t = bool(title) and not d.get("zh_title")
        need_s = bool(synopsis) and not d.get("zh_synopsis")
        if not (need_t or need_s):
            return d

    if lnmodels.is_local("auxiliary"):
        # Sakura 这类句子级本地模型不会按 T:/S: 两行格式输出，硬塞批量
        # 只会把标题和简介糊成一段；本地分开问，慢一点但稳定且 0 元。
        got_t = tr_title(title, model) if need_t else ""
        got_s = tr_synopsis(synopsis, model) if need_s else ""
    else:
        user = f"标题：{title or '(无)'}\n简介：{synopsis or '(无)'}"
        try:
            out, _ = lt.call_llm(
                _BATCH_SYS, user, model, 0.3, role="auxiliary")
        except Exception:  # noqa: BLE001
            return d
        got_t, got_s = _parse_batch(out or "")

    # 校验 + 写回都在锁内（读-改-写是一个原子步骤）
    with DETAIL_LOCK:
        d = load_detail(wid)
        if need_t:
            if got_t and got_t != title and len(got_t) <= max(40, len(title) * 2):
                d["zh_title"] = got_t
                # 重试成功 → 清掉上一次的失败标记，否则 detail 里会
                # 同时存在 zh_title 和 zh_title_failed，语义自相矛盾
                # （UI 现在只看 zh_title 才没露馅，后续任何"看 failed"的逻辑都会误判）。
                d.pop("zh_title_failed", None)
            else:
                # 译不出来（比如标题是专有名词）也要留痕，
                # 否则每轮批量都会重试这本，白花 token
                d["zh_title_failed"] = True
        if need_s:
            if got_s and lt.detect_chinese(got_s):
                d["zh_synopsis"] = got_s
                d.pop("zh_syn_failed", None)
            else:
                # 翻不出（或模型把日文抄回来）也留痕，避免无限重试
                d["zh_syn_failed"] = True
        d["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_detail(wid, d)
    return d


def recs_batch_state() -> dict:
    """列表页「自动补中文标题/简介」的进度：多少本已翻、多少本还欠。

    纯读操作，GET/POST 都该能打（前端用 GET 轮询；早先只注册了 POST，
    于是 GET 命中 404、轮询静默失败 → 推荐/书库/书架列表里的书名一直不翻）。
    """
    pend = done = 0
    for it in _recs_all():
        wid = str(it.get("id") or "")
        if not wid:
            continue
        if batch_state(wid) == "error":
            done += 1
            continue
        det = load_detail(wid)
        # 没有简介的书不该永远算「欠翻译」：只要标题处理过就算完成。
        has_title = bool(it.get("title"))
        has_syn = bool(det.get("synopsis") or it.get("catchphrase"))
        if _tr_done(det, has_title, has_syn):
            done += 1
        else:
            pend += 1
    return {"ok": True, "done": done, "pending": pend}


def _recs_all() -> list:
    """推荐缓存 + 书库合并（详情/翻译都可能来自这两处）。

    这里要 include_hidden：被「不感兴趣」隐藏的书，你从阅读历史点进去
    仍然该能看详情、能翻译 —— 隐藏是"别再推给我"，不是"删了它"。
    """
    out, seen = [], set()
    try:
        for it in recs.cached(include_hidden=True) or []:
            wid = str(it.get("id") or "")
            if wid and wid not in seen:
                seen.add(wid)
                out.append(it)
    except Exception:  # noqa: BLE001
        pass
    try:
        for wid, it in (recs._load_lib() or {}).items():
            if str(wid) not in seen:
                seen.add(str(wid))
                it = dict(it)
                it.setdefault("id", wid)
                out.append(it)
    except Exception:  # noqa: BLE001
        pass
    # 书架上的书也要算进来：它们的中文标题/简介来自同一个详情缓存，
    # 而书架卡直接读这份缓存。用户报「书架里的书标题没翻译」就是这个缺口
    # ——书在书架上，却没人给它排队翻译。
    try:
        for it in library():
            wid = str(it.get("id") or "")
            if wid and wid not in seen:
                seen.add(wid)
                out.append({"id": wid,
                            "title": it.get("title_jp") or "",
                            "url": (novel_meta(it["slug"]) or {}).get("url") or ""})
    except Exception:  # noqa: BLE001
        pass
    return out


def _find_rec(work_id: str) -> dict:
    for it in _recs_all():
        if str(it.get("id")) == str(work_id):
            return it
    return {}


BATCH_JOBS: dict = {}       # work_id -> {status, at, err}
BATCH_LOCK = threading.Lock()
BATCH_Q: queue.Queue = queue.Queue()
_BATCH_WORKER_STARTED = False


def batch_state(work_id: str) -> str:
    return (BATCH_JOBS.get(str(work_id)) or {}).get("status") or "idle"


def _ensure_batch_worker() -> None:
    global _BATCH_WORKER_STARTED
    if _BATCH_WORKER_STARTED:
        return
    with BATCH_LOCK:
        if _BATCH_WORKER_STARTED:
            return
        _BATCH_WORKER_STARTED = True
    threading.Thread(target=_batch_worker, daemon=True,
                     name="meta-translate").start()


def _batch_worker() -> None:
    """串行补标题/简介。

    以前一本一个线程：列表一次排 40 本 = 40 个并发请求打向本地 Sakura，
    它扛不住，超时/漏行后书名一直不翻。这里统一排一条队列，按顺序问。
    """
    while not STOP.is_set():
        try:
            wid = BATCH_Q.get(timeout=0.5)
        except queue.Empty:
            continue
        except Exception:  # noqa: BLE001
            continue
        try:
            with BATCH_LOCK:
                if batch_state(wid) != "queued":
                    continue
                BATCH_JOBS[wid] = {"status": "running",
                                   "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            it = _find_rec(wid)
            det = load_detail(wid)
            syn = det.get("synopsis") or (it.get("catchphrase") or "")
            if not det.get("synopsis") and (it.get("url") or ""):
                det = refresh_detail(wid, it.get("url") or "")
                syn = det.get("synopsis") or syn
            title = it.get("title") or ""
            d = translate_one(wid, title, syn)
            # 模型不可达时 translate_one 会静默返回旧数据；不落失败标记的话
            # 前端每 2 秒重排一次、永远 pending，既刷屏又没进展。
            changed = False
            if title and not d.get("zh_title") and not d.get("zh_title_failed"):
                d["zh_title_failed"] = True
                changed = True
            if syn and not d.get("zh_synopsis") and not d.get("zh_syn_failed"):
                d["zh_syn_failed"] = True
                changed = True
            if changed:
                with DETAIL_LOCK:
                    save_detail(wid, d)
            BATCH_JOBS[wid] = {"status": "done",
                               "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        except (Exception, SystemExit) as e:  # noqa: BLE001
            BATCH_JOBS[wid] = {"status": "error",
                               "err": _worker_err_msg(e)[:120],
                               "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                               "ts": time.time()}
        finally:
            BATCH_Q.task_done()


def start_batch_translate(work_id: str) -> str:
    """后台翻一本书的标题+简介（列表页用，不能阻塞渲染）。"""
    wid = str(work_id)
    with BATCH_LOCK:
        st = (BATCH_JOBS.get(wid) or {}).get("status")
        if st in ("queued", "running"):
            return "running"
        d = load_detail(wid)
        if d.get("zh_title") and d.get("zh_synopsis"):
            BATCH_JOBS[wid] = {"status": "done"}
            return "done"
        BATCH_JOBS[wid] = {"status": "queued",
                           "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _ensure_batch_worker()
    BATCH_Q.put(wid)
    return "queued"


def _tr_done(d: dict, has_title: bool, has_syn: bool) -> bool:
    """这本书的标题/简介是否已经**处理过**（成功或确认译不出）。"""
    ok_t = bool(d.get("zh_title")) or not has_title or bool(d.get("zh_title_failed"))
    ok_s = bool(d.get("zh_synopsis")) or not has_syn or bool(d.get("zh_syn_failed"))
    return ok_t and ok_s


def batch_translate_missing(limit: int = 40) -> int:
    """把推荐列表里**还没翻**的作品排进后台翻译队列，返回排了几个。

    列表页需要中文标题才能扫读，所以打开列表时顺带把缺的补上；
    每本一个请求、永久缓存，翻过就永不重复。
    """
    n = 0
    for it in _recs_all():
        if n >= limit:
            break
        wid = str(it.get("id") or "")
        if not wid:
            continue
        d = load_detail(wid)
        # 已经翻过（或确认译不出）就跳过
        if _tr_done(d, bool(it.get("title")), bool(d.get("synopsis"))):
            continue
        st = batch_state(wid)
        if st in ("queued", "running"):
            continue
        if st == "error":
            # 失败后冷却 10 分钟再自动重试，别每次翻页都重打一遍模型。
            _at = float((BATCH_JOBS.get(wid) or {}).get("ts") or 0)
            if time.time() - _at < 600:
                continue
        if start_batch_translate(wid) in ("queued", "running"):
            n += 1
    return n


def recent_read() -> dict | None:
    """最近在读的书 —— 老读者打开站点，第一件事是"接着看"。

    以前打开首页要自己找到那本书再点进去，多两步。
    """
    best = None
    for slug in all_local_slugs():
        pr = _read_book(slug).get("progress") or {}
        at = pr.get("at") or ""
        ch = int(pr.get("chapter") or 0)
        if not ch or not at:
            continue
        if best is None or at > best[0]:
            best = (at, slug, ch)
    if not best:
        return None
    _, slug, ch = best
    meta = novel_meta(slug) or {}
    zh = (meta.get("zh_titles") or {}).get("book") or meta.get("title") or slug
    have = have_count(slug, meta)
    return {"slug": slug, "title": zh, "chapter": ch,
            "have": have, "at": best[0],
            "next": (ch + 1) if ch < have else ch}


def recent_banner() -> str:
    r = recent_read()
    if not r:
        return ""
    nxt = r["next"]
    more = (f' · 剩余 {r["have"] - r["chapter"]} 章'
            if r["have"] > r["chapter"] else '')
    return (
        '<div class="resume">'
        '<div class="rs-t">继续阅读</div>'
        f'<div class="rs-b">{lr.esc(r["title"])}</div>'
        f'<div class="rs-s">上次读至第 {r["chapter"]} 章{more}</div>'
        '<div class="ctrls" style="margin-top:14px">'
        f'<a class="lnkbtn primary" href="/read/{attrescape(r["slug"])}?from={nxt}#c{nxt}">'
        f'从第 {nxt} 章继续</a>'
        f'<a class="lnkbtn" href="/book?id={attrescape(_source_id(r["slug"]))}">'
        '查看详情</a>'
        '</div></div>')


def _source_id(slug: str) -> str:
    return str((novel_meta(slug) or {}).get("source_id") or slug)


def _slug_aliases() -> dict:
    try:
        return lncatalog.load_aliases(recs.LIB_PATH)
    except Exception:  # noqa: BLE001
        return {}


def _resolve_slug(slug: str) -> str:
    return lncatalog.resolve_alias(slug, _slug_aliases())


def _query_without(query: str, drop=("id", "slug")) -> str:
    junk = set(drop)
    pairs = [(k, v) for k, v in urllib.parse.parse_qsl(
        query, keep_blank_values=True) if k not in junk]
    return ("?" + urllib.parse.urlencode(pairs)) if pairs else ""


def page_tags(tag: str) -> str:
    """按标签找书 —— 标签 chip 点进来应该能看到同类作品。

    这是"发现"的关键路径：读者看到「勘違い」这个标签，会想知道还有哪些书
    是这个味道。没有这个页面，标签就只是装饰。
    """
    tag = (tag or "").strip()
    try:
        pool = list(recs.cached() or [])
    except Exception:  # noqa: BLE001
        pool = []
    try:
        pool += [it for it in (recs._load_lib() or {}).values()
                 if not it.get("hidden")]     # 隐藏过的不再出现在标签页
    except Exception:  # noqa: BLE001
        pass
    seen = set()
    hits = []
    for it in pool:
        wid = str(it.get("id") or "")
        if not wid or wid in seen:
            continue
        tags = it.get("tags") or []
        if tag and tag not in tags:
            continue
        seen.add(wid)
        hits.append(it)
    hits.sort(key=lambda x: -(x.get("points") or 0))

    if not tag:
        counts: dict[str, int] = {}
        for it in hits:
            for t in dict.fromkeys(it.get("tags") or []):
                if t:
                    counts[str(t)] = counts.get(str(t), 0) + 1
        all_rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        rows = all_rows[:200]
        if not rows:
            return ('<a class="back" href="/">← 返回书架</a>'
                    '<h1>标签浏览</h1><p class="s">还没有带标签的作品。'
                    '从推荐页加入书架，或点开一本书查看它的标签。</p>')
        cloud = "".join(
            f'<a class="tagcard" href="/tags?q={urllib.parse.quote(t)}">'
            f'<b>{lr.esc(t)}</b><span>{n} 本</span></a>'
            for t, n in rows)
        more = (f" · 显示前 {len(rows)} 个" if len(all_rows) > len(rows) else "")
        return (f'<a class="back" href="/">← 返回书架</a>'
                f'<header class="book"><div class="kicker">标签浏览</div>'
                f'<h1>全部标签</h1><div class="meta">共 {len(all_rows)} 个标签'
                f'{more} · 按作品数排序 · 点标签看同类作品</div></header>'
                f'<div class="tagcloud">{cloud}</div>')
    # 号码必须与真正渲染的卡同源：常见标签（異世界之类）在 400+ 本的书库里
    # 很容易超过 60，旧文案写「找到 200 本」却只画 60 张卡 = 数字骗人。
    total = len(hits)
    shown = hits[:60]
    cards = "".join(_finding_card(h) for h in shown)
    if not cards:
        cards = (f'<p class="s">当前缓存中的 {len(pool)} 部作品没有该标签。'
                 '可在推荐页换一批，扩大候选池。</p>')
    more = f" · 显示前 {len(shown)} 本" if total > len(shown) else ""
    return (f'<a class="back" href="/">← 返回书架</a>'
            f'<header class="book"><div class="kicker">标签浏览</div>'
            f'<h1>「{lr.esc(tag)}」</h1>'
            f'<div class="meta">找到 {total} 本 · 按评分排序{more}</div></header>'
            f'<div class="cards" style="margin-top:16px">{cards}</div>')


def page_tags_doc(tag: str) -> str:
    body = page_tags(tag)
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<script>(function(){{var s=null;try{{s=localStorage.getItem('ln-theme');}}catch(e){{}}
var d=(s==='dark'||s==='light')?s:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.documentElement.setAttribute('data-t',d);document.documentElement.style.colorScheme=d;}})();</script>
<title>{lr.esc(tag)} · 标签</title><link rel="icon" href="data:,">{PWA_HEAD}<style>{CSS}</style></head><body class="pg-list">
<main>
<div class="pagebar"><a class="iconbtn" href="/settings" title="设置">设置</a></div>
{body}
</main>
<script>
{ACTION_JS}
{DISLIKE_JS}
</script></body></html>'''


def _work_pool() -> list[dict]:
    """所有已知作品的合并池：推荐缓存 + 书库留档 + 本地已加入的书。

    三个来源都要，因为"相似"这件事不该受"这本书是爬来的还是你加进来的"影响。
    去重按 source_id；没有标签的作品直接丢掉（无标签无从谈相似）。
    """
    pool: list[dict] = []
    seen: set[str] = set()

    def add(it: dict, tags=None) -> None:
        wid = str(it.get("id") or it.get("source_id") or "")
        t = list(tags if tags is not None else (it.get("tags") or []))
        t = [x for x in t if x]
        if not wid or wid in seen or not t:
            return
        seen.add(wid)
        row = dict(it)
        row["id"] = wid
        row["tags"] = t
        pool.append(row)

    try:
        for it in recs.cached() or []:
            add(it)
    except Exception:  # noqa: BLE001
        pass
    try:
        lib = recs._load_lib() or {}
        # 隐藏的（"不感兴趣"）不能当相似作品的候选 —— 否则你又会被推回来。
        for it in lib.values():
            if not it.get("hidden"):
                add(it)
    except Exception:  # noqa: BLE001
        pass
    for s in all_local_slugs():
        meta = novel_meta(s) or {}
        add({"id": meta.get("source_id"), "title": meta.get("title"),
             "author": meta.get("author"), "url": meta.get("url"),
             "tags": meta.get("tags"), "points": meta.get("points") or 0,
             "episodes": len(meta.get("episodes") or [])}, meta.get("tags"))
    return pool


SIM_MIN_SCORE = 0.9          # 低于这个分不算"相似"（别硬凑满 N 本）
SIM_MAX_SHARED = 5           # 卡片上最多列几个共有标签


def similar_works(work_id: str, tags, author: str = "", n: int = 6,
                  pool: list[dict] | None = None) -> list[tuple[dict, list[str], float]]:
    """同标签的相似作品，按 **IDF 加权的标签重合度** 排序。

    为什么不能用"重合标签个数"排序：
    異世界 / 転生 / 主人公最強 这类大词几乎人人都有，谁重合得多谁排前面，
    结果推出来的全是"最热门"而不是"最像"。所以给每个标签按
    log(1 + N/df) 加权 —— 重合一个冷门标签（勘違い、悪役令嬢）
    比重合三个大词更能说明味道相同。这正是用户口味画像里
    "有辨识度的标签优先"的同一个思路。

    `pool` 可注入（自检用合成池验证加权逻辑，不碰真实数据）。
    """
    wid = str(work_id or "")
    mine = {t for t in (tags or []) if t}
    if not mine:
        return []
    pool = _work_pool() if pool is None else pool
    if not pool:
        return []
    total = len(pool)
    df: dict[str, int] = {}
    for it in pool:
        for t in set(it.get("tags") or []):
            df[t] = df.get(t, 0) + 1

    rows = []
    for it in pool:
        if str(it.get("id") or "") == wid:
            continue                      # 别把自己推给自己
        shared = [t for t in dict.fromkeys(it.get("tags") or []) if t in mine]
        if not shared:
            continue
        score = sum(math.log(1 + total / (1 + df.get(t, 1))) for t in shared)
        if author and it.get("author") and it.get("author") == author:
            score += 1.2                  # 同作者通常同一味道
        if score < SIM_MIN_SCORE:
            continue
        rows.append((score, it, shared))
    rows.sort(key=lambda r: (-r[0], -(r[1].get("points") or 0),
                             str(r[1].get("id") or "")))
    return [(it, shared, score) for score, it, shared in rows[:n]]


def similar_block(work_id: str, tags, author: str = "", n: int = 6) -> str:
    """详情页的「同标签的相似作品」。

    详情页是"要不要读"的决策点。读者看完简介的下一句话就是
    「还有没有类似的」—— 没有这一块，他就得自己回书架猜。
    """
    try:
        rows = similar_works(work_id, tags, author=author, n=n)
    except Exception:  # noqa: BLE001
        return ""
    if not rows:
        return ""
    have = shelf_source_ids()
    items = []
    for it, shared, _sc in rows:
        wid2 = str(it.get("id") or "")
        if not wid2:
            continue
        det2 = load_detail(wid2)
        zh = det2.get("zh_title") or ""
        jp = it.get("title") or ""
        name = zh or jp
        sub = (f'<span class="simjp">{lr.esc(jp)}</span>'
               if zh and zh != jp else "")
        on = ('<span class="chip ok">在书架</span>'
              if wid2 in have else "")
        items.append(
            f'<a class="simrow" href="/book?id={attrescape(wid2)}">'
            f'<span class="simt">{lr.esc(name)}{sub}{on}</span>'
            f'<span class="simtag">共同标签 · '
            f'{lr.esc("、".join(shared[:SIM_MAX_SHARED]))}</span>'
            f'<span class="simp">{it.get("episodes") or 0} 话 · '
            f'{ln_fmt(it.get("points"))}pt</span></a>')
    if not items:
        return ""
    return ('<details class="shelf" open><summary><span class="arrow">▸</span>'
            '相似作品<span class="n">' + str(len(items)) + ' 本'
            '</span></summary>'
            '<div class="simlist">' + "".join(items) + '</div>'
            '<div class="s" style="margin:10px 2px 14px;font-family:var(--ui);'
            'font-size:11.5px;color:var(--ct)">'
            '按标签重合度排序，冷门标签权重更高'
            '</div></details>')


def dislike_button(wid: str, label: str = "不感兴趣") -> str:
    """「不感兴趣」按钮 —— 推荐卡和书库卡共用。

    只有一个按钮，但点下去会展开原因选择：**原因决定扣哪些标签**。
    「太套路了」只该怪套路标签（異世界転生 之类），不能连带把
    有辨识度的标签（勘違い、悪役令嬢）一起扣掉 —— 那是在教坏画像。
    """
    if not wid:
        return ""
    return f'<button data-dislike="{attrescape(str(wid))}">{lr.esc(label)}</button>'


def queue_view() -> dict:
    """翻译列表的数据（页面与 /api/queue 共用一处，避免两套口径）。"""
    view = SCHED.view(
        lambda slug: have_count(slug, novel_meta(slug) or {}),
        lambda slug: len((novel_meta(slug) or {}).get("episodes") or []))
    view["over_budget"] = SCHED.over_budget()
    for row in view["rows"] + view["paused_rows"]:
        meta = novel_meta(row["slug"]) or {}
        row["title"] = ((meta.get("zh_titles") or {}).get("book")
                        or meta.get("title") or row["slug"])
        row["read"] = read_chapter(row["slug"])
    # Failed/completed are archive rows, not queue candidates.  Keep the latest
    # record per book and enrich with the same title/progress fields.
    failed, completed = [], []
    try:
        records = jobstore.STORE.records()
    except Exception:  # noqa: BLE001
        records = []
    latest = {}
    for r in records:
        slug = str(r.get("slug") or "")
        if slug:
            latest[slug] = r
    for slug, r in latest.items():
        st = str(r.get("status") or "")
        if st not in ("provider_error", "error", "interrupted",
                      "budget_exhausted", "partial", "done", "cancelled"):
            continue
        meta = novel_meta(slug) or {}
        title = ((meta.get("zh_titles") or {}).get("book")
                 or meta.get("title") or slug)
        have = have_count(slug, meta)
        total = len(meta.get("episodes") or [])
        row = {"slug": slug, "title": title, "status": st,
               "error": str(r.get("error") or ""),
               "have": have, "total": total,
               "updated_at": r.get("updated_at") or ""}
        if st in ("done", "partial", "cancelled"):
            completed.append(row)
        else:
            failed.append(row)
    view["failed"] = sorted(failed, key=lambda x: x["updated_at"], reverse=True)[:20]
    view["completed"] = sorted(completed, key=lambda x: x["updated_at"], reverse=True)[:20]
    return view


def queue_body(embedded: bool = False) -> str:
    v = queue_view()
    rows = v["rows"]
    reading = [r for r in rows if r["reason"] == "reading"]
    queued = [r for r in rows if r["reason"] == "queue"]
    paused_rows = v["paused_rows"]
    all_rows = rows + paused_rows
    have_sum = sum(int(r.get("have") or 0) for r in all_rows)
    total_sum = sum(int(r.get("total") or 0) for r in all_rows)
    all_pct = round(have_sum / total_sum * 100) if total_sum else 0
    left_chars = max(0, total_sum - have_sum)

    def row_html(r: dict) -> str:
        pct = round((r["have"] / r["total"]) * 100) if r["total"] else 0
        why = ("在读 · 持续翻译" if r["reason"] == "reading" else "翻译队列")
        if r.get("queued") and r["reason"] == "reading":
            why += "（也在翻译队列里）"
        if r.get("read"):
            why += f" · 读到第 {r['read']} 章"
        return (f'<li class="qrow" data-slug="{attrescape(r["slug"])}">'
                f'<div class="qmain"><a href="/read/{attrescape(r["slug"])}">'
                f'{lr.esc(r["title"])}</a>'
                f'<span class="qwhy">{lr.esc(why)}</span></div>'
                f'<div class="qops">'
                f'<button data-q="pause">暂停</button>'
                + (f'<button data-q="up">上移</button>'
                   f'<button data-q="down">下移</button>'
                   f'<button data-q="remove">移出队列</button>'
                   if r["reason"] == "queue" else
                   f'<button data-q="forget">移出队列</button>')
                + '</div>'
                f'<div class="qbar"><i style="width:{pct}%"></i></div>'
                f'<div class="qmeta"><span>已译 {r["have"]}/{r["total"]}</span>'
                f'<span>{pct}%</span></div></li>')

    empty = ('<p class="s">还没有正在读或排队的书。去书架点开一本书，'
             '它就会一直往后翻；或在这里把书加进翻译列表。</p>')
    body = ""
    if reading:
        body += (f'<h3 class="qgroup">正在读'
                 f'<span>自动持续翻译 · {len(reading)} 本</span></h3>'
                 '<ul class="qlist">' + "".join(row_html(r) for r in reading) + '</ul>')
    if queued:
        body += (f'<h3 class="qgroup">翻译队列'
                 f'<span>按顺序提前翻 · {len(queued)} 本</span></h3>'
                 '<ul class="qlist">' + "".join(row_html(r) for r in queued) + '</ul>')
    if paused_rows:
        body += (f'<h3 class="qgroup">已暂停'
                 f'<span>不会自动继续 · {len(paused_rows)} 本</span></h3>'
                 '<ul class="qlist">'
                 + "".join(
                     f'<li class="qrow is-paused" data-slug="{attrescape(r["slug"])}">'
                     f'<div class="qmain"><a href="/read/{attrescape(r["slug"])}">'
                     f'{lr.esc(r["title"])}</a>'
                     f'<span class="qwhy">已暂停</span></div>'
                     f'<div class="qops">'
                     f'<button data-q="resume">继续</button>'
                     f'<button data-q="forget">移出队列</button>'
                     f'</div>'
                     f'<div class="qbar"><i style="width:'
                     f'{round(r["have"] / r["total"] * 100) if r["total"] else 0}%"></i></div>'
                     f'<div class="qmeta"><span>已译 {r["have"]}/{r["total"]}</span>'
                     f'<span>{round(r["have"] / r["total"] * 100) if r["total"] else 0}%</span></div>'
                     f'</li>'
                     for r in paused_rows) + '</ul>')
    if not all_rows:
        body = empty

    _left = v["budget_left"]
    status = ("已全局暂停" if v["paused"] else
              ("今日超出预算（仍在继续）" if v["over_budget"] else "运行中"))
    crumbs = ('' if embedded else
              '<nav class="crumbs"><a href="/">← 返回书架</a>'
              '<span>·</span><span>翻译列表</span></nav>')
    return f'''{crumbs}
<header class="book"><div class="bookline"><div><h1>翻译列表</h1>
<div class="meta">在读就一直翻；也可以把书加进来提前翻</div></div></div>
<div class="bookmeta">状态 <b>{status}</b> · 今日云端已用 <b>{v["used_today"]:,}</b> /
{v["budget"]:,} token（0 = 不限）· 剩余 <b>{max(0, _left):,}</b></div>
<div class="qstats">
  <div><b>{len(all_rows)}</b><span>本在列表</span></div>
  <div><b>{len(reading)}</b><span>在读自动翻</span></div>
  <div><b>{len(queued)}</b><span>排队提前翻</span></div>
  <div><b>{len(paused_rows)}</b><span>已暂停</span></div>
</div>
<div class="qprog">
  <div class="qprog-head"><span>全部进度</span>
    <span>已译 {have_sum}/{total_sum} 章 · 还差 {left_chars} 章 · {all_pct}%</span></div>
  <div class="qbar"><i style="width:{all_pct}%"></i></div>
</div>
<div class="tools" style="margin-top:10px">
  <button id="q-toggle" data-paused="{int(v["paused"])}">{'继续全部' if v["paused"] else '全部暂停'}</button>
  <label style="font-family:var(--ui);font-size:13px;color:var(--ct)">
    每日预算 <input id="q-budget" type="number" min="0" step="10000"
      value="{v["budget"]}" style="width:96px;padding:4px 6px;border-radius:6px;
      border:1px solid var(--rule);background:var(--paper);color:var(--ink)"> token
  </label>
  <label style="font-family:var(--ui);font-size:13px;color:var(--ct)">
    离开多久算"没读了" <input id="q-idle" type="number" min="1" max="1440"
      value="{v["idle_minutes"]}" style="width:64px;padding:4px 6px;border-radius:6px;
      border:1px solid var(--rule);background:var(--paper);color:var(--ink)"> 分钟
  </label>
</div>
<p class="s" style="margin-top:8px">本地模型 0 元，不计入 token；这里统计的是云端消耗。
  预算只是提醒：超了仍会继续翻你正在读的书；想停请用「暂停」。
  {'<b style="color:#c05a5a">今日预算已用尽</b> <button id="q-add5">+5 万</button> <button id="q-add10">+10 万</button>' if v["budget"] > 0 and _left <= 0 else ''}</p>
</header>
{body}
<div class="fb" style="margin-top:26px"><h3>把书加进翻译列表</h3>
<p class="s">从书架里挑一本（已译完的会显示 100%，加进去也不会重复翻）。</p>
<div class="lib-search" style="margin-top:8px">
  <input id="q-add" placeholder="搜索书架里的书名" autocomplete="off">
  <button id="q-add-btn">加入</button>
</div>
<ul class="qlist" id="q-cands"></ul>
</div>'''


def page_queue() -> str:
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>翻译列表</title>
<link rel="icon" href="data:,">{PWA_HEAD}<style>{CSS}</style></head><body class="pg-home">
<main>
<div class="pane on" id="pane-queue">{queue_body()}</div>
</main>
<script>{QUEUE_JS}{META_JS}</script>
</body></html>'''


def page_detail(work_id: str) -> str | None:
    """作品详情页 —— 决定"要不要读"的地方。

    合格的轻小说作品页要回答四个问题：
      1. 讲什么？        → 简介
      2. 什么类型？      → 标签 / 分类
      3. 多长、完结没、口碑？ → 话数 / 字数 / 积分 / 状态
      4. 我读到哪了？    → 阅读进度 + 目录
    并给出下一步动作：加入书架 / 开始阅读 / 去源站。
    """
    slug = None
    for s in all_local_slugs():
        if s == work_id or (novel_meta(s) or {}).get("source_id") == work_id:
            slug = s
            break

    item = None
    try:
        for cand in recs.cached(include_hidden=True) or []:
            if str(cand.get("id")) == str(work_id):
                item = cand
                break
    except Exception:  # noqa: BLE001
        pass
    if item is None:
        try:
            item = (recs._load_lib() or {}).get(str(work_id))
        except Exception:  # noqa: BLE001
            item = None
    if item is None and slug:
        meta = novel_meta(slug) or {}
        item = {"title": meta.get("title"), "author": meta.get("author"),
                "url": meta.get("url"), "tags": meta.get("tags") or [],
                "episodes": len(meta.get("episodes") or [])}
    if not item:
        return None

    title = item.get("title") or ""
    url = item.get("url") or ""
    author = item.get("author") or ""
    tags = list(item.get("tags") or [])
    genre = GENRE_ZH.get(item.get("genre") or "", item.get("genre") or "")
    status = item.get("status") or ""
    episodes = item.get("episodes") or 0
    chars = item.get("characters") or 0
    points = item.get("points") or item.get("review_points") or 0
    updated = item.get("updated") or item.get("last_episode_at") or ""

    det = refresh_detail(str(work_id), url) if url else {}
    synopsis = (det.get("synopsis") or item.get("synopsis")
                or item.get("catchphrase") or "")
    toc = det.get("toc") or []
    if not toc and slug:
        _m = novel_meta(slug) or {}
        if (_m.get("source") or "") == "local":
            # 本地书没有源站目录可抓：直接用导入时解析出的章节列表。
            toc = [{"title": "", "episodes": [
                {"title": e.get("title") or f"第{i + 1}话",
                 "at": ""} for i, e in enumerate(_m.get("episodes") or [])]}]

    # 中文标题：本地已译的优先，其次详情缓存（按需翻好存下的）
    zh_title = ""
    if slug:
        zh_title = ((novel_meta(slug) or {}).get("zh_titles") or {}).get("book") or ""
    if not zh_title:
        zh_title = det.get("zh_title") or ""
    zh_syn = det.get("zh_synopsis") or ""
    # 有没有正在后台翻
    tr_pending = bool((TR_JOBS.get(str(work_id)) or {}).get("status") in ("queued", "running"))

    facts = []
    if genre:
        facts.append((genre, "g"))
    if status:
        facts.append((status, ""))
    if episodes:
        facts.append((f"约 {episodes} 话", ""))
    if chars:
        facts.append((f"{chars / 10000:.1f} 万字" if chars >= 10000 else f"{chars} 字", ""))
    if points:
        facts.append((f"★ {points:,} pt", ""))
    if updated:
        facts.append((f"更新 {updated}", ""))
    chips = "".join(f'<span class="chip {c}">{lr.esc(t)}</span>' for t, c in facts)
    tag_chips = "".join(
        f'<a class="chip tag" href="/tags?q={urllib.parse.quote(t)}">{lr.esc(t)}</a>'
        for t in tags[:30])

    # 目录
    toc_html = ""
    if toc:
        parts = []
        for ch in toc:
            eps = ch.get("episodes") or []
            shown = eps[:400]
            rows = "".join(
                '<li><span class="epn">' + lr.esc(e.get("title") or "") +
                '</span><span class="epd">' + lr.esc(e.get("at") or "") + "</span></li>"
                for e in shown)
            ct = ch.get("title") or ""
            if ct:
                # 分卷话数必须和真正列出的条数同源：单卷超过 400 话时
                # 写「500 话」却只画 400 条 = 数字骗人（标签页同款问题）。
                more = f" · 显示前 {len(shown)}" if len(eps) > len(shown) else ""
                parts.append('<div class="tocch">' + lr.esc(ct) +
                             f'<span class="n">{len(eps)} 话{more}</span></div>')
            parts.append('<ul class="toc">' + rows + "</ul>")
        n_eps = det.get("episode_count") or episodes
        # 大目录默认折叠：130 话全展开会把手机详情页撑到 ~1 万像素，
        # 读者要滚很久才能看到下面的内容。短目录（≤20 话）仍默认展开，
        # 不用为两三章的书多点一次。
        toc_open = " open" if n_eps <= 20 else ""
        toc_html = (f'<details class="shelf"{toc_open}><summary><span class="arrow">▸</span>'
                    '目录<span class="n">共 ' + str(n_eps) + ' 话</span></summary>'
                    + "".join(parts) + "</details>")

    # 操作区
    if slug:
        tk = read_tracking(slug)
        _bd = _read_book(slug)
        fav = bool(_bd.get("favorites"))
        pr = (_bd.get("progress") or {})
        at = int(pr.get("chapter") or 1)

        def on(cond):
            return " on" if cond else ""

        # ⚠ ★收藏 的 on 状态必须**来自真实数据**。
        # 踩过（用户就在这一步卡住）：这里原来写死 class="lnkbtn on"，
        # 于是①星永远显示"已收藏"，用户以为「加入书架」被当成了收藏；
        # ②点击时前端读到 on=true → 永远发 value:false → **收藏永远开不了**，
        # 连点四次都"没反应"（server.log: favorite=False ×5）。
        ops = ('<div class="ctrls" style="margin-top:16px">'
               f'<a class="lnkbtn primary" href="/read/{attrescape(slug)}?from={at}#c{at}">继续阅读</a>'
               f'<button type="button" class="lnkbtn{on(fav)}" data-d-slug="{attrescape(slug)}"'
               f' data-d-act="favorite" title="收藏表示偏好：用于学习阅读口味，'
               f'并始终检查更新；与能否阅读无关。">'
               f'{"★ 已收藏" if fav else "☆ 收藏"}</button>'
               f'<button type="button" class="lnkbtn{on(tk == "finished")}" data-d-slug="{attrescape(slug)}" data-d-act="finished">读完</button>'
               f'<button type="button" class="lnkbtn{on(tk == "dropped")}" data-d-slug="{attrescape(slug)}" data-d-act="dropped">弃文</button>'
               f'<button type="button" class="lnkbtn danger" data-d-slug="{attrescape(slug)}" data-d-act="off">移出书架</button>'
               f'<button type="button" class="lnkbtn" data-qadd="{attrescape(slug)}"'
               f' title="加入后即使不打开这本书也会按顺序提前翻译">加入翻译列表</button>'
               '</div>'
               # 用户明确提过：「加入书架不等于收藏」。这段解释默认收起，
               # 需要时能查，但不再每次占三行。
               '<details class="minihelp"><summary>加入书架与收藏的区别</summary>'
               '<div>加入书架决定<b>能否阅读</b>；收藏记录<b>偏好</b>'
               '（参与口味学习）。两者相互独立，只读不收藏完全可行。</div></details>')
        have = have_count(slug, novel_meta(slug) or {})
        prog = (f'<div class="fb" style="margin-top:26px"><h3>阅读进度</h3>'
                f'<div class="s">已读至第 {at} 章' +
                (f' · 本书已译 {have} 章' if have else '') + '</div></div>')
    else:
        ops = ('<div class="ctrls" style="margin-top:16px">'
               f'<button type="button" class="primary" data-d-add="{attrescape(url)}" data-d-id="{attrescape(str(work_id))}"'
               f' title="加入书架后可阅读与翻译；这不是收藏，也不影响偏好画像。">加入书架</button>'
               '<a class="lnkbtn" href="/">返回书架</a></div>'
               '<details class="minihelp"><summary>加入书架的含义</summary>'
               '<div>加入书架只是让你<b>能够阅读</b>这部作品，不是收藏，也不影响偏好画像。</div>'
               '</details>')
        prog = ""

    src_link = (f'<a class="lnkbtn" href="{attrescape(url)}" target="_blank" rel="noopener">'
                '在源站查看（日文）</a>') if url else ""
    # 中文当主标题（大），日文原名跟在后面（小 + 半透明）
    sub = ""
    if zh_title and zh_title != title:
        sub = f'<div class="jp-sub">{lr.esc(title)}</div>'
    elif not zh_title:
        # 还没译：先显示日文，并在下面说明正在翻
        sub = ""
    _is_local = bool(slug and ((novel_meta(slug) or {}).get("source") == "local"
                              or str((novel_meta(slug) or {}).get("source_id") or "").startswith("local-")))
    _lm = novel_meta(slug) if slug else {}
    if _is_local:
        # 本地导入没有源站简介：优先用导入时留下的 description；
        # 没有就显示正文开头摘录，明确标注“不是源站简介”。
        _desc = str(_lm.get("description") or _lm.get("synopsis") or "").strip()
        if not _desc and slug:
            try:
                with open(os.path.join(NOVELS, slug, "raw", "0000.txt"),
                          encoding="utf-8") as _f:
                    _desc = _f.read(900).strip()
            except OSError:
                _desc = ""
        if _desc:
            syn = (f'<div class="syn">{lr.esc(_desc)}</div>'
                   '<div class="s" style="margin-top:6px">'
                   '本地文件开头摘录（不是源站简介）</div>')
        else:
            syn = '<span class="s">本地文件没有可读的开头摘录。</span>'
    elif synopsis:
        if zh_syn:
            syn = (f'<div class="syn">{lr.esc(zh_syn)}</div>'
                   f'<details class="orig"><summary>查看日文原文</summary>'
                   f'<div class="syn jp">{lr.esc(synopsis)}</div></details>')
        else:
            syn = (f'<div class="syn">{lr.esc(synopsis)}</div>'
                   + ('<div class="s" style="margin-top:8px">正在翻译简介…</div>'
                      if tr_pending else
                      '<div class="s" style="margin-top:8px">'
                      '暂无中文简介，可点击下方按钮翻译。</div>'))
    else:
        syn = '<span class="s">暂时无法获取简介，可点击下方按钮重试</span>'
    h_zh = zh_title or title

    # 同标签的相似作品：详情页是"要不要读"的决策点，
    # 读者看完简介的下一句就是「还有没有类似的」
    # 详情信息块：把源站/本地文件里已有的元信息一次列出来，
    # 避免读者只看到一句简介和几个标签。
    _info = []
    if author:
        _info.append(("作者", author))
    _info.append(("来源", "本地导入" if _is_local else "源站"))
    if episodes:
        _info.append(("章节", f"{episodes} 话"))
    if chars:
        _info.append(("字数", f"{chars / 10000:.1f} 万字" if chars >= 10000 else f"{chars} 字"))
    if points:
        _info.append(("评价", f"{points:,} pt"))
    if updated:
        _info.append(("更新", updated))
    if _is_local:
        if _lm.get("file_name"):
            _info.append(("文件", str(_lm.get("file_name"))))
        if _lm.get("format"):
            _info.append(("格式", str(_lm.get("format")).upper()))
        if _lm.get("created_at"):
            _info.append(("加入", str(_lm.get("created_at"))))
        _info.append(("已译", f"{have_count(slug, _lm)} 话"))
    _info_html = "".join(
        f'<div class="infrow"><span>{lr.esc(k)}</span><b>{lr.esc(v)}</b></div>'
        for k, v in _info)
    _info_html = (f'<div class="info-block"><div class="info-title">作品信息</div>'
                  f'<div class="infobox">{_info_html}</div></div>'
                  if _info else "")

    sim_html = similar_block(str(work_id), tags, author=author)

    return (
        '<a class="back" href="/">← 返回书架</a>'
        '<header class="book">'
        f'<div class="kicker">{lr.esc(author) or "未知作者"}</div>'
        f'<h1>{lr.esc(zh_title or title)}</h1>{sub}'
        f'<div class="chips">{chips}</div>'
        f'<div class="chips">{tag_chips}</div>'
        f'{cover_html(item)}'
        f'{ops}{src_link}</header>'
        + (f'<div class="fb" style="margin-top:28px"><h3>作品简介</h3>'
           f'{syn}</div>' if syn else '')
        + f'{prog}'
        + f'{_info_html}'
        + ('' if _is_local else
           '<div class="ctrls" style="margin:16px 0">'
           + ('' if zh_syn else
              f'<button type="button" id="d-tr" data-id="{attrescape(str(work_id))}">'
              + ('翻译中…' if tr_pending else '翻译标题与简介')
              + '</button>'
              + '<span class="hint">标题与简介较短，翻译开销极小</span>')
           + f'<button type="button" id="d-refresh" data-id="{attrescape(str(work_id))}">刷新作品信息</button>'
           '</div>')
        # 相似作品必须排在**目录前面**：目录动辄几百话（有的作品 400+），
        # 放在目录之后等于藏起来了 —— 读者永远看不到"还有类似的吗"。
        + f'{sim_html}'
        + f'{toc_html}'
    )


DETAIL_JS = _read_static("detail.js")


def page_detail_doc(work_id: str) -> str | None:
    body = page_detail(work_id)
    if body is None:
        return None
    _sl = _slug_index().get(str(work_id))
    _local = bool(_sl and ((novel_meta(_sl) or {}).get("source") == "local"
                           or str((novel_meta(_sl) or {}).get("source_id") or "").startswith("local-")))
    # 本地书没有源站简介：别再自动打 /api/translate_meta（它只会返回"没有内容"）。
    _has_zh_syn = _local or bool(
        (load_detail(str(work_id)) or {}).get("zh_synopsis"))
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<script>(function(){{var s=null;try{{s=localStorage.getItem('ln-theme');}}catch(e){{}}
var d=(s==='dark'||s==='light')?s:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.documentElement.setAttribute('data-t',d);document.documentElement.style.colorScheme=d;}})();</script>
<title>作品详情</title><link rel="icon" href="data:,">{PWA_HEAD}<style>{CSS}</style></head><body class="pg-detail">
<script>window.__WID__={_js_json(str(work_id))};window.__ZH_SYN__={'true' if _has_zh_syn else 'false'};</script>
<main>
<div class="pagebar"><a class="iconbtn" href="/settings" title="设置">设置</a></div>
{body}
</main>
<script>
{ACTION_JS}
{DETAIL_JS}
</script></body></html>'''


def _trans_summary_html() -> str:
    """设置页的「翻译」摘要：模型角色 + 今日花费（只读）。"""
    try:
        mc = lnmodels.public_config()
        models = mc.get("roles") or {}
        line = " · ".join(
            f"{label} {((models.get(role) or {}).get('model') or '?')}"
            for role, label in (("translate", "翻译"),
                                ("auxiliary", "辅助"), ("review", "校对")))
        spent = float(mc.get("spent_today") or 0)
        daily = float(mc.get("daily_budget") or 0)
        cur = mc.get("currency", "CNY")
        budget = (f"今日 {cur} {spent:.4f} / {daily:.2f}" if daily > 0
                  else f"今日约 {cur} {spent:.4f}（未设日预算）")
        key = ("本地端点，无需密钥" if mc.get("local")
               else ("密钥已配置" if mc.get("key_configured") else "未配置密钥"))
        return (f'<div class="s">{lr.esc(line)}</div>'
                f'<div class="s">{lr.esc(budget)} · {lr.esc(key)}</div>')
    except Exception:  # noqa: BLE001
        return '<div class="s">模型信息暂时不可用</div>'


def queue_summary_html() -> str:
    try:
        v = queue_view()
    except Exception:  # noqa: BLE001
        return ""
    rows = list(v.get("rows") or []) + list(v.get("paused_rows") or [])
    if not rows:
        return ('<div class="ui-panel"><div class="ui-section-head">'
                '<div><span class="ui-kicker">TRANSLATION</span>'
                '<h2>翻译列表</h2><p>现在没有进行中的任务。</p></div>'
                '<a class="ui-btn ui-btn-ghost" href="/queue">打开</a></div></div>')
    have = sum(int(r.get("have") or 0) for r in rows)
    total = sum(int(r.get("total") or 0) for r in rows)
    pct = round(have / total * 100) if total else 0
    cur = next((r for r in rows if r.get("reason") == "reading"), rows[0])
    _all_paused = bool(rows) and all(r.get("reason") == "paused" for r in rows)
    status = ("已全局暂停" if v.get("paused") else
              ("已暂停" if _all_paused else
               ("今日超出预算（仍在继续）" if v.get("over_budget") else "运行中")))
    return ('<div class="ui-panel" data-queue-summary>'
            '<div class="ui-section-head"><div><span class="ui-kicker">TRANSLATION</span>'
            f'<h2>翻译进行中</h2><p>{len(rows)} 本 · {lr.esc(status)} · '
            f'已译 {have}/{total} 话（{pct}%）</p></div>'
            '<a class="ui-btn ui-btn-ghost" href="/queue">查看队列</a></div>'
            f'<div class="ui-qbar"><i style="width:{pct}%"></i></div>'
            f'<p class="ui-help">当前：{lr.esc(cur.get("title") or cur.get("slug") or "")}'
            f' · 今日云端 {int(v.get("used_today") or 0):,} token</p></div>')


def page_settings() -> str:
    lan_enabled = BIND_HOST not in ("127.0.0.1", "localhost")
    remembered = 0
    if lan_enabled:
        try:
            remembered = len(devstore.describe(device_store_path()))
        except Exception:  # noqa: BLE001
            remembered = 0
    return lnui.render_settings(
        pwa_head=PWA_HEAD,
        translation_summary=_trans_summary_html(),
        lan_enabled=lan_enabled,
        remembered=remembered,
        queue_summary=queue_summary_html(),
    )



IMPORT_THREADS: set[str] = set()
IMPORT_LOCK = threading.RLock()


def _import_jobs_dir() -> str:
    return os.path.join(DATA, "import_jobs")


def _import_job_path(job_id: str) -> str:
    if not re.fullmatch(r"imp-[0-9A-Za-z_-]+", job_id or ""):
        raise ValueError("非法导入任务")
    return os.path.join(_import_jobs_dir(), f"{job_id}.json")


def _import_data_path(job_id: str) -> str:
    return os.path.join(_import_jobs_dir(), f"{job_id}.bin")


def _read_import_job(job_id: str) -> dict:
    path = _import_job_path(job_id)
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_import_job(job: dict) -> None:
    os.makedirs(_import_jobs_dir(), exist_ok=True)
    job["updated_at"] = lncatalog.utc_now()
    lndata.atomic_write_json(_import_job_path(str(job["id"])), job)


def _run_import_job(job_id: str) -> None:
    job = _read_import_job(job_id)
    if not job:
        return
    bin_path = _import_data_path(job_id)
    try:
        with open(bin_path, "rb") as f:
            data = f.read()
        job["status"] = "running"
        job["progress"] = max(0.01, float(job.get("progress") or 0.0))
        job.pop("error", None)
        _write_import_job(job)

        def progress(value):
            try:
                pct = max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                return
            if pct < 1.0 and pct - float(job.get("progress") or 0) < 0.01:
                return
            job["progress"] = round(pct, 4)
            _write_import_job(job)

        info = lnimport.import_bytes(
            data, str(job.get("filename") or "upload.txt"),
            title=str(job.get("title") or ""),
            author=str(job.get("author") or ""),
            slug=str(job.get("slug") or ""),
            novels_dir=NOVELS, progress=progress)
        slug = str(info.get("slug") or job.get("slug") or "")
        job.update({"status": "done", "progress": 1.0, "slug": slug,
                    "title": info.get("title") or "",
                    "chapters": info.get("chapters") or 0,
                    "created": bool(info.get("created"))})
        try:
            lndata.atomic_write_json(
                os.path.join(NOVELS, slug, ".import.json"),
                {"schema_version": 1,
                 "sha256": job.get("sha256") or "",
                 "filename": job.get("filename") or "",
                 "state": "done",
                 "chapters": job["chapters"],
                 "completed_at": lncatalog.utc_now()})
        except OSError:
            pass
        _write_import_job(job)
    except (Exception, SystemExit) as ex:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = f"{type(ex).__name__}: {ex}"
        try:
            _write_import_job(job)
        except OSError:
            pass
    finally:
        with IMPORT_LOCK:
            IMPORT_THREADS.discard(job_id)


def _start_import_job(job_id: str) -> None:
    with IMPORT_LOCK:
        if job_id in IMPORT_THREADS:
            return
        IMPORT_THREADS.add(job_id)
    threading.Thread(target=_run_import_job, args=(job_id,), daemon=True,
                     name=f"import-{job_id}").start()


def _new_import_job(name: str, title: str, author: str, data: bytes) -> dict:
    os.makedirs(_import_jobs_dir(), exist_ok=True)
    job_id = "imp-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4)
    slug = ""
    try:
        slug = lncatalog.choose_slug(lncatalog.new_local_id(), _slug_aliases())
        n = 2
        while os.path.isdir(os.path.join(NOVELS, slug)):
            slug = lncatalog.choose_slug(
                lncatalog.new_local_id() + f"-{n}", _slug_aliases())
            n += 1
    except Exception:  # noqa: BLE001
        slug = ""
    with open(_import_data_path(job_id), "wb") as f:
        f.write(data)
    job = {"id": job_id, "status": "queued", "progress": 0.0,
           "filename": name, "title": title, "author": author,
           "slug": slug, "sha256": hashlib.sha256(data).hexdigest(),
           "chapters": 0, "created_at": lncatalog.utc_now()}
    _write_import_job(job)
    _start_import_job(job_id)
    return job


def page_import() -> str:
    return lnui.render_import(pwa_head=PWA_HEAD)


def page_library(items: list[dict], jobs: dict) -> str:
    """分堆渲染：收藏置顶、看完收起、放弃更靠后。"""
    # 分组必须覆盖**所有** tracking 取值。
    # 踩过：状态机加了 tracking="want" 之后忘了建这一堆，
    # 于是书从所有分组里掉出去 —— 书架显示"还是空的"，
    # 但 library() 明明有 1 本（用户看到的就是"点了没反应"）。
    def tk(it):
        return it.get("tracking") or "want"

    # ⚠ 只有在书架上的书才显示。
    # "在书架上" = 收藏 或 有 tracking 标记（见 library() 的 on_shelf）。
    # 踩过：没有这个过滤时，点"移出书架/移除在看"会退回 tracking=want，
    # 而 want 也是一个分组 → 书永远删不掉（用户报的 bug）。
    # 之前的"兜底把漏掉的书放回新加入"更是把这个问题藏起来了，已删除。
    shelved = [it for it in items if it.get("on_shelf")]

    fav = [it for it in shelved if it["favorite"]]
    rest = [it for it in shelved if not it["favorite"]]
    want = [it for it in rest if tk(it) == "want" and it["read"] > 0]
    new_books = [it for it in rest if tk(it) == "want" and it["read"] == 0]
    reading = [it for it in rest if tk(it) == "reading"]
    finished = [it for it in rest if tk(it) == "finished"]
    dropped = [it for it in rest if tk(it) == "dropped"]

    # 「有 N 本更新了」只列**当前还会查更新**的书（与 watch_list() 同一判定）。
    # 踩过：这里原来用全量 items，于是移出书架/弃文/看完（非收藏）的书也被算进来 ——
    # 明明已经不查它了、也读不到新章，首页却还报"有 N 本更新了"，点进去点不开。
    # 用零 I/O 的 _item_watches(it)，与书架卡片徽标**同一份判定**：
    # 两处各写一遍迟早漂移，而且这里每本再 book_status()+_read_book() 两次文件读，
    # 书架几百本时正好撞上首页 0.5s 的性能红线。
    updated = [it for it in shelved
               if it.get("has_update") and _item_watches(it)]
    upd_html = ""
    if updated:
        lis = "".join(
            f'<li><a href="/read/{it["slug"]}?from={max(1, it["read"])}">'
            f'{lr.esc(it["title"][:34])}</a> '
            f'<span style="color:var(--ct);font-size:.85em">'
            f'新增{(" " + str(it["new_episodes"]) + " 话") if it["new_episodes"] else "章节"}'
            f'{("，最新 " + it["last_episode_at"]) if it.get("last_episode_at") else ""}</span></li>'
            for it in updated)
        upd_html = (f'<div class="fb" style="margin:22px 0 0">'
                    f'<h3>{len(updated)} 部作品有新章节</h3>'
                    f'<ul style="margin:2px 0 0;padding-left:18px;'
                    f'font-family:var(--ui);font-size:13px;line-height:2">{lis}</ul></div>')

    def shelf(title, items_, open_=True, note="", key=""):
        if not items_:
            return ""
        total_n = len(items_)
        # 每个堆单独分页：只渲染当前页，书多了也不会一次铺几百张卡片
        page = _shelf_page(key)
        pages = max(1, (total_n + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(1, min(page, pages))
        if key:
            _remember_shelf_page(key, page)
        chunk = items_[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
        body = "".join(_card(it, jobs) for it in chunk)
        _anchor = "shelf:" + (key or title)
        pg = pager(total_n, page, PAGE_SIZE, _anchor) if total_n > PAGE_SIZE else ""
        # 顶部也放精简分页：翻页回来落在堆顶，不用再滚到底（用户报过"要从下往上看"）。
        pg_top = pager(total_n, page, PAGE_SIZE, _anchor, compact=True) if total_n > PAGE_SIZE else ""
        _sid = f' id="shelf-{attrescape(key)}"' if key else ""
        return (f'<details class="shelf"{" open" if open_ else ""}'
                f' data-shelfkey="{attrescape(key or title)}"{_sid}>'
                f'<summary><span class="arrow">▸</span>{title}'
                f'<span class="n">{total_n} 本{note}</span></summary>'
                f'{pg_top}'
                f'<div class="cards">{body}</div>{pg}</details>')

    # ★ 书架数量必须与实际显示的卡片一致
    # 踩过：页签/标题用 len(items)（=所有状态文件，含你已移出书架的书），
    # 而分组用 shelved → 书架空了还显示"1 本"。
    shelf_count = len(shelved)

    # 用户原话：「我加入书架不等于收藏，因为我（不加）看不了」。
    # 所以他很容易把"在书架上"当成"我收藏了"，也怕自己被系统当成"我喜欢"。
    # 这一行必须在**所有按钮上面**，当场把两条轴分清。
    shelf_legend = ('<div class="shelf-legend">'
                    '加入书架表示<b>可阅读</b>；收藏用于<b>记录偏好</b>。两者相互独立。</div>')

    shelves = (
        shelf("已收藏", fav, True, " · 参与偏好学习，始终检查更新", key="fav")
        + shelf("在读", reading, True, "", key="reading")
        + shelf("想读", want, True, " · 已加入书架，尚未开始", key="want")
        + shelf("未开始", new_books, True, "", key="new")
        + shelf("已读完", finished, False, "", key="finished")
        + shelf("已弃文", dropped, False, " · 不再检查更新", key="dropped")
    )
    if shelf_count:
        shelf_tools = (
            '<div class="fb" id="shelf-top" style="margin:14px 0 6px">'
            + shelf_legend
            + '<div class="row shelf-search" style="display:flex;gap:8px;flex-wrap:wrap;margin:0">'
              '<input id="q" placeholder="搜索书名或作者" style="flex:1;min-width:150px">'
              '<button id="check-all">检查全部更新</button>'
              '<a class="chip" href="/import">导入本地书</a>'
              '<a class="chip" href="/tags">标签</a></div>'
              '<div class="filters" id="sfilter">'
              '<button data-f="all" class="on">全部</button>'
              '<button data-f="fav">已收藏</button>'
              '<button data-f="reading">在读</button>'
              '<button data-f="want">想读</button>'
              '<button data-f="new">未开始</button>'
              '<button data-f="finished">已读完</button>'
              '<button data-f="dropped">已弃文</button>'
              '</div>'
              '<div class="s" id="fsum" style="font-family:var(--ui);font-size:12px;'
              'color:var(--ct);margin-top:6px"></div>'
              '</div>'
        )
        empty_hint = ('<p id="empty" style="display:none;color:var(--ct);text-align:center;'
                      'font-family:var(--ui);font-size:13px;padding:20px 0">没有匹配的作品</p>')
    else:
        # 空书架别再摆一排用不上的筛选/查更按钮；给一个明确的下一步。
        shelf_tools = ''
        empty_hint = ''
        shelves = (
            '<div class="fb" style="text-align:center;padding:36px 18px">'
            '<p style="margin:0 0 8px;font-size:15px;font-weight:600">书架中还没有作品</p>'
            '<p class="s" style="margin:0 0 14px;line-height:1.7">在「推荐」或「书库」中挑选作品，'
            '加入书架后即可开始阅读；手里已有日文 EPUB/TXT 也可以直接导入。</p>'
            '<a class="chip" href="/import">导入本地 EPUB / TXT</a></div>'
        )
    try:
        findings = findings_html()
    except Exception as e:  # noqa: BLE001
        findings = f'<div class="fb">推荐位暂时不可用：{lr.esc(type(e).__name__)}</div>'
    # 阅读统计（学自 Kavita 的阅读会话：能算连续天数/每日时长）
    try:
        _st = reading_stats()
        if _st["days"] > 0:
            # 一行小字，不占首屏；数字含义照实说（history.jsonl 的"阅读记录条数"）。
            stats_html = (f'<div class="stats-line">连续阅读 {_st["streak"]} 天 · '
                          f'今日 {_st["today"]} 次</div>')
        else:
            stats_html = ''
    except Exception:  # noqa: BLE001
        stats_html = ''
    try:
        resume_html = recent_banner()
    except Exception:  # noqa: BLE001
        resume_html = ""
    try:
        library_html = library_pane(query=LIB_VIEW["q"], want_only=LIB_VIEW["want"],
                                    tags=LIB_VIEW["tags"])
    except Exception as e:  # noqa: BLE001
        library_html = f'<div class="fb">书库暂时不可用：{lr.esc(type(e).__name__)}</div>'
    try:
        queue_html = queue_body(embedded=True)
    except Exception as e:  # noqa: BLE001
        queue_html = f'<div class="fb">翻译列表暂时不可用：{lr.esc(type(e).__name__)}</div>'

    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<script>(function(){{var s=null;try{{s=localStorage.getItem('ln-theme');}}catch(e){{}}
var d=(s==='dark'||s==='light')?s:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.documentElement.setAttribute('data-t',d);document.documentElement.style.colorScheme=d;}})();</script>
<title>轻小说书架</title><link rel="icon" href="data:,">{PWA_HEAD}<style>{CSS}</style></head><body class="pg-home">
<main>
{recovery_notice_html()}
<header class="hero">
  <div class="hero-row">
    <div>
      <h1>轻小说书架</h1>
    </div>
    <a class="iconbtn" href="/settings" title="设置">设置</a>
  </div>
  {stats_html}
</header>
{resume_html}
<nav class="tabs">
  <a data-tab="recs" class="on">推荐</a>
  <a data-tab="shelf">书架 {shelf_count}</a>
  <a data-tab="lib">书库</a>
  <a data-tab="queue">翻译列表</a>
</nav>

<div class="pane on" id="pane-recs">
{findings}
{upd_html}
</div>

<div class="pane" id="pane-shelf">
<details class="shelf" open><summary><span class="arrow">▸</span>全部作品
  <span class="n">{shelf_count} 本</span></summary>
{shelf_tools}
{shelves}
{empty_hint}
</details>
</div>

<div class="pane" id="pane-lib">
{library_html}
</div>

<div class="pane" id="pane-queue">
{queue_html}
</div>
</main>
<script>{ACTION_JS}{LIB_JS}{QUEUE_JS}{META_JS}{DISLIKE_JS}</script></body></html>'''


def _read_text_upto(slug: str, upto: int, cap: int = 400_000) -> str:
    """已读章节（1 .. upto-1）的译文拼起来。

    只用来判断"这个人/这个词在读过的地方有没有出现"，不做别的 ——
    所以封顶 40 万字：一本 500 章的书也不会因为"扫一遍"把阅读页拖慢。
    """
    parts: list[str] = []
    size = 0
    for ch in range(1, upto):
        p = os.path.join(NOVELS, slug, "chapters", f"{ch - 1:04d}.txt")
        try:
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                continue
            with open(p, encoding="utf-8") as f:
                t = f.read(max(0, cap - size))
        except OSError:
            continue
        if not t:
            continue
        parts.append(t)
        size += len(t)
        if size >= cap:
            break
    return "\n".join(parts)


def _tail_excerpt(text: str, n: int = 2, width: int = 140) -> list[str]:
    """没生成梗概时的兜底：上一章最后几段（读者自己读过的内容，不会剧透）。

    跳过太短的段落：章末常常是「恳请多多支持」「――――」这种收尾装饰，
    拿它当"上次讲到"等于什么都没说。
    """
    paras = [x.strip() for x in (text or "").split("\n") if x.strip()]
    meaty = [p for p in paras if len(p) >= 24] or paras
    return [p[:width] + ("…" if len(p) > width else "") for p in meaty[-n:]]


def memory_panel(slug: str, meta: dict, upto: int) -> str:
    """阅读页顶部的「前情 · 人物」折叠块。

    数据本来就有（summaries / characters / glossary），以前只喂翻译 prompt，
    读者看不见。这里把它搬到界面上，但**只用到 upto 之前的章节**：
    隔两周回来点开第 37 章，先看"上次讲到哪 + 这几个人是谁"，不给后文剧透。

    一项都凑不出来就返回空串（不渲染空壳面板）。
    """
    try:
        _lib = recs._load_lib() or {}
        _tag_it = _lib.get(_source_id(slug)) or {}
    except Exception:  # noqa: BLE001
        _tag_it = {}
    tags = [str(t) for t in ((_tag_it.get("tags") or meta.get("tags") or [])) if t]
    if upto <= 1:
        text = ""
    else:
        text = _read_text_upto(slug, upto)
    if not text and not tags:
        return ""
    glossary = meta.get("glossary") or {}
    summaries = meta.get("summaries") or {}
    prev = upto - 1

    # ---- 上次讲到：优先用梗概（最近两章），没有就用上一章结尾 ----
    recap: list[tuple[int, str, str]] = []      # (章号, 标题, 文本)
    if text:
        for ch in (prev - 1, prev):
            s = (summaries.get(str(ch)) or "").strip()
            if ch >= 1 and s:
                recap.append((ch, zh_title_of(meta, ch), s))
        from_summary = bool(recap)
        if not recap:
            p = os.path.join(NOVELS, slug, "chapters", f"{prev - 1:04d}.txt")
            try:
                tail = _tail_excerpt(open(p, encoding="utf-8").read()) if os.path.exists(p) else []
            except OSError:
                tail = []
            if tail:
                recap.append((prev, zh_title_of(meta, prev), "\n".join(tail)))
    else:
        from_summary = False

    # ---- 人物：只列在已读章节里真的出现过的人 ----
    chars: list[tuple[str, str, str]] = []      # (中文名, 日文名, 简介)
    seen_zh = set()
    for jp, info in (meta.get("characters") or {}).items():
        zh = (glossary.get(jp) or "").strip()
        if not (zh and zh in text) and jp not in text:
            continue
        desc = ""
        if isinstance(info, dict):
            desc = (info.get("desc") or "").strip()
        elif isinstance(info, str):
            desc = info.strip()
        chars.append((zh or jp, jp, desc))
        seen_zh.add(zh or jp)

    # ---- 术语：已读章节里出现过的（人物已在上面列过，不重复）----
    terms = [(jp, zh) for jp, zh in glossary.items()
             if zh and zh in text and zh not in seen_zh]

    if not recap and not chars and not terms and not tags:
        return ""

    recap_html = ""
    if recap:
        recap_html = '<ol class="recap">' + "".join(
            f'<li><a href="/read/{attrescape(slug)}?from={ch}#c{ch}">'
            f'<b>第 {ch} 章 · {lr.esc(t)}</b></a>'
            f'<p>{lr.esc(body).replace(chr(10), "<br>")}</p></li>'
            for ch, t, body in recap) + '</ol>'
        if not from_summary:
            recap_html += ('<p class="mem-hint">这一章还没有提要句，先显示结尾；'
                           '生成梗概后会换成剧情摘要。</p>')

    chars_html = "".join(
        f'<li><b>{lr.esc(zh)}</b><span class="jpname">{lr.esc(jp)}</span>'
        f'{f"<p>{lr.esc(desc)}</p>" if desc else ""}</li>'
        for zh, jp, desc in chars)
    terms_html = "".join(
        f'<span class="mterm">{lr.esc(zh)}<i>{lr.esc(jp)}</i></span>'
        for jp, zh in terms)
    tags_html = "".join(
        f'<a class="mterm" href="/tags?q={urllib.parse.quote(t)}">'
        f'{lr.esc(t)}</a>' for t in tags[:12])

    blocks = []
    if tags:
        blocks.append(f'<h4>关键词</h4><div class="mterms">{tags_html}</div>')
    if recap:
        blocks.append(f'<h4>上次讲到</h4>{recap_html}')
    if chars:
        blocks.append(f'<h4>这几个人是谁</h4><ul class="mchars">{chars_html}</ul>')
    if terms:
        blocks.append(f'<h4>术语</h4><div class="mterms">{terms_html}</div>')
    _bits = []
    if tags:
        _bits.append(f"{len(tags)} 个关键词")
    if recap:
        _bits.append(f"上次讲到第 {prev} 章")
    head = " · ".join(_bits)
    _label = []
    if tags:
        _label.append("关键词")
    if recap:
        _label.append("前情")
    if chars or terms:
        _label.append("人物")
    _notes = []
    if tags:
        _notes.append("关键词来自本书标签")
    if chars or terms:
        _notes.append("人物和术语只列已读章节出现过的")
    else:
        _notes.append("人物/术语表还没有建立")
    _notes.append("不剧透后文")
    return (f'<details class="membox" id="membox"><summary>{" · ".join(_label)}'
            f'<span class="mem-n">{lr.esc(head)}</span></summary>'
            f'<div class="mem">{"".join(blocks)}'
            f'<p class="mem-note">{lr.esc("；".join(_notes))}。</p>'
            f'</div></details>')


def recovery_notice_html() -> str:
    h = jobstore.STORE.health(refresh=True)
    if not h.get("read_only"):
        return ""
    files = "、".join(x.get("file", "?") for x in h.get("corrupt") or [])
    return (
        '<div class="recovery-warn" role="alert">'
        '<b>只读恢复模式</b>：任务日志损坏'
        + (f'（{attrescape(files)}）' if files else "")
        + '。已译章节、书架、阅读进度和备份仍可用；'
          '开始/停止翻译等任务写入已暂停。'
        f'<code>{attrescape(h.get("repair_command") or "")}</code></div>'
    )


def page_reader(slug: str, from_ch: int | None = None, limit: int = 1) -> str | None:
    meta = novel_meta(slug)
    if not meta:
        return None
    total = len(meta.get("episodes") or [])
    done = have_count(slug, meta)
    st = load_state()
    bd = _read_book(slug)
    fav = bool(bd.get("favorites"))
    finished = bool(bd.get("finished"))
    dropped = bool(bd.get("dropped"))
    upd = bool(bd.get("has_update"))
    prog = st["progress"].get(slug) or {}
    have = set(zh_chapters(slug, total))
    if from_ch is not None:
        start = max(1, min(from_ch, total))
    elif prog.get("chapter"):
        # 回到上次读到的地方（书架显示"读到第 N 章"，点进来就该是第 N 章）
        start = max(1, min(int(prog["chapter"]), total))
    else:
        start = 1
    # 从 start 起取连续已译的若干章。
    # 踩过（用户报「我还没开始看，怎么就第二话了，我第一话呢？」）：
    # 原来 start 本身没译文时会**偷偷跳到**后面第一个有译文的章 ——
    # 于是从没读过的人一进来就是第 2 章，第 1 章永远没人翻，
    # 还要被记成"读到第 2 章"。现在只连续取，落地章没译文就渲染占位块，
    # 译好后由前端就地替换（不用手动刷新）。
    shown, c = [], start
    while c <= total and len(shown) < limit and c in have:
        shown.append(c)
        c += 1
    need = 0 if start in have else start

    # 占位块：告诉读者"这一章正在翻"，而不是假装它不存在
    if need:
        ep_title = (meta["episodes"][need - 1].get("title")
                    if need - 1 < len(meta["episodes"]) else "")
        sections = (f'<section class="ch pending" id="need-{need}" data-need="{need}">'
                    f'<h2><span class="no">{need}</span>{lr.esc(zh_title_of(meta, need, ep_title))}</h2>'
                    f'<p class="jp-title">{lr.esc(ep_title)}</p>'
                    f'<p class="pending-note">这一章还没译好 —— 正在翻译，'
                    f'译好会自动出现在这里，不用刷新。</p></section>')
    else:
        sections = "".join(lr.render_chapter_html(slug, i - 1) for i in shown)

    # 术语表改过之后，用旧译名翻的章节给一条**就地**提示 + 重翻入口。
    # 只查本页渲染的这一两章（逐章读边车），不扫全书。
    stale_ch = [i for i in shown
                if lt.chapter_glossary_stale(slug, i - 1, meta)]
    stale_html = ""
    if stale_ch:
        _sc = stale_ch[0]
        stale_html = (
            f'<div class="stale-note">这一章是按<b>旧术语表</b>翻的，'
            f'人名/专有名词可能和后面不一致。'
            f'<button class="lnkbtn" data-stale-retranslate="{_sc}">'
            f'按新术语表重翻本章</button>'
            f'<span class="s">（只重翻这一章，会花 token）</span></div>')
    js = job_view(slug)
    zh = meta.get("zh_titles") or {}
    title = zh.get("book") or meta.get("title") or slug
    tcfg = trans_cfg(slug)
    ceiling = auto_ceiling(slug, meta)
    # 「翻到第 N 章」输入框的默认值。没开翻译时 auto_ceiling 返回 0，原写法回退成
    # **总章数** → 一次点击就静默把整本翻完（踩过：一本 185 章被一次点掉）。
    # 改成回退到"读到 + ahead"（与开启后的自动上限同源），最小 1，绝不等于整本。
    ceil_default = ceiling or min(total, max(1, read_chapter(slug) + tcfg["ahead"]))
    _pct = round(done / total * 100) if total else 0
    # 续读位置（学自 Kavita 的 BookScrollId）
    _prog = _read_book(slug).get("progress") or {}
    resume_ch = bool(_prog.get("chapter") and int(_prog["chapter"]) == start)
    # 回到**实际停下的位置**（scroll），不是读到过的最远处（max_scroll）
    history_scroll = round(float(_prog.get("scroll") or 0), 3)
    _sb = SCHED.state["books"].get(slug) or {}
    _paused_book = bool(_sb.get("paused"))
    note_reading(slug, persist=True)   # 打开阅读页 = 在读（落盘一次，轮询只续内存）
    _left = SCHED.budget_left()
    _qrows = len(SCHED.view(
        lambda s: have_count(s, novel_meta(s) or {}),
        lambda s: len((novel_meta(s) or {}).get("episodes") or []))["rows"])
    _over = SCHED.over_budget()
    if _paused_book:
        policy_note = "本书翻译已暂停 · 点下方「继续翻译」恢复"
    elif _over:
        policy_note = (f"读至第 {read_chapter(slug)} 章 · "
                       f"今日已用 {SCHED.state.get('used_today', 0):,} token"
                       f"（超出预算，仍在继续）· 翻译列表 {_qrows} 本")
    else:
        policy_note = (f"读至第 {read_chapter(slug)} 章 · "
                       f"今日已用 {SCHED.state.get('used_today', 0):,} token"
                       f" · 翻译列表 {_qrows} 本")
    _auto_label = "继续翻译" if _paused_book else "停止翻译本书"
    _mc = lnmodels.public_config()
    _models = _mc.get("roles") or {}
    _model_line = " · ".join(
        f"{label} {(_models.get(role) or {}).get('model', '?')}"
        for role, label in (("translate", "翻译"),
                            ("auxiliary", "辅助"), ("review", "校对")))
    _spent = float(_mc.get("spent_today") or 0)
    _daily = float(_mc.get("daily_budget") or 0)
    _budget_line = (f"今日 {_mc.get('currency', 'CNY')} {_spent:.4f} / "
                    f"{_daily:.2f}" if _daily > 0 else
                    f"今日约 {_mc.get('currency', 'CNY')} {_spent:.4f}（未设日预算）")
    _key_line = ("本地端点，无需密钥" if _mc.get("local")
                 else ("密钥已配置" if _mc.get("key_configured")
                       else "未配置密钥"))
    model_note = (f'<div class="s model-note">{lr.esc(_model_line)}<br>'
                  f'{lr.esc(_budget_line)} · {lr.esc(_key_line)}</div>')

    toc = toc_list(slug, meta, have, shown)
    mem_html = memory_panel(slug, meta, start)

    # 章末导航：读到本章末尾能直接翻上一章/下一章，不必滚回顶部找目录。
    # 本页渲染的是 start 起连续已译的若干章；「下一章」= 本页最后一章 + 1。
    #
    # ⚠ 落地章还没译文时（need），**不许**给「下一章」的链接：那种页面正文是占位块，
    # 点「下一章」会落到**再下一个**占位页，而那一页的 tick() 会用 after=need+1 去排翻译
    # —— 正在等的那一章被跳过、可能永久缺译（读者也永远等不到它）。所以这种情况下：
    # 下一章已译 → 给真链接（这是"绕开空洞"的正当出口）；没译 → 只显示一句实话。
    _last = shown[-1] if shown else start
    _prev, _next = start - 1, _last + 1
    # 翻章链接带锚点 `#c<N>`（缺译时是 `#need-N`）：点下去浏览器**直接落在正文**，
    # 而不是回到页面顶部再让用户自己往下翻过标题和目录（用户报过这条）。
    _prev_anchor = f"c{_prev}" if _prev in have else f"need-{_prev}"
    _prev_html = (f'<a class="navbtn" href="/read/{attrescape(slug)}?from={_prev}#{_prev_anchor}">'
                  f'← 上一章</a>'
                  if _prev >= 1 else '<span class="navbtn off">← 已在第 1 章</span>')
    _next_have = (_next <= total and (not need or _next in have))
    if _next_have:
        _next_html = (f'<span id="nav-next"><a class="navbtn"'
                      f' href="/read/{attrescape(slug)}?from={_next}#c{_next}">下一章 →</a></span>')
    elif _next > total:
        _next_html = '<span class="navbtn off">已是最后一章</span>'
    else:
        # 译好之前不是链接，但**可点**：点了就催翻译。
        # 旧版这里是个 span（注释说可点，实际没有 handler），读者只能干等。
        _next_html = ('<span id="nav-next"><button class="navbtn off" data-wait="1">'
                      '下一章（这一章译好才有下一章）</button></span>')
    # 「↑ 目录」：目录现在是折叠的 `<details id="tocbox">`，锚点指到它本身才有效
    # （原来指 `#toc`，目录收起时那个 nav 不可见 → 点了像没反应）。
    chapnav = (f'<nav class="chapnav">{_prev_html}'
               f'<a class="navbtn mid" href="#tocbox">↑ 目录</a>'
               f'{_next_html}</nav>')
    # 底部固定栏（novelia 式五格）：上一章 / 详情 / 目录 / 设置 / 下一章。
    # 阅读时手在屏幕下半部，翻章/开目录不用滚回顶部；顶部不再放第二套导航。
    _bar_prev = (f'<a href="/read/{attrescape(slug)}?from={_prev}#{_prev_anchor}">← 上章</a>'
                 if _prev >= 1 else '<span class="off">← 上章</span>')
    _bar_next = (f'<a href="/read/{attrescape(slug)}?from={_next}#c{_next}">下章 →</a>'
                 if _next_have else
                 '<button data-wait="1" title="催翻译下一章">下章 →</button>')
    # 「详情」用源站 id（与推荐/书架卡一致）：详情缓存按 id 存，
    # 用 slug 会另建一份 `<slug>.json`，同一本书两份详情互相看不见。
    _detail_id = str(meta.get("source_id") or slug)
    # 校对只对“本页已有译文”的章节显示；落地章还在翻译时没有可校对文本。
    review_btn = ''
    review_box = ''
    download_btn = ''
    if done:
        # 「带得走」：已译内容可以下成 EPUB（Markdown 只能在本站读）。
        download_btn = (f'<a class="dlbtn" href="/export/{attrescape(slug)}.epub" '
                        f'download>下载 EPUB</a>')
    if shown and not need:
        review_btn = '<button id="review-open">校对本章</button>'
        review_box = f'''<div id="reviewbox" style="display:none">
  <h3>校对 · 第 {start} 章</h3>
  <div class="review-tools">
    <button id="review-rules">规则检查（不花 token）</button>
    <button id="review-ai">AI 校对（消耗 token）</button>
    <button id="review-close">收起</button>
  </div>
  <div id="review-status"></div>
  <div id="review-list"></div>
</div>'''

    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<script>(function(){{var s=null,f=null,h=null;
try{{s=localStorage.getItem('ln-theme');f=localStorage.getItem('ln-fs');h=localStorage.getItem('ln-lh');}}catch(e){{}}
var d=(s==='dark'||s==='light')?s:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
var r=document.documentElement;r.setAttribute('data-t',d);r.style.colorScheme=d;
if(f==='s'||f==='l')r.setAttribute('data-fs',f);
if(h==='tight'||h==='loose')r.setAttribute('data-lh',h);}})();</script>
<title>{lr.esc(title)} · 阅读</title><link rel="icon" href="data:,">{PWA_HEAD}<style>{CSS}{LNUI_CSS}</style></head><body class="pg-read hidejp" data-ui-reader="next">
<div id="bar"></div>
<div id="ui-reader-top" data-ui-reader-top>
  <div class="ui-reader-top-title">{lr.esc(title)}</div>
  <div class="ui-reader-top-sub">第 {start} 话 · 已译 {done}/{total}</div>
</div>
<div id="ui-chapter-toast" role="status" aria-live="polite">第 {start} 话 · {lr.esc(zh_title_of(meta, start, (meta.get('episodes') or [{}])[start-1].get('title') if start-1 < len(meta.get('episodes') or []) else ''))}</div>
<main>
{recovery_notice_html()}
{stale_html}
<nav class="crumbs"><a href="/">← 返回书架</a>
  <span>·</span><span>{lr.esc(meta.get('author') or '')}</span>
  <span style="margin-left:auto;display:flex;gap:6px">
    <button data-act="finished" data-slug="{attrescape(slug)}" class="lnkbtn{' on' if finished else ''}"
      title="归入已读完分组，不再占用待读列表">{'已读完' if finished else '读完'}</button>
    <button data-act="dropped" data-slug="{attrescape(slug)}" class="lnkbtn{' on' if dropped else ''}"
      title="不再检查更新，也不参与偏好学习（会同时取消收藏）">{'已弃文' if dropped else '弃文'}</button>
    <button data-act="favorite" data-slug="{attrescape(slug)}" class="lnkbtn{' on' if fav else ''}"
      title="收藏表示偏好：用于学习阅读口味，并始终检查更新。与能否阅读无关。">{'★ 已收藏' if fav else '☆ 收藏'}</button>
  </span></nav>
<header class="book">
  <div class="bookline">
    <div style="min-width:0">
      <h1>{lr.esc(title)}</h1>
      <div class="meta">{lr.esc(meta.get('title') or '')}</div>
    </div>
    <button id="btn-more" class="morebtn">多译 5 章</button>
  </div>
  <details class="adv" id="trans-settings">
    <summary>阅读与翻译设置</summary>
    <div class="tools">
      <button id="toggle-jp" aria-pressed="false">显示日文原文</button>
      <button id="btn-speak" title="用浏览器自带的语音朗读本章（不花 token）">朗读本章</button>
      <button id="btn-auto">{_auto_label}</button>
      <button id="open-feedback">反馈本章</button>
      <a class="dlbtn" href="/queue">翻译列表</a>
      {review_btn}
      {download_btn}
    </div>
    <div class="readopts" aria-label="阅读排版">
      <label>字号
        <select id="r-fs">
          <option value="s">小</option>
          <option value="m">标准</option>
          <option value="l">大</option>
        </select>
      </label>
      <label>行距
        <select id="r-lh">
          <option value="tight">紧凑</option>
          <option value="normal">标准</option>
          <option value="loose">宽松</option>
        </select>
      </label>
    </div>
    <div class="tools" style="margin-top:8px">
      <span class="ceil-row">
        <label for="ceil">翻到第</label>
        <input id="ceil" type="number" min="1" max="{total}"
          value="{ceil_default}" inputmode="numeric" enterkeyhint="done"
          aria-label="翻到第几章"
          style="width:64px;padding:4px 6px;border-radius:6px;
          border:1px solid var(--rule);background:var(--paper);color:var(--ink);font-size:13px">
        <span>章</span>
        <button id="btn-ceil">确认翻译</button>
      </span>
    </div>
    <div class="s" style="text-align:left;font-family:var(--ui);font-size:12px;
         color:var(--ct);margin-top:8px" id="policy-note">
      {policy_note}
    </div>
    {model_note}
  </details>
  {('<p style="text-align:center;color:#c05a5a;font-family:var(--ui);'
    'font-size:13px;margin-top:10px">源站新增'
    + ((' ' + str(bd.get('new_episodes')) + ' 话') if bd.get('new_episodes') else '章节')
    + '（' + (bd.get('last_episode_at') or '') + '），向下滚动可继续翻译</p>') if upd else ''}
</header>
<details class="tocbox" id="tocbox"{' open' if not shown and not need else ''}>
  <summary>已译章节 <span class="tocn" id="toc-count">{done}/{total}</span>
    <span class="toc-hint">点击展开</span></summary>
  <nav class="toc" id="toc"{'' if toc else ' style="display:none"'}>
  <ol id="toc-list">{toc}</ol>
  <p class="toc-note">点击章节可直接跳转；左右滑动或按 ← → / j k 翻章（本页内章节不重新加载）。</p></nav>
</details>
{mem_html}
{sections}
{'<div class="chapend">本章完</div>' if shown and not need else ''}
{chapnav}
{review_box}
<div id="anchor"></div>
</main>
<div id="fbpanel">
  <h3>阅读反馈</h3>
  <div class="where" id="fb-where">当前：第 1 章</div>
  <div class="row">
    <button data-v="good">对味</button>
    <button data-v="bad">不合口味</button>
    <button data-v="trans">翻译问题</button>
  </div>
  <textarea id="fb-note" placeholder="可填写译名错误、语气问题、翻译过于公式化等具体意见（自动关联当前章节）"></textarea>
  <div class="row" style="margin-top:10px;align-items:center">
    <button id="fb-send">提交</button>
    <button id="fb-close">取消</button>
    <span id="fb-status"></span>
  </div>
</div>
<div id="translatebar"><i id="tb-fill" style="width:{_pct}%"></i>
  <div class="tb-row"><span id="tb-status">准备中…</span><span id="tb-seg"></span><span id="tb-prog">已译 {done}/{total}（{_pct}%）</span><button id="tb-stop" title="停止翻译，并关闭这本书的自动翻译">停止</button></div>
</div>
<nav id="readerbar" aria-label="阅读导航">
  {_bar_prev}
  <a href="/book?id={attrescape(_detail_id)}">详情</a>
  <a href="#tocbox" id="rb-toc">目录</a>
  <button id="rb-settings">设置</button>
  {_bar_next}
</nav>
<script>
window.__SLUG__={_js_json(slug)};
window.__TOTAL__={total}; window.__DONE__={done}; window.__START__={start};
window.__NEED__={need};
window.__JOB_INFO__={_js_json(js)};
window.__NEXT__={_next if _next <= total else 0};
window.__NEXTHAVE__={'true' if _next_have else 'false'};
// NEXTTRANS 和 NEXTHAVE 是**两件事**：NEXTHAVE=下一章能不能点过去（没译文也能点，
// 点过去是"占位页 + 自动开翻"）；NEXTTRANS=下一章**现在就有译文**。
// 预翻（读者还在读本章时先把下一章译好）必须看 NEXTTRANS —— 只看 NEXTHAVE 的话
// 它永远为真，预翻永不触发，于是每翻一章都要干等 30~45 秒。
window.__NEXTTRANS__={'true' if _next <= total and _next in have else 'false'};
window.__SCROLL__={history_scroll}; window.__RESUME__={'true' if resume_ch else 'false'};
window.__TENABLED__={'false' if _paused_book else 'true'};
window.__CEIL__=0;   // v5.1：不再有"读到 + N 章"上限，持续翻译由调度器负责
window.__BUDGET_LEFT__={max(0, _left)};
window.__JOB__={json.dumps(js.get('status') or 'idle')};
{ACTION_JS}
{READER_JS}
{REVIEW_JS}
{LNUI_READER_JS}
</script></body></html>'''


# ------------------------------------------------------------------ HTTP

def _as_int(v, default=None, lo=None, hi=None):
    """把请求里的数字参数安全地转成 int（非法值退回 default，再夹到范围）。

    前端手误 / 旧缓存 / 手改 URL 传个 `page=abc` 不该让整个请求抛异常：
    虽然 handle_one_request 会兜一个 500，但 JSON 接口的调用方拿到的是
    「服务端处理出错」而不是可解析的 JSON，前端只能静默失败。
    """
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    if n is None:
        return None
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


class Handler(BaseHTTPRequestHandler):
    server_version = "lnserve/1.0"

    def log_message(self, fmt, *a):  # 安静点
        pass

    def handle_one_request(self):  # noqa: N802
        """任何未预料的异常都要**留下证据**，并给浏览器一个明确的 500。

        踩过：请求处理里抛异常时，socketserver 只会把连接丢掉 ——
        浏览器看到的是"页面打不开/一直转"，日志里却什么都没有，
        用户只能说"有时候要自己刷新一下"。现在把 traceback 写进
        data/server.log，并且回一个能看懂的 500。
        """
        try:
            super().handle_one_request()
        except Exception:  # noqa: BLE001
            try:
                with open(os.path.join(DATA, "server.log"), "a",
                          encoding="utf-8") as f:
                    # 把关口令从要落盘的 path 里抹掉：异常日志不许写进 token
                    # （否则 data/server.log 会留一份凭据）。
                    _p = re.sub(r"(?i)(token=)[^&\s]+", r"\1***",
                                str(getattr(self, "path", "?")))
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 请求处理异常 "
                            f"{getattr(self, 'command', '?')} {_p}\n")
                    traceback.print_exc(file=f)
            except OSError:
                pass
            try:
                self._send(500, "服务端处理出错，请刷新一次".encode(),
                           "text/plain; charset=utf-8")
            except Exception:  # noqa: BLE001
                pass

    def _security_headers(self) -> None:
        # Pages and scripts are intentionally inline, so the CSP allows inline
        # styles/scripts but still blocks third-party code and framing.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy",
                         "camera=(), microphone=(), geolocation=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Permitted-Cross-Domain-Policies", "none")

    def _send(self, code: int, body: bytes, ctype: str,
              headers=None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        for key, value in _header_items(headers):
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_attachment(self, data: bytes, ctype: str, filename: str,
                         fallback: str = "download.bin") -> None:
        """回一个"下载"响应。中文文件名走 RFC 5987，同时给一个 ASCII 兜底名
        （老浏览器/命令行工具只认 fallback）。"""
        quoted = urllib.parse.quote(filename)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition",
                         f'attachment; filename="{fallback}"; '
                         f"filename*=UTF-8''{quoted}")
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _cover(self, key: str) -> None:
        """回一张封面。带 ETag + 一天的缓存：一页十张卡不该每次都重下。"""
        p = lc.path_of(key)
        if not p:
            self._send(404, b"", "text/plain; charset=utf-8")
            return
        st = os.stat(p)
        etag = f'"{int(st.st_mtime)}-{st.st_size}"'
        if (self.headers.get("If-None-Match") or "").strip() == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "public, max-age=86400")
            self._security_headers()
            self.end_headers()
            return
        with open(p, "rb") as f:
            data = f.read()
        ext = p.rsplit(".", 1)[-1]
        self.send_response(200)
        self.send_header("Content-Type", lc.MYTYPE.get(ext, "image/jpeg"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "public, max-age=86400")
        self._security_headers()
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def html(self, s: str, code: int = 200) -> None:
        self._send(code, s.encode("utf-8"), "text/html; charset=utf-8")

    def js(self, o, code: int = 200,
           headers: dict[str, str] | None = None) -> None:
        self._send(code, json.dumps(o, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", headers)

    def body(self) -> dict:
        try:
            return json.loads(self._request_body() or b"{}")
        except (ValueError, json.JSONDecodeError):
            return {}

    def _request_body(self, *, limit: int = REQUEST_BODY_LIMIT) -> bytes:
        if hasattr(self, "_cached_body"):
            return self._cached_body
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            raise ValueError("invalid content length")
        if n < 0 or n > limit:
            raise ValueError("request body too large")
        self._cached_body = self.rfile.read(n) if n else b""
        return self._cached_body

    def _import_upload(self, u) -> None:
        """POST /api/import?name=xxx.epub —— 原始文件体，不 base64。"""
        try:
            data = self._request_body(limit=IMPORT_BODY_LIMIT)
        except ValueError:
            self.js({"ok": False,
                     "error": "文件太大（上限 32MB）"}, 413)
            return
        if not data:
            self.js({"ok": False, "error": "没有收到文件"}, 400)
            return
        q = urllib.parse.parse_qs(u.query, encoding="utf-8")
        name = (q.get("name") or [""])[0]
        name = os.path.basename(str(name).replace("\\", "/")).strip()
        if not name:
            name = "upload.txt"
        title = (q.get("title") or [""])[0].strip()
        author = (q.get("author") or [""])[0].strip()
        try:
            info = lnimport.import_bytes(
                data, name, lt=lt, title=title, author=author)
        except lnimport.ImportError_ as e:
            self.js({"ok": False, "error": str(e)}, 400)
            return
        except (Exception, SystemExit) as e:  # noqa: BLE001
            traceback.print_exc()
            self.js({"ok": False,
                     "error": f"{type(e).__name__}: {e}"}, 500)
            return
        try:
            ensure_on_shelf(info["slug"])
        except (Exception, SystemExit) as e:  # noqa: BLE001
            # 书已经建好了；上架失败只影响"立刻能在书架看到"，不毁导入结果。
            print(f"[导入] 上架失败：{type(e).__name__}: {e}")
        _META_CACHE.pop(info["slug"], None)
        _SLUG_IDX[0] = None
        self.js({"ok": True, **info})

    def _send_file(self, filepath: str, ctype: str, filename: str) -> None:
        """流式回一个文件（分块，不把 15MB 备份读进内存）。

        `_send()` 是"body 已经在内存里"的回法；备份包可能有几十 MB 且是临时文件，
        用这个单独走。文件名走 Content-Disposition，浏览器会存成它。
        """
        size = os.path.getsize(filepath)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        # 文件名只含字母数字和 . -，不需要再转义；也不接受外部输入。
        self.send_header("Content-Disposition",
                         'attachment; filename="%s"' % filename)
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        try:
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # 用户点了"取消下载"很正常，不是错误。
            pass

    def backup(self) -> None:
        """`/api/backup`：把译文 + 书架状态 + 口味画像打包下载。

        为什么要有这个接口（而不是只留命令行）：容器文件系统会被重置，
        写在同一棵树里的 zip 会跟着一起消失；**只有下载到手机存储
        （/sdcard/Download）才算离开容器的第二份**。这是备份唯一有意义的形态。

        打包本身约 2~4 秒（1000+ 个小文件），浏览器下载栏有进度，不做额外提示。
        """
        tmp = ""
        try:
            fd, tmp = tempfile.mkstemp(prefix="lntrans-backup-", suffix=".zip")
            os.close(fd)
            man = bk.build(tmp)
            self._send_file(tmp, "application/zip", bk.default_name())
            print(f"[backup] 已导出 {man['files']} 个文件 / "
                  f"{man['bytes'] / 1048576:.1f} MB")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send(500, "备份失败，请稍后重试（详情见终端日志）".encode(),
                       "text/plain; charset=utf-8")
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _note_peer(self) -> None:
        try:
            note_peer(self.client_address[0])
        except Exception:  # noqa: BLE001
            pass

    def _peer(self) -> str:
        """对端地址。抽成方法只为自检能塞一个"非回环"对端（本机测不到真远端）。"""
        try:
            return self.client_address[0]
        except (IndexError, TypeError):
            return ""

    def _cookie_value(self, name: str) -> str:
        m = re.search(
            rf"(?:^|;\s*){re.escape(name)}=([^;]*)",
            self.headers.get("Cookie") or "",
        )
        return urllib.parse.unquote(m.group(1)) if m else ""

    def _host_ok(self) -> bool:
        return host_verdict(self.headers.get("Host") or "", _allowed_host_names())

    def _origin_ok(self) -> bool:
        return origin_verdict(
            self.headers.get("Origin") or "",
            self.headers.get("Host") or "",
            self.headers.get("Sec-Fetch-Site") or "",
        )

    def _reject_host(self) -> None:
        self._send(
            400,
            b"Bad Host header",
            "text/plain; charset=utf-8",
        )

    def _forbidden(self) -> None:
        if os.environ.get("LNTRANS_DEBUG_ORIGIN"):
            print("[origin] path=%r host=%r origin=%r site=%r ua=%r" % (
                self.path, self.headers.get("Host"),
                self.headers.get("Origin"),
                self.headers.get("Sec-Fetch-Site"),
                self.headers.get("User-Agent"),
            ), flush=True)
        if urllib.parse.urlparse(self.path).path.startswith("/api/"):
            self.js({"ok": False, "error": "跨站写请求已拒绝"}, 403)
            return
        self._send(403, b"Cross-site request rejected",
                   "text/plain; charset=utf-8")

    def _redirect(self, location: str, headers=None) -> None:
        self.send_response(303)
        self.send_header("Content-Length", "0")
        self.send_header("Location", _safe_next(location))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        for key, value in _header_items(headers):
            self.send_header(key, value)
        self.end_headers()

    def _redirect301(self, location: str) -> None:
        self.send_response(301)
        self.send_header("Content-Length", "0")
        self.send_header("Location", _safe_next(location))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()

    def _login(self) -> None:
        if not self._host_ok():
            self._reject_host()
            return
        if not AUTH_REQUIRED:
            self._redirect("/")
            return
        if not self._origin_ok():
            self._forbidden()
            return
        peer = self._peer()
        retry = _rate_retry(
            "login", peer, LOGIN_FAIL_LIMIT, LOGIN_FAIL_WINDOW)
        if retry:
            self._send(
                429,
                _auth_page("/", "登录尝试过多，请稍后再试。").encode("utf-8"),
                "text/html; charset=utf-8",
                {"Retry-After": str(retry)},
            )
            return
        try:
            raw = self._request_body(limit=16 * 1024)
        except ValueError:
            self._send(413, _auth_page("/", "登录请求过大。").encode("utf-8"),
                       "text/html; charset=utf-8")
            return
        try:
            form = urllib.parse.parse_qs(
                raw.decode("utf-8"), keep_blank_values=True)
        except UnicodeDecodeError:
            form = {}
        presented = (form.get("token") or [""])[0]
        next_path = _safe_next((form.get("next") or ["/"])[0])
        if not _token_ok(presented, AUTH_TOKEN):
            _rate_hit("login", peer, LOGIN_FAIL_WINDOW)
            self._send(
                401,
                _auth_page(next_path, "口令不正确。").encode("utf-8"),
                "text/html; charset=utf-8",
            )
            return
        _rate_clear("login", peer)
        sid = issue_session()
        cookies = [
            f"{AUTH_COOKIE}={urllib.parse.quote(sid)}; Path=/; HttpOnly; "
            f"SameSite=Lax; Max-Age={AUTH_SESSION_TTL}"
        ]
        # 「记住这台电脑」：独立随机值，重启服务后仍能认；不是主口令。
        try:
            secret, record = devstore.issue(
                device_store_path(), label=self.headers.get("User-Agent") or "",
                ttl=AUTH_DEVICE_TTL)
            cookies.append(
                f"{AUTH_DEVICE_COOKIE}={urllib.parse.quote(secret)}; Path=/; "
                f"HttpOnly; SameSite=Lax; Max-Age={AUTH_DEVICE_TTL}"
            )
            print(f"[auth] 已记住设备 {record['id']}（{record['label'][:40] or '未知浏览器'}）",
                  flush=True)
        except Exception:  # noqa: BLE001
            # 写不进数据根（只读/满盘）也别让登录失败：本次会话照常可用。
            traceback.print_exc()
        self._redirect(next_path, [("Set-Cookie", c) for c in cookies])

    def _logout(self) -> None:
        """退出本设备 = 会话作废 + 删掉这台电脑被记住的凭据。"""
        revoke_session(self._cookie_value(AUTH_COOKIE))
        secret = self._cookie_value(AUTH_DEVICE_COOKIE)
        if secret:
            try:
                devstore.revoke(device_store_path(), secret)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
        self._redirect("/login", [
            ("Set-Cookie",
             f"{AUTH_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"),
            ("Set-Cookie",
             f"{AUTH_DEVICE_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"),
        ])

    def _presented_token(self) -> tuple[str, str]:
        """API 客户端可直接用 Bearer；浏览器只走登录表单 + 随机会话。"""
        auth = (self.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip(), "header"
        x = (self.headers.get("X-LNToken") or "").strip()
        if x:
            return x, "header"
        return "", ""

    def _gate(self) -> bool:
        """放行返回 True；否则回 401（/api 给 JSON、其余给口令页）并返回 False。"""
        if not self._host_ok():
            self._reject_host()
            return False
        presented, _src = self._presented_token()
        if auth_verdict(
            self._peer(), AUTH_REQUIRED, AUTH_TOKEN, presented,
            host=self.headers.get("Host") or "",
            forwarded=has_proxy_headers(self.headers),
            allow_local=AUTH_LOCAL_BYPASS,
        ):
            return True
        if session_valid(self._cookie_value(AUTH_COOKIE)):
            return True
        if self._device_login():
            return True
        self._unauthorized()
        return False

    def _device_login(self) -> bool:
        """这台电脑之前登录过（凭据在数据根里），重启服务也认。"""
        secret = self._cookie_value(AUTH_DEVICE_COOKIE)
        if not secret:
            return False
        try:
            record = devstore.verify(device_store_path(), secret,
                                     ttl=AUTH_DEVICE_TTL)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return False
        if not record:
            return False
        return True

    def _unauthorized(self) -> None:
        u = urllib.parse.urlparse(self.path)
        if u.path.startswith("/api/"):
            self._send(401, json.dumps(
                {"ok": False, "login_required": True,
                 "error": "需要登录；口令见启动服务的终端"},
                ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8")
            return
        next_path = u.path + (("?" + u.query) if u.query else "")
        self._send(401, _auth_page(next_path).encode("utf-8"),
                   "text/html; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        self._note_peer()
        if urllib.parse.urlparse(self.path).path == "/login":
            if not self._host_ok():
                self._reject_host()
                return
            if not AUTH_REQUIRED:
                self._redirect("/")
                return
            try:
                ql = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query,
                    keep_blank_values=True,
                )
            except ValueError:
                ql = {}
            nxt = _safe_next((ql.get("next") or ["/"])[0])
            self._send(200, _auth_page(nxt).encode("utf-8"),
                       "text/html; charset=utf-8")
            return
        if not self._gate():
            return
        # BaseHTTPRequestHandler 把 self.path 按 latin-1 解码：
        # 中文参数（书库搜索）会变成乱码，导致"搜到了却显示没有"。
        # 先还原成字节再按 UTF-8 解一次。
        try:
            target = self.path.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            target = self.path
        u = urllib.parse.urlparse(target)
        # keep_blank_values=True 很关键：默认会**丢掉空值参数**，
        # 于是 `?q=` 这种"清空搜索"的请求根本传不进来 —— 用户搜过之后
        # 就再也回不到全部列表（踩过这个 bug）。
        q = urllib.parse.parse_qs(u.query, encoding="utf-8",
                                  keep_blank_values=True)
        path = u.path

        if path == "/":
            self.html(ui_home_page())
            return

        if path == "/classic":
            items = library()
            self.html(page_library(items, JOBS))
            return

        if path == "/discover":
            self.html(ui_home_page())
            return

        if path == "/shelf":
            self.html(ui_shelf_page())
            return

        if path == "/library":
            raw = (q.get("tags") or q.get("tag") or [""])[0]
            self.html(ui_library_page([x.strip() for x in raw.split(",") if x.strip()]))
            return

        if path == "/settings":
            self.html(page_settings())
            return

        if path == "/preview":
            self.html(lnui.render_preview())
            return

        if path == "/import":
            self.html(page_import())
            return

        if path == "/manifest.webmanifest":
            man = {
                "name": "轻小说书架",
                "short_name": "书架",
                "start_url": "/discover",
                "scope": "/",
                "display": "standalone",
                "orientation": "portrait",
                "background_color": "#f7f5f0",
                "theme_color": "#7a5f33",
                "icons": [
                    {"src": "/icon-192.png", "sizes": "192x192",
                     "type": "image/png", "purpose": "any"},
                    {"src": "/icon-512.png", "sizes": "512x512",
                     "type": "image/png", "purpose": "any maskable"},
                ],
            }
            self._send(200, json.dumps(man, ensure_ascii=False).encode("utf-8"),
                       "application/manifest+json; charset=utf-8")
            return

        if path in ("/icon-192.png", "/icon-512.png"):
            name = path.lstrip("/")
            try:
                with open(os.path.join(HERE, "static", name), "rb") as f:
                    data = f.read()
            except OSError:
                self.html("not found", 404)
                return
            self._send(200, data, "image/png")
            return

        if path == "/tags":
            qt = (q.get("q") or [""])[0]
            self.html(page_tags_doc(qt) if qt else ui_tags_page())
            return

        if path == "/queue":
            self.html(lnui.render_queue(queue_view(), pwa_head=PWA_HEAD))
            return

        if path == "/book":
            # 已入库作品统一跳到稳定 slug；候选仍未导入，继续用 id 详情页。
            wid = (q.get("id") or [""])[0] or (q.get("slug") or [""])[0]
            _stable = _slug_index().get(str(wid)) if wid else ""
            if _stable:
                self._redirect301(
                    f"/book/{urllib.parse.quote(_stable)}"
                    + _query_without(u.query))
                return
            doc = page_detail_doc(wid) if wid else None
            if doc is None:
                self.html("<h1>没有这部作品</h1><p><a href='/'>回书架</a></p>", 404)
                return
            self.html(doc)
            return

        if path.startswith("/book/") and path != "/book/":
            slug = urllib.parse.unquote(path[len("/book/"):])
            final = _resolve_slug(slug)
            if final != slug:
                if not novel_meta(final):
                    self.html("<h1>没有这部作品</h1><p><a href='/'>回书架</a></p>",
                              404)
                    return
                self._redirect301(
                    f"/book/{urllib.parse.quote(final)}"
                    + _query_without(u.query))
                return
            meta = novel_meta(slug) or {}
            if not meta:
                self.html("<h1>没有这部作品</h1><p><a href='/'>回书架</a></p>", 404)
                return
            wid = str(meta.get("source_id") or slug)
            doc = page_detail_doc(wid)
            if doc is None:
                self.html("<h1>没有这部作品</h1><p><a href='/'>回书架</a></p>", 404)
                return
            self.html(doc)
            return

        if path.startswith("/export/") and path.endswith(".epub"):
            slug = urllib.parse.unquote(path[len("/export/"):-len(".epub")])
            if not novel_meta(slug):
                self.html("<h1>没有这部作品</h1>", 404)
                return
            tmp = ""
            try:
                fd, tmp = tempfile.mkstemp(suffix=".epub")
                os.close(fd)
                p, info = epub.build(slug, tmp)
                with open(p, "rb") as f:
                    data = f.read()
            except ValueError as e:
                self.html(f"<h1>还不能导出</h1><p>{lr.esc(str(e))}</p>"
                          f'<p><a href="/read/{attrescape(slug)}">回阅读页</a></p>', 404)
                return
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                self.html("<h1>导出失败</h1><p>详情见终端日志。</p>", 500)
                return
            finally:
                if tmp:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
            self._send_attachment(data, "application/epub+zip",
                                  (info["title"] or slug) + ".epub",
                                  fallback=f"{slug}.epub")
            return

        if path.startswith("/cover/"):
            # 封面：key 只允许安全字符且明确拒绝 `..`（与注释承诺一致）。
            key = path[len("/cover/"):]
            if (not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,139}", key or "")
                    or ".." in key):
                self.html("bad cover", 400)
                return
            self._cover(key)
            return

        if path == "/api/import_job":
            jid = (q.get("id") or [""])[0]
            try:
                job = _read_import_job(jid)
            except ValueError:
                job = {}
            if not job:
                self.js({"ok": False, "error": "导入任务不存在"}, 404)
                return
            if (job.get("status") in ("queued", "running")
                    and jid not in IMPORT_THREADS):
                job["status"] = "interrupted"
                job["resume"] = True
                _write_import_job(job)
            self.js({"ok": True, **job})
            return

        if path == "/api/backup":
            # 全量备份下载。放在 /api/ 下，所以 --lan 模式下同样受口令保护；
            # 回环地址（手机自己）免口令，点一下就能存进手机「下载」目录。
            self.backup()
            return

        if path == "/api/trstate":
            wid = str((q.get("id") or [""])[0])
            d2 = load_detail(wid)
            self.js({"status": tr_job_state(wid),
                     "zh_title": d2.get("zh_title") or "",
                     "zh_synopsis": d2.get("zh_synopsis") or ""})
            return

        if path == "/api/detail":
            # 只读刷新：id 从 query 取（前端「重抓」走 POST，见 do_POST）。
            wid = str((q.get("id") or [""])[0])
            self.js(refresh_work_detail(wid, force=False))
            return

        if path == "/api/batchstate":
            # 列表页自动补中文标题的轮询（只读，前端用 GET）。
            self.js(recs_batch_state())
            return

        m = re.match(r"^/read/(.+)$", path)
        if m:
            slug = urllib.parse.unquote(m.group(1))
            _final_slug = _resolve_slug(slug)
            if _final_slug != slug:
                if not novel_meta(_final_slug):
                    self.html("<h1>没有这部作品</h1><p><a href='/'>回书架</a></p>",
                              404)
                    return
                _suffix = ("?" + u.query) if u.query else ""
                self._redirect301(
                    f"/read/{urllib.parse.quote(_final_slug)}{_suffix}")
                return
            frm = (q.get("from") or [None])[0]
            # 一页几章：默认 1（用户嫌 3 章一页太长）。允许 ?n=1..5 覆盖（测试/特殊需求）。
            _n = _as_int((q.get("n") or ["1"])[0] or 1, 1, lo=1, hi=5)
            # 打开时才查更新：这样既不浪费请求，标记又总是最新的。
            # 但**不能让它拖住渲染**（源站慢时整页白屏 = "页面打不开、得刷新"）。
            if novel_meta(slug) and not q.get("nocheck"):
                check_on_open_bounded(slug)
            html = page_reader(slug, int(frm) if (frm or "").isdigit() else None, limit=_n)
            if html is None:
                self.html("<h1>没有这部作品</h1><p><a href='/'>回书架</a></p>", 404)
                return
            set_opened(slug)
            # 状态机转换：打开阅读页 = 开始看 → want 自动转 reading
            # （STATE-MACHINE.md 里定义的；以前只写在文档没实现）
            try:
                if read_tracking(slug) == "want":
                    apply_action(slug, "reading", True)
            except Exception:  # noqa: BLE001
                pass
            self.html(html)
            return

        if path == "/api/queue":
            self.js(queue_view())
            return

        if path == "/api/library":
            # 注意：必须把 "page" 也算进这个判断。
            # 踩过：点"下一页"只发 ?page=N（不带 q/want），落到了书架分支，
            # 页码从未保存 → 点下一页完全没反应。
            if "q" in q or "want" in q or "page" in q or "tag" in q:
                # 书库视图操作（搜索 / 只看想看 / 标签筛选 / 翻页）
                if "q" in q:
                    LIB_VIEW["q"] = (q.get("q") or [""])[0]
                if "want" in q:
                    LIB_VIEW["want"] = (q.get("want") or ["0"])[0] == "1"
                if "tag" in q:
                    # 标签可多选：`?tag=a&tag=b` 取全部非空值（语义 AND，同时满足）。
                    # `?tag=` 一个空值 = 清空筛选。
                    LIB_VIEW["tags"] = recs._norm_tags("", q.get("tag"))
                    LIB_PAGE["n"] = 1        # 换标签筛选就回第 1 页，别停在翻不到的尾页
                if "page" in q:
                    LIB_PAGE["n"] = _as_int((q.get("page") or ["1"])[0] or 1, 1, lo=1)
                self.js({"ok": True, "q": LIB_VIEW["q"], "want": LIB_VIEW["want"],
                         "tags": LIB_VIEW["tags"]})
                return
            # 默认：书架 JSON（前端定时刷新用）
            items = library()
            wl = [dict(it, job=JOBS.get(it["slug"])) for it in items]
            self.js({"items": wl})
            return

        if path == "/api/booklib":
            # 书库条目（爬过的书）。total 与书库面板的分页基准同源（可浏览全库），
            # 不能用整库条数（含隐藏）——否则前端/测试按 total 算出的页数会多出空页。
            #
            # 也支持 ?limit=&offset=（默认 300、硬上限 1000）。`items` 默认是**截断**
            # 过的（372 本只回 300 条），所以 limit/offset/total/more 必须一起回，
            # 否则拿到 300 条的人会以为"书库只有 300 本"（数字骗人）。
            _lim = _as_int((q.get("limit") or ["300"])[0], 300, lo=1, hi=1000)
            _off = _as_int((q.get("offset") or ["0"])[0], 0, lo=0)
            _total = recs.library_count()
            self.js({"items": recs.library_items(limit=_lim, offset=_off),
                     "total": _total, "limit": _lim, "offset": _off,
                     "more": _off + _lim < _total})
            return

        if path == "/api/recs":
            # 读推荐列表用 GET（写/刷新仍走 POST）。
            # 只有 POST 的接口没法用 GET 检查，测试只能绕道去解析 HTML，
            # 而且"只读"的事用 POST 本身就不合适。
            self.js({"ok": True, "stale": recs.is_stale(),
                     "items": recs.cached(), "scan": recs.scan_state()})
            return

        if path == "/api/recsjob":
            # 「重新抓取」是后台线程，前端轮询这里显示进度。
            # 之前是同步接口：点了要等 3.5 分钟且页面零反馈 = "点了没用"。
            self.js(recs.scan_state())
            return

        if path == "/api/net":
            # 平板该用哪个地址 —— 手机开热点后网卡/IP 会变，
            # 所以这个必须**现查**，不能启动时算好写死（那样热点一开就过期）。
            port = self.server.server_address[1]
            # 开了鉴权就把口令拼进地址：本页是手机（回环/已鉴权）在看，
            # 平板照抄这行地址即可，不必自己再输口令。
            self.js({"lan": BIND_HOST not in ("127.0.0.1", "localhost"),
                     "port": port,
                     "auth_required": bool(AUTH_REQUIRED),
                     # 谁连上来过（只看 IP 和时间，不记请求内容）
                     "peers": peer_list(),
                     "urls": [f"http://{e['ip']}:{port}/" for e in lan_ipv4()],
                     "ap_urls": [f"http://{e['ip']}:{port}/"
                                 for e in lan_ipv4() if e["ap"]]})
            return

        if path == "/api/job":
            slug = (q.get("slug") or [""])[0]
            # 这里**不能**刷新心跳：心跳要反映 worker 的真实存活。前端每 2.5s
            # 轮询一次，若轮询也刷心跳，job_view 的"卡死兜底"就永远不触发
            # （worker 真死了前端也会一直转下去）。
            # 注意：**不能**把"有人查状态"当成"在读"。踩过：我用 curl 查了
            # 4 本书的 /api/job，它们全被标成在读，调度器排队去翻它们。
            # 真正的"在读"信号只有两个：打开阅读页、上报进度。
            self.js(job_view(slug))
            return

        if path == "/api/recovery":
            h = jobstore.STORE.health(refresh=True)
            h.pop("jobs_root", None)
            self.js(h)
            return

        if path == "/api/modelcfg":
            self.js(lnmodels.public_config())
            return

        if path == "/api/jobs":
            slug = (q.get("slug") or [""])[0]
            rows = [jobstore.STORE.public_view(r)
                    for r in jobstore.STORE.records()
                    if not slug or r.get("slug") == slug]
            h = jobstore.STORE.health(refresh=True)
            h.pop("jobs_root", None)
            self.js({"ok": True, "items": rows,
                     "recovery": h})
            return

        if path == "/api/reviewstate":
            slug = (q.get("slug") or [""])[0]
            ch = _as_int((q.get("chapter") or ["1"])[0], 1, lo=1)
            self.js(review_state(slug, ch))
            return

        if path == "/api/reviewreport":
            slug = (q.get("slug") or [""])[0]
            ch = _as_int((q.get("chapter") or ["1"])[0], 1, lo=1)
            if not novel_meta(slug):
                self.js({"ok": False, "error": "作品不存在"})
                return
            self.js({"ok": True, "report": rview.latest_report(slug, ch)})
            return

        if path == "/api/next":
            slug = (q.get("slug") or [""])[0]
            frm = _as_int((q.get("from") or ["1"])[0], 1, lo=1)
            meta = novel_meta(slug)
            if not meta:
                self.js({"html": "", "added": 0})
                return
            total = len(meta.get("episodes") or [])
            done = have_count(slug, meta)
            have = set(zh_chapters(slug, total))
            # 从 from 起取**连续**已译章。
            # 踩过（用户报「我第一话呢？」）：原来 from 本身没译文时会
            # `elif not want: c += 1` 跳过它去拿后面那章 —— 读者从第 3 章
            # 接着往下滚，看到的是第 5 章，中间第 4 章凭空消失。
            # 现在：缺哪章就停在哪章，并把需要的那一章号告诉前端去补翻译。
            want, c = [], max(1, frm)
            while c <= total and len(want) < 2 and c in have:
                h = lr.render_chapter_html(slug, c - 1)
                if not h:
                    break
                want.append(h)
                c += 1
            need = 0 if (want or c > total) else c
            self.js({"html": "\n".join(want), "added": len(want), "done": done,
                     "need": need, "have": sorted(have), "total": total,
                     "more": bool(c <= total)})
            return

        if path == "/api/toc":
            # 已译章节列表（全站唯一一份渲染，前端译好新章后就地刷新它）。
            # 用户要求「你汉化完了显示汉化章节，我点进去来看」。
            slug = (q.get("slug") or [""])[0]
            meta = novel_meta(slug)
            if not meta:
                self.js({"html": "", "count": 0, "total": 0})
                return
            total = len(meta.get("episodes") or [])
            have = zh_chapters(slug, total)
            onpage = {int(x) for x in (q.get("onpage") or [""])[0].split(",") if x.isdigit()}
            self.js({"html": toc_list(slug, meta, set(have), onpage),
                     "count": len(have), "total": total})
            return

        if path == "/api/chapter":
            # 单章正文（前端把"这一章还没译好"的占位块换成真内容用）
            slug = (q.get("slug") or [""])[0]
            ch = _as_int((q.get("ch") or ["0"])[0], 0, lo=0)
            meta = novel_meta(slug)
            if not meta or not (1 <= ch <= len(meta.get("episodes") or [])):
                self.js({"html": "", "done": 0})
                return
            if not has_zh(slug, ch - 1):
                self.js({"html": "", "done": have_count(slug, meta),
                         "invalid_translation": True})
                return
            self.js({"html": lr.render_chapter_html(slug, ch - 1),
                     "done": have_count(slug, meta)})
            return

        if path == "/api/state":
            self.js(load_state())
            return

        self.html("<h1>404</h1>", 404)

    def do_POST(self) -> None:  # noqa: N802
        self._note_peer()
        u = urllib.parse.urlparse(self.path)
        if u.path == "/login":
            self._login()
            return
        if not self._gate():
            return
        if not self._origin_ok():
            self._forbidden()
            return
        if u.path == "/logout":
            self._logout()
            return
        if u.path == "/api/import_async":
            try:
                data = self._request_body(limit=IMPORT_BODY_LIMIT)
            except ValueError:
                self.js({"ok": False, "error": "文件太大（上限 32MB）"}, 413)
                return
            if not data:
                self.js({"ok": False, "error": "没有收到文件"}, 400)
                return
            qq = urllib.parse.parse_qs(u.query, encoding="utf-8")
            name = os.path.basename(str((qq.get("name") or ["upload.txt"])[0]).replace(chr(92), "/"))
            title = str((qq.get("title") or [""])[0]).strip()
            author = str((qq.get("author") or [""])[0]).strip()
            try:
                job = _new_import_job(name, title, author, data)
            except (OSError, ValueError) as ex:
                self.js({"ok": False, "error": f"{type(ex).__name__}: {ex}"}, 500)
                return
            self.js({"ok": True, "id": job["id"], "job": job})
            return

        if u.path == "/api/import_retry":
            jid = str(d.get("id") or "")
            try:
                job = _read_import_job(jid)
            except ValueError:
                job = {}
            if not job:
                self.js({"ok": False, "error": "导入任务不存在"}, 404)
                return
            if not os.path.isfile(_import_data_path(jid)):
                self.js({"ok": False, "error": "原始文件已丢失，请重新导入"}, 410)
                return
            job["status"] = "queued"
            job["error"] = ""
            job["progress"] = 0.0
            _write_import_job(job)
            _start_import_job(jid)
            self.js({"ok": True, **job})
            return

        if u.path == "/api/import":
            # 文件走原始 body（不是 JSON/base64），所以要在通用大小检查之前分流。
            self._import_upload(u)
            return
        raw_len = self.headers.get("Content-Length")
        if raw_len:
            try:
                n = int(raw_len)
            except ValueError:
                self.js({"ok": False, "error": "Content-Length 无效"}, 400)
                return
            if n < 0 or n > REQUEST_BODY_LIMIT:
                self.js({"ok": False, "error": "请求体过大"}, 413)
                return
        d = self.body()

        if u.path == "/api/detail":
            # 详情页「重抓简介/目录」：清掉旧缓存后重新抓一次（force=true）
            wid = str(d.get("id") or "")
            self.js(refresh_work_detail(wid, force=bool(d.get("force"))))
            return

        if u.path == "/api/translate_batch":
            # 列表页用：把还没翻的推荐排进后台队列
            n = batch_translate_missing(limit=_as_int(d.get("limit"), 40, lo=1, hi=500))
            self.js({"ok": True, "queued": n})
            return

        if u.path == "/api/batchstate":
            self.js(recs_batch_state())
            return

        if u.path == "/api/translate_meta":
            wid = str(d.get("id") or "")
            if not wid:
                self.js({"ok": False, "error": "缺少 id"})
                return
            item = None
            try:
                for cand in recs.cached(include_hidden=True) or []:
                    if str(cand.get("id")) == wid:
                        item = cand
                        break
            except Exception:  # noqa: BLE001
                item = None
            if item is None:
                try:
                    item = (recs._load_lib() or {}).get(wid)
                except Exception:  # noqa: BLE001
                    item = None
            title = (item or {}).get("title") or ""
            det = load_detail(wid)
            if not det.get("toc") and (item or {}).get("url"):
                det = refresh_detail(wid, item.get("url") or "")
            syn = det.get("synopsis") or (item or {}).get("catchphrase") or ""
            if not title and not syn:
                self.js({"ok": False, "error": "没有可翻译的内容"})
                return
            st = start_translation(wid, title, syn)
            d2 = load_detail(wid)
            self.js({"ok": True, "status": st,
                     "zh_title": d2.get("zh_title") or "",
                     "zh_synopsis": bool(d2.get("zh_synopsis"))})
            return

        if u.path == "/api/progress":
            slug = d.get("slug") or ""
            # 只对真实存在的作品写进度。空/伪造 slug 会经 update_book()
            # 在 data/books/ 里造出一个 `.json` 或 `__no_such_book__.json`，
            # 这是自检残留之外的真实数据污染（本机已复现）。
            if not novel_meta(slug):
                self.js({"ok": False, "error": "作品不存在"})
                return
            sc = d.get("scroll")
            try:
                scv = float(sc) if sc is not None else None
            except (TypeError, ValueError):
                scv = None
            set_progress(slug, _as_int(d.get("chapter"), 1, lo=1), scv)
            note_reading(slug, persist=True)
            self.js({"ok": True})
            return

        if u.path == "/api/review":
            slug = str(d.get("slug") or "")
            meta = novel_meta(slug)
            if not meta:
                self.js({"ok": False, "error": "作品不存在"})
                return
            ch = _as_int(d.get("chapter"), 0, lo=1)
            total = len(meta.get("episodes") or [])
            if not (1 <= ch <= total):
                self.js({"ok": False, "error": f"章号超出范围：{ch}/{total}"})
                return
            if not has_zh(slug, ch - 1):
                self.js({"ok": False, "error": "这一章还没有译文，无法校对"})
                return
            j = start_review(
                slug, ch, use_llm=bool(d.get("llm")),
                fix=bool(d.get("fix")), learn=bool(d.get("learn", True)))
            self.js({"ok": True, "job": j})
            return

        if u.path == "/api/stop":
            slug = d.get("slug") or ""
            if not novel_meta(slug):
                self.js({"ok": False, "error": "作品不存在"})
                return
            blocked = _job_recovery_block()
            if blocked:
                self.js(blocked, 503)
                return
            # 停止 = 取消当前任务 + 暂停本书的持续翻译（否则调度器 2 秒后又排队）
            _r = cancel_job(slug, disable=False)
            SCHED.set_paused(slug, True)
            self.js(_r)
            return

        if u.path == "/api/translate":
            blocked = _job_recovery_block()
            if blocked:
                self.js(blocked, 503)
                return
            slug = d.get("slug") or ""
            count = _as_int(d.get("count"), 2, lo=1, hi=200)
            reason = d.get("reason") or "user"
            meta = novel_meta(slug)
            if not meta:
                self.js({"ok": False, "error": "作品不存在"})
                return
            SCHED.set_paused(slug, False)   # 手动点翻译 = 恢复本书持续翻译
            note_reading(slug, persist=True)
            # 预算只做提醒（见 lnsched.over_budget）：在读的书不该因为
            # "今天的额度用完了"而停下来 —— 那是"翻译又卡了"的来源。
            latest = jobstore.STORE.latest(slug)
            if (latest and latest.get("status") == "interrupted"
                    and not bool(d.get("resume"))):
                self.js({
                    "ok": False,
                    "needs_recovery": True,
                    "error": "上一次翻译中断，请确认后继续",
                    "job": jobstore.STORE.public_view(latest),
                }, 409)
                return
            with LOCK:
                mem_active = (JOBS.get(slug) or {}).get("status") in (
                    "queued", "running")
            durable_active = jobstore.STORE.active(slug)
            already_active = bool(mem_active or durable_active)
            if not already_active:
                retry = _rate_retry(
                    "translate", self._peer(),
                    TRANSLATE_RATE_LIMIT, TRANSLATE_RATE_WINDOW)
                if retry:
                    self.js({
                        "ok": False,
                        "retry_after": retry,
                        "error": "翻译启动过于频繁，请稍后再试",
                    }, 429, {"Retry-After": str(retry)})
                    return
            force = bool(d.get("force"))
            if force and already_active:
                # 重翻已有译文不能被"任务进行中"静默吞掉：start_job 会返回
                # 正在跑的那个任务，UI 以为排队成功，最后却什么都没重翻。
                self.js({"ok": False,
                         "error": "有翻译任务在进行，等它结束再重翻本章"}, 409)
                return
            fill = bool(d.get("fill"))
            total_ep = len(meta.get("episodes") or [])
            _ceiling_given = bool(d.get("ceiling"))
            ceil = (_as_int(d.get("ceiling"), 1, lo=1)
                    if _ceiling_given else total_ep)
            after = (_as_int(d.get("after"), None, lo=1)
                     if d.get("after") not in (None, "") else None)
            if fill and not _ceiling_given:
                # 「更新了 +N 话 · 点我翻译」是用户**此刻的明确意图**，不该被
                # "自动翻译未开"挡住（原来 fill 不带 ceiling → auto_ceiling=0 →
                # allowed_targets 返回空 → 静默不翻，按钮名骗人）。
                #
                # 但也不能理解成"把全部欠账一次翻完"：按钮上写的是「+N 话」，
                # 而实际可能欠几十话（真实数据：一本 20/61 的欠 41 话 ≈ 25 万 token）。
                # 所以只翻**最新的那 N 话**（after = 总章数 - N）；最新几话已经译好
                # 时退回"按顺序补最早的缺章"。一次点击最多 10 话。
                total_ep = len(meta.get("episodes") or [])
                n_new = max(1, min(count, 10))
                ceil = total_ep
                after = max(1, total_ep - n_new)
                count = n_new
                fill = False
            try:
                j = start_job(slug, count, reason, after=after,
                              fill=fill, ceiling=ceil,
                              resume_of=(latest or {}).get("job_id")
                              if d.get("resume") else None,
                              force=force)
            except jobstore.RecoveryRequired:
                self.js(_job_recovery_block() or {
                    "ok": False, "read_only": True,
                    "error": "任务日志损坏，暂时不能开始翻译",
                }, 503)
                return
            if not already_active:
                _rate_hit("translate", self._peer(), TRANSLATE_RATE_WINDOW)
            self.js({"ok": True, "job": j})
            return

        if u.path == "/api/feedback":
            slug = d.get("slug") or ""
            if not novel_meta(slug):
                self.js({"ok": False, "error": "作品不存在"})
                return
            rec = {
                "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "slug": slug,
                "chapter": _as_int(d.get("chapter"), 0, lo=0),
                "vote": d.get("vote") or "",
                "note": (d.get("note") or "")[:2000],
                "read": True,
            }
            append_feedback(rec["slug"], rec)
            self.js({"ok": True})
            return

        if u.path == "/api/log":
            try:
                with open(os.path.join(DATA, "client.log"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({"at": time.strftime("%H:%M:%S"), **d},
                                       ensure_ascii=False) + "\n")
            except OSError:
                pass
            self.js({"ok": True})
            return

        if u.path == "/api/status":
            slug = d.get("slug") or ""
            # 兼容两种写法：flag=favorites/finished/dropped 与 action=...
            flag = d.get("action") or d.get("flag") or ""
            alias = {"favorites": "favorite"}
            flag = alias.get(flag, flag)
            value = d.get("value")
            if not slug:
                self.js({"ok": False, "error": "缺少 slug"})
                return
            # ⚠ 本地没有这部作品时必须拒绝，**不能**给它建状态文件：
            # 踩过 —— 前端测试/手抖发来一个不存在的 slug，`update_book()` 会
            # 老老实实在 data/books/ 里造出一个 `__xxx.json`，
            # 于是"自检产物没清干净"（真数据目录里多出垃圾）。
            # 状态只对真实存在的作品有意义。
            if not novel_meta(slug):
                self.js({"ok": False, "error": "本地没有这部作品，改不了它的状态"})
                return
            if flag not in ("favorite", "reading", "finished", "dropped", "want",
                            "off", "remove", "shelf_off"):
                self.js({"ok": False, "error": f"未知操作：{flag}"})
                return
            try:
                with open(os.path.join(DATA, "server.log"), "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%H:%M:%S')} {slug} {flag}={value}\n")
            except OSError:
                pass
            r = apply_action(slug, flag, None if value is None else bool(value))
            # 回传**变更后的真实状态**，前端据此渲染 ⟹ UI 必然等于实际
            # （removed 必须回传：前端靠它知道"已移出书架"，不回传就永远不触发）
            self.js({"ok": True, "favorite": r["favorites"],
                     "tracking": r["tracking"],
                     "cleared_favorite": bool(r.get("cleared_favorite")),
                     "removed": bool(r.get("removed"))})
            return

        if u.path == "/api/transcfg":
            slug = d.get("slug") or ""
            if not novel_meta(slug):
                self.js({"ok": False, "error": "作品不存在"})
                return
            # v5.1：不再有"自动翻译开关 / 读到+N章"。这个接口保留只为
            # 兼容旧前端：enabled=true = 恢复本书持续翻译，false = 暂停本书。
            # ahead/max_chapters 接受但忽略（上限模型已废弃）。
            if "enabled" in d:
                SCHED.set_paused(slug, not bool(d["enabled"]))
                if d["enabled"]:
                    note_reading(slug, persist=True)
            if d.get("paused") is not None:
                SCHED.set_paused(slug, bool(d["paused"]))
            meta = novel_meta(slug) or {}
            _paused = bool((SCHED.state["books"].get(slug) or {}).get("paused"))
            self.js({"ok": True, "paused": _paused,
                     # 兼容旧前端/旧测试的字段：enabled = "没被暂停"。
                     # 新代码请不要再用它，改用 paused。
                     "cfg": {"enabled": not _paused, "ahead": 0},
                     "ceiling": len(meta.get("episodes") or [])})
            return

        if u.path == "/api/queue":
            act = str(d.get("action") or "")
            slug = str(d.get("slug") or "")
            if act == "add":
                if not novel_meta(slug):
                    self.js({"ok": False, "error": "作品不存在"})
                    return
                SCHED.enqueue(slug)
            elif act == "remove":
                SCHED.dequeue(slug)
            elif act == "forget":
                # 彻底移出翻译列表：停掉进行中的任务 + 清掉在读/队列/暂停状态。
                try:
                    cancel_job(slug, disable=False)
                except Exception:  # noqa: BLE001
                    pass
                SCHED.forget(slug)
            elif act == "pause":
                SCHED.set_paused(slug, True)
            elif act == "resume":
                # 只解除暂停，不顺手改"在读"状态：这本书在队列里就继续按队列翻。
                SCHED.set_paused(slug, False)
            elif act in ("up", "down"):
                rows = [r["slug"] for r in queue_view()["rows"]
                        if r["reason"] == "queue"]
                if slug in rows:
                    i = rows.index(slug)
                    j = i - 1 if act == "up" else i + 1
                    if 0 <= j < len(rows):
                        a = SCHED.state["books"][slug]
                        b = SCHED.state["books"][rows[j]]
                        a["order"], b["order"] = b.get("order"), a.get("order")
                        SCHED.save()
            elif act == "pause_all":
                SCHED.pause_all(bool(d.get("paused")))
            elif act == "budget":
                SCHED.set_budget(_as_int(d.get("tokens"), 150000, lo=0))
            elif act == "idle":
                SCHED.set_idle(_as_int(d.get("minutes"), 30, lo=1, hi=1440))
            else:
                self.js({"ok": False, "error": "未知操作"})
                return
            self.js({"ok": True, **queue_view()})
            return

        if u.path == "/api/shelfpage":
            key = _shelf_key(d.get("key"))
            page = _as_int(d.get("page"), 1, lo=1)
            _remember_shelf_page(key, page)
            self.js({"ok": True, "key": key, "page": _shelf_page(key)})
            return

        if u.path == "/api/dislike":
            # 「不感兴趣」= 隐藏 + **喂画像**。
            # 只隐藏不学，等于每次都给同一类书按一次"不喜欢"却什么都没记住。
            nid = str(d.get("id") or "")
            reason = str(d.get("reason") or "meh")
            if not nid:
                self.js({"ok": False, "error": "缺少作品 id"})
                return
            try:
                _hid = recs.set_hidden(nid, True)   # 立刻不再出现在推荐里
            except Exception as e:  # noqa: BLE001
                self.js({"ok": False, "error": f"{type(e).__name__}: {e}"})
                return
            learned, changes, note = 0, [], ""
            if not _hid:
                # 不在书库档案里（比如刚抓到的、还没 merge）→ 说清楚，
                # 别让前端以为已经永久屏蔽了
                note = "这本不在书库档案里，下次刷新可能还会出现"
            try:
                lf = recs._load_lnfind()
                work = None
                for cand in (recs.cached(include_hidden=True) or []):
                    if str(cand.get("id")) == nid:
                        work = cand
                        break
                if work is None:
                    work = (recs._load_lib() or {}).get(nid)
                if not work:
                    note = "这本不在缓存里，只隐藏了，没东西可学"
                elif lf.already_learned(nid):
                    note = "这本之前已经学过一次了，这次只隐藏（避免重复扣分）"
                else:
                    work = dict(work)
                    work["id"] = nid
                    # 原因决定**扣哪些标签**和**扣多少**：
                    #  «太套路了» 只该怪套路标签（異世界転生 之类），
                    #  不能连带把有辨识度的标签（勘違い、悪役令嬢）一起扣 ——
                    #  那是在教坏画像，正是用户反复强调的"误解系"偏好所在。
                    weight = {"theme": 0.8, "cliche": 0.4,
                              "author": 0.5, "meh": 0.25}.get(reason, 0.25)
                    only = None
                    if reason == "cliche":
                        formula = (lf.load_profile() or {}).get("formula_tags") or {}
                        hits = [t for t in (work.get("tags") or []) if t in formula]
                        if hits:
                            only = hits
                        else:
                            # 一个套路标签都没命中 → 无从归因，就轻轻扣一笔
                            weight = 0.2
                    changes = lf.learn_from_work(work, direction=-1, weight=weight,
                                                 reason=reason, only_tags=only,
                                                 verbose=False)
                    learned = len(changes)
                    if not changes:
                        note = "没有可归因的标签，画像未变"
            except Exception as e:  # noqa: BLE001
                note = f"画像没更新：{type(e).__name__}: {e}"
            self.js({"ok": True, "hidden": bool(_hid), "learned": learned,
                     "changes": changes, "note": note})
            return

        if u.path == "/api/hide":
            nid = str(d.get("id") or "")
            ok = recs.set_hidden(nid, bool(d.get("value"))) if nid else False
            self.js({"ok": ok})
            return

        if u.path == "/api/want":
            nid = str(d.get("id") or "")
            ok = recs.set_want(nid, bool(d.get("value"))) if nid else False
            self.js({"ok": ok})
            return

        if u.path == "/api/recs":
            if d.get("rotate"):
                # 「换一批」：只挪本地游标，秒回，不打源站。
                self.js(recs.rotate(_as_int(d.get("n"), recs.RECS_PAGE, lo=1)))
            elif d.get("topup"):
                # 只用书库里已经抓过的书排一批出来：不联网、不花钱、秒回。
                # 空缓存时没必要让用户先等两分钟。
                r = recs.topup(top=_as_int(d.get("top"), recs.RECS_STORE, lo=1))
                r["ok"] = bool(r.get("ok"))
                self.js(r)
            elif d.get("refresh"):
                # 「重新抓取」：默认后台跑（立刻返回，前端轮询 /api/recsjob）。
                # wait=true 保留同步语义给命令行/测试用 ——
                # 同步等 3.5 分钟在浏览器里必然被当成"死了"。
                if d.get("wait"):
                    try:
                        items = recs.refresh(top=_as_int(d.get("top"), recs.RECS_STORE, lo=1))
                        self.js({"ok": True, "count": len(items)})
                    except Exception as e:  # noqa: BLE001
                        self.js({"ok": False, "error": f"{type(e).__name__}: {e}"})
                else:
                    # queries 可指定：自检用单个关键词把"异步 + 进度"的契约
                    # 在几秒内测完，而不是真的打 20 个词等两分钟。
                    _qs = d.get("queries")
                    if not isinstance(_qs, list) or not _qs:
                        _qs = None
                    started = recs.refresh_async(top=_as_int(d.get("top"), recs.RECS_STORE, lo=1),
                                                 queries=_qs)
                    self.js({"ok": True, "started": started,
                             "already": (not started),
                             "scan": recs.scan_state()})
            else:
                self.js({"ok": True, "stale": recs.is_stale(),
                         "items": recs.cached(), "scan": recs.scan_state()})
            return

        if u.path == "/api/add":
            url = (d.get("url") or "").strip()
            # Mark the candidate as "want" before touching the network.  If the
            # source fetch/import fails, discovery can still show a retry card
            # instead of silently losing the click.
            sy = lnlib.syosetu_source(url) if lnlib else None
            if "kakuyomu.jp/works/" in url:
                m = re.search(r"/works/(\d+)", url)
                wid = m.group(1) if m else ""
            elif sy:
                wid = sy[1]
                url = f"{lnlib.SYOSETU_DOMAINS[sy[0]]}/{sy[1].lower()}/"
            else:
                self.js({"ok": False,
                         "error": "只支持 kakuyomu / 成为小说家（ncode）链接"})
                return
            try:
                if wid:
                    recs.set_want(wid, True)
            except Exception:  # noqa: BLE001
                pass
            try:
                if os.path.isdir(NOVELS):
                    for s in os.listdir(NOVELS):
                        mm = novel_meta(s)
                        if mm and str(mm.get("source_id")) == wid:
                            # 已在本地：确保它在书架上（可能之前被移出过），
                            # 然后照样补一次书名翻译
                            try:
                                ensure_on_shelf(s)
                                if wid:
                                    start_batch_translate(wid)
                            except (Exception, SystemExit) as e:  # noqa: BLE001
                                self.js({"ok": False,
                                         "error": f"上架失败：{type(e).__name__}: {e}"})
                                return
                            self.js({"ok": True, "slug": s, "existed": True})
                            return
                import argparse as _ap
                lt.cmd_init(_ap.Namespace(url=url, slug=None, force=False))
                # ★ 必须显式上架（tracking=want）：cmd_init 只建目录，
                #   不写书架状态 → 书加进来了却在书架上看不见（用户报的 bug）。
                #   注意这**不是收藏**，favorites 保持为空。
                #
                # ⚠ 不能只看"cmd_init 没抛异常"就说成功：它历史上会在
                #   「slug 撞车」（两部日文标题都缩成同一个 ASCII 短名）时**静默
                #   return**，于是 `/api/add` 回 ok=true、书却没建也没上架 ——
                #   用户看到的就是「点加入书架永远失败」。所以这里**按结果验证**：
                #   本地要有这个 source_id，且状态文件里真的在书架上。
                local = slug_for_source(wid)
                if not local:
                    self.js({"ok": False,
                             "error": "没建成（源站异常或同名作品冲突），请再点一次"})
                    return
                try:
                    ensure_on_shelf(local)
                except (Exception, SystemExit) as e:  # noqa: BLE001
                    self.js({"ok": False,
                             "error": f"上架失败：{type(e).__name__}: {e}"})
                    return
                _bd = _read_book(local)
                if not (_bd.get("favorites") or _bd.get("tracking") in TRACKING):
                    self.js({"ok": False, "error": "上架没写进状态文件"})
                    return
                # 立刻排一个「书名+简介」翻译：用户刚点「加入书架」，
                # 马上就能在书架上看到中文书名（否则要等下一次列表页轮询，
                # 用户看到的就是"书架里的书标题没翻译"）。
                try:
                    if wid:
                        start_batch_translate(wid)
                except (Exception, SystemExit):  # noqa: BLE001
                    pass
                self.js({"ok": True, "slug": local})
            except SystemExit:
                self.js({"ok": False, "error": "创建失败（链接或源站问题）"})
            except Exception as e:  # noqa: BLE001
                self.js({"ok": False, "error": f"{type(e).__name__}: {e}"})
            return

        if u.path == "/api/check":
            if d.get("all"):
                wl = watch_list()
                res = check_updates([s for s in wl if s])
            else:
                slug = d.get("slug") or ""
                r = check_on_open(slug, force=True) if slug else {}
                res = [r] if r else []
            self.js({"ok": True, "checked": len(res), "results": res})
            return

        if u.path == "/api/favorite":
            slug = d.get("slug") or ""
            fav = toggle_favorite(slug) if slug else False
            self.js({"ok": True, "favorite": fav})
            return

        self.js({"ok": False, "error": "unknown"})

    def do_HEAD(self) -> None:  # noqa: N802
        if not self._gate():
            return
        self._send(200, b"", "text/html")



def ui_work_rows() -> tuple[list[dict], dict]:
    """Rows for /shelf and /library.  Local books win over flat candidates."""
    local = library()
    local_ids = {str(it.get("id") or "") for it in local if it.get("id")}
    rows: list[dict] = []
    for it in local:
        wid = str(it.get("id") or "")
        if not wid:
            continue
        rows.append({
            "id": wid, "slug": it.get("slug") or "",
            "title": it.get("title") or it.get("title_jp") or "",
            "title_jp": it.get("title_jp") or "",
            "author": it.get("author") or "", "tags": it.get("tags") or [],
            "total": it.get("total") or 0, "read": it.get("read") or 0,
            "tracking": it.get("tracking") or "",
            "on_shelf": bool(it.get("on_shelf")), "favorite": bool(it.get("favorite")),
            "source_key": ("local" if (it.get("local")
                             or str(wid).startswith("local-")) else "source"),
            "href": f"/book/{urllib.parse.quote(str(it.get('slug') or ''))}",
            "read_href": f"/read/{urllib.parse.quote(str(it.get('slug') or ''))}",
            "url": "", "added_at": it.get("added_at") or it.get("updated") or "",
        })
    try:
        candidates = recs.library_items(limit=1000, include_hidden=False)
    except Exception:  # noqa: BLE001
        candidates = []
    for r in candidates:
        wid = str(r.get("id") or "")
        if not wid or wid in local_ids:
            continue
        title_zh = r.get("title_zh") or ""
        rows.append({
            "id": wid, "slug": "",
            "title": title_zh or r.get("title") or "",
            "title_jp": r.get("title") or "",
            "author": r.get("author") or "", "tags": r.get("tags") or [],
            "total": r.get("episodes") or 0, "read": 0, "tracking": "",
            "on_shelf": False, "favorite": False,
            "want": bool(r.get("want")),
            "source_key": "source", "href": f"/book?id={urllib.parse.quote(wid)}",
            "read_href": "", "url": r.get("url") or "",
            "added_at": r.get("added_at") or r.get("updated") or "",
        })
    counts = {"all": len(rows), "source": 0, "local": 0}
    for r in rows:
        counts[r["source_key"]] = counts.get(r["source_key"], 0) + 1
    return rows, counts


def ui_unimported_wants() -> list[dict]:
    try:
        lib = recs._load_lib() or {}
    except Exception:  # noqa: BLE001
        return []
    local_ids = {str(it.get("id") or "") for it in library()}
    out = []
    for wid, it in lib.items():
        if not it.get("want") or it.get("hidden") or str(wid) in local_ids:
            continue
        if not it.get("url"):
            continue
        out.append({"id": str(wid), "title": it.get("title") or "",
                    "author": it.get("author") or "",
                    "tags": it.get("tags") or [], "url": it.get("url") or ""})
    out.sort(key=lambda r: r.get("title") or "")
    return out


def ui_library_page(tags=()) -> str:
    rows, counts = ui_work_rows()
    selected = [str(t) for t in tags if t]
    if selected:
        rows = [r for r in rows if all(t in (r.get("tags") or []) for t in selected)]
        counts = {"all": len(rows), "source": 0, "local": 0}
        for r in rows:
            counts[r["source_key"]] = counts.get(r["source_key"], 0) + 1
    return lnui.render_library(rows, source_counts=counts,
                              selected_tags=selected, pwa_head=PWA_HEAD,
                              tag_payload=ui_tag_payload(rows))


def ui_shelf_page() -> str:
    rows, _ = ui_work_rows()
    rows = [r for r in rows if r.get("on_shelf")]
    wants = ui_unimported_wants()
    counts = {"all": len(rows) + len(wants), "source": 0, "local": 0}
    for r in rows:
        counts[r["source_key"]] = counts.get(r["source_key"], 0) + 1
    counts["source"] = counts.get("source", 0) + len(wants)
    return lnui.render_shelf(rows, wants, source_counts=counts, pwa_head=PWA_HEAD,
                              tag_payload=ui_tag_payload(rows + wants))


def ui_tag_payload(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    latest: dict[str, str] = {}
    works: list[list[str]] = []
    for r in rows:
        tags = [str(t) for t in (r.get("tags") or []) if t]
        if tags:
            works.append(tags)
        at = str(r.get("added_at") or "")
        for t in tags:
            counts[t] = counts.get(t, 0) + 1
            if at > latest.get(t, ""):
                latest[t] = at
    tags = [{"name": t, "count": n, "latest": latest.get(t, "")}
            for t, n in counts.items()]
    tags.sort(key=lambda x: (-x["count"], x["name"]))
    recent = [x["name"] for x in sorted(
        (x for x in tags if x.get("latest")),
        key=lambda x: (x["latest"], x["name"]), reverse=True)][:12]
    return {"tags": tags, "recent": recent, "works": works}


def ui_tags_page() -> str:
    rows, _ = ui_work_rows()
    p = ui_tag_payload(rows)
    return lnui.render_tags(p["tags"], p["recent"], p["works"], pwa_head=PWA_HEAD)


def ui_home_candidates() -> list[dict]:
    shelf = shelf_source_ids()
    rows: list[dict] = []
    seen: set[str] = set()

    def add(row: dict) -> None:
        wid = str(row.get("id") or "")
        if not wid or wid in seen or wid in shelf:
            return
        if str(wid).startswith("local-"):
            return
        seen.add(wid)
        rows.append(row)

    try:
        for it in recs.cached() or []:
            if it.get("hidden"):
                continue
            add({"id": str(it.get("id") or ""), "title": it.get("title") or "",
                 "title_jp": it.get("title") or "", "author": it.get("author") or "",
                 "tags": it.get("tags") or [], "total": it.get("episodes") or 0,
                 "url": it.get("url") or "", "want": False})
    except Exception:  # noqa: BLE001
        pass
    try:
        lib_rows, _ = ui_work_rows()
    except Exception:  # noqa: BLE001
        lib_rows = []
    for r in lib_rows:
        if r.get("source_key") != "source" or r.get("local"):
            continue
        add({"id": str(r.get("id") or ""), "title": r.get("title") or "",
             "title_jp": r.get("title_jp") or "", "author": r.get("author") or "",
             "tags": r.get("tags") or [], "total": r.get("total") or 0,
             "url": r.get("url") or "", "want": bool(r.get("want"))})
    return rows


def ui_home_page() -> str:
    candidates = ui_home_candidates()
    try:
        recent = recent_read()
    except Exception:  # noqa: BLE001
        recent = None
    for i, r in enumerate(candidates[:12]):
        try:
            zh = (load_detail(str(r.get("id") or "")) or {}).get("zh_title") or ""
            if zh:
                r = dict(r)
                r["title"] = zh
                candidates[i] = r
        except Exception:  # noqa: BLE001
            pass
    return lnui.render_home(candidates, recent, pwa_head=PWA_HEAD,
                            notice=recovery_notice_html())


def main() -> None:
    global BIND_HOST, AUTH_REQUIRED, AUTH_LOCAL_BYPASS, AUTH_TOKEN
    global JOBS_READ_ONLY, JOBS_RECOVERY_INFO
    # 启动信息（尤其 --lan 随机生成的口令）必须**立刻**可见：用户常把服务
    # 重定向到日志 / nohup / systemd，stdout 的块缓冲会把 token 滞留在内存里，
    # 日志里迟迟没有 → 平板打不开又查不到口令。行缓冲对交互终端无副作用。
    for _stream in (sys.stdout, sys.stderr):
        try:
            # Windows 终端常是 GBK/cp936；状态文案里可能含 emoji。只设
            # line_buffering 时，一个无法编码的字符会让服务在启动阶段退出。
            _stream.reconfigure(line_buffering=True, errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="轻小说本地阅读服务")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--lan", action="store_true",
                    help="绑到 0.0.0.0，让同一局域网/手机热点下的设备（平板）也能访问")
    ap.add_argument("--require-auth", action="store_true",
                    help="即使绑定回环地址也要求口令（反代/隧道部署的显式开关）")
    ap.add_argument("--watch", action="store_true",
                    help="开启定时查更新（默认不开启：打开书时才查，更省）")
    ap.add_argument("--every-hours", type=float, default=12.0,
                    help="--watch 时的检查间隔（默认 12 小时）")
    a = ap.parse_args(_REAL_ARGV[1:])

    try:
        recs._load_lib()
    except recs.lncatalog.CatalogSchemaError as ex:
        print(f"书目 schema 不匹配：{ex}；请先运行 migrate_reset.py。",
              file=sys.stderr)
        sys.exit(2)

    try:
        runtime_lock = lndata.acquire_lock(LAYOUT)
    except lndata.DataRootError as ex:
        print(f"启动失败：{ex}", file=sys.stderr)
        raise SystemExit(2)
    # Normal shutdown releases below; this is the crash/early-exception safety
    # net.  The OS releases the advisory lock even if Python cannot run atexit.
    atexit.register(runtime_lock.__exit__, None, None, None)
    print(f"数据根模式：{LAYOUT.mode}"
          + (f"（{LAYOUT.home}）" if LAYOUT.home else ""))
    print(f"数据根锁：{LAYOUT.lock_path}")

    recovered = jobstore.STORE.reconcile_startup()
    JOBS_RECOVERY_INFO = jobstore.STORE.health(refresh=True)
    JOBS_READ_ONLY = bool(JOBS_RECOVERY_INFO.get("read_only"))
    if recovered.get("changed"):
        print(f"任务恢复：{recovered['changed']} 个中断任务已标为 interrupted，"
              "等待你在阅读页确认恢复")
    if JOBS_READ_ONLY:
        print("任务日志损坏：已进入受限恢复模式；阅读、进度、书架和备份可用，"
              "开始/停止翻译等任务写入已禁用", file=sys.stderr)
        for item in JOBS_RECOVERY_INFO.get("corrupt") or []:
            print(f"  - {item['file']}: {item['error']}", file=sys.stderr)
        print(f"  修复命令：{JOBS_RECOVERY_INFO.get('repair_command')}",
              file=sys.stderr)

    n = 0 if JOBS_READ_ONLY else dedupe_feedback()
    if not runtime_lock.is_held():
        raise RuntimeError(
            "数据根锁在反馈清理后被意外关闭：" + runtime_lock.diagnostics())
    if n:
        print(f"已清理 {n} 条重复反馈")
    m = 0 if JOBS_READ_ONLY else migrate_shelf_state()
    if not runtime_lock.is_held():
        raise RuntimeError(
            "数据根锁在书架迁移后被意外关闭：" + runtime_lock.diagnostics())
    if m:
        print(f"已把 {m} 本『有进度但无书架标记』的书标为在读（避免从书架消失）")

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    threading.Thread(target=_job_watchdog, daemon=True,
                     name="job-watchdog").start()
    threading.Thread(target=_translation_dispatcher, daemon=True,
                     name="translation-dispatcher").start()
    _resume_interrupted_after_restart()
    if not runtime_lock.is_held():
        raise RuntimeError(
            "数据根锁在 worker 启动后被意外关闭：" + runtime_lock.diagnostics())

    # 默认**不开**定时轮询：改成"打开某本书时才查它"（用户要求，省 token）。
    # 需要主动推送式检查时用 --watch 显式开启。
    if a.watch:
        w = threading.Thread(target=update_daemon, args=(a.every_hours,), daemon=True)
        w.start()
        print(f"已开启定时检查：每 {a.every_hours} 小时查一次『收藏 + 近期读过』")
    else:
        print("更新检查：打开某本书时才会查它（默认按需，可用 --watch 改为定时）")

    # --lan：绑 0.0.0.0，让手机热点/同一 Wi-Fi 下的平板也能访问（用户要求）。
    # 绑 0.0.0.0 后**回环地址照样能用**，手机自己的浏览器不受影响。
    if a.lan and a.host == "127.0.0.1":
        a.host = "0.0.0.0"
    BIND_HOST = a.host
    # 三种“对外形态”任一成立就必须上口令：
    #   1) 绑非回环地址（--lan / --host 0.0.0.0）；
    #   2) 显式配置了非回环 LNTRANS_ALLOWED_HOSTS（反代/隧道）；
    #   3) 用户显式 --require-auth。
    # 回环 peer 只对“Host 也是回环且没有代理头”的本机浏览器免登录。
    AUTH_LOCAL_BYPASS = not a.require_auth
    if auth_required_for(a.host, explicit_allowed_hosts(),
                         force=a.require_auth):
        AUTH_REQUIRED = True
        try:
            AUTH_TOKEN, token_source = load_access_token(
                os.environ.get("LNTRANS_TOKEN") or "",
                os.environ.get("LNTRANS_TOKEN_FILE") or "",
            )
        except OSError as ex:
            print(f"启动失败：{ex}", file=sys.stderr)
            raise SystemExit(2)
        if not AUTH_TOKEN:
            AUTH_TOKEN = secrets.token_urlsafe(24)
            token_source = "本次启动随机生成"
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    if not runtime_lock.is_held():
        raise RuntimeError(
            "数据根锁在 HTTP 服务创建后被意外关闭：" + runtime_lock.diagnostics())
    # Docker/systemd stop sends SIGTERM, not KeyboardInterrupt.  Shut down from
    # a helper thread because HTTPServer.shutdown() waits for serve_forever().
    def _graceful_stop(_signum, _frame):
        threading.Thread(target=srv.shutdown, daemon=True).start()
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _graceful_stop)
    # 必须先把 sockname 打出来：端口被占时 ThreadingHTTPServer 直接抛异常，
    # 而 --lan 下用户最容易搞不清"到底绑上没有"。
    print(f"书架已启动：http://127.0.0.1:{a.port}/")
    if a.host not in ("127.0.0.1", "localhost"):
        ips = lan_ipv4()
        print(f"已开放局域网（绑 {a.host}:{a.port}）：")
        if not ips:
            print("  （现在没查到可用网卡地址；手机开热点后再看页面底部的地址）")
        for e in ips:
            star = "★" if e["ap"] else " "
            hint = "  ← 热点/局域网，平板大概率用这个" if e["ap"] else ""
            print(f"  {star} http://{e['ip']}:{a.port}/   [{e['if']}]{hint}")
        print(f"  访问口令：{AUTH_TOKEN}")
        print(f"  口令来源：{token_source}")
        print("  （平板打开地址后输入口令；网址本身不会带口令。"
              "只有「回环 peer + 回环 Host + 无代理头」的本机浏览器免登录。）")
        print("  （可用 LNTRANS_TOKEN 或 LNTRANS_TOKEN_FILE 固定口令；"
              "自定义域名用 LNTRANS_ALLOWED_HOSTS 加入白名单。）")
        if len(AUTH_TOKEN) < 8:
            print("  注意：当前口令少于 8 个字符，建议换成更长的随机口令。",
                  file=sys.stderr)
        print("  注意：口令不对的请求会被拒绝（401）。口令别外传。")
    elif AUTH_REQUIRED:
        # 绑回环但配置了外部 Host 白名单 / --require-auth：反代部署的标准形态。
        print("已启用访问口令（反代/外部 Host 或 --require-auth）：")
        print(f"  访问口令：{AUTH_TOKEN}")
        print(f"  口令来源：{token_source}")
        print("  反代必须保留原始 Host 并带口令访问；不要把它改写成 127.0.0.1。")
    print(f"作品目录：{NOVELS}")
    print(f"你的进度/收藏/反馈：{state_path()}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        STOP.set()
        srv.server_close()
        runtime_lock.__exit__(None, None, None)
        print("数据根锁已释放")


if __name__ == "__main__":
    main()