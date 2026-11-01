#!/usr/bin/env python3
"""翻译调度（lnsched）回归：谁该被翻、翻多久、花多少。

这一层独立于翻译本身（不调模型、不写章节），所以能用纯函数式的断言把
"在读持续翻 / 翻译列表 / 空闲停 / 预算停 / 暂停"全部钉死。
上一版把策略写在 worker 里，只能靠真实翻译验证 —— 改一次等于烧一次钱。
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BASE = sys.argv[1] if len(sys.argv) > 1 else ""

_s = importlib.util.spec_from_file_location("lnsched", os.path.join(HERE, "lnsched.py"))
sch_mod = importlib.util.module_from_spec(_s)
sys.argv = ["lnsched"]
_s.loader.exec_module(sch_mod)

fails = []
TMP = tempfile.mkdtemp(prefix="lnsched-test-")


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


clock = {"t": 1_000_000.0}
S = sch_mod.Scheduler(os.path.join(TMP, "sched.json"), now=lambda: clock["t"])
MISSING = {"a": [3, 4, 5], "b": [1, 2], "c": []}


def missing(slug):
    return list(MISSING.get(slug, []))


print("=" * 66)
print("1. 在读的书：一直翻，没有「读到 + N 章」上限")
print("=" * 66)
S.note_read("a")
act = S.pick(missing)
check("在读的书会被选中", act and act.slug == "a" and act.reason == "reading", str(act))
check("没在读、没排队的书一概不翻（不白花钱）", S.pick(lambda s: [1]) is None
      or S.pick(lambda s: [1]).slug in ("a",), "")

print()
print("=" * 66)
print("2. 空闲超时：读者走了就停")
print("=" * 66)
clock["t"] += 31 * 60
check("超过空闲时间不再翻这本书", S.pick(missing) is None)

print()
print("=" * 66)
print("3. 翻译列表：显式加入按顺序翻，与在读无关")
print("=" * 66)
S.enqueue("b")
act = S.pick(missing)
check("排队中的书被翻", act and act.slug == "b" and act.reason == "queue", str(act))
S.enqueue("a")
S.dequeue("b")
S.enqueue("b")
rows = [(r["slug"], r["order"]) for r in S.view(lambda s: 0, lambda s: 10)["rows"]]
check("队列按加入顺序（先入先翻）", rows and rows[0][0] == "a", str(rows))

print()
print("=" * 66)
print("4. 全书译完 → 记 done 并移出队列，不再每轮扫它")
print("=" * 66)
S4 = sch_mod.Scheduler(os.path.join(TMP, "s4.json"), now=lambda: clock["t"])
S4.enqueue("c")
act = S4.pick(missing)
check("已译完的书不返回任务", act is None, str(act))
check("已译完的书被移出队列", not (S4.state["books"]["c"].get("queued_at")))

print()
print("=" * 66)
print("5. 暂停与全局预算")
print("=" * 66)
S.note_read("a")
S.set_paused("a", True)
check("暂停的书不翻", (S.pick(missing) or sch_mod.Action("", "", 0)).slug != "a")
S.set_paused("a", False)
S.set_budget(100)
S.add_usage(60)
check("预算未超时能翻", not S.over_budget() and S.budget_left() == 40)
S.add_usage(50)
check("超预算只是提醒（不会因此停掉在读的书）",
      S.over_budget() and (S.pick(missing) is not None))
S.pause_all(True)
S.set_budget(1000)
check("全局暂停时谁都不翻", S.pick(missing) is None)
S.pause_all(False)
S.set_budget(0)
check("预算 0 = 不限（over_budget 永远为假）", not S.over_budget())

S.set_budget(1000)
S.state["used_today"] = 0
S.add_usage(500, cost=0)
check("本地模型 0 元不计入 token 预算", S.state["used_today"] == 0,
      str(S.state["used_today"]))
S.add_usage(500, cost=0.001)
check("云端有费用才计入 token 预算", S.state["used_today"] == 500,
      str(S.state["used_today"]))
S.state["used_today"] = 0
S.set_budget(100)

print()
print("=" * 66)
print("6. 跨天预算归零（按本地日期）")
print("=" * 66)
S.set_budget(100)
S.add_usage(100)
check("用满预算后 over_budget 为真（仅提醒）", S.over_budget())
clock["t"] += 24 * 3600
S.budget_left()          # 触发跨天结算
check("跨天后用量归零", S.state["used_today"] == 0 and not S.over_budget())

print()
print("=" * 66)
print("7. 持久化：重启后队列/预算/暂停都还在")
print("=" * 66)
S.note_read("a")
S.add_usage(7)
S.save()
S2 = sch_mod.Scheduler(os.path.join(TMP, "sched.json"), now=lambda: clock["t"])
check("重启后仍在翻 a", (S2.pick(missing) or sch_mod.Action("", "", 0)).slug == "a")
check("重启后今日用量保留", S2.state["used_today"] == 7, str(S2.state["used_today"]))
check("重启后预算保留", S2.state["daily_budget"] == 100)

print()
print("=" * 66)
print("8. 坏状态文件不能让服务起不来")
print("=" * 66)
bad = os.path.join(TMP, "bad.json")
with open(bad, "w", encoding="utf-8") as f:
    f.write("{not json")
S3 = sch_mod.Scheduler(bad, now=lambda: clock["t"])
check("坏 JSON → 用默认状态启动（不抛异常）",
      S3.state["daily_budget"] == sch_mod.DEFAULT_BUDGET)

print()
print("=" * 66)
print("9. HTTP 层：/queue 页面与 /api/queue 操作")
print("=" * 66)


def post(path, payload):
    req = urllib.request.Request(
        BASE.rstrip("/") + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # 409/429 也是"正常回答"（预算用尽、需要恢复、限流），接口会带 JSON body。
        try:
            return json.loads(e.read())
        except Exception:  # noqa: BLE001
            return {"ok": False, "http": e.code}


def get(path):
    with urllib.request.urlopen(BASE.rstrip("/") + path, timeout=15) as r:
        return r.status, r.read()


if BASE:
    st, body = get("/queue")
    page = body.decode("utf-8", "replace")
    check("翻译列表页面 200", st == 200)
    check("页面说明了新模型（在读一直翻 / 也能提前攒书）",
          "读就一直翻" in page and "提前翻" in page and "翻译列表" in page)
    check("翻译列表有统计卡 / 总进度（不只是几行字）",
          'data-ui-queue' in page and 'ui-queue-summary' in page
          and 'ui-qstat' in page)
    check("预算口径写清「本地不计 token」",
          "本地模型 0 元，不计入 token" in page and "今日云端已用" in page)
    slug = "__flow_seed__"          # 运行器在服务端数据根建的闭环种子书
    r = post("/api/queue", {"action": "add", "slug": slug})
    check("加入翻译列表", bool(r.get("ok")))
    # 注意：这本书可能同时"在读"（前面的测试打开过它），而 candidates() 里
    # 在读优先于队列 —— 判定要看 queued 标志，不能只看 reason。
    row = next((x for x in r.get("rows", []) if x["slug"] == slug), None)
    check("加入后出现在列表里且带队列身份",
          bool(row and row.get("queued")), str(row))
    _st2, _body2 = get("/queue")
    check("书进列表后按组显示（正在读 / 队列 / 暂停）",
          'ui-queue-group' in _body2.decode("utf-8", "replace"))
    r = post("/api/queue", {"action": "pause", "slug": slug})
    paused = {x["slug"] for x in r.get("paused_rows", [])}
    check("暂停后进入已暂停组（不再花钱）", slug in paused, str(paused))
    r = post("/api/queue", {"action": "resume", "slug": slug})
    rows = {x["slug"] for x in r.get("paused_rows", [])}
    check("继续后不再处于暂停组", slug not in rows, str(rows))
    r = post("/api/queue", {"action": "budget", "tokens": 12345})
    check("每日预算可设置", r.get("budget") == 12345, str(r.get("budget")))
    r = post("/api/queue", {"action": "pause_all", "paused": True})
    check("全局暂停开关生效", r.get("paused") is True)
    post("/api/queue", {"action": "pause_all", "paused": False})
    r = post("/api/queue", {"action": "remove", "slug": slug})
    # 移出的是"队列"身份；如果这本书正好在读，它仍会以"在读"继续翻（设计如此）。
    queued = {x["slug"] for x in r.get("rows", []) if x["reason"] == "queue"}
    check("移出队列（不再按队列顺序翻它）", slug not in queued, str(queued))
    r = post("/api/queue", {"action": "add", "slug": "__no_such_book__"})
    check("不存在的书不能加入（不造脏状态）", not r.get("ok"))

    # 预算用尽：自动请求（阅读页 tick）必须被挡住，否则"预算"形同虚设；
    # 但显式请求（resume/手动翻到第 N 章）是用户此刻的意图，不能自锁。
    post("/api/queue", {"action": "budget", "tokens": 1})
    r = post("/api/translate", {"slug": slug, "count": 1, "reason": "reader",
                                "after": 1})
    check("超预算不会挡住自动翻译（预算是提醒不是刹车）",
          not r.get("budget_exhausted"), str(r)[:120])
    post("/api/queue", {"action": "budget", "tokens": 12345})

    # 「移出队列」必须真的把书移出列表：只 dequeue 的话，一本"在读"的书
    # 仍旧留在页面上（用户报过「移除队列没用」）。forget 要连在读/暂停一起清。
    post("/api/queue", {"action": "add", "slug": slug})
    post("/api/queue", {"action": "pause", "slug": slug})
    r = post("/api/queue", {"action": "forget", "slug": slug})
    _st, _body = get("/api/queue")
    q = json.loads(_body)
    _all = (q.get("rows") or []) + (q.get("paused_rows") or [])
    check("forget 把书从翻译列表彻底移出（在读/队列/暂停都清）",
          all(x.get("slug") != slug for x in _all), str(q)[:200])
else:
    print("  ⚠ HTTP 层跳过（没有隔离测试服务）")

print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    print(f"保留现场：{TMP}")
    sys.exit(1)
shutil.rmtree(TMP, ignore_errors=True)
print("✅ 调度逻辑全部通过")
