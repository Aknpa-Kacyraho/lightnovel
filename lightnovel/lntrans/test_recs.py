#!/usr/bin/env python3
"""回归：「换一批」真的换了 + 「重新抓取」异步带进度 + 局域网地址。

**为什么必须有这个测试**（用户原话："为什么点了换一批没用。等了很久网页不刷新"）：

原来那个按钮叫「换一批（重新抓取）」，做的事是**用同一组关键词重打一次源站**。
同一个关键词集合抓回来必然是同一批书、同一个排序 —— 实测重抓一次拿到的
12 本和分数一字不差（25.5/25.2/24.8/…）。所以用户等了将近两分钟，
页面刷新后**一模一样**。这不是"慢"，是**语义错了**：
把"给我看点别的"实现成了"再算一遍同样的东西"。
"等了很久不刷新"是第二个 bug：整个抓取是一个同步 HTTP 请求，
全程页面零反馈，而文案还写着"约 1 分钟"（实测 1 分 53 秒）。

所以这里断言的是**行为**，不是代码长什么样：
  1. 换一批之后，页面上渲染的书**和换之前一本都不重复**；
  2. 换一批**不更新** at/新鲜度（否则「缓存较旧」永远不出现 = 骗人）；
  3. 缓存只有一屏时，换一批会**自动从书库补货**，而不是原地打转；
  4. 「重新抓取」立刻返回（异步）+ 进度可查 + 不会叠第二个任务；
  5. 书库条目字段名要映射对（points→review_points）——
     映射错了不会报错，只会**静默返回空表**，看起来像"书库没合适的书"。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("LNTRANS_DATA_ROOT") or HERE
PROF_DIR = os.environ.get("LNTRANS_LNFINDER") or os.path.join(
    os.path.dirname(HERE), "lnfinder")
ISOLATED = os.environ.get("LNTRANS_TEST_SERVER") == "1"
fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def get(path: str) -> str:
    with urllib.request.urlopen(BASE + path, timeout=90) as r:
        return r.read().decode("utf-8")


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def rec_ids(html: str) -> list:
    """页面上推荐位里**真正渲染出来**的书（按出现顺序）。"""
    m = re.search(r"为你推荐(.*?)</details>", html, re.S)
    seg = m.group(1) if m else ""
    return re.findall(r'class="card rec" data-rid="([^"]+)"', seg)


# ============================================================
print("=" * 64)
print("A. 离线：window / rotate / topup / rank_library 的语义")
print("=" * 64)

_spec = importlib.util.spec_from_file_location(
    "lnrecs", os.path.join(HERE, "lnrecs.py"))
recs = importlib.util.module_from_spec(_spec)
sys.argv = ["lnrecs"]
_spec.loader.exec_module(recs)

# 这个测试进程的数据根是**空的**（runner 给每个测试单独一个根）。
# 不自己造料，断言就会"通过"但什么都没验证 —— 那是最坏的一种绿。
_prof = {}
try:
    with open(os.path.join(PROF_DIR, "taste_profile.json"), encoding="utf-8") as _f:
        _prof = json.load(_f)
except OSError:
    pass
_tw = _prof.get("tag_weights") or {}
_blocked = set(_prof.get("blocked_tags") or [])
_pool = [t for t, _w in sorted(_tw.items(), key=lambda kv: -kv[1])
         if t not in _blocked]
check("A0 前置条件：画像里有可用标签（没有就没法验证推荐，不能假绿）",
      len(_pool) >= 2, f"tag_weights {len(_tw)} 项，可用 {len(_pool)}")
if len(_pool) < 2:
    print("❌ 画像里没有标签，本测试无法验证任何东西")
    sys.exit(1)

_tags = _pool[:3]
_N = 30          # 30 本 → 3 屏（RECS_PAGE=12），够验证轮换
_lib, _items = {}, []
for i in range(_N):
    wid = "l%02d" % i
    _lib[wid] = {"id": wid, "title": "测试书 %02d" % i, "author": "作者%d" % i,
                 "url": "https://kakuyomu.jp/works/" + wid,
                 "tags": list(_tags), "genre": "テスト",
                 "episodes": 40, "characters": 90000, "points": 5000,
                 "updated": "2099-01-01", "sources": ["测试"]}
    # 缓存顺序就是打分顺序（l00 最高）→ 第 1 屏 l00..l11，第 2 屏 l12..l23
    _items.append(dict(_lib[wid], score=100 - i, hits=list(_tags),
                       reasons=[], origins=["测试"]))
# 一本被"不感兴趣"隐藏的书：本地补货也不许把它捞回来
_lib["hid1"] = {"id": "hid1", "title": "已隐藏", "author": "x",
                "url": "https://kakuyomu.jp/works/hid1", "tags": list(_tags),
                "genre": "テスト", "episodes": 40, "characters": 90000,
                "points": 5000, "updated": "2099-01-01", "hidden": True,
                "sources": ["测试"]}
_items.append(dict(_lib["hid1"], score=99, hits=list(_tags),
                   reasons=[], origins=["测试"]))
os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
with open(os.path.join(ROOT, "data", "library.json"), "w", encoding="utf-8") as f:
    json.dump(_lib, f, ensure_ascii=False)
_AT = 1000000000.0        # 一个明显"很旧"的时间戳，用来验证换一批不动它
with open(os.path.join(ROOT, "data", "recs.json"), "w", encoding="utf-8") as f:
    json.dump({"at": _AT, "items": _items}, f, ensure_ascii=False)

_win0 = recs.window()
check("A1 window() 三个数自洽（0 <= start <= end <= total）",
      0 <= _win0["start"] <= _win0["end"] <= _win0["total"],
      f"start={_win0['start']} end={_win0['end']} total={_win0['total']}")
check("A2 window().items 条数 == end-start（数字不许骗人）",
      len(_win0["items"]) == _win0["end"] - _win0["start"],
      f"{len(_win0['items'])} vs {_win0['end'] - _win0['start']}")
check("A2b 已隐藏的书不在候选里（隐藏 = 别再推给我）",
      all(str(it.get("id")) != "hid1" for it in _win0["items"]) and
      _win0["total"] == _N, f"total={_win0['total']} 期望 {_N}")

_page1 = [str(it.get("id")) for it in _win0["items"]]
_r1 = recs.rotate()
_page2 = [str(it.get("id")) for it in recs.window()["items"]]
check("A3 rotate() 成功且候选不止一屏（一屏的话「换一批」没有意义）",
      _r1.get("ok") is True and _r1.get("total", 0) > recs.RECS_PAGE,
      json.dumps(_r1, ensure_ascii=False))
check("★ A4 换一批之后是新的一批：第 2 屏与第 1 屏**零重复**（bug 本体）",
      bool(_page2) and not (set(_page2) & set(_page1)),
      f"第1屏 {len(_page1)} 本 / 第2屏 {len(_page2)} 本 / 交集 {len(set(_page2) & set(_page1))}")
check("A5 第 2 屏起点正好往后挪一屏",
      recs.window()["start"] == _win0["start"] + recs.RECS_PAGE,
      f"start={recs.window()['start']}")
check("★ A6 换一批**不刷新** at（否则「缓存较旧」永远不显示 = 骗人）",
      recs._load_cache().get("at", 0) == _AT,
      f"at {recs._load_cache().get('at', 0)}（期望 {_AT}）")

# 翻满一圈：每个起点都不同，最后回到第 1 屏，而且**每本书恰好出现一次**。
# （total 不是页大小整数倍时，"加一屏再取模"会让两屏重叠 ——
#   用户看到的就是"换了一批怎么还有刚才那几本"，和原 bug 同一种观感。）
_c = recs._load_cache()
_c.pop("cursor", None)
recs._save_raw(_c)
_n_pages = max(1, (_r1["total"] + recs.RECS_PAGE - 1) // recs.RECS_PAGE)
_seen, _all_ids = [], []
for _ in range(_n_pages):
    _seen.append(recs.window()["start"])
    _all_ids += [str(it.get("id")) for it in recs.window()["items"]]
    recs.rotate()
check("A7 翻满一圈：起点序列刚好是每一屏且回到开头",
      len(_seen) == len(set(_seen)) == _n_pages and recs.window()["start"] == 0,
      f"起点序列 {_seen}（共 {_n_pages} 屏）")
check("★ A7b 轮完一圈，候选里每本书**恰好出现一次**（页与页之间不许重叠）",
      len(_all_ids) == len(set(_all_ids)) == _r1["total"],
      f"轮完 {len(_all_ids)} 本 / 去重 {len(set(_all_ids))} / 候选共 {_r1['total']} 本")

# 缓存只有一屏时（比如刚抓完 12 本）：必须从书库补货，不能原地打转；
# 而且补货换了榜单后不能给"和刚才一样"的那一屏（否则又是"点了没用"的观感）。
_saved = recs._load_cache()
try:
    _old = _saved.get("items", [])[:3]
    recs._save_raw({"at": _AT, "items": _old, "cursor": None})
    _old_ids = {str(it.get("id")) for it in recs.window()["items"]}
    _r2 = recs.rotate()
    _new_ids = {str(it.get("id")) for it in recs.window()["items"]}
    check("★ A8 缓存只有一屏时，换一批自动从书库补货（不再原地打转）",
          _r2.get("ok") is True and _r2.get("total", 0) > recs.RECS_PAGE,
          f"书库 {len(_lib) - 1} 本 → 换出 {_r2.get('total')} 本候选")
    check("★ A8b 补货换榜单后给的那一屏，和刚才那屏**零重复**（不许拿旧书充数）",
          bool(_new_ids) and not (_new_ids & _old_ids),
          f"刚才 {len(_old_ids)} 本 / 换后 {len(_new_ids)} 本 / 交集 {len(_new_ids & _old_ids)}")
finally:
    recs._save_raw(_saved)

# 书库里全是隐藏书 → 如实说"没有"，不许假装换成功
_saved_lib = recs._load_lib
try:
    recs._save_raw({"at": _AT, "items": []})
    recs._load_lib = lambda: {"hid1": dict(_lib["hid1"])}
    _r3 = recs.rotate()
    check("A9 没有料时 rotate 如实返回 ok=False（不许假装换成功）",
          _r3.get("ok") is False and _r3.get("reason") == "empty",
          json.dumps(_r3, ensure_ascii=False))
finally:
    recs._load_lib = _saved_lib
    recs._save_raw(_saved)

# 字段映射：书库叫 points/updated，打分器读 review_points/last_episode_at。
# 不映射会**静默返回空表**（每本都判"评价点不足"），比报错难查得多。
_w = recs._work_from_lib("x", {"points": 4321, "updated": "2026-01-02",
                               "episodes": 9, "tags": list(_tags)})
check("★ A10 书库条目字段名映射正确（错了只会静默返回空表）",
      _w.get("review_points") == 4321 and _w.get("last_episode_at") == "2026-01-02",
      json.dumps(_w, ensure_ascii=False))
_ranked = recs.rank_library()
check("A11 rank_library 排得出结果，且不把隐藏的书捞回来",
      len(_ranked) > 0 and "hid1" not in {str(it.get("id")) for it in _ranked},
      f"{len(_ranked)} 本，隐藏 1 本")
check("A12 rank_library 的字段名和 refresh 写出来的一致（两条路径同一种卡片）",
      all({"id", "title", "url", "tags", "genre", "points", "updated",
           "score", "hits"} <= set(it) for it in _ranked[:5]),
      json.dumps(_ranked[0], ensure_ascii=False)[:120] if _ranked else "")

# 异步 + 进度 + 不重复叠任务（打桩，不碰网络）
_saved_refresh = recs.refresh


def _fake_refresh(top=recs.RECS_STORE, queries=None):
    recs.SCAN.update(running=True, done=0, total=2, found=0, error="",
                     started=time.time(), ended=0.0)
    time.sleep(0.4)
    recs.SCAN.update(done=1, found=7)
    time.sleep(0.4)
    recs.SCAN.update(running=False, ended=time.time())
    return []


try:
    recs.refresh = _fake_refresh
    recs.SCAN.update(running=False)
    _first = recs.refresh_async()
    _second = recs.refresh_async()
    check("★ A13 抓取中再点一次不会叠第二个任务（不重复打源站）",
          _first is True and _second is False, f"{_first} {_second}")
    _st = recs.scan_state()
    check("A14 scan_state() 有 running/done/total 供前端显示进度",
          {"running", "done", "total", "found", "error"} <= set(_st),
          json.dumps({k: _st[k] for k in ("running", "done", "total")}))
    _deadline = time.time() + 10
    while recs.scan_state()["running"] and time.time() < _deadline:
        time.sleep(0.1)
    check("A15 抓完 running 归 False（否则前端永远转圈）",
          recs.scan_state()["running"] is False)
finally:
    recs.refresh = _saved_refresh
    recs.SCAN.update(running=False)

_n_q = len(recs._load_lnfind().DEFAULT_SCAN_QUERIES)
_note = recs.scan_q_note()
_note_m = re.search(r"约 (\d+) 分钟", _note)
check("A16 耗时说明里的关键词数和分钟数都算自真实值（不再写死「约 1 分钟」）",
      f"{_n_q} 个关键词" in _note and "榜单/推荐源" in _note
      and bool(_note_m)
      and int(_note_m.group(1)) >= max(1, round(_n_q * 5.7 / 60)),
      _note)

# 外部设备登记（局域网模式下"平板连上没"只能靠它看）
srv_mod = None
_s2 = importlib.util.spec_from_file_location("lnserve2", os.path.join(HERE, "lnserve.py"))
srv_mod = importlib.util.module_from_spec(_s2)
_s2.loader.exec_module(srv_mod)
srv_mod.PEERS.clear()
srv_mod.note_peer("127.0.0.1")
srv_mod.note_peer("::1")
srv_mod.note_peer("10.9.9.1")
_pl = srv_mod.peer_list()
check("★ 只登记外部设备（回环不算），且只记 ip 和时间、不记请求内容",
      [p for p in _pl if p["ip"] == "10.9.9.1"] and
      not [p for p in _pl if p["ip"] in ("127.0.0.1", "::1")] and
      all(set(p) == {"ip", "ago", "at"} for p in _pl),
      json.dumps(_pl, ensure_ascii=False))
for _i in range(60):
    srv_mod.note_peer("10.9.9.%d" % (_i + 2))
check("PEERS 有上限（不会被刷爆内存）",
      len(srv_mod.peer_list()) <= srv_mod.PEERS_MAX,
      f"{len(srv_mod.peer_list())} <= {srv_mod.PEERS_MAX}")
srv_mod.PEERS.clear()

# 局域网地址枚举：只给非回环 IPv4，并标出像热点的那张网卡
_ips = srv_mod.lan_ipv4()
check("A17 lan_ipv4() 只给非回环地址，且每条都带「像不像热点」的标记",
      all(not e["ip"].startswith("127.") for e in _ips) and
      all(set(e) >= {"if", "ip", "ap"} for e in _ips),
      json.dumps(_ips, ensure_ascii=False))
# 这一条决定"告诉用户平板上输哪个地址"，错了就怎么都打不开：
# 平板连的是手机**热点**那张网卡，不是手机自己连的 Wi-Fi。
check("A18 名字启发式的边界（★ 只是兜底，真判据是 `_is_tethering_addr()` 的 53 端口实测 —— "
      "真机上光看名字会答错，所以绝不能拿它当唯一判据）",
      srv_mod._looks_like_hotspot("ap0", "192.168.43.1") is True and
      srv_mod._looks_like_hotspot("wlan1", "192.168.1.1") is True and
      srv_mod._looks_like_hotspot("wlan0", "10.20.30.41") is False and
      srv_mod._looks_like_hotspot("rmnet_data1", "10.20.30.41") is False,
      "ap0/wlan1 算热点，普通 wlan / 移动数据不算")

# ============================================================
print()
print("=" * 64)
print("B. 在线：页面上的「换一批」真的换了另一批书")
print("=" * 64)

if not ISOLATED:
    print("  （未在隔离服务下运行，跳过在线部分）")
else:
    # 先本地补货排一批（不联网）：这样"换前/换后"读的是**同一份榜单**的两屏，
    # 两屏天然不重复 —— 否则换前来自旧缓存、换后来自新榜单，断言就变弱了。
    _tp = post("/api/recs", {"topup": True})
    check("B0 空/小缓存能用书库存量补货（秒回，不联网）",
          _tp.get("ok") is True and _tp.get("count", 0) > 0,
          json.dumps(_tp, ensure_ascii=False)[:100])
    _html1 = get("/classic")
    _ids1 = rec_ids(_html1)
    check("B1 推荐位真的渲染出卡片", len(_ids1) > 0, f"{len(_ids1)} 张")
    _m = re.search(r'为你推荐\s*<span class="n">(\d+) 本', _html1)
    check("B2 标题写的本数 == 实际渲染的卡片数（数字不骗人）",
          bool(_m) and int(_m.group(1)) == len(_ids1),
          f"标题 {_m.group(1) if _m else '?'} / 实际 {len(_ids1)}")
    check("B3 推荐位有两个按钮：换一批（本地）+ 重新抓取源站（慢，虚线）",
          'id="recs-next"' in _html1 and 'id="recs-refresh" class="ghost"' in _html1)
    check("B3b 回环模式下**不**显示「平板用这个地址」（不给用户看没用的东西）",
          'id="lanurl"' not in _html1)

    _rot = post("/api/recs", {"rotate": True})
    _ids2 = rec_ids(get("/classic"))
    check("★ B4 点「换一批」后页面渲染的是**另一批**书（零重复）",
          bool(_ids2) and not (set(_ids2) & set(_ids1)),
          f"换前 {_ids1[:2]} → 换后 {_ids2[:2]}")
    check("B5 换一批的响应里有总数（前端能显示第 X–Y 本 / 共 Z 本）",
          _rot.get("ok") is True and _rot.get("total", 0) > 0,
          json.dumps(_rot, ensure_ascii=False))

    _j0 = json.loads(get("/api/recsjob"))
    check("B6 /api/recsjob 没在抓时如实报 running=false",
          _j0.get("running") is False and "total" in _j0,
          json.dumps(_j0, ensure_ascii=False))
    _net = json.loads(get("/api/net"))
    check("B7 /api/net 如实报告是否开放了局域网（隔离服务绑回环 = false）",
          _net.get("lan") is False and isinstance(_net.get("urls"), list),
          json.dumps(_net, ensure_ascii=False)[:100])
    check("B7b /api/net 带 peers（谁连上来过）和 ap_urls（热点地址排前面）",
          isinstance(_net.get("peers"), list) and isinstance(_net.get("ap_urls"), list),
          json.dumps({k: _net.get(k) for k in ("peers", "ap_urls")}, ensure_ascii=False))

    # —— 「重新抓取」必须是异步的：同步等两分钟就是"网页不刷新"的根因 ——
    # 只用一个关键词（不是 20 个），几秒就能把契约验完，不花钱、不慢。
    _t0 = time.time()
    _kick = post("/api/recs", {"refresh": True, "queries": ["百合"]})
    _dt = time.time() - _t0
    check("★ B8 「重新抓取」立刻返回、不阻塞页面（异步）",
          _kick.get("ok") is True and _dt < 10,
          f"耗时 {_dt:.2f}s started={_kick.get('started')}")
    check("B9 立刻返回时带 started/already，能区分「我发起的」和「已经在跑」",
          "started" in _kick and "already" in _kick,
          json.dumps(_kick, ensure_ascii=False)[:120])

    _saw_running = False
    _deadline = time.time() + 120
    while time.time() < _deadline:
        _s = json.loads(get("/api/recsjob"))
        if _s.get("running"):
            _saw_running = True
        else:
            break
        time.sleep(1.0)
    _s = json.loads(get("/api/recsjob"))
    check("B10 抓取期间能查到进度（页面才有东西显示，不像卡死）",
          _saw_running or _s.get("total") == 1,
          json.dumps(_s, ensure_ascii=False)[:120])
    check("B11 抓完 running 归 False 且带回候选数",
          _s.get("running") is False and isinstance(_s.get("found"), int),
          json.dumps(_s, ensure_ascii=False)[:120])
    check("B12 抓完如实报告失败原因（空字符串 = 没错）",
          _s.get("error", "") == "", f"error={_s.get('error')!r}")
    check("B13 抓完页面还是能正常打开（异步抓取不会把服务拖死）",
          "为你推荐" in get("/classic"))

# ============================================================
print()
print("=" * 64)
print("C. 流派榜入池 + origins 逐条落库 + 卡片可见（全桩，不联网）")
print("=" * 64)


class _FakeLnlib:
    GENRE_JP = {"FANTASY": "奇幻", "LOVE_STORY": "恋爱", "SF": "科幻",
                "HORROR": "恐怖", "MYSTERY": "悬疑", "DRAMA": "戏剧"}
    GENRE_SLUG = {"FANTASY": "fantasy", "LOVE_STORY": "love_story",
                  "SF": "sf", "HORROR": "horror", "MYSTERY": "mystery",
                  "DRAMA": "drama"}

    @staticmethod
    def kakuyomu_rankings():
        def _w(prefix, n=4):
            return [{"id": f"{prefix}-{i}", "title": f"{prefix} {i}",
                     "tags": list(_tags), "genre": "テスト", "episodes": 10,
                     "characters": 10000, "review_points": 100,
                     "last_episode_at": "2099-01-01",
                     "url": f"https://kakuyomu.jp/works/{prefix}-{i}"}
                    for i in range(n)]
        return {"weekly": _w("disc-weekly"),
                "recommended": _w("disc-rec"),
                "fresh": _w("disc-fresh")}

    @staticmethod
    def kakuyomu_search(q, pages=1):
        return [{"id": "kw-" + q, "title": "关键词书 " + q, "tags": list(_tags),
                 "genre": "テスト", "episodes": 10, "characters": 10000,
                 "review_points": 100, "last_episode_at": "2099-01-01",
                 "url": "https://kakuyomu.jp/works/kw-" + q}]

    @staticmethod
    def kakuyomu_ranking(g, range_="weekly"):
        # 给 GENRE_TOP_N+5 本，验证 refresh 会切到 top-N（B 方案：控住书库膨胀）
        return [{"id": "rk-%s-%02d" % (g, i), "title": "流派书 %s %d" % (g, i),
                 "tags": list(_tags), "genre": "テスト", "episodes": 10,
                 "characters": 10000, "review_points": 100,
                 "last_episode_at": "2099-01-01",
                 "url": "https://kakuyomu.jp/works/rk-%s-%02d" % (g, i)}
                for i in range(recs.GENRE_TOP_N + 5)]


class _FakeLf:
    lnlib = _FakeLnlib()
    DEFAULT_SCAN_QUERIES = ["q1"]

    @staticmethod
    def load_profile():
        return {"genre_weights": {"FANTASY": 5, "LOVE_STORY": 3}}

    @staticmethod
    def top_genres(prof, n=4):
        return ["FANTASY", "LOVE_STORY"]

    @staticmethod
    def score_work(w, prof):
        return (10.0, ["t"], ["r"])


_saved_lnfind = recs._load_lnfind
_saved_sleep_c = recs.time.sleep
recs._load_lnfind = lambda: _FakeLf
recs.time.sleep = lambda _s: None
try:
    recs.refresh(queries=["q1"])
    _lib2 = recs._load_lib()
    _genre = {k: v for k, v in _lib2.items()
              if any(str(o).startswith("流派:") for o in (v.get("origins") or []))}
    check("C1 流派榜入池：每流派只留 top-N（不把整榜 110 本灌库）",
          len(_genre) == 2 * recs.GENRE_TOP_N,
          f"{len(_genre)} 本，期望 {2 * recs.GENRE_TOP_N}")
    check("C2 origins 逐条落库（「流派:奇幻」进了 library.json）",
          any("流派:奇幻" in (v.get("origins") or []) for v in _genre.values()),
          str(next(iter(_genre.values()), {}).get("origins")))
    check("C3 关键词书照旧留档（原行为不回归）",
          any(k.startswith("kw-") for k in _lib2))
    check("C4 SCAN.total = 关键词数 + 流派数（进度不骗人）",
          recs.SCAN.get("total") == 1 + 2, f"total={recs.SCAN.get('total')}")
    _rk = {str(it.get("id")): it for it in recs.rank_library()}
    _gid = next(iter(_genre))
    check("★ C5 rank_library 用库里的 origins，不再被 sources 冲成「推荐抓取」",
          any("流派:" in o for o in (_rk.get(_gid, {}).get("origins") or [])),
          str(_rk.get(_gid, {}).get("origins")))
    _card = srv_mod.work_status_chips({"id": _gid, "origins": ["流派:奇幻"]})
    check("★ C6 卡片**不再**渲染「来源」（去重：只有 origins、没有书架关系时返回空）",
          _card == "", _card[:140])

    # 完整重抓（queries=None）才加发现源；自定义关键词只跑那组。
    recs.refresh(queries=None)
    _lib3 = recs._load_lib()
    _disc = {k: v for k, v in _lib3.items()
             if any(str(o).startswith(("总周榜", "首页推荐", "新作随机",
                                       "总月榜", "探索:"))
                    for o in (v.get("origins") or []))}
    _oris = {str(o) for v in _disc.values() for o in (v.get("origins") or [])}
    check("★ C7 完整重抓会混入总榜/推荐/新作/月榜/画像外流派",
          {"总周榜", "首页推荐", "新作随机", "总月榜"} <= _oris
          and any(o.startswith("探索:") for o in _oris),
          f"{len(_disc)} 本 / {sorted(_oris)[:8]}")
    check("C8 发现源也计入进度总数（不出现 done > total）",
          recs.SCAN.get("total") == 1 + 2 + 6,
          f"total={recs.SCAN.get('total')}")
finally:
    recs._load_lnfind = _saved_lnfind
    recs.time.sleep = _saved_sleep_c

print()
print("=" * 64)
print("D. Catalog schema + 旧 flat 双读")
print("=" * 64)
_cat = recs.lncatalog
_flat_seed = {
    "kakuyomu-100": {
        "title": "旧候选", "tags": ["TS"], "first_seen": "2026-01-01 00:00:00",
        "sources": ["推荐抓取"],
    },
    "kakuyomu-200": {
        "title": "旧想看", "tags": ["百合"], "first_seen": "2026-01-02 00:00:00",
        "want": True, "sources": ["推荐抓取"],
    },
}
_seed = _cat.from_legacy_flat(_flat_seed)
check("旧 flat 无用户动作进 candidates", "kakuyomu-100" in _seed["candidates"])
check("want 进 items 且 shelf=want",
      _seed["items"]["kakuyomu-200"]["shelf"] == "want"
      and _seed["items"]["kakuyomu-200"]["added_at"])
check("source 从 id 前缀推导", _seed["candidates"]["kakuyomu-100"]["source"] == "kakuyomu")
check("source_first_seen 保留", _seed["candidates"]["kakuyomu-100"]["source_first_seen"]
      == "2026-01-01 00:00:00")
_view = _cat.legacy_view(_seed)
check("legacy_view 同时给旧视图 candidates + items",
      "kakuyomu-100" in _view and _view["kakuyomu-200"]["want"] is True)
with tempfile.TemporaryDirectory(prefix="lncatalog-") as _td:
    _p = os.path.join(_td, "library.json")
    _seed["aliases"]["old-slug"] = "kakuyomu-200"
    _cat.save(_p, _seed)
    _loaded = _cat.load(_p)
    check("save/load 保留 items/candidates/aliases",
          _loaded["schema_version"] == 1
          and _loaded["aliases"]["old-slug"] == "kakuyomu-200")
    with open(os.path.join(_td, "slug-aliases.json"), "w", encoding="utf-8") as _f:
        json.dump({"very-old": "old-slug"}, _f)
    _aliases = _cat.load_aliases(_p)
    check("alias sidecar 可读且可递归解析",
          _cat.resolve_alias("very-old", _aliases) == "kakuyomu-200")
    check("alias key 不会被新 slug 偷走",
          _cat.choose_slug("very-old", _aliases) == "very-old-2")
    check("A→B→A 复活允许复用旧 key",
          _cat.choose_slug("very-old", {"very-old": "current"}, current="current")
          == "very-old")
    _old_path = recs.LIB_PATH
    try:
        recs.LIB_PATH = _p
        _dual = recs._load_lib()
        check("_load_lib 双读新 catalog 并摊平给旧视图",
              set(_dual) == {"kakuyomu-100", "kakuyomu-200"})
        _dual["kakuyomu-100"]["want"] = True
        recs._save_lib(_dual)
        _after = _cat.load(_p)
        check("旧写入保留分区并把 want 升级成 item",
              "kakuyomu-100" in _after["items"]
              and _after["items"]["kakuyomu-100"]["shelf"] == "want")
        check("旧写入不丢 aliases", _after["aliases"]["old-slug"] == "kakuyomu-200")
        with open(_p, "w", encoding="utf-8") as _f:
            json.dump({"schema_version": 999, "items": {}, "candidates": {},
                       "aliases": {}}, _f)
        try:
            recs._load_lib()
            _read_failed = False
        except _cat.CatalogSchemaError:
            _read_failed = True
        check("_load_lib 遇到错误 schema 也 fail fast", _read_failed)
    finally:
        recs.LIB_PATH = _old_path
    _novels = os.path.join(_td, "novels")
    _book = os.path.join(_novels, "kakuyomu-300")
    os.makedirs(_book)
    check("无 checkpoint = not_imported",
          _cat.import_state({"id": "kakuyomu-300"}, _novels) == "not_imported")
    with open(os.path.join(_book, ".import.json"), "w", encoding="utf-8") as _f:
        json.dump({"complete": False}, _f)
    check("未完成 checkpoint = importing",
          _cat.import_state({"id": "kakuyomu-300"}, _novels) == "importing")
    with open(os.path.join(_book, "meta.json"), "w", encoding="utf-8") as _f:
        json.dump({"title": "t"}, _f)
    with open(os.path.join(_book, ".import.json"), "w", encoding="utf-8") as _f:
        json.dump({"complete": True}, _f)
    check("complete + meta = imported",
          _cat.import_state({"id": "kakuyomu-300"}, _novels) == "imported")
try:
    _cat.load_obj({"schema_version": 999, "items": {}, "candidates": {},
                   "aliases": {}})
    _schema_failed = False
except _cat.CatalogSchemaError:
    _schema_failed = True
check("schema_version 不匹配 fail fast", _schema_failed)

print()
print("=" * 64)
print("E. reset 扫描：自动 / 人工 / 已规范 / 忽略 + dry-run 报告")
print("=" * 64)
_spec_m = importlib.util.spec_from_file_location(
    "lnreset", os.path.join(HERE, "migrate_reset.py"))
lnreset = importlib.util.module_from_spec(_spec_m)
_spec_m.loader.exec_module(lnreset)
with tempfile.TemporaryDirectory(prefix="lnreset-") as _td:
    _nov = os.path.join(_td, "novels")
    def _book(name, meta):
        d = os.path.join(_nov, name)
        os.makedirs(d)
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)
    _book("kakuyomu-1", {"source": "kakuyomu", "source_id": "1",
                         "slug": "kakuyomu-1", "title": "t"})
    _book("old-title", {"source": "kakuyomu", "source_id": "2",
                        "slug": "old-url", "title": "t"})
    _book("local-old", {"source": "local", "source_id": "local-abc",
                        "slug": "local-old", "title": "t"})
    _book("broken", {"title": "t"})
    os.makedirs(os.path.join(_nov, "empty"))
    with open(os.path.join(_nov, ".DS_Store"), "w", encoding="utf-8") as f:
        f.write("x")
    _rows = lnreset.scan(_nov)
    check("扫描：已规范目录不迁移",
          [x["dir"] for x in _rows["conforming"]] == ["kakuyomu-1"])
    check("扫描：标题型源站/本地目录进自动",
          {x["dir"] for x in _rows["auto"]} == {"old-title", "local-old"})
    _old = next(x for x in _rows["auto"] if x["dir"] == "old-title")
    check("扫描：alias key 同时包含目录名和实际 URL slug",
          set(_old["old_urls"]) == {"old-title", "old-url"})
    check("扫描：本地新 id 是 local-UUID",
          next(x for x in _rows["auto"] if x["dir"] == "local-old")["new_id"]
          .startswith("local-"))
    check("扫描：坏 meta / 缺 source_id 进人工",
          {x["dir"] for x in _rows["manual"]} == {"broken", "empty"})
    check("扫描：点文件和空目录被忽略或人工",
          any(x["dir"] == ".DS_Store" for x in _rows["ignored"]))
    _map1 = lnreset.id_map(_rows)
    _map2 = lnreset.id_map(lnreset.scan(_nov))
    check("id-map 幂等（同一旧目录得到同一新 id）", _map1 == _map2)
    _rep = lnreset.write_report(_rows, os.path.join(_td, "reports"), dry_run=True)
    _rj = json.loads(open(_rep, encoding="utf-8").read())
    check("dry-run 报告落盘且标 dry_run", _rj["dry_run"] is True
          and _rj["counts"]["auto"] == 2)
    check("dry-run 没重命名原目录", os.path.isdir(os.path.join(_nov, "old-title")))
    _v1 = lnreset.split_volume("無双ゲーに転生 2")
    _v2 = lnreset.split_volume("無双ゲーに転生_1_～聖剣～")
    _v3 = lnreset.split_volume("村づくりゲームのNPC　０３")
    _v4 = lnreset.split_volume(
        "無双ゲーに転生したと思ったら 2 ～聖剣を抱きし最凶少女～ (文庫)")
    check("卷号：末尾裸数字/_N_/全角数字/数字+～都能拆",
          (_v1[1], _v2[1], _v3[1], _v4[1]) == ("2", "1", "3", "2"),
          f"{_v1} {_v2} {_v3} {_v4}")
    check("卷号：不同卷不产生同一 dedupe_key",
          lnreset.dedupe_key({"title": "NPC 1", "author": "a"})
          != lnreset.dedupe_key({"title": "NPC 2", "author": "a"}))
    _dups = lnreset.suspected_duplicates({
        "auto": [
            {"dir": "a", "title": "以为转生到萌游大奖的成人游戏，实际是洋馆恐怖游戏",
             "author": "", "volume": ""},
            {"dir": "b", "title": "关于以为转生到萌系游戏大奖获奖作实际是洋馆恐怖游戏",
             "author": "", "volume": ""},
            {"dir": "c", "title": "村づくりゲームのNPC 1", "author": "x", "volume": "1"},
            {"dir": "d", "title": "村づくりゲームのNPC 2", "author": "x", "volume": "2"},
        ],
        "conforming": [],
    })
    check("疑似重复：近标题同卷进组，不同卷不进",
          any({x["dir"] for x in g} == {"a", "b"} for g in _dups)
          and not any({x["dir"] for x in g} == {"c", "d"} for g in _dups),
          str(_dups))

with tempfile.TemporaryDirectory(prefix="lnreset-write-") as _td:
    _nov = os.path.join(_td, "novels")
    _old = os.path.join(_nov, "old-title")
    os.makedirs(_old)
    with open(os.path.join(_old, "meta.json"), "w", encoding="utf-8") as _f:
        json.dump({"slug": "old-title", "source": "local",
                   "source_id": "local-abc", "title": "local title",
                   "author": "a", "episodes": [], "created_at": "2026-01-01 00:00:00"}, _f)
    os.makedirs(os.path.join(_td, "data", "books"))
    with open(os.path.join(_td, "data", "books", "old-title.json"),
              "w", encoding="utf-8") as _f:
        json.dump({"progress": {"chapter": 3},
                   "tracking": "reading", "favorites": "2026-01-01"}, _f)
    _src = os.path.join(_nov, "kakuyomu-123")
    os.makedirs(_src)
    with open(os.path.join(_src, "meta.json"), "w", encoding="utf-8") as _f:
        json.dump({"id": "kakuyomu-123", "slug": "kakuyomu-123",
                   "source": "kakuyomu", "source_id": "kakuyomu-123",
                   "title": "source title", "author": "b", "episodes": [],
                   "created_at": "2026-01-02 00:00:00"}, _f)
    with open(os.path.join(_td, "data", "library.json"), "w",
              encoding="utf-8") as _f:
        json.dump({"cand": {"id": "cand", "title": "candidate"},
                   "old-title": {"id": "old-title", "title": "local title"},
                   "kakuyomu-123": {"id": "kakuyomu-123",
                                    "title": "source title"}}, _f)
    _rows = lnreset.scan(_nov)
    _res = lnreset.write_migration(_rows, _nov)
    _new = _rows["auto"][0]["new_id"]
    _m = json.loads(open(os.path.join(_nov, _new, "meta.json"),
                         encoding="utf-8").read())
    check("write：本地目录重命名且 meta.id/slug 更新",
          not os.path.exists(_old) and _m.get("id") == _new
          and _m.get("slug") == _new)
    _catobj = _cat.load(os.path.join(_td, "data", "library.json"))
    check("write：本地书进入 items 且保留进度状态",
          _catobj["items"][_new]["shelf"] == "reading"
          and _catobj["items"][_new]["favorite"] is True)
    check("write：已规范源站书也进入 items",
          "kakuyomu-123" in _catobj["items"]
          and _catobj["items"]["kakuyomu-123"]["sources"] == ["kakuyomu"])
    check("write：alias 指向新 id",
          _catobj["aliases"].get("old-title") == _new)
    check("write：books 状态跟着重命名",
          os.path.exists(os.path.join(_td, "data", "books", _new + ".json")))
    check("write：备份和 id-map 落盘",
          os.path.isdir(_res["backup"])
          and os.path.exists(os.path.join(_td, "data", "reset-id-map.json")))
    _again = lnreset.write_migration(lnreset.scan(_nov), _nov)
    check("write：重复执行幂等，不再重命名", _again["renamed"] == [])


with tempfile.TemporaryDirectory(prefix="lnreset-merge-") as _td:
    _nov = os.path.join(_td, "novels")
    _lo = os.path.join(_nov, "local-old")
    _so = os.path.join(_nov, "kakuyomu-dup123")
    os.makedirs(_lo)
    os.makedirs(_so)
    with open(os.path.join(_lo, "meta.json"), "w", encoding="utf-8") as _f:
        json.dump({"source": "local", "source_id": "local-abc",
                   "title": "same title", "author": "a", "episodes": []}, _f)
    with open(os.path.join(_so, "meta.json"), "w", encoding="utf-8") as _f:
        json.dump({"id": "kakuyomu-dup123", "slug": "kakuyomu-dup123",
                   "source": "kakuyomu", "source_id": "dup123",
                   "title": "same title", "author": "a", "episodes": []}, _f)
    os.makedirs(os.path.join(_td, "data", "books"))
    with open(os.path.join(_td, "data", "library.json"), "w", encoding="utf-8") as _f:
        json.dump({"local-old": {"id": "local-old"},
                   "kakuyomu-dup123": {"id": "kakuyomu-dup123"}}, _f)
    _r = lnreset.scan(_nov)
    _res = lnreset.write_migration(_r, _nov)
    _cat2 = _cat.load(os.path.join(_td, "data", "library.json"))
    _win = _r["auto"][0]["new_id"]
    check("同书精确合并：只留本地 item，源站归档", 
          _win in _cat2["items"] and "kakuyomu-dup123" not in _cat2["items"]
          and os.path.isdir(os.path.join(_td, "data", "merged", "kakuyomu-dup123")))
    check("同书精确合并：alias + 报告", 
          _cat2["aliases"].get("kakuyomu-dup123") == _win
          and len(_r.get("merged") or []) == 1)


print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：")
    for f in fails:
        print("   - " + f)
    sys.exit(1)
print("✅ test_recs 全部通过")
