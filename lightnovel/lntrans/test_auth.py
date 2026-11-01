#!/usr/bin/env python3
"""回归：局域网登录、会话、Host/Origin、CSRF 与限速。

边界：
  * 回环地址仍免登录；
  * 远端必须通过表单登录，网址里的 token 不再能直接换 Cookie；
  * Cookie 保存随机会话，不保存主口令；
  * 跨站写请求、伪造 Host、暴力登录和频繁开翻译都会被拒绝或限速。
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


if os.environ.get("LNTRANS_TEST_SERVER") != "1" or not os.environ.get("LNTRANS_DATA_ROOT"):
    print("✗ 拒绝运行：需要 LNTRANS_DATA_ROOT 隔离 + LNTRANS_TEST_SERVER=1")
    sys.exit(2)

_s = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
sv = importlib.util.module_from_spec(_s)
_s.loader.exec_module(sv)


print("=" * 66)
print("A. 纯判据：Host、Origin、会话、口令文件、限速")
print("=" * 66)
check("回环 127.0.0.1 / 127.0.0.5 / ::1 / localhost",
      all(sv._peer_is_loopback(x) for x in
          ("127.0.0.1", "127.0.0.5", "::1", "localhost")))
check("局域网 192.168.1.9 不是回环", not sv._peer_is_loopback("192.168.1.9"))
check("不需要口令时放行",
      sv.auth_verdict("192.168.1.9", False, "", None) is True)
check("远端无/错口令拒绝，正确口令放行",
      sv.auth_verdict("192.168.1.9", True, "abc", None) is False
      and sv.auth_verdict("192.168.1.9", True, "abc", "abd") is False
      and sv.auth_verdict("192.168.1.9", True, "abc", "abc") is True)
check("回环 peer + 回环 Host + 无代理头才免登录",
      sv.allow_without_auth("127.0.0.1", "127.0.0.1:8099")
      and sv.allow_without_auth("127.0.0.1", "localhost")
      and not sv.allow_without_auth("127.0.0.1", "ln.example.ts.net")
      and not sv.allow_without_auth("127.0.0.1", "127.0.0.1", True)
      and not sv.allow_without_auth("192.168.1.9", "127.0.0.1"))
check("回环 peer + 代理 Host：无口令必须拒绝（反代不能白拿）",
      sv.auth_verdict("127.0.0.1", True, "abc", None,
                      host="ln.example.ts.net") is False)
check("回环 peer + 回环 Host：本机浏览器免登录",
      sv.auth_verdict("127.0.0.1", True, "abc", None,
                      host="127.0.0.1:8099") is True)
check("--require-auth（allow_local=False）时回环也要口令",
      sv.auth_verdict("127.0.0.1", True, "abc", None,
                      host="127.0.0.1", allow_local=False) is False)
check("外部 Host 白名单 / 非回环绑定会要求口令",
      sv.auth_required_for("127.0.0.1", {"ln.example.ts.net"})
      and sv.auth_required_for("0.0.0.0", set())
      and not sv.auth_required_for("127.0.0.1", {"127.0.0.1"})
      and not sv.auth_required_for("127.0.0.1", set()))
check("_token_ok 对 None/非字符串不抛",
      sv._token_ok(None, "x") is False and sv._token_ok(123, "123") is True)
check("内联 JSON 不会让 </script> 提前闭合",
      "</script>" not in sv._js_json("</script>")
      and "<\\/script>" in sv._js_json("</script>"))

allowed = {"localhost", "192.168.1.8", "reader.local"}
check("Host 白名单接受域名/IPv4 与端口",
      sv.host_verdict("192.168.1.8:8099", allowed)
      and sv.host_verdict("reader.local:8099", allowed))
check("Host 白名单拒绝 DNS rebinding 域名",
      not sv.host_verdict("evil.example:8099", allowed))
check("同源 Origin 通过，跨站/空 Origin 拒绝",
      sv.same_origin("http://192.168.1.8:8099", "192.168.1.8:8099")
      and not sv.same_origin("http://evil.example:8099", "192.168.1.8:8099")
      and not sv.same_origin("null", "192.168.1.8:8099")
      and not sv.same_origin("http://192.168.1.8:bad", "192.168.1.8:8099"))
check("Sec-Fetch-Site: cross-site 拒绝写请求",
      not sv.origin_verdict("", "192.168.1.8:8099", "cross-site"))
check("无 Origin 的非浏览器客户端仍可用",
      sv.origin_verdict("", "192.168.1.8:8099", ""))
check("登录后跳转只允许站内路径",
      sv._safe_next("/read/book?from=2") == "/read/book?from=2"
      and sv._safe_next("//evil.example/") == "/"
      and sv._safe_next("https://evil.example/") == "/"
      and sv._safe_next("/ok\r\nLocation: x") == "/")

env_token, env_source = sv.load_access_token("env-token", "")
check("口令优先读环境变量", env_token == "env-token" and "LNTRANS_TOKEN" in env_source)
check("空白口令文件路径不会误读当前目录",
      sv.load_access_token("", "   ") == ("", ""))
_tf = tempfile.NamedTemporaryFile(
    mode="w", encoding="utf-8", delete=False, suffix=".token")
_tf.write("file-token\n")
_tf.close()
try:
    file_token, file_source = sv.load_access_token("", _tf.name)
    check("口令文件支持固定口令",
          file_token == "file-token" and _tf.name in file_source)
finally:
    os.remove(_tf.name)

sv.clear_auth_state()
_sid = sv.issue_session()
check("浏览器会话是随机值且不等于主口令",
      bool(_sid) and _sid != "master-password" and len(_sid) >= 32)
check("会话有效，注销后立即失效",
      sv.session_valid(_sid)
      and (sv.revoke_session(_sid) is None)
      and not sv.session_valid(_sid))

sv.clear_auth_state()
check("登录失败达到阈值后给出重试时间",
      sv._rate_retry("login", "peer", 2, 60) == 0
      and (sv._rate_hit("login", "peer", 60) is None)
      and sv._rate_retry("login", "peer", 2, 60) == 0
      and (sv._rate_hit("login", "peer", 60) is None)
      and sv._rate_retry("login", "peer", 2, 60) > 0)


print("=" * 66)
print("B. 端到端：远端登录、Cookie、Host/Origin、安全头")
print("=" * 66)
TOKEN = "s3cr3t-master-token"


class RemoteHandler(sv.Handler):
    """把对端伪装成局域网地址；本机回环连接走不到远端鉴权分支。"""

    def setup(self):
        super().setup()
        self.client_address = ("192.168.7.7", 40000)


def start(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, int(srv.server_address[1])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(NoRedirect)


def fetch(url, *, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    opener = _opener if data is not None else urllib.request.build_opener()
    try:
        with opener.open(req, timeout=5) as r:
            # 保留 HTTPMessage 而不是 dict：登录要同时种两个 Set-Cookie，
            # dict 会把它们合成一个，测试就看不见设备凭据了。
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def login(base, token, next_path="/"):
    body = urllib.parse.urlencode(
        {"token": token, "next": next_path}).encode("utf-8")
    return fetch(
        base + "/login",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": base,
        },
    )


sv.AUTH_REQUIRED = True
sv.AUTH_TOKEN = TOKEN
sv.clear_auth_state()
srv, port = start(RemoteHandler)
base = f"http://127.0.0.1:{port}"
try:
    code, hdr, body = fetch(base + "/api/net")
    check("远端无会话 → 401", code == 401, f"得到 {code}")
    check("401 也带安全响应头",
          "Content-Security-Policy" in hdr
          and hdr.get("X-Frame-Options") == "DENY"
          and hdr.get("Referrer-Policy") == "no-referrer"
          and hdr.get("X-Content-Type-Options") == "nosniff")

    code, hdr, body = fetch(base + "/?token=" + urllib.parse.quote(TOKEN))
    check("网址 query token 不再能登录",
          code == 401 and "Set-Cookie" not in hdr, f"得到 {code}")
    check("未登录首页显示表单登录页",
          "登录轻小说书架" in body.decode("utf-8", "replace")
          and "action=\"/login\"" in body.decode("utf-8", "replace"))

    code, hdr, body = login(base, "wrong")
    check("错误口令登录 → 401", code == 401, f"得到 {code}")

    code, hdr, body = login(base, TOKEN)
    scs = hdr.get_all("Set-Cookie") or []
    sc_session = next((c for c in scs if c.startswith("ln_session=")), "")
    sc_device = next((c for c in scs if c.startswith("ln_device=")), "")
    check("正确口令 → 303 并种会话 Cookie", code == 303 and bool(sc_session),
          f"得到 {code} {str(scs)[:80]}")
    check("Cookie 是随机会话而非主口令",
          all(TOKEN not in c and "ln_token=" not in c for c in scs))
    check("会话 Cookie 为 HttpOnly + SameSite=Lax",
          "HttpOnly" in sc_session and "SameSite=Lax" in sc_session)
    check("登录同时种「记住这台电脑」凭据",
          bool(sc_device) and "HttpOnly" in sc_device
          and "Max-Age=" in sc_device and TOKEN not in sc_device,
          sc_device[:60])
    cookie = sc_session.split(";", 1)[0]
    device_cookie = sc_device.split(";", 1)[0]

    code, hdr, body = fetch(base + "/api/net", headers={"Cookie": cookie})
    payload = json.loads(body.decode("utf-8"))
    check("会话 Cookie 可继续访问", code == 200, f"得到 {code}")
    check("页面 API 不再返回带口令的网址",
          TOKEN not in body.decode("utf-8")
          and all("?token=" not in u for u in payload.get("urls") or [])
          and payload.get("auth_required") is True)
    check("200 响应带安全头",
          "Content-Security-Policy" in hdr
          and hdr.get("Cross-Origin-Opener-Policy") == "same-origin"
          and hdr.get("X-Permitted-Cross-Domain-Policies") == "none")

    code, _, _ = fetch(base + "/api/net",
                       headers={"Cookie": f"ln_token={TOKEN}"})
    check("旧 ln_token 主口令 Cookie 已失效", code == 401, f"得到 {code}")
    code, _, _ = fetch(base + "/api/net",
                       headers={"Authorization": f"Bearer {TOKEN}"})
    check("API 客户端 Bearer 主口令仍可用", code == 200, f"得到 {code}")

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/api/net", headers={"Host": "evil.example"})
    res = conn.getresponse()
    res.read()
    check("伪造 Host（DNS rebinding）→ 400", res.status == 400, f"得到 {res.status}")
    conn.close()

    evil_body = json.dumps({"slug": "book", "chapter": 1}).encode()
    code, _, _ = fetch(
        base + "/api/progress",
        data=evil_body,
        headers={
            "Cookie": cookie,
            "Origin": "http://evil.example",
            "Content-Type": "application/json",
        },
    )
    check("跨站 Origin 写请求 → 403", code == 403, f"得到 {code}")
    code, _, _ = fetch(
        base + "/api/progress",
        data=evil_body,
        headers={
            "Cookie": cookie,
            "Origin": base,
            "Content-Type": "application/json",
        },
    )
    check("同源写请求仍正常处理", code == 200, f"得到 {code}")

    def seed_rate_book(slug):
        d = os.path.join(sv.NOVELS, slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({
                "work_id": slug, "slug": slug, "title": slug,
                "source_id": slug, "episodes": [{"id": "1", "title": "第一话"}],
                "progress": {"translated_through": 0, "fetched_through": 1},
                "glossary": {}, "characters": {}, "style": {},
            }, f, ensure_ascii=False)

    seed_rate_book("rate-book-a")
    seed_rate_book("rate-book-b")
    _orig_start_job = sv.start_job
    sv.start_job = lambda *_a, **_k: {"ok": True, "status": "queued"}
    sv.TRANSLATE_RATE_LIMIT = 1
    sv.TRANSLATE_RATE_WINDOW = 60
    try:
        tr_headers = {
            "Cookie": cookie, "Origin": base, "Content-Type": "application/json",
        }
        code1, _, _ = fetch(
            base + "/api/translate",
            data=json.dumps({"slug": "rate-book-a", "count": 1}).encode(),
            headers=tr_headers,
        )
        code2, hdr2, _ = fetch(
            base + "/api/translate",
            data=json.dumps({"slug": "rate-book-b", "count": 1}).encode(),
            headers=tr_headers,
        )
        check("翻译启动超过频率上限 → 429",
              code1 == 200 and code2 == 429
              and int(hdr2.get("Retry-After") or 0) > 0,
              f"{code1}/{code2}")
    finally:
        sv.start_job = _orig_start_job

    sv.clear_auth_state()
    sv.LOGIN_FAIL_LIMIT = 2
    sv.LOGIN_FAIL_WINDOW = 60
    check("第一次错口令 401", login(base, "bad-1")[0] == 401)
    check("第二次错口令 401", login(base, "bad-2")[0] == 401)
    code, hdr, _ = login(base, TOKEN)
    check("连续失败后即使口令正确也先限速",
          code == 429 and int(hdr.get("Retry-After") or 0) > 0,
          f"得到 {code}")
finally:
    srv.shutdown()
    srv.server_close()


print("=" * 66)
print("C. 重启后免输口令；退出本设备后失效；回环仍免登录")
print("=" * 66)
sv.clear_auth_state()
srv, port = start(RemoteHandler)
base = f"http://127.0.0.1:{port}"
try:
    code, hdr, _ = login(base, TOKEN)
    scs = hdr.get_all("Set-Cookie") or []
    cookie = next(c for c in scs if c.startswith("ln_session=")).split(";", 1)[0]
    device_cookie = next(c for c in scs if c.startswith("ln_device=")).split(";", 1)[0]

    # 模拟服务重启：内存里的会话全部清空，磁盘上的设备凭据还在。
    sv.clear_auth_state()
    code, _, _ = fetch(base + "/api/net", headers={"Cookie": cookie})
    check("重启后旧会话确实失效（模拟成立）", code == 401, f"得到 {code}")
    code, _, _ = fetch(base + "/api/net", headers={"Cookie": device_cookie})
    check("重启后只凭「记住的电脑」直接进入", code == 200, f"得到 {code}")

    code, hdr, _ = fetch(
        base + "/logout",
        data=b"",
        headers={
            "Cookie": device_cookie,
            "Origin": base,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    clears = hdr.get_all("Set-Cookie") or []
    check("退出返回 303，并同时清除会话与设备凭据",
          code == 303
          and any(c.startswith("ln_session=;") and "Max-Age=0" in c for c in clears)
          and any(c.startswith("ln_device=;") and "Max-Age=0" in c for c in clears),
          f"得到 {code} {str(clears)[:80]}")
    code, _, _ = fetch(base + "/api/net", headers={"Cookie": device_cookie})
    check("退出后设备凭据立即失效", code == 401, f"得到 {code}")
finally:
    srv.shutdown()
    srv.server_close()

srv2, port2 = start(sv.Handler)
try:
    code, _, _ = fetch(f"http://127.0.0.1:{port2}/api/net")
    check("回环 peer + 回环 Host 在 AUTH_REQUIRED=True 时仍免登录",
          code == 200, f"得到 {code}")
finally:
    srv2.shutdown()
    srv2.server_close()

# 反代场景：peer 仍是 127.0.0.1，但 Host 是外部域名且在白名单里。
# 旧实现只看 peer → 无口令 200；修复后必须 401。
_old_hosts = os.environ.get("LNTRANS_ALLOWED_HOSTS")
os.environ["LNTRANS_ALLOWED_HOSTS"] = "ln.example.ts.net"
sv._HOST_NAMES_CACHE = (0.0, set())
sv.AUTH_REQUIRED = True
sv.AUTH_TOKEN = TOKEN
sv.AUTH_LOCAL_BYPASS = True
srv3, port3 = start(sv.Handler)
try:
    def raw_get(headers):
        c = http.client.HTTPConnection("127.0.0.1", port3, timeout=5)
        c.request("GET", "/api/net", headers=headers)
        r = c.getresponse()
        r.read()
        c.close()
        return r.status

    check("反代 Host + 回环 peer：无口令 401", raw_get(
        {"Host": "ln.example.ts.net"}) == 401)
    check("反代 Host + 带口令 200", raw_get(
        {"Host": "ln.example.ts.net",
         "Authorization": f"Bearer {TOKEN}"}) == 200)
    check("回环 Host 的本机请求仍 200", raw_get(
        {"Host": f"127.0.0.1:{port3}"}) == 200)
    check("回环 Host + 代理头：不再当成本机", raw_get(
        {"Host": f"127.0.0.1:{port3}",
         "X-Forwarded-For": "203.0.113.7"}) == 401)
finally:
    srv3.shutdown()
    srv3.server_close()
    if _old_hosts is None:
        os.environ.pop("LNTRANS_ALLOWED_HOSTS", None)
    else:
        os.environ["LNTRANS_ALLOWED_HOSTS"] = _old_hosts
    sv._HOST_NAMES_CACHE = (0.0, set())


print()
_all = not fails
print("回归结果：", "全部通过 ✅" if _all else f"仍有失败 ❌ {fails}")
if not _all:
    sys.exit(1)
