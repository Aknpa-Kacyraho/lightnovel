#!/usr/bin/env python3
"""闭环回归：「读到哪，后台就翻到哪」。

前端行为（阅读页滚到接近底部时）：
  1. GET  /api/job?slug=     看后台有没有在翻
  2. POST /api/translate     请求翻接下来的章节
  3. 轮询 /api/job 直到 done
  4. GET  /api/next?from=N   取新译好的章节 HTML

⚠ 这个文件原来是个**手工脚本**，不是测试：
  · 它没有 sys.exit —— 打真实 8099 时一路 print，永远显示"通过"；
  · 它会真的调用 DeepSeek 翻一章，然后 sleep(5) 轮询最长 10 分钟；
  · 也就是说每次跑自检都在**花用户的钱和时间**。
现在改成真断言 + 真退出码，并跑在**桩 LLM** 上（见 run_selftests.py），
端到端覆盖同一条链路，token 成本为 0。

单独手工跑（对着已经在跑的服务）：
    python3 test_flow.py http://127.0.0.1:8099 <作品slug>
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
SLUG = sys.argv[2] if len(sys.argv) > 2 else "__flow_seed__"
_ROOT = (os.environ.get("LNTRANS_SERVER_ROOT")
         or os.environ.get("LNTRANS_DATA_ROOT") or os.getcwd())
fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def get(path, timeout=30):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post(path, payload, timeout=30):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


print("=" * 64)
print(f"A. 闭环：{SLUG}（读到哪翻到哪）")
print("=" * 64)

try:
    j = get(f"/api/job?slug={SLUG}")
except Exception as e:  # noqa: BLE001
    print(f"  ❌ /api/job 不可达：{type(e).__name__}: {e}")
    sys.exit(1)
check("1) 能查到后台任务状态", isinstance(j, dict) and "status" in j, str(j.get("status")))

before = get(f"/api/next?slug={SLUG}&from=1")
check("2) 能取到当前已译章节", "html" in before,
      f"HTML {len(before.get('html') or '')} 字，已译到第 {before.get('done')} 章")
_done0 = int(before.get("done") or 0)

r = post("/api/translate", {"slug": SLUG, "count": 2, "ceiling": 4,
                            "reason": "selftest"})
check("3) 触发翻译被接受", bool(r.get("ok")), str(r)[:120])

status, last = None, {}
_deadline = time.time() + 120          # 桩 LLM 很快；真模型才需要几分钟
while time.time() < _deadline:
    time.sleep(1)
    last = get(f"/api/job?slug={SLUG}")
    status = last.get("status")
    if status in ("done", "provider_error", "interrupted",
                  "budget_exhausted", "partial"):
        break
check("4) 任务跑完（不是卡在 running）", status == "done",
      f"status={status} msg={last.get('message')} err={last.get('error')}")
check("4b) 完成结果带持久 job_id 与完成章清单",
      bool(last.get("job_id"))
      and isinstance(last.get("completed_chapters"), list)
      and len(last.get("completed_chapters") or []) >= 1,
      str({k: last.get(k) for k in
           ("job_id", "completed_chapters", "remaining_chapters")}))
_done_ch = (last.get("completed_chapters") or [0])[0]
_sidecar = os.path.join(
    _ROOT, "novels", SLUG, "chapters", f"{int(_done_ch) - 1:04d}.meta.json")
try:
    with open(_sidecar, encoding="utf-8") as _f:
        _sm = json.load(_f)
except (OSError, json.JSONDecodeError):
    _sm = {}
check("4c) 已完成章节的旁车真实落盘",
      _sm.get("status") == "complete"
      and len(_sm.get("content_sha256") or "") == 64
      and (_sm.get("tokens") or {}).get("input", 0) >= 0,
      _sidecar)

after = get(f"/api/next?slug={SLUG}&from={_done0 + 1}")
check("5) 新译的章节真的取得到", int(after.get("added") or 0) > 0,
      f"新增 {after.get('added')} 章，HTML {len(after.get('html') or '')} 字，"
      f"总已译 {after.get('done')}")
check("6) 返回的是中文译文（没把日文原样抄回来）",
      any("\u4e00" <= c <= "\u9fff" for c in (after.get("html") or "")),
      (after.get("html") or "")[:60].replace("\n", " "))
check("7) 译文长度合理（不是空壳）", len(after.get("html") or "") > 50,
      f"{len(after.get('html') or '')} 字")

print()
print("=" * 64)
print("B. 停止：按钮名字就是承诺（停任务 + 关自动翻译）")
print("=" * 64)

_cfg0 = post("/api/transcfg", {"slug": SLUG}).get("cfg") or {}
post("/api/transcfg", {"slug": SLUG, "enabled": True})
_r = post("/api/translate", {"slug": SLUG, "count": 1, "ceiling": 8,
                             "reason": "selftest-stop"})
check("8) 停止前任务能入队", bool(_r.get("ok")), str(_r)[:100])
_s = post("/api/stop", {"slug": SLUG, "disable": True})
check("9) /api/stop 返回 cancelled", _s.get("status") == "cancelled", str(_s)[:100])
_j = get(f"/api/job?slug={SLUG}")
check("10) 停止后状态**仍是** cancelled（排队项不会把任务翻回 running）",
      _j.get("status") == "cancelled", f"status={_j.get('status')}")
_cfg1 = post("/api/transcfg", {"slug": SLUG}).get("cfg") or {}
check("11) 停止会关闭自动翻译（否则阅读页 tick 立刻再排一次 = 按钮骗人）",
      _cfg1.get("enabled") is False, json.dumps(_cfg1, ensure_ascii=False))
post("/api/transcfg", {"slug": SLUG, "enabled": bool(_cfg0.get("enabled", True))})

print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("✅ 闭环测试通过")
