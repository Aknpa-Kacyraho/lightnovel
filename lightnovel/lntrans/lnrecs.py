#!/usr/bin/env python3
"""lnrecs —— 把 lnfinder 的推荐能力接到书架服务上（之前它一直只有命令行）。

设计：
  * 推荐结果缓存到 `data/recs.json`，**不每次请求都去抓源站**
    （否则打开书架就要打十几次 Kakuyomu）。
  * 缓存带 TTL（默认 12 小时），过期后由「换一批」按钮或前台触发刷新。
  * 复用 lnfinder 的画像（taste_profile.json）与打分器，
    **不重写一套推荐逻辑**——测试才会对准生产代码。
  * 只推荐"库里有原文可读"的：给出日文标题 + 标签 + 命中理由。
    翻译是花钱的，所以**不预先翻译**，用户点了「加入书架」才建（暂不翻）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lndata  # noqa: E402
import lncatalog  # noqa: E402

LAYOUT = lndata.resolve_layout()
lndata.apply_environment(LAYOUT)
_ROOT = LAYOUT.data_root
# lnfinder 的**代码**（lnfind.py / lnlib.py）永远在真实目录里。
LNFINDER = os.path.join(os.path.dirname(HERE), "lnfinder")
# 画像 / 候选池等**数据**可以重定向。LNTRANS_LNFINDER 指数据目录 ——
# 「不感兴趣」接口会写画像，自检打它。没有这个开关，测试就会改掉真实的
# taste_profile.json（和当初 lnrecs 没读 LNTRANS_DATA_ROOT 是同一个坑）。
# 注意：只重定向数据，不重定向代码 ——
# 踩过：一开始把整个目录换掉，结果 lnfind.py 也去临时目录找了，直接 FileNotFound。
_PROF_DIR = LAYOUT.finder_root
DATA = os.path.join(_ROOT, "data")
RECS_PATH = os.path.join(DATA, "recs.json")
# 书库：凡是抓过的作品都留档，用户以后想找还能找到（用户明确要求：
# 「你爬过的书可以留下来进入书库之类的地方，万一我以后又想看了去哪找」）
LIB_PATH = os.path.join(DATA, "library.json")
TTL_SEC = 12 * 3600
# 一屏显示几本 / 缓存里存几本。
# 存得比一屏多，是为了让「换一批」能在**本地**翻页：
# 否则只能靠重新打源站来"换"，而同样的关键词抓回来还是同一批书 ——
# 用户点了「换一批」等了三分半，看到的还是那 12 本（用户报过这个 bug）。
RECS_PAGE = 12
RECS_STORE = 60
# 流派榜每流派只留 top-N 进书库（B 方案）：4 流派 × 30 = 每次刷新最多 +120 本，
# 库增长可控，又够「换一批」本地轮换。全存（A）会让 library.json 无界膨胀。
GENRE_TOP_N = 30
SCAN_PAGES = 2
# 不靠画像标签也能遇到新书：总榜/推荐/新作/月榜各取一小撮，
# 再轮换两个画像外的流派。每源有上限，避免一次重抓把书库灌爆。
DISCOVERY_TOP_N = 18
DISCOVERY_GENRE_TOP_N = 12
DISCOVERY_GENRES = 2

_lf = None

# 保护"读-改-写"的全局锁。服务端是多线程（ThreadingHTTPServer + 后台 refresh），
# 没有它：两个请求同时 `_load_lib → 改 → _save_lib` 会互相覆盖（丢隐藏/想看），
# 或共用同一 .tmp 文件把 JSON 写坏。用 RLock：rotate 内部还会再调 topup/merge。
_IO_LOCK = threading.RLock()

# 「重新抓取」的进度（给前端轮询用，让用户看得见它在动）。
# 之前是同步接口：点了按钮要等 20 个关键词 × 约 10 秒 ≈ 3.5 分钟，
# 期间页面零反馈，用户以为"点了没用/网页死了"。
SCAN: dict = {"running": False, "done": 0, "total": 0, "found": 0,
              "error": "", "started": 0.0, "ended": 0.0}
# 保护 SCAN 的 check-then-set。服务是 ThreadingHTTPServer：两个「重新抓取」
# 并发进来时，无锁的"看 running → 写 running"会让两边都通过，真的抓两遍。
_SCAN_LOCK = threading.Lock()


def _load_lnfind():
    """惰性加载 lnfinder（它依赖网络库，且加载较慢）。"""
    global _lf
    if _lf is not None:
        return _lf
    with _IO_LOCK:      # 双重检查：两个线程首次并发别各自 exec_module 一遍
        if _lf is not None:
            return _lf
        spec = importlib.util.spec_from_file_location(
            "lnfind", os.path.join(LNFINDER, "lnfind.py"))
        mod = importlib.util.module_from_spec(spec)
        _saved_argv = sys.argv
        sys.argv = ["lnfind"]   # 别让 lnfind 的 argparse 解析宿主进程(lnserve)的参数
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.argv = _saved_argv
        # 让它用自己目录下的画像/候选池，别写到这里
        mod.PROFILE_PATH = os.path.join(_PROF_DIR, "taste_profile.json")
        mod.HISTORY_PATH = os.path.join(_PROF_DIR, "history.jsonl")
        mod.POOL_PATH = os.path.join(_PROF_DIR, "candidates.json")
        mod.REPORT_DIR = os.path.join(_PROF_DIR, "reports")
        sys.path.insert(0, LNFINDER)
        _lf = mod
        return mod


def _quarantine(path: str, why: str) -> None:
    """数据文件解析失败：**不许静默当成空**（用户会以为整座书架/整个缓存没了）。

    踩过：`_load_lib` 原来对 JSON 损坏一律 `return {}`，没有备份、没有告警 ——
    用户视角就是"我收藏的书/library 全没了"，还无处找回。
    现在把坏文件挪到 `<name>.corrupt-<时间戳>` 留证（可人工找回），再以空数据继续；
    挪走后下一次保存会写出全新的好文件，也不会每读一次就重复报错。
    """
    bak = f"{path}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        os.replace(path, bak)
    except OSError:
        bak = ""
    note = f"已备份为 {os.path.basename(bak)}（可人工找回）" if bak else "备份失败，按空数据继续"
    print(f"  ⚠ {os.path.basename(path)} 损坏（{why}）：{note}", file=sys.stderr)


def _load_cache() -> dict:
    if not os.path.exists(RECS_PATH):
        return {"at": 0, "items": []}
    try:
        with open(RECS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        _quarantine(RECS_PATH, f"JSON 解析失败: {e}")
        return {"at": 0, "items": []}
    except OSError:
        return {"at": 0, "items": []}


def _save_raw(c: dict) -> None:
    """原样写回缓存（不动 at）。「换一批」只挪游标，不能刷新新鲜度时间。"""
    os.makedirs(DATA, exist_ok=True)
    # 唯一 tmp 名：并发（或多进程）写也不会互相截断同一个临时文件。
    tmp = f"{RECS_PATH}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
    os.replace(tmp, RECS_PATH)


def _save_cache(items: list[dict]) -> None:
    # 新抓一轮 → 游标归零（从头看起），at 更新
    _save_raw({"at": time.time(), "items": items})


def _load_lib() -> dict:
    if not os.path.exists(LIB_PATH):
        return {}
    try:
        with open(LIB_PATH, encoding="utf-8") as f:
            obj = json.load(f)
    except json.JSONDecodeError as e:
        _quarantine(LIB_PATH, f"JSON 读取失败: {e}")
        return {}
    except OSError:
        return {}
    # New partitioned catalog is flattened for existing page/data callers.
    # Schema errors intentionally propagate: a malformed catalog must fail
    # fast instead of silently looking like an empty library.
    if lncatalog.is_catalog(obj):
        return lncatalog.legacy_view(
            lncatalog.load_obj(obj, path=LIB_PATH))
    return obj


def _save_lib(d: dict) -> None:
    os.makedirs(DATA, exist_ok=True)
    # If the file is already a partitioned catalog, preserve items/candidates/
    # aliases while old flat-view callers mutate their compatibility view.
    current = None
    if os.path.exists(LIB_PATH):
        try:
            with open(LIB_PATH, encoding="utf-8") as f:
                current = json.load(f)
        except (OSError, json.JSONDecodeError):
            current = None
    if isinstance(current, dict) and lncatalog.is_catalog(current):
        lncatalog.save(LIB_PATH,
                       lncatalog.merge_flat_view(current, d))
        return
    tmp = f"{LIB_PATH}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, LIB_PATH)


def merge_into_library(works: list[dict], source: str = "推荐抓取") -> int:
    """把抓到的作品并入书库（按 id 去重，保留首次见到时间与最新标签）。"""
    with _IO_LOCK:      # 读-改-写整段原子，别和 set_hidden/set_want 互相覆盖
        lib = _load_lib()
        n = 0
        for w in works:
            wid = str(w.get("id") or "")
            if not wid:
                continue
            cur = lib.get(wid)
            if cur is None:
                lib[wid] = {
                    "id": wid, "title": w.get("title"), "url": w.get("url"),
                    "author": w.get("author"), "tags": w.get("tags") or [],
                    "genre": w.get("genre_jp") or w.get("genre"),
                    "episodes": w.get("episodes"), "characters": w.get("characters"),
                    "points": w.get("review_points"),
                    "updated": w.get("last_episode_at"),
                    "first_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "source_first_seen": lncatalog.utc_now(),
                    "sources": [source],
                    # 逐条来源（「流派:奇幻」/ 关键词），rank_library 卡片要按它显示。
                    # 只存 sources 那层粗粒度的话，流派信息到卡片就没了。
                    "origins": list(w.get("origins") or [source]),
                }
                n += 1
            else:
                # 更新会变的字段，标签取并集
                cur["tags"] = list(dict.fromkeys((cur.get("tags") or []) + (w.get("tags") or [])))
                for k, src_key in (("episodes", "episodes"), ("points", "review_points"),
                                   ("updated", "last_episode_at"), ("author", "author")):
                    v = w.get(src_key)
                    if v not in (None, ""):
                        cur[k] = v
                srcs = cur.setdefault("sources", [])
                if source not in srcs:
                    srcs.append(source)
                cur["origins"] = list(dict.fromkeys(
                    (cur.get("origins") or []) + list(w.get("origins") or [])))
        _save_lib(lib)
        return n


def _norm_tags(tag: str = "", tags=None) -> list[str]:
    """把「单选 tag + 多选 tags」合并成去重、去空的有序标签列表。"""
    out: list[str] = []
    for t in (list(tags) if tags else []) + ([tag] if tag else []):
        if isinstance(t, str) and t.strip() and t not in out:
            out.append(t)
    return out


def _lib_filtered(query: str = "", want_only: bool = False,
                  include_hidden: bool = False, tag: str = "",
                  tags=None) -> list[dict]:
    """书库条目按「隐藏 / 想看 / 标签 / 关键词」过滤、按新到旧排序，**不截断**。

    只过滤排序一次：分页的"总数"和"这一页的卡"必须来自同一份结果，
    否则库超过一页上限时页数与实际条数对不上（数字在骗人）。
    标签支持多选，语义为 **AND（同时满足）**：选「异世界」+「TS」只留两者都带的。
    """
    lib = _load_lib()
    rows = list(lib.values())
    if not include_hidden:
        rows = [r for r in rows if not r.get("hidden")]
    if want_only:
        rows = [r for r in rows if r.get("want")]
    wanted = _norm_tags(tag, tags)
    if wanted:
        # 精确命中标签（点 facet chip 走这条）。子串匹配是 query 的活，
        # 两者语义不同：点「TS」不该把「TSF」也带出来。
        rows = [r for r in rows if all(t in (r.get("tags") or [])
                                       for t in wanted)]
    if query:
        q = query.strip().lower()
        rows = [r for r in rows if q in json.dumps(
            {k: r.get(k) for k in ("title", "author", "tags", "genre")},
            ensure_ascii=False).lower()]
    rows.sort(key=lambda r: (r.get("first_seen") or ""), reverse=True)
    return rows


def library_items(query: str = "", want_only: bool = False,
                  include_hidden: bool = False, limit: int = 300,
                  offset: int = 0, tag: str = "", tags=None) -> list[dict]:
    """书库列表（新到旧）。默认不含「隐藏」的。支持 offset 分页。"""
    rows = _lib_filtered(query, want_only, include_hidden, tag, tags)
    if offset:
        rows = rows[offset:]
    return rows[:limit]


def library_count(query: str = "", want_only: bool = False,
                  include_hidden: bool = False, tag: str = "", tags=None) -> int:
    """书库在**当前过滤条件下**的完整条数（不受 limit 影响）。

    分页页数必须用它，不能用被 limit 截断后的条数 ——
    否则库比一页上限大时，末尾会多出翻不到的空页。
    """
    return len(_lib_filtered(query, want_only, include_hidden, tag, tags))


def library_tags(top: int = 40, min_count: int = 2) -> list[tuple[str, int]]:
    """书库（未隐藏）里出现频次最高的标签，供「可点标签 facet」使用。

    频次 = 有多少本书带这个标签，用来给 chip 标注数量。
    只取前 top 个、且至少出现 min_count 次 —— 长尾标签全列出来反而没法挑
    （400+ 本的库里频率为 1 的标签有一大堆）。
    """
    counts: dict[str, int] = {}
    for r in _load_lib().values():
        if r.get("hidden"):
            continue
        for t in set(r.get("tags") or []):
            if t:
                counts[t] = counts.get(t, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [(t, n) for t, n in ranked if n >= min_count][:top]


def set_want(nid: str, want: bool) -> bool:
    with _IO_LOCK:
        lib = _load_lib()
        if nid not in lib:
            return False
        lib[nid]["want"] = bool(want)
        if want:
            lib[nid]["hidden"] = False      # 想看就取消隐藏
        _save_lib(lib)
        return True


def set_hidden(nid: str, hidden: bool) -> bool:
    """从书库隐藏（不想再看到它）。"""
    with _IO_LOCK:
        lib = _load_lib()
        if nid not in lib:
            return False
        lib[nid]["hidden"] = bool(hidden)
        if hidden:
            lib[nid]["want"] = False
        _save_lib(lib)
        return True


def hidden_count() -> int:
    return len([r for r in _load_lib().values() if r.get("hidden")])


def is_stale() -> bool:
    return (time.time() - _load_cache().get("at", 0)) > TTL_SEC


def cached(include_hidden: bool = False) -> list[dict]:
    """推荐缓存。默认**不含已隐藏的**。

    踩过：书库页「隐藏」只过滤了 library_items()，而推荐位直接读 cached()，
    于是你点了"不感兴趣/隐藏"，书库里没了，推荐卡照样还在推 ——
    用户视角就是"点了没反应"。隐藏 = 不想再看到，在**所有**列表里都该生效。
    """
    items = _load_cache().get("items") or []
    if include_hidden:
        return items
    try:
        lib = _load_lib()
    except Exception:  # noqa: BLE001
        return items
    return [it for it in items
            if not (lib.get(str(it.get("id"))) or {}).get("hidden")]


def _start_of(cur: str | None, items: list[dict]) -> int:
    """游标（第一本那条的 id）在**已过滤**列表里的下标。

    用 id 而不是下标：隐藏一本就会让所有下标错位，
    存下标的话「换一批」会莫名跳过/重复某些书。
    游标失效（书被隐藏或缓存换过）就回到第一屏 —— 宁可回到开头，不能错位。
    """
    if cur:
        for i, it in enumerate(items):
            if str(it.get("id")) == str(cur):
                return i
    return 0


def window(n: int = RECS_PAGE) -> dict:
    """当前该显示的一屏推荐（已排除隐藏）。

    返回 dict 而不是 list：前端要显示「第 X–Y 本 / 共 Z 本」，
    数字必须等于实际渲染的卡片数，不能让页面自己算。
    """
    c = _load_cache()
    items = cached()
    total = len(items)
    start = 0 if n <= 0 else _start_of(c.get("cursor"), items)
    if start >= total:
        start = 0
    page = items[start:start + n] if n > 0 else items
    return {
        "items": page,
        "start": start,
        "end": start + len(page),
        "total": total,
        "stored": len(c.get("items") or []),
        "at": c.get("at", 0),
        "stale": is_stale(),
    }


def rotate(n: int = RECS_PAGE) -> dict:
    """「换一批」：把游标往后挪一屏。**纯本地**，不打源站、不花时间。

    这是用户点「换一批」的本意（给我看点别的）。
    之前它等于「重新抓取」：同样 20 个关键词抓回来还是同一批书，
    排序也确定，所以刷新完页面一模一样 —— 用户视角就是"点了没用"。

    实测证据（2026-07）：用同样的 20 个关键词重抓一次，
    拿到的是**完全相同的 12 本、分数也一样**（25.5/25.2/24.8/…）——
    "换一批"退化成"重算一遍同样的东西"。
    """
    with _IO_LOCK:   # 读游标 → 改 → 写回必须原子，否则会盖掉后台 refresh 的新缓存
        items = cached()
        total = len(items)
        c = _load_cache()
        start = _start_of(c.get("cursor"), items) if total else 0
        # 只有一屏（比如刚抓完 12 本、或上一版缓存）→ 本地拿书库补一批出来。
        # 补货后列表换了，不能简单往后挪一屏：新列表的前几屏里往往还是刚才那 12 本，
        # 用户看到的还是"换了一批怎么还有它"。所以按"和刚才那屏重叠最少"来选。
        if total <= n:
            seen = {str(it.get("id")) for it in items}
            top = topup()
            items = cached()
            total = len(items)
            c = _load_cache()
            if total <= n:
                return {"ok": False,
                        "reason": "empty" if total == 0 else "single_page",
                        "total": total, "topped": bool(top.get("ok"))}
            nxt = _least_overlap_page(items, seen, n)
            c["cursor"] = str(items[nxt].get("id"))
            _save_raw(c)
            return {"ok": True, "start": nxt, "total": total, "cursor": c["cursor"],
                    "topped": bool(top.get("ok"))}
        nxt = _next_page(start, n, total)
        c["cursor"] = str(items[nxt].get("id"))
        _save_raw(c)
        return {"ok": True, "start": nxt, "total": total, "cursor": c["cursor"]}


def _least_overlap_page(items: list[dict], seen: set, step: int) -> int:
    """在 items 里挑一屏，使它与 `seen`（用户刚看过的那批）**重叠最少**。

    补货换了榜单时用它：新榜单第一屏通常还是旧那 12 本（同一套打分），
    直接给第一屏 = 用户点了「换一批」却看到同一批书（就是原 bug 的观感）。
    挑重叠为 0 的那屏；实在没有就挑重叠最少的。
    """
    step = step if step > 0 else 1
    best, best_ov = 0, None
    for cand in range(0, len(items), step):
        page = {str(x.get("id")) for x in items[cand:cand + step]}
        ov = len(page & seen)
        if best_ov is None or ov < best_ov:
            best, best_ov = cand, ov
            if ov == 0:
                break
    return best


def _next_page(start: int, step: int, total: int) -> int:
    """下一屏的起始下标（**按页对齐**）。

    踩过：一开始写成 `(start + step) % total`。total 不是 step 的整数倍时
    （比如 30 本 / 每屏 12 本）最后一步 24+12=36 → 36%30=6，
    第 4 屏变成 items[6..17] —— 和第 1 屏**重叠 6 本**，而且永远回不到开头。
    用户看到的就是"换了一批，怎么还是有刚才那几本"（和原 bug 同一种观感）。
    按页对齐后：0 → 12 → 24 → 0，每本书在轮完一圈里恰好出现一次。
    """
    step = step if step > 0 else 1
    nxt = (start // step + 1) * step
    return 0 if nxt >= total else nxt


def _work_from_lib(wid: str, it: dict) -> dict:
    """把**书库条目**还原成打分器认识的形状。

    字段名不一样（书库是 points/updated，打分器读 review_points/last_episode_at）。
    不映射的后果不是报错而是**静默归零**：rp=0 → 每本都判"评价点不足"，
    `rank_library()` 返回空表 —— 看起来像"书库不适合推荐"，其实是名字没对上。
    """
    g = it.get("genre")
    return {
        "id": wid, "title": it.get("title"), "url": it.get("url"),
        "author": it.get("author"), "tags": it.get("tags") or [],
        "genre": g, "genre_jp": g,
        "episodes": it.get("episodes"), "characters": it.get("characters"),
        "review_points": it.get("points"), "last_episode_at": it.get("updated"),
    }


def _cache_item(w: dict, sc: float, hits: list, reasons: list,
                origins: list | None = None) -> dict:
    """缓存条目的形状。refresh（抓源站）和 rank_library（本地排序）共用一份，
    免得两条路径渲染出不一样的卡片。"""
    return {
        "id": w.get("id"), "title": w.get("title"),
        "url": w.get("url"), "author": w.get("author"),
        "tags": (w.get("tags") or [])[:10],
        "genre": w.get("genre_jp") or w.get("genre"),
        "status": w.get("serial_status"),
        "episodes": w.get("episodes"),
        "characters": w.get("characters"),
        "points": w.get("review_points"),
        "updated": w.get("last_episode_at"),
        "score": round(sc, 1),
        "hits": hits,
        "reasons": reasons[:6],
        "origins": (origins if origins is not None
                    else (w.get("origins") or []))[:3],
    }


def rank_library(top: int = RECS_STORE) -> list[dict]:
    """用画像给**书库里已有的**作品排序（纯本地、不打源站、不花一分钱）。

    书库是历次抓取留下的（现在 300+ 本），本身就是现成的候选池。
    「换一批」要的是"还有哪些没看过"，而**重新打源站只会拿回同一批**；
    所以轮换的料从这里出，不靠再抓一遍。
    """
    lf = _load_lnfind()
    prof = lf.load_profile()
    lib = _load_lib()
    scored = []
    nerr = 0
    for wid, it in lib.items():
        if it.get("hidden"):
            continue        # 隐藏 = 别再推给我，本地补货也得守这条
        w = _work_from_lib(str(wid), it)
        try:
            sc, hits, reasons = lf.score_work(w, prof)
        except Exception:  # noqa: BLE001
            nerr += 1
            continue
        if sc > -900:
            scored.append((w, sc, hits, reasons))
    if nerr:
        # 不静默：全部异常时会返回空表，看起来像"书库没有合适的书"，
        # 实际是代码坏了（"返回空 = 通过"是最难查的一种假绿）
        print(f"  rank_library：{nerr} 本打分失败（已跳过）", file=sys.stderr)
    scored.sort(key=lambda x: -x[1])
    out = []
    for w, sc, hits, reasons in scored[:top]:
        it = lib.get(str(w.get("id"))) or {}
        # 用库里存下来的逐条 origins（「流派:奇幻」等）；没有才退回粗粒度 sources。
        # 之前这里恒用 sources（值只会是"推荐抓取"），把 refresh 打好的流派来源冲掉了。
        oris = it.get("origins") or it.get("sources") or ["书库"]
        out.append(_cache_item(w, sc, hits, reasons, origins=list(oris)))
    return out


def topup(top: int = RECS_STORE) -> dict:
    """只用书库里已有的作品补满候选（本地、秒回、不花钱）。

    **不更新 `at`**：freshness 只描述"上次打源站是什么时候"，
    本地重排不算新抓一轮 —— 顺手刷新 `at` 会让「缓存较旧」的提示永远不出现。
    """
    try:
        items = rank_library(top)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if not items:
        return {"ok": False, "reason": "empty"}
    with _IO_LOCK:
        c = _load_cache()
        c["items"] = items
        c.setdefault("at", 0)
        c.pop("cursor", None)
        _save_raw(c)
    return {"ok": True, "count": len(items)}


def scan_state() -> dict:
    """「重新抓取」进度快照（前端轮询）。"""
    s = dict(SCAN)
    if s["running"] and s["started"]:
        s["elapsed"] = round(time.time() - s["started"], 1)
    else:
        s["elapsed"] = 0.0
    return s


def refresh(top: int = RECS_STORE, queries: list[str] | None = None) -> list[dict]:
    """抓一轮候选并按画像打分，写入缓存。

    实测（20 个关键词，真打 Kakuyomu）：**1 分 53 秒**，不是最初文案写的"约 1 分钟"。
    （2026-10 起另加画像 top-4 流派榜、每榜 top-N，多 4 次页面请求，总时长更长。）
    所以它不是「换一批」，而是「重新抓取」——
    要等两分钟的事必须让用户看得见进度：走 refresh_async + scan_state。

    ⚠ 同一个关键词集合抓回来**必然是同一批书、同一个排序**（实测过：
    重抓一次拿到的 12 本和分数一字不差）。所以「换一批」不能靠它，
    得靠 rank_library 从书库里换 —— 那是本地、秒回的。
    """
    lf = _load_lnfind()
    prof = lf.load_profile()
    qs = list(queries or lf.DEFAULT_SCAN_QUERIES)
    if qs:
        rot = int(SCAN.get("qrot") or 0) % len(qs)
        qs = qs[rot:] + qs[:rot]
        SCAN["qrot"] = (rot + 3) % len(qs)
    genres = lf.top_genres(prof)          # 画像最偏、且站点有榜的流派（0~4 个）

    # 只有"完整重抓"才带发现源；调用方传了自定义关键词就只跑那组，
    # 免得好心加料反而让调试/测试拿到一池不相干的书。
    extra_jobs: list[tuple[str, object]] = []
    if queries is None:
        home_cache: dict = {}

        def _home(key: str) -> list:
            if "v" not in home_cache:
                home_cache["v"] = lf.lnlib.kakuyomu_rankings() or {}
            return (home_cache["v"].get(key) or [])[:DISCOVERY_TOP_N]

        extra_jobs = [
            ("总周榜", lambda: _home("weekly")),
            ("首页推荐", lambda: _home("recommended")),
            ("新作随机", lambda: _home("fresh")),
            ("总月榜", lambda: lf.lnlib.kakuyomu_ranking(
                "all", "monthly")[:DISCOVERY_TOP_N]),
        ]
        try:
            gkeys = [g for g in getattr(lf.lnlib, "GENRE_SLUG", {})
                     if g not in genres]
            if gkeys:
                grot = int(SCAN.get("grot") or 0) % len(gkeys)
                picks = (gkeys[grot:] + gkeys[:grot])[:DISCOVERY_GENRES]
                SCAN["grot"] = (grot + DISCOVERY_GENRES) % len(gkeys)
                for g in picks:
                    name = lf.lnlib.GENRE_JP.get(g, g)
                    extra_jobs.append((
                        f"探索:{name}",
                        lambda g=g: lf.lnlib.kakuyomu_ranking(
                            g, "monthly")[:DISCOVERY_GENRE_TOP_N]))
        except Exception as e:  # noqa: BLE001
            print(f"  探索流派准备失败：{type(e).__name__}", file=sys.stderr)

    SCAN.update(running=True, done=0,
                total=len(qs) + len(genres) + len(extra_jobs), found=0,
                error="", started=time.time(), ended=0.0)
    prev_ids = {str(x.get("id")) for x in (_load_cache().get("items") or [])}
    pool: dict[str, dict] = {}

    def _merge(w: dict, origin: str) -> None:
        prev = pool.get(w["id"])
        if prev is None:
            w["origins"] = [origin]
            pool[w["id"]] = w
        else:
            prev["tags"] = list(dict.fromkeys(prev.get("tags", []) + w.get("tags", [])))
            prev["origins"] = list(dict.fromkeys(prev["origins"] + [origin]))

    try:
        for q in qs:
            print(f"  → 搜索 {q}", file=sys.stderr)
            try:
                for w in lf.lnlib.kakuyomu_search(q, pages=SCAN_PAGES):
                    _merge(w, q)
            except Exception as e:  # noqa: BLE001
                print(f"    {q} 失败：{type(e).__name__}", file=sys.stderr)
            finally:
                SCAN["done"] = SCAN.get("done", 0) + 1
                SCAN["found"] = len(pool)
            time.sleep(0.7)

        # 流派榜：画像最偏的流派各取 top-N（B 方案，控住书库膨胀）。
        for g in genres:
            name = lf.lnlib.GENRE_JP.get(g, g)
            print(f"  → 流派榜 {name}", file=sys.stderr)
            try:
                for w in lf.lnlib.kakuyomu_ranking(g, "weekly")[:GENRE_TOP_N]:
                    _merge(w, f"流派:{name}")
            except Exception as e:  # noqa: BLE001
                print(f"    流派榜 {name} 失败：{type(e).__name__}", file=sys.stderr)
            finally:
                SCAN["done"] = SCAN.get("done", 0) + 1
                SCAN["found"] = len(pool)
            time.sleep(0.7)

        # 发现源：总榜/首页推荐/新作/月榜 + 画像外流派轮换。
        # 不用画像标签也能遇到新书；每源有上限，避免书库被同一个榜单灌满。
        for label, fetch in extra_jobs:
            print(f"  → {label}", file=sys.stderr)
            try:
                for w in (fetch() or []):
                    _merge(w, label)
            except Exception as e:  # noqa: BLE001
                print(f"    {label} 失败：{type(e).__name__}", file=sys.stderr)
            finally:
                SCAN["done"] = SCAN.get("done", 0) + 1
                SCAN["found"] = len(pool)
            time.sleep(0.7)

        # 凡是抓过的都留档进书库
        added = merge_into_library(list(pool.values()), source="推荐抓取")
        if added:
            print(f"  （书库新增 {added} 本）", file=sys.stderr)

        # 抓完**再给整个书库排一次序**（不只是这一轮的池子）：
        # 书库 = 历次抓取的并集，用它排序自然拿到"这一轮 + 以前抓过的"，
        # 于是「换一批」有 5 页料，而不是只有 12 本。
        try:
            ranked = rank_library(max(top, RECS_STORE + 60))
        except Exception as e:  # noqa: BLE001
            print(f"  书库排序失败，退回只排本轮：{type(e).__name__}", file=sys.stderr)
            ranked = []
        if ranked:
            items = ranked
            if prev_ids:
                fresh = [it for it in ranked if str(it.get("id")) not in prev_ids]
                if fresh:
                    # 新 ID 优先但别占满整页：发现源一次能带进几十本，
                    # 全塞前面会把真正高分的旧书挤掉。只留三分之一给"新"。
                    cap = max(6, top // 3)
                    items = fresh[:cap]
                    seen = {str(it.get("id")) for it in items}
                    items += [it for it in ranked
                              if str(it.get("id")) not in seen][:max(0, top - len(items))]
            items = items[:top]
        else:
            scored = []
            for w in pool.values():
                sc, hits, reasons = lf.score_work(w, prof)
                if sc > -900:
                    scored.append((w, sc, hits, reasons))
            scored.sort(key=lambda x: -x[1])
            items = [_cache_item(w, sc, hits, reasons) for w, sc, hits, reasons in scored[:top]]
        with _IO_LOCK:
            _save_cache(items)
        SCAN["found"] = len(items)
        return items
    finally:
        SCAN["running"] = False
        SCAN["ended"] = time.time()


def refresh_async(top: int = RECS_STORE, queries: list[str] | None = None) -> bool:
    """后台跑 refresh，立刻返回。已在跑则返回 False（不叠第二次，省得算两遍）。

    SCAN 的状态**在起线程之前就同步写好**：不然线程还没调度起来，
    接口返回的进度是 0/0（前端显示"正在抓取 0/0"），
    而且那个"已经在跑"的判据也有一瞬间不成立 —— 连点两下会真的抓两遍。
    """
    with _SCAN_LOCK:
        if SCAN.get("running"):
            return False
        try:
            n = len(queries) if queries else len(_load_lnfind().DEFAULT_SCAN_QUERIES)
        except Exception:  # noqa: BLE001
            n = 0
        SCAN.update(running=True, done=0, total=n, found=0, error="",
                    started=time.time(), ended=0.0)
    t = threading.Thread(target=_refresh_job, args=(top, queries), daemon=True)
    t.start()
    return True


def _refresh_job(top: int, queries: list[str] | None) -> None:
    try:
        refresh(top=top, queries=queries)
    except Exception as e:  # noqa: BLE001
        SCAN["running"] = False
        SCAN["error"] = f"{type(e).__name__}: {e}"
        SCAN["ended"] = time.time()
        print(f"  重新抓取失败：{SCAN['error']}", file=sys.stderr)


_Q_NOTE: str | None = None


def scan_q_note() -> str:
    """「重新抓取」到底要多久 —— 按实测算，不许写"约 1 分钟"。

    实测（2026-07，本机 20 个关键词、真打 Kakuyomu）：**1 分 53 秒**，
    即约 5.7 秒/关键词（含每次 0.7 秒的礼貌间隔）。原文案写"约 1 分钟"，
    数字骗人比慢更糟：用户会以为卡死了，然后再也不点。
    """
    global _Q_NOTE
    if _Q_NOTE is None:
        n, extra = 0, 0
        try:
            lf = _load_lnfind()
            n = len(lf.DEFAULT_SCAN_QUERIES)
            genres = lf.top_genres(lf.load_profile())
            gkeys = [g for g in getattr(lf.lnlib, "GENRE_SLUG", {})
                     if g not in genres]
            # 4 个固定发现源（周榜/推荐/新作/月榜）+ 轮换的画像外流派。
            extra = len(genres) + 4 + (min(DISCOVERY_GENRES, len(gkeys))
                                       if gkeys else 0)
        except Exception:  # noqa: BLE001
            pass
        jobs = n + extra
        _Q_NOTE = (f"{n} 个关键词 + {extra} 个榜单/推荐源，"
                   f"约 {max(1, round(jobs * 5.7 / 60))} 分钟"
                   if jobs else "需联网")
    return _Q_NOTE


def trending(top: int = 8) -> list[dict]:
    """候选池里最近更新的作品（不依赖画像，纯"新书/更新"）。"""
    lf = _load_lnfind()
    pool = lf.load_pool()
    if not pool:
        return []
    rows = sorted(pool, key=lambda w: (w.get("last_episode_at") or ""), reverse=True)
    out = []
    for w in rows[:top]:
        out.append({
            "id": w.get("id"), "title": w.get("title"), "url": w.get("url"),
            "author": w.get("author"), "tags": (w.get("tags") or [])[:8],
            "episodes": w.get("episodes"), "points": w.get("review_points"),
            "updated": w.get("last_episode_at"),
        })
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="刷新书架推荐缓存")
    ap.add_argument("--top", type=int, default=RECS_STORE)
    a = ap.parse_args()
    print(f"刷新推荐（{len(_load_lnfind().DEFAULT_SCAN_QUERIES)} 个搜索词）…")
    items = refresh(a.top)
    print(f"完成，缓存 {len(items)} 条 → {RECS_PATH}\n")
    for i, it in enumerate(items[:8], 1):
        print(f"{i}. {it['score']:>5}分  {it['title'][:40]}")
        print(f"      命中：{'、'.join(it['hits'][:6])}")
