#!/usr/bin/env python3
"""lnfind —— 轻小说发现工具（采集 + 个性化推荐）

为什么不是"又一个推荐列表"：
  普通网页 AI 只会背热门作品。真正影响阅读体验的是**标签组合**
  （ざまぁ / 追放 / チート / 悪役令嬢 / もふもふ …），
  而标签偏好在各站都是公开可搜的。这个工具做的事：
    1. 从上游源站按标签/榜单/搜索拉取候选池（含冷门作）
    2. 用你的偏好画像对每个标签加权打分
    3. 用标签命中数下限 + 负标签黑名单 + 质量下限做过滤
  所以它推荐的是"你喜欢的标签组合"，不是"大家都看的书"。

用法：
  python3 lnfind.py profile                       # 查看当前偏好画像
  python3 lnfind.py learn --like ざまぁ 追放 --skip ハーレム
  python3 lnfind.py new  --tags ざまぁ --days 30  # 近期有新章/新作
  python3 lnfind.py recommend --tags ざまぁ --top 20
  python3 lnfind.py author レオナールD             # 找同作者其它作品
  python3 lnfind.py interesting                  # 自动发现候选新标签
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lnlib  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# 数据目录必须跟随 LNTRANS_LNFINDER（自检隔离靠它）——画像/历史/候选池
# 都是**真实资产**，写死路径会让隔离测试污染真数据（AGENTS.md 硬规则）。
# 只重定向数据，代码始终在本文件所在目录（lnlib 也从 HERE 导入）。
_DATA_DIR = os.environ.get("LNTRANS_LNFINDER") or HERE
PROFILE_PATH = os.path.join(_DATA_DIR, "taste_profile.json")
POOL_PATH = os.path.join(_DATA_DIR, "candidates.json")
REPORT_DIR = os.path.join(_DATA_DIR, "reports")

# 标签权重统一区间：0 = 已彻底不想看，12 = 极偏好。
# 上限防止单个标签靠反复点赞主导打分；下限防止反复点踩把权重推到无界的负数
# （负到 score ≤ -900 会被推荐过滤器永久丢弃）。learn_from_work 与 cmd_learn
# 共用同一夹取，避免两处漂移。
TAG_W_MIN, TAG_W_MAX = 0.0, 12.0

# 画像「自升级」：口味会变，权重不能只增不减。每次写入画像前，把长期没被
# 触碰的权重按时间半衰期**向中性 1.0 收缩**（旧偏好自然退场、近期信号占比更大）。
# 半衰期 90 天（偏稳）；两次结算间隔不到 DECAY_MIN_INTERVAL_HOURS(12h) 就不动，
# 免得同一天反复 learn 时被无限细碎地衰减。blocked_tags / formula_tags 不衰减。
DECAY_HALFLIFE_DAYS = 90.0
DECAY_MIN_INTERVAL_HOURS = 12.0


def clamp_tag_weight(v: float) -> float:
    return max(TAG_W_MIN, min(round(v, 2), TAG_W_MAX))

# 冷启动画像。默认面向"误解系/反套路"口味：稀缺，且排斥公式化套路。
DEFAULT_PROFILE = {
    "tag_weights": {
        # —— 核心口味：误解系（暗影大人那一挂），稀缺所以给高权重
        "勘違い": 6.0, "無自覚": 5.5, "無自覚最強": 5.0, "勘違い系": 5.0,
        "すれ違い": 4.0, "認識齟齬": 4.5, "実力隠し": 3.5,
        "シリアスとギャグ": 2.5, "コメディ": 2.0, "ギャグ": 2.0,
        # —— 反派千金：用户明确喜欢，但不要公式化的那批
        "悪役令嬢": 4.0, "悪役令息": 3.5, "乙女ゲーム": 2.0,
        # —— TS / 性转：高辨识度偏好
        "TS": 5.0, "TS転生": 5.0, "TSっ子": 4.5, "性転換": 4.0, "TS少女": 4.0,
        # —— 百合/GL：高辨识度偏好
        "百合": 5.0, "ガールズラブ": 4.5, "GL": 4.0, "百合コメディ": 3.5,
        "じれじれ": 2.5, "女主人公": 1.5,
        # —— 反套路佐料
        "もう遅い": 3.0, "ざまぁ": 2.0, "チートなし": 2.5,
        "成長": 2.0, "ヒューマンドラマ": 2.0, "群像劇": 2.0,
    },
    "genre_weights": {
        "FANTASY": 0.8, "LOVE_STORY": 1.0, "DRAMA": 1.1,
        "MYSTERY": 1.2, "SF": 1.0, "OTHERS": 0.9, "ACTION": 0.9,
    },
    # 公式化套路：命中越多扣越多；作品若含"误解系"标签则减免
    # （误解系常套着异世界壳子，不能一刀切）
    "formula_tags": {
        "異世界転生": 1.6, "異世界転移": 1.6, "異世界": 1.0, "ハーレム": 2.5,
        "追放": 1.8, "ざまぁ": 1.3, "チート": 1.6, "無双": 1.8,
        "スローライフ": 1.2, "主人公最強": 1.6, "テンプレ": 2.5,
        "俺TUEEE": 2.0, "ご都合主義": 2.0, "成り上がり": 1.2,
        "貞操逆転": 1.5, "男女比": 1.5, "配信": 0.8,
    },
    "misunderstanding_tags": ["勘違い", "無自覚", "勘違い系", "無自覚最強", "認識齟齬", "すれ違い"],
    # B 档（只命中 1 个偏好）的门槛：弱标签权重低，单靠它不足以推荐，
    # 除非分数够高或评价点极高。防止「只碰到 ざまぁ(+2)」这类弱匹配混进来。
    "weak_hit_min_score": 3.0,
    "weak_hit_min_points": 20000,
    "blocked_tags": ["NTR", "寝取られ", "グロ", "リョナ", "ホラー"],
    # 自升级：halflife_days = 权重向中性 1.0 收缩到一半所需天数；last = 上次
    # 结算时间（空 = 尚未开始，首次接触只立基线不衰减）。load_profile 会给
    # 老画像自动补上这个键，无需迁移。
    "decay": {"halflife_days": DECAY_HALFLIFE_DAYS, "last": ""},
    "min_review_points": 50,
    "min_episodes": 5,
    "min_tag_hits": 1,
}


# 扫描用的默认搜索词：站内标签太宽泛时，用描述性词组去挖。
# 「误解系」的典型代表是《陰の実力者になりたくて!》(暗影大人)。
DEFAULT_SCAN_QUERIES = [
    # 误解系（代表作：陰の実力者になりたくて!）
    "陰の実力者", "周囲が勘違い", "誤解される", "無自覚", "勘違い",
    "実力隠し", "無自覚チート", "周囲が誤解", "認識違い", "思い込み",
    # TS / 性转
    "TS", "TS転生", "TSっ子", "性転換", "TS少女",
    # 百合 / GL
    "百合", "ガールズラブ", "GL", "百合コメディ", "TS百合",
]


def die(msg: str) -> None:
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(1)


def load_profile() -> dict:
    if not os.path.exists(PROFILE_PATH):
        save_profile(DEFAULT_PROFILE)
        return json.loads(json.dumps(DEFAULT_PROFILE))
    with open(PROFILE_PATH, encoding="utf-8") as f:
        prof = json.load(f)
    # 补齐新增的默认配置项，并落盘——否则新加的阈值只活在内存里，
    # 下次读文件又不见了（踩过一次）。
    missing = [k for k in DEFAULT_PROFILE if k not in prof]
    for k in missing:
        prof[k] = json.loads(json.dumps(DEFAULT_PROFILE[k]))
    if missing:
        save_profile(prof)
    return prof


def save_profile(prof: dict) -> None:
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False, indent=2)


def apply_time_decay(prof: dict, *, now: datetime | None = None,
                     min_interval_hours: float | None = None,
                     verbose: bool = False) -> int:
    """把长期未更新的权重向中性 1.0 收缩（时间半衰期衰减），就地改 prof。

    只在**写入画像前**调用。收缩只作用于 tag_weights / genre_weights：
      new = 1.0 + (old - 1.0) * 0.5 ** (elapsed_days / halflife_days)
    于是 90 天不理，强偏好过半回到中性；但一直被 reinforce 的标签衰减后又被加回，
    稳定在偏好位 —— 这就是「初始喜好没有进化空间」的解药。

    护栏：blocked_tags 不打折（拉黑是明确的「不要」）；formula_tags 数值不动
    （那是惩罚词典、不是偏好）；只衰减不删除。返回被改动的标签数。
    未到 min_interval_hours 或没有有效 last 时不动（首次接触只立基线）。
    """
    now = now or datetime.now()
    dec = prof.setdefault("decay", {})
    try:
        halflife = float(dec.get("halflife_days") or DECAY_HALFLIFE_DAYS)
    except (TypeError, ValueError):
        halflife = DECAY_HALFLIFE_DAYS
    min_hours = (DECAY_MIN_INTERVAL_HOURS if min_interval_hours is None
                 else min_interval_hours)

    last_raw = dec.get("last") or ""
    if not last_raw:
        dec["last"] = now.isoformat(timespec="seconds")   # 首次：只立基线
        return 0
    try:
        last = datetime.fromisoformat(last_raw)
    except (TypeError, ValueError):
        dec["last"] = now.isoformat(timespec="seconds")
        return 0
    elapsed_days = (now - last).total_seconds() / 86400.0
    if elapsed_days * 24.0 < min_hours or halflife <= 0:
        return 0                                          # 太频繁，攒着
    factor = 0.5 ** (elapsed_days / halflife)

    blocked = set(prof.get("blocked_tags") or [])
    changed = 0
    for key in ("tag_weights", "genre_weights"):
        table = prof.get(key) or {}
        for t, w in list(table.items()):
            if t in blocked:
                continue
            try:
                new = round(1.0 + (float(w) - 1.0) * factor, 2)
            except (TypeError, ValueError):
                continue
            if new != w:
                table[t] = new
                changed += 1
    dec["last"] = now.isoformat(timespec="seconds")
    if changed:
        log_event("decay", factor=round(factor, 4),
                  elapsed_days=round(elapsed_days, 2), changed=changed)
        if verbose:
            print(f"  画像随时间衰减：{changed} 个标签向中性收缩 "
                  f"（间隔 {elapsed_days:.1f} 天，因子 {factor:.3f}）")
    return changed


# ------------------------------------------------------------------ 采集

def top_genres(prof: dict, n: int = 4) -> list[str]:
    """画像里权重最高、且站点有榜/检索页的前 n 个流派（用于流派发现）。"""
    gw = prof.get("genre_weights") or {}
    return sorted((g for g in gw if g in lnlib.GENRE_SLUG),
                  key=lambda g: gw[g], reverse=True)[:n]


def collect(tags: list[str], *, include_rankings: bool, pages: int,
            genres: list[str] | None = None) -> list[dict]:
    """拉候选池：榜单 + 流派榜 + 每个偏好标签的搜索页（含冷门作）。"""
    pool: dict[str, dict] = {}

    def add(works: list[dict], origin: str) -> None:
        for w in works:
            if not w.get("id"):
                continue
            w.setdefault("origins", [])
            w["origins"].append(origin)
            # 跨源 id 不能只看数字/ncode：kakuyomu 与 syosetu 各有一套编号。
            key = f"{w.get('source') or 'kakuyomu'}:{w['id']}"
            prev = pool.get(key)
            if prev is None:
                pool[key] = w
            else:
                # 合并标签（不同入口拿到的标签可能不同）
                merged = list(dict.fromkeys(list(prev.get("tags") or []) + list(w.get("tags") or [])))
                prev["tags"] = merged
                prev["origins"] = list(dict.fromkeys(prev["origins"] + [origin]))

    if include_rankings:
        print("→ 抓取 Kakuyomu 首页榜单/推荐/新章 …", file=sys.stderr)
        try:
            r = lnlib.kakuyomu_rankings()
            add(r["weekly"], "周榜")
            add(r["recommended"], "随机推荐")
            add(r["fresh"], "30天内有新章")
        except lnlib.FetchError as e:
            print(f"  榜单抓取失败：{e}", file=sys.stderr)

        print("→ 抓取成为小说家吧榜单（一般向 + R18）…", file=sys.stderr)
        for r18, label in ((False, "小说家周榜"), (True, "小说家R18周榜")):
            try:
                add(lnlib.syosetu_rankings(r18=r18), label)
            except Exception as e:  # noqa: BLE001
                print(f"  {label}失败：{e}", file=sys.stderr)

    for g in (genres or []):
        name = lnlib.GENRE_JP.get(g, g)
        print(f"→ 抓流派榜：{name}", file=sys.stderr)
        try:
            add(lnlib.kakuyomu_ranking(g, "weekly"), f"流派:{name}")
        except lnlib.FetchError as e:
            print(f"  失败：{e}", file=sys.stderr)
        time.sleep(0.8)

    for tag in tags:
        print(f"→ 按标签抓取：{tag}", file=sys.stderr)
        try:
            add(lnlib.kakuyomu_search(tag, pages=pages), f"标签:{tag}")
        except lnlib.FetchError as e:
            print(f"  失败：{e}", file=sys.stderr)
        try:
            add(lnlib.syosetu_search(tag), f"小说家标签:{tag}")
        except Exception as e:  # noqa: BLE001
            print(f"  小说家失败：{e}", file=sys.stderr)
        time.sleep(0.8)

    return list(pool.values())


def load_pool() -> list[dict]:
    if not os.path.exists(POOL_PATH):
        return []
    try:
        with open(POOL_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        # 候选池是缓存：坏了就当空的，下次重抓即可，不该让整个命令崩掉。
        print(f"  候选池读取失败（当空处理）：{e}", file=sys.stderr)
        return []


def save_pool(works: list[dict]) -> None:
    with open(POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(works, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ 历史画像

HISTORY_PATH = os.path.join(_DATA_DIR, "history.jsonl")


def log_event(kind: str, **fields) -> None:
    """追加一条历史事件（只增不改），便于回溯画像怎么长出来的。"""
    rec = {"at": datetime.now().isoformat(timespec="seconds"), "kind": kind}
    rec.update(fields)
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_history() -> list[dict]:
    if not os.path.exists(HISTORY_PATH):
        return []
    out = []
    with open(HISTORY_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def already_learned(ident: str) -> bool:
    """同一部作品只自动加权一次，避免重复喂导致权重膨胀。"""
    return any(e.get("id") == ident for e in load_history() if e.get("kind") in ("like", "dislike"))


def _learned_or_read(ident: str) -> bool:
    """导入时的去重：喜欢/不喜欢/**读过（中性）**都算「已导入过」。

    与 already_learned 分开：already_learned 只管"已加权过的"（like/dislike），
    好让「先记读过、之后明确表白」仍能生效；导入去重则连"读过"也不该重复记。
    """
    return any(e.get("id") == ident for e in load_history()
               if e.get("kind") in ("like", "dislike", "read"))


def learn_from_work(work: dict, *, direction: int = 1, weight: float = 0.6,
                    dampen_common: bool = True, verbose: bool = True,
                    only_tags: list[str] | None = None, reason: str = "") -> list[str]:
    """按一部作品的标签自动微调画像。

    设计取舍：一次只加一点点（默认 0.6）。当前只对「套路标签」
    （formula_tags）额外打折；**没有**实现基于 tag_df 的 IDF 加权
    （文档曾宣称有，属过度承诺，此处按真实实现更正）。
    """
    prof = load_profile()
    decayed = apply_time_decay(prof, verbose=verbose)
    tw = prof["tag_weights"]
    formula = prof.get("formula_tags") or {}
    changes = []
    want = {x.strip() for x in only_tags} if only_tags else None
    for t in work.get("tags") or []:
        t = (t or "").strip()
        if not t:
            continue
        if want is not None and t not in want:
            continue          # 定向模式：只动指定的标签，不误伤其它偏好
        delta = weight
        if dampen_common and t in formula:
            delta = weight * 0.4          # 套路标签：微弱加权，别让它主导
        if direction < 0 and t in prof["blocked_tags"]:
            continue
        new = clamp_tag_weight(tw.get(t, 1.0) + delta * direction)
        if new != tw.get(t):
            tw[t] = new
            changes.append(f"  {t}  {new - delta*direction:5.2f} → {new:5.2f}")
    if changes or decayed:
        # 只有真的改了画像才落盘 / 记 history：空改动（标签全不匹配、或全是
        # 已拉黑标签）也写一条 like/dislike，会让历史被无意义的记录灌满，
        # 还会让 already_learned 误判"这本书已处理过"。（衰减的落盘由
        # apply_time_decay 的 decay 事件负责，这里只管权重变更事件。）
        save_profile(prof)
    if work.get("id") and changes:
        log_event("like" if direction > 0 else "dislike",
                  id=work["id"], source=work.get("source"), title=work.get("title"),
                  url=work.get("url"), tags=work.get("tags"), changes=changes,
                  reason=reason, only_tags=only_tags)
    if verbose and changes:
        print(f"  「{work.get('title')}」→ 画像调整 {len(changes)} 处：")
        print("\n".join(changes))
    return changes


def resolve_work(query: str) -> dict | None:
    """把「作品名 / URL / id」解析成带标签的作品。"""
    m = re.search(r"/works/(\d+)", query)
    if m:
        wid = m.group(1)
        # 已经在候选池里就直接用
        for w in load_pool():
            if w.get("id") == wid:
                return w
        ws = None
        try:
            ws = lnlib.kakuyomu_search(wid)
        except lnlib.FetchError as e:
            print(f"  搜索失败：{e}", file=sys.stderr)
        if ws:
            return next((w for w in ws if w.get("id") == wid), None)
        return None
    # 当作标题搜索
    try:
        ws = lnlib.kakuyomu_search(query)
    except lnlib.FetchError as e:
        print(f"  搜索失败：{e}", file=sys.stderr)
        return None
    if not ws:
        return None
    q = query.strip()
    exact = [w for w in ws if w.get("title", "").strip() == q]
    if exact:
        return exact[0]
    # 宽松匹配：查询串是标题的子串（例如省略了 ～副标题～）。
    # 但**有歧义就不猜**：多个候选都含该子串时，取第一条会用错作品的标签
    # 污染画像（和下面"不随便返回第一条"是同一个理由）。
    partial = [w for w in ws if q and q in (w.get("title") or "")]
    if len(partial) == 1:
        return partial[0]
    if partial:
        print(f"  「{q}」匹配到多部作品，无法确定是哪一本：", file=sys.stderr)
        for w in partial[:3]:
            print(f"    - {w.get('title')}", file=sys.stderr)
        return None
    # 没有任何像样的匹配：**不能**随便返回第一条，否则会用错作品的标签污染画像
    print(f"  未精确匹配到「{q}」。最接近的候选：", file=sys.stderr)
    for w in ws[:3]:
        print(f"    - {w.get('title')}", file=sys.stderr)
    print("  想用其中某一本，请把完整标题或 URL 再喂一次。", file=sys.stderr)
    return None


# ------------------------------------------------------------------ 打分

def score_work(w: dict, prof: dict) -> tuple[float, list[str], list[str]]:
    tags = [t.strip() for t in (w.get("tags") or []) if t.strip()]
    tw = prof["tag_weights"]
    gw = prof["genre_weights"]
    blocked = prof["blocked_tags"]

    score = 0.0
    hits, reasons = [], []

    for t in tags:
        if t in blocked:
            return -999.0, [], [f"命中黑名单标签：{t}"]
        if t in tw:
            score += tw[t]
            hits.append(t)
            reasons.append(f"标签「{t}」+{tw[t]:g}")

    g = w.get("genre") or ""
    if g in gw:
        score += gw[g]
        reasons.append(f"类型「{w.get('genre_jp') or g}」+{gw[g]:g}")

    # 质量下限：过滤掉刚开坑、无人问津的
    rp = w.get("review_points") or 0
    if rp < prof["min_review_points"]:
        return -999.0, hits, [f"评价点不足（{rp} < {prof['min_review_points']}）"]
    if (w.get("episodes") or 0) < prof["min_episodes"]:
        return -999.0, hits, [f"章节数不足（{w.get('episodes')}）"]

    # 命中一个就够（用户明确要求：不要求全部命中，多命中只是分更高）。
    # 但"一个偏好标签都没命中、只靠类型分"的作品不算推荐，会淹掉结果。
    if len(hits) < prof["min_tag_hits"]:
        return -998.0, hits, ["没有任何偏好标签命中"]

    # 热度做温和封顶加成，避免"只看最火"（用户抱怨的正是这个）
    score += min(rp / 5000.0, 2.0)
    # 近 60 天有更新的小幅加成：连载中的书更可能有后续
    le = w.get("last_episode_at") or ""
    if le:
        try:
            if datetime.strptime(le, "%Y-%m-%d") >= datetime.now() - timedelta(days=60):
                score += 0.5
                reasons.append("近期有更新 +0.5")
        except ValueError:
            pass

    # —— 反公式化：套路标签越多扣越多，缓解"看多了要死人"的问题 ——
    formula = prof.get("formula_tags") or {}
    mis_tags = set(prof.get("misunderstanding_tags") or [])
    is_mis = bool(set(tags) & mis_tags)
    fhit = [t for t in tags if t in formula]
    if fhit:
        pen = sum(formula[t] for t in fhit)
        # 误解系作品常套着异世界/后宫壳子，惩罚打三折
        factor = 0.3 if is_mis else 1.0
        # 只命中少量偏好的作品，惩罚再打七折：
        # 用户要的是"命中一个就值得看"，别让套路扣分把它挤出榜
        if len(hits) <= 2:
            factor *= 0.7
        pen *= factor
        score -= pen
        tail = "（误解系减免）" if is_mis else ""
        reasons.append(f"公式化套路 -{pen:.1f}{tail}：{'、'.join(fhit[:5])}")

    # 多命中偏好标签本身就该加分（用户：多匹配最好）
    if len(hits) >= 2:
        multi = min((len(hits) - 1) * 0.8, 3.2)
        score += multi
        reasons.append(f"命中 {len(hits)} 个偏好标签 +{multi:.1f}")

    # —— 反套路/辨识度加成：画像外的稀有标签带来新鲜感 ——
    known = set(tw) | set(blocked)
    rare = [t for t in tags if t not in known and t not in formula]
    if rare and hits:
        # 只在"至少命中一个偏好"时才给辨识度加成。
        # 否则一本零命中但标签冷门的书会靠这个加成混进榜，违背推荐本意。
        bonus = min(len(rare) * 0.25, 1.5)
        score += bonus
        reasons.append(f"辨识度 +{bonus:.2f}（{len(rare)} 个非套路标签）")

    return score, hits, reasons


def review_points(w: dict) -> int:
    try:
        return int(w.get("review_points") or 0)
    except (TypeError, ValueError):
        return 0


def render_rows(rows: list[tuple[dict, float, list[str], list[str]]], limit: int,
                tiered: bool = False) -> str:
    """tiered=True 时分层输出：多命中（≥2）在前，单命中在后。

    单命中那一层按评价点排序——因为它是"只对一个口味"的作品，
    分数天然低，用热度排才能把真正的宝藏顶出来，而不是被埋在第 60 名。
    """
    out = []
    if tiered:
        multi = [r for r in rows if len(r[2]) >= 2]
        single = sorted([r for r in rows if len(r[2]) == 1],
                        key=lambda r: -review_points(r[0]))
        if multi:
            out.append(f"\n{'='*68}\n【A 档】命中 2 个以上偏好（{len(multi)} 部）——最对味\n{'='*68}")
            out.append(_render_block(multi, limit))
        if single:
            out.append(f"\n{'='*68}\n【B 档】只命中 1 个偏好（{len(single)} 部，按评价点排）"
                       f"——窄但可能更惊喜\n{'='*68}")
            out.append(_render_block(single, limit))
        return "\n".join(out)
    return _render_block(rows, limit)


def _render_block(rows, limit: int) -> str:
    out = []
    for i, (w, sc, hits, reasons) in enumerate(rows[:limit], 1):
        tags = "、".join((w.get("tags") or [])[:8])
        badge = f"[{'★'*min(len(hits),5)}{'☆'*max(0,5-len(hits))}] 命中{len(hits)}个偏好"
        out.append(
            f"\n{i}. 【{sc:.1f}分】{badge} {w.get('title','')}\n"
            f"   类型 {w.get('genre_jp') or w.get('genre')} · {w.get('serial_status')} · "
            f"{w.get('episodes')}话 · {lnlib.fmt_int(w.get('characters'))}字 · "
            f"评价{lnlib.fmt_int(w.get('review_points'))}pt · 更新 {w.get('last_episode_at')}\n"
            f"   作者 {w.get('author')}  |  来源 {','.join(w.get('origins') or [])}\n"
            f"   标签 {tags}\n"
            f"   命中：{'；'.join(reasons[:6]) or '（仅热度）'}\n"
            f"   {w.get('url')}"
        )
    return "\n".join(out)


def cmd_like(args) -> None:
    """把一部看过的作品喂给画像，自动按标签加权。"""
    for q in args.queries:
        print(f"→ 解析：{q}", file=sys.stderr)
        w = resolve_work(q)
        if not w:
            print(f"  跳过「{q}」（未匹配）。", file=sys.stderr)
            continue
        if already_learned(w["id"]):
            print(f"  「{w.get('title')}」已经喂过，跳过（避免权重重复膨胀）。")
            continue
        learn_from_work(w, direction=args.direction, weight=args.weight,
                        only_tags=args.only)
    prof = load_profile()
    strong = sorted(prof["tag_weights"].items(), key=lambda x: -x[1])[:8]
    print("\n当前最强的 8 个口味标签：" + "、".join(f"{t}({v:g})" for t, v in strong))


_MODE_LABEL = {"like": "+ 喜欢（加权画像）", "neutral": "· 中性（只记历史，不动权重）",
               "dislike": "− 不喜欢（降权画像）"}


def cmd_import(args) -> None:
    """从文件批量导入作品（一行一本，或用 | 分隔的导出记录）。

    支持普通文本：每行「标题」或「标题 | 作者 | URL」都行；EPUB 从文件名取书名。

    **导入 ≠ 喜欢**：默认 `--mode auto` —— 从「收藏导出」（n.novelia 收藏接口
    的 JSON）来的算**喜欢**、加权；纯文本/EPUB 的「看过」只记进历史（kind=read），
    **不动画像权重**（看过一本书不代表喜欢它）。想统一口径用
    `--mode like|neutral|dislike`。
    """
    paths = list(args.paths)
    # (书名, 该条目在 auto 模式下的默认动作)
    entries: list[tuple[str, str]] = []
    for p in paths:
        if p.lower().endswith(".epub"):
            base = os.path.basename(p)
            entries.append((os.path.splitext(base)[0], "neutral"))
            continue
        if not os.path.exists(p):
            print(f"  跳过不存在的文件：{p}", file=sys.stderr)
            continue
        text = open(p, encoding="utf-8", errors="replace").read()

        # 情况一：n.novelia.cc 收藏接口的 JSON 导出 —— 这是「收藏」，算喜欢
        # GET /api/user/favored-web/default 或 /api/user/favored-wenku/default
        parsed = None
        stripped = text.lstrip()
        if stripped[:1] in "{[":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        if parsed is not None:
            items = parsed.get("items") if isinstance(parsed, dict) else parsed
            if isinstance(items, dict):
                items = items.get("items") or items.get("content") or []
            got = 0
            for it in items or []:
                if not isinstance(it, dict):
                    continue
                # 网文用 titleJp/titleZh，文库用 volumeTitle/novelTitle
                for key in ("titleZh", "titleJp", "title", "novelTitleZh",
                            "novelTitleJp", "volumeTitle", "name"):
                    v = it.get(key)
                    if isinstance(v, str) and v.strip():
                        entries.append((v.strip(), "like"))
                        got += 1
                        break
            print(f"  从 JSON 导出解析出 {got} 条书名（收藏 → 喜欢）")
            continue

        # 情况二：纯文本，一行一本 —— 这是「看过」，默认中性
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            # 兼容「标题 | 作者 | url」「标题\t作者」等
            for sep in ("|", "\t"):
                if sep in raw:
                    raw = raw.split(sep)[0].strip()
                    break
            entries.append((raw, "neutral"))

    if not entries:
        die("没有可导入的内容。给一个文本文件，或一行一个书名。")

    n_like = n_neutral = n_dislike = 0
    ok = skip = fail = 0
    for name, auto_action in entries:
        action = args.mode if args.mode != "auto" else auto_action
        print(f"→ {name}", file=sys.stderr)
        w = resolve_work(name)
        if not w:
            fail += 1
            print("  未匹配", file=sys.stderr)
            continue
        if _learned_or_read(w["id"]):
            skip += 1
            continue
        if args.dry_run:
            print(f"  匹配到：{w.get('title')}")
            print(f"    标签：{'、'.join(w.get('tags') or [])}")
            print(f"    动作：{_MODE_LABEL[action]}")
            ok += 1
            continue
        if action == "neutral":
            # 只留痕，不改画像——「看过」不是「喜欢」
            log_event("read", id=w["id"], source=w.get("source"),
                      title=w.get("title"), url=w.get("url"), tags=w.get("tags"))
            n_neutral += 1
        else:
            learn_from_work(w, direction=1 if action == "like" else -1,
                            weight=args.weight)
            if action == "like":
                n_like += 1
            else:
                n_dislike += 1
        ok += 1
        time.sleep(0.6)
    print(f"\n导入完成：已处理 {ok} 本（喜欢 {n_like}、中性 {n_neutral}、"
          f"降权 {n_dislike}），跳过 {skip} 本（喂过/读过），未匹配 {fail} 本。")
    if ok:
        log_event("import", count=ok, mode=args.mode, weight=args.weight)


def cmd_history(args) -> None:
    """看画像的学习轨迹。"""
    hs = load_history()
    likes = [e for e in hs if e["kind"] == "like"]
    dislikes = [e for e in hs if e["kind"] == "dislike"]
    reads = [e for e in hs if e["kind"] == "read"]
    print(f"共 {len(hs)} 条记录：喜欢 {len(likes)}、不喜欢 {len(dislikes)}"
          f"、读过 {len(reads)}、导入 {len([e for e in hs if e['kind']=='import'])} 次")
    print(f"（记录文件：{HISTORY_PATH}）\n")
    for e in (hs[-args.last:] if args.last else []):
        if e["kind"] == "import":
            mode = f"（{e['mode']}）" if e.get("mode") else ""
            print(f"  {e['at']}  导入 {e.get('count')} 本{mode}")
            continue
        mark = {"like": "♥", "read": "·"}.get(e["kind"], "✗")
        print(f"  {e['at']} {mark} {e.get('title')}")
        print(f"      {e.get('url')}")
        tags = e.get("tags") or []
        if tags:
            print(f"      标签：{'、'.join(tags[:10])}")


# 反馈用语 → 相关标签。命中关键词就把改动收敛到这些标签上，
# 避免"整本降权"误伤用户真正喜欢的标签。
FEEDBACK_RULES: list[tuple[tuple[str, ...], list[str]]] = [
    (("后宫", "ハーレム", "harem"),            ["ハーレム"]),
    (("公式", "套路", "流水线", "模板", "看腻"), ["異世界転生", "異世界転移", "追放", "ざまぁ",
                                                 "チート", "無双", "主人公最強", "成り上がり"]),
    (("误解系", "误会", "装傻", "无自觉"),       ["勘違い", "無自覚"]),
    (("打脸", "爽文", "爽"),                    ["ざまぁ", "もう遅い"]),
    (("百合", "gl"),                            ["百合", "ガールズラブ", "GL"]),
    (("性转", "ts", "变身"),                    ["TS", "TS転生", "性転換", "TSっ子"]),
    (("慢生活", "治愈", "日常", "种田"),         ["スローライフ", "ほのぼの", "内政", "領地経営"]),
    (("病娇",),                                 ["ヤンデレ"]),
    (("恋爱", "甜", "糖", "拉扯"),               ["ラブコメ", "じれじれ", "溺愛"]),
]


def feedback_targets(reason: str) -> list[str]:
    low = (reason or "").lower()
    hits: list[str] = []
    for keys, tags in FEEDBACK_RULES:
        if any(k.lower() in low for k in keys):
            hits.extend(tags)
    if hits:
        return list(dict.fromkeys(hits))
    # 没识别出具体原因：退回"套路标签"（看腻了最可能针对的就是它们），
    # 而不是整本降权——否则会连带压低用户真正喜欢的 TS/百合 等偏好
    return list((load_profile().get("formula_tags") or {}).keys())


def cmd_feedback(args) -> None:
    """自然语言反馈：解析原因 → 只改相关标签 → 确认后才写入。"""
    work = resolve_work(args.work)
    if not work:
        die(f"没找到「{args.work}」。给完整标题或 kakuyomu URL。")

    tags = work.get("tags") or []
    proposed = [t for t in feedback_targets(args.reason) if t in tags]
    prof = load_profile()

    print(f"作品：{work.get('title')}")
    print(f"它的标签：{'、'.join(tags)}")
    print(f"你的反馈：{args.reason}")
    print()
    if proposed:
        print(f"我理解为针对这几个标签：{'、'.join(proposed)}")
        print("（其它标签不动，避免误伤你真正喜欢的偏好）")
    else:
        print("没从你的话里识别出它身上具体哪个标签，所以不好定向。")
        print(f"建议从它的标签里挑，例如：--only {' '.join(tags[:3])}")

    formula = prof.get("formula_tags") or {}
    eff = [t for t in (list(args.only) if args.only else proposed) if t in tags]
    print()
    print("预演（这一步没写任何东西）：")
    if eff:
        for t in eff:
            old_v = prof["tag_weights"].get(t, 1.0)
            # 与 learn_from_work 完全一致的算法，否则预演会骗人
            delta = args.weight * (0.4 if t in formula else 1.0)
            new_v = max(0.0, round(old_v - delta, 2))
            note = "（套路标签，按 40% 计）" if t in formula else ""
            print(f"  {t}: {old_v:g} → {new_v:g} {note}")
    else:
        print("  （无可改动的标签）")

    if not args.yes:
        print()
        print("确认执行请加 --yes；想只改自己指定的标签，用 --only 标签1 标签2。")
        return

    final_tags = list(args.only) if args.only else proposed
    if not final_tags:
        # 没有可定向的标签时**不写**：以前回退成 only_tags=None，
        # 会把整本书所有标签（含误解系偏好）一起降权，与注释承诺相反。
        print("\n没识别出可改的标签，未写入。想定向扣分请加 --only 标签1 标签2。")
        return
    if args.only:
        print(f"（按你的 --only 指定：{'、'.join(args.only)}）")
    learn_from_work(work, direction=-1, weight=args.weight,
                    only_tags=final_tags, reason=args.reason)
    print("\n已记录。当前最强的 8 个标签：")
    strong = sorted(load_profile()["tag_weights"].items(), key=lambda x: -x[1])[:8]
    print("  " + "、".join(f"{t}({v:g})" for t, v in strong))


def cmd_clinic(args) -> None:
    """口味诊所：从你喂过的作品统计「喜欢/不喜欢 与标签的相关性」。"""
    hs = [e for e in load_history() if e["kind"] in ("like", "dislike")]
    if len(hs) < args.min_samples:
        print(f"样本太少（{len(hs)} 条，需要 ≥{args.min_samples} 条）。")
        print("多喂几本（like/dislike/feedback）再来看，统计才有意义。")
        return
    from collections import defaultdict
    like_df: dict[str, int] = defaultdict(int)
    dislike_df: dict[str, int] = defaultdict(int)
    n_like = n_dis = 0
    for e in hs:
        ts = e.get("tags") or []
        if e["kind"] == "like":
            n_like += 1
            for t in ts:
                like_df[t.strip()] += 1
        else:
            n_dis += 1
            for t in ts:
                dislike_df[t.strip()] += 1

    print(f"样本：喜欢 {n_like} 本、不喜欢 {n_dis} 本\n")
    print("倾向于「喜欢」的标签（喜欢中出现率 − 不喜欢中出现率）：")
    alltags = set(like_df) | set(dislike_df)
    rows = []
    for t in alltags:
        lr = like_df[t] / n_like if n_like else 0
        dr = dislike_df[t] / n_dis if n_dis else 0
        rows.append((lr - dr, t, like_df[t], dislike_df[t]))
    rows.sort(reverse=True)
    for d, t, a, b in rows[: args.top]:
        if d <= 0:
            break
        print(f"  +{d:.2f}  {t}   （喜欢 {a} / 不喜欢 {b}）")
    print("\n倾向于「不喜欢」的标签：")
    for d, t, a, b in sorted(rows)[: args.top]:
        if d >= 0:
            break
        print(f"  {d:.2f}  {t}   （喜欢 {a} / 不喜欢 {b}）")
    print("\n提示：样本少时相关性可能只是巧合，别急着据此大改权重。")


def cmd_scan(args) -> None:
    """一次扫多个搜索词，合并去重后按偏好打分。

    用途：当某个口味在标签体系里没有精确对应词时（例如"误解系"，
    站内标签是宽泛的「勘違い」，一半是后宫喜剧），用多个更贴近的描述性
    搜索词去挖，再打分排序。比单个标签精准得多。
    """
    prof = load_profile()
    queries = args.queries or DEFAULT_SCAN_QUERIES
    pool: dict[str, dict] = {}
    for q in queries:
        print(f"→ 搜索：{q}", file=sys.stderr)
        try:
            for w in lnlib.kakuyomu_search(q):
                prev = pool.get(w["id"])
                if prev is None:
                    w["origins"] = [f"搜索:{q}"]
                    pool[w["id"]] = w
                else:
                    prev["tags"] = list(dict.fromkeys(prev.get("tags", []) + w.get("tags", [])))
                    prev["origins"] = list(dict.fromkeys(prev["origins"] + [f"搜索:{q}"]))
        except lnlib.FetchError as e:
            print(f"  失败：{e}", file=sys.stderr)
        time.sleep(0.8)

    save_pool(list(pool.values()))
    scored = []
    for w in pool.values():
        sc, hits, reasons = score_work(w, prof)
        if sc > -900:
            scored.append((w, sc, hits, reasons))
    scored.sort(key=lambda x: -x[1])
    print(f"扫了 {len(queries)} 个搜索词，去重后候选 {len(pool)} 部 → "
          f"通过过滤 {len(scored)} 部，Top {args.top}：")
    print(render_rows(scored, args.top))

    if args.report:
        write_report(scored[: args.top], f"扫描推荐（{'/'.join(queries[:5])}…）")


def write_report(rows, title: str) -> None:
    prof = load_profile()
    os.makedirs(REPORT_DIR, exist_ok=True)
    base = os.path.join(REPORT_DIR, f"recommend-{time.strftime('%Y%m%d-%H%M')}")
    path = base + ".md"
    n = 2
    while os.path.exists(path):          # 同一分钟内多次生成不要互相覆盖
        path = f"{base}-{n}.md"
        n += 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 轻小说推荐：{title}\n\n生成时间：{datetime.now():%Y-%m-%d %H:%M}\n\n")
        f.write("规则：**命中一个偏好即可推荐**，命中越多分越高；"
                "只命中 1 个的按评价点单独排在后面（窄，但常有被埋没的宝藏）。\n\n")
        f.write(f"偏好标签：{', '.join(prof['tag_weights'])}\n\n")
        for i, (w, sc, hits, reasons) in enumerate(rows, 1):
            f.write(f"## {i}. [{w.get('title')}]({w.get('url')})  ·  {sc:.1f}分"
                    f"  ·  命中 {len(hits)} 个偏好\n\n")
            f.write(f"- 类型：{w.get('genre_jp')}｜{w.get('serial_status')}｜{w.get('episodes')} 话｜"
                    f"{lnlib.fmt_int(w.get('characters'))} 字｜评价 {lnlib.fmt_int(w.get('review_points'))}pt\n")
            f.write(f"- 作者：{w.get('author')}｜最近更新：{w.get('last_episode_at')}\n")
            f.write(f"- 标签：{'、'.join(w.get('tags') or [])}\n")
            if w.get("catchphrase"):
                f.write(f"- 一句话：{lnlib.unescape(w['catchphrase'])}\n")
            f.write(f"- 命中：{'；'.join(reasons)}\n")
            f.write(f"- 来源：{','.join(w.get('origins') or [])}\n\n")
    print(f"\n报告已写入：{path}")


def cmd_profile(args) -> None:
    prof = load_profile()
    print("当前偏好画像：", PROFILE_PATH)
    print("\n标签权重（越高越优先）：")
    for t, v in sorted(prof["tag_weights"].items(), key=lambda x: -x[1]):
        print(f"  {v:5.1f}  {t}")
    print("\n类型权重：", prof["genre_weights"])
    print("黑名单标签：", prof["blocked_tags"])
    print(
        f"下限：评价点 {prof['min_review_points']} · 章节 {prof['min_episodes']} · "
        f"最少命中标签 {prof['min_tag_hits']}"
    )
    dec = prof.get("decay") or {}
    print(
        f"自升级：半衰期 {dec.get('halflife_days')} 天向中性收缩 · "
        f"上次结算 {dec.get('last') or '（未开始，首次反馈时立基线）'}"
    )


def cmd_learn(args) -> None:
    prof = load_profile()
    decayed = apply_time_decay(prof)
    changed = []
    for t in args.like or []:
        prof["tag_weights"][t] = clamp_tag_weight(prof["tag_weights"].get(t, 1.0) + 1.0)
        if t in prof["blocked_tags"]:
            prof["blocked_tags"].remove(t)
        changed.append(f"  +1.0  {t}  → {prof['tag_weights'][t]}")
    for t in args.dislike or []:
        prof["tag_weights"][t] = clamp_tag_weight(prof["tag_weights"].get(t, 1.0) - 1.0)
        changed.append(f"  -1.0  {t}  → {prof['tag_weights'][t]}")
    for t in args.skip or []:
        if t not in prof["blocked_tags"]:
            prof["blocked_tags"].append(t)
        changed.append(f"  屏蔽  {t}")
    if changed or decayed:
        save_profile(prof)
    if changed:
        print("已更新偏好画像：")
        print("\n".join(changed))
    elif decayed:
        print(f"（画像已按时间向中性衰减 {decayed} 个标签，未指定任何 --like/--dislike/--skip）")
    else:
        print("没有改动。用 --like / --dislike / --skip 指定标签。")


def cmd_new(args) -> None:
    prof = load_profile()
    tags = args.tags or list(prof["tag_weights"].keys())[:6]
    works = collect(tags, include_rankings=True, pages=args.pages,
                    genres=top_genres(prof))
    save_pool(works)
    cutoff = datetime.now() - timedelta(days=args.days)
    fresh = []
    for w in works:
        le = w.get("last_episode_at") or ""
        try:
            when = datetime.strptime(le, "%Y-%m-%d")
        except ValueError:
            continue
        if when >= cutoff:
            fresh.append(w)
    scored = []
    for w in fresh:
        sc, hits, reasons = score_work(w, prof)
        if sc > -900:
            scored.append((w, sc, hits, reasons))
    scored.sort(key=lambda x: (-x[1], x[0].get("last_episode_at") or ""))
    print(f"候选 {len(works)} 部，其中 {len(fresh)} 部在近 {args.days} 天内有更新，"
          f"符合偏好 {len(scored)} 部：")
    print(render_rows(scored, args.top))


def cmd_recommend(args) -> None:
    prof = load_profile()
    if args.pool and os.path.exists(POOL_PATH):
        works = load_pool()
        print(f"使用本地候选池（{len(works)} 部）", file=sys.stderr)
    else:
        tags = args.tags or list(prof["tag_weights"].keys())[:6]
        works = collect(tags, include_rankings=True, pages=args.pages,
                        genres=top_genres(prof))
        save_pool(works)
    if args.tag:
        works = [w for w in works if args.tag in (w.get("tags") or [])]
    if args.all_of:
        # 对应站点搜索语法里的 `标签$`：要求全部标签同时命中
        works = [w for w in works
                 if all(t in (w.get("tags") or []) for t in args.all_of)]
    scored = []
    for w in works:
        sc, hits, reasons = score_work(w, prof)
        if sc > -900:
            scored.append((w, sc, hits, reasons))
    scored.sort(key=lambda x: -x[1])
    # B 档门槛：弱命中要有硬实力（分数够或评价点极高）才配被推荐
    floor_s = prof.get("weak_hit_min_score", 3.0)
    floor_p = prof.get("weak_hit_min_points", 20000)
    before = len(scored)
    scored = [r for r in scored
              if len(r[2]) >= 2 or r[1] >= floor_s or review_points(r[0]) >= floor_p]
    dropped = before - len(scored)

    n_multi = sum(1 for r in scored if len(r[2]) >= 2)
    n_single = sum(1 for r in scored if len(r[2]) == 1)
    print(f"候选 {len(works)} 部 → 通过过滤 {len(scored)} 部"
          f"（命中≥2 的 {n_multi} 部、只命中 1 的 {n_single} 部）"
          + (f"；另剔除 {dropped} 部弱命中" if dropped else ""))
    if not args.tier and args.all_of:
        print("提示：--all-of 是硬性全命中；不加它时命中一个即可推荐。")
    print(render_rows(scored, args.top, tiered=args.tier))

    if args.report:
        write_report(scored[: args.top], "按偏好推荐")


def cmd_author(args) -> None:
    prof = load_profile()
    name = args.name
    print(f"→ 搜索作者：{name}", file=sys.stderr)
    try:
        works = lnlib.kakuyomu_search(name)
    except lnlib.FetchError as e:
        print(f"  搜索失败：{e}", file=sys.stderr)
        return
    own = [w for w in works if (w.get("author") or "").strip() == name.strip()]
    listed = own or works
    scored = []
    for w in listed:
        sc, hits, reasons = score_work(w, prof)
        if sc > -900:                 # 与 recommend/new/interesting 保持一致：
            scored.append((w, sc, hits, reasons))   # 拉黑标签的作品不进榜
    scored.sort(key=lambda x: -x[1])
    note = "同作者作品" if own else "关键词命中的作品（未精确匹配到作者名）"
    print(f"{note}，共 {len(scored)} 部：")
    print(render_rows(scored, args.top))


def cmd_interesting(args) -> None:
    """从已有候选池里统计标签频次，帮你发现还没加进画像的标签。"""
    works = load_pool()
    if not works:
        die("候选池为空，先跑一次 recommend 或 new。")
    prof = load_profile()
    freq: dict[str, int] = {}
    for w in works:
        for t in w.get("tags") or []:
            t = t.strip()
            if t:
                freq[t] = freq.get(t, 0) + 1
    known = set(prof["tag_weights"]) | set(prof["blocked_tags"])
    unknown = [(t, c) for t, c in freq.items() if t not in known]
    unknown.sort(key=lambda x: -x[1])
    print(f"候选池 {len(works)} 部的标签频次（未在画像中的，出现≥{args.min_count} 次）：")
    for t, c in unknown:
        if c >= args.min_count:
            print(f"  {c:3d}×  {t}")
    print("\n想加进画像：python3 lnfind.py learn --like 标签名")


# ------------------------------------------------------------------ CLI

def main() -> None:
    p = argparse.ArgumentParser(description="轻小说发现工具：多源采集 + 偏好打分")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("profile", help="查看偏好画像").set_defaults(fn=cmd_profile)

    lp = sub.add_parser("learn", help="调整偏好画像")
    lp.add_argument("--like", nargs="*", help="加权的标签")
    lp.add_argument("--dislike", nargs="*", help="降权的标签")
    lp.add_argument("--skip", nargs="*", help="拉黑的标签")
    lp.set_defaults(fn=cmd_learn)

    np_ = sub.add_parser("new", help="近期更新/新作")
    np_.add_argument("--tags", nargs="*", help="用哪些标签抓（默认取画像里权重最高的几个）")
    np_.add_argument("--days", type=int, default=30)
    np_.add_argument("--pages", type=int, default=1)
    np_.add_argument("--top", type=int, default=15)
    np_.set_defaults(fn=cmd_new)

    rp = sub.add_parser("recommend", help="按偏好推荐")
    rp.add_argument("--tags", nargs="*", help="用哪些标签抓")
    rp.add_argument("--tag", help="只保留含该标签的作品")
    rp.add_argument("--all-of", nargs="*", dest="all_of",
                    help="硬性要求同时含全部这些标签（默认不开启：命中一个即可）")
    rp.add_argument("--tier", action="store_true", default=True,
                    help="分层展示：多命中在前，单命中按评价点排（默认开启）")
    rp.add_argument("--no-tier", dest="tier", action="store_false",
                    help="关闭分层，按总分混排")
    rp.add_argument("--pool", action="store_true", help="不重新抓取，用本地候选池")
    rp.add_argument("--pages", type=int, default=1)
    rp.add_argument("--top", type=int, default=20)
    rp.add_argument("--report", action="store_true", help="同时输出 Markdown 报告")
    rp.set_defaults(fn=cmd_recommend)

    ap = sub.add_parser("author", help="找某作者的作品")
    ap.add_argument("name")
    ap.add_argument("--top", type=int, default=15)
    ap.set_defaults(fn=cmd_author)

    lk = sub.add_parser("like", help="喂一部看过的作品，按标签自动加权画像")
    lk.add_argument("queries", nargs="*", help="作品名 / kakuyomu URL / id")
    lk.add_argument("--weight", type=float, default=0.6, help="每标签加权步长（默认 0.6）")
    lk.add_argument("--only", nargs="*", help="只调整这些标签（定向反馈，避免误伤其它偏好）")
    lk.set_defaults(fn=cmd_like, direction=1)

    dk = sub.add_parser("dislike", help="喂一部不喜欢的作品，反向降权")
    dk.add_argument("queries", nargs="*", help="作品名 / kakuyomu URL / id")
    dk.add_argument("--weight", type=float, default=0.6)
    dk.add_argument("--only", nargs="*", help="只调整这些标签")
    dk.set_defaults(fn=cmd_like, direction=-1)

    im = sub.add_parser("import", help="批量导入作品（收藏→喜欢、看过→中性；默认不动权重）")
    im.add_argument("paths", nargs="*", help="txt（一行一本）或 epub 路径")
    im.add_argument("--mode", choices=["auto", "like", "neutral", "dislike"],
                    default="auto",
                    help="auto=收藏导出算喜欢、纯文本/EPUB 看过算中性（默认）；"
                         "或统一 like|neutral|dislike")
    im.add_argument("--weight", type=float, default=0.4,
                    help="每标签加权步长（默认 0.4，仅 like/dislike 生效）")
    im.add_argument("--dry-run", action="store_true", help="只显示匹配结果，不写画像")
    im.set_defaults(fn=cmd_import)

    fb = sub.add_parser("feedback", help="用自然语言反馈一部作品（先预演，--yes 才写入）")
    fb.add_argument("work", help="作品名或 URL")
    fb.add_argument("reason", help="你的反馈，如「后宫太多」「太公式化了」")
    fb.add_argument("--only", nargs="*", help="强制只改这些标签")
    fb.add_argument("--weight", type=float, default=0.5)
    fb.add_argument("--yes", action="store_true", help="确认执行（不加只预演）")
    fb.set_defaults(fn=cmd_feedback)

    cl = sub.add_parser("clinic", help="口味诊所：统计喜好与标签的相关性")
    cl.add_argument("--min-samples", type=int, default=6)
    cl.add_argument("--top", type=int, default=10)
    cl.set_defaults(fn=cmd_clinic)

    hi = sub.add_parser("history", help="查看画像学习轨迹")
    hi.add_argument("--last", type=int, default=20)
    hi.set_defaults(fn=cmd_history)

    sc = sub.add_parser("scan", help="扫描多个搜索词，挖宽泛标签下的稀缺口味")
    sc.add_argument("queries", nargs="*", help="搜索词（默认一组误解系相关词）")
    sc.add_argument("--top", type=int, default=20)
    sc.add_argument("--report", action="store_true", help="输出 Markdown 报告")
    sc.set_defaults(fn=cmd_scan)

    ip = sub.add_parser("interesting", help="发现候选新标签")
    ip.add_argument("--min-count", type=int, default=2)
    ip.set_defaults(fn=cmd_interesting)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
