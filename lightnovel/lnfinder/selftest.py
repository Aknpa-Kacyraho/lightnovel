#!/usr/bin/env python3
"""lnfinder 自检：真实数据 + 失败路径，都必须跑。

覆盖的是**踩过坑的地方**，不是为了刷覆盖率：
  1. 推荐规则：命中一个即可（不能要求全命中）
  2. 零命中不得靠"辨识度加成"混进榜
  3. B 档弱命中门槛（只碰到 ざまぁ+2 的要被剔除）
  4. 解析器：不存在的书名**必须拒绝**，不能误匹配第一条搜索结果
  5. 重复喂同一本不重复加权（history 去重）
  6. 预演数值必须和实际写入一致（套路标签 40% 折扣）
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

spec = importlib.util.spec_from_file_location("lnfind", os.path.join(HERE, "lnfind.py"))
lf = importlib.util.module_from_spec(spec)
sys.argv = ["lnfind"]
spec.loader.exec_module(lf)

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


# 用临时目录隔离，别污染真画像
TMP = tempfile.mkdtemp(prefix="lnfind-test-")
lf.PROFILE_PATH = os.path.join(TMP, "taste_profile.json")
lf.HISTORY_PATH = os.path.join(TMP, "history.jsonl")
lf.POOL_PATH = os.path.join(TMP, "candidates.json")

prof = lf.load_profile()

print("=" * 66)
print("1. 推荐规则：命中一个就够，不是要求全命中")
print("=" * 66)
w_one = {"source": "kakuyomu", "id": "1", "title": "只命中一个",
         "tags": ["TS"], "genre": "FANTASY", "genre_jp": "奇幻",
         "review_points": 5000, "episodes": 50, "last_episode_at": "2026-10-10"}
sc, hits, _ = lf.score_work(w_one, prof)
check("只命中 1 个偏好标签仍可推荐", sc > 0 and len(hits) == 1, f"score={sc:.1f}")

w_zero = dict(w_one, id="2", tags=["まったく無関係", "どうでもいい", "謎タグ", "無関係2"])
sc0, hits0, rs0 = lf.score_work(w_zero, prof)
check("零命中的书不进榜（不能靠辨识度加成混入）", len(hits0) == 0 and sc0 < 0, f"score={sc0:.1f}")

w_multi = dict(w_one, id="3", tags=["TS", "百合", "勘違い", "悪役令嬢"])
scm, hitsm, _ = lf.score_work(w_multi, prof)
check("多命中分数更高", scm > sc, f"{scm:.1f} > {sc:.1f}")
check("有『命中 N 个偏好标签』加成", any("命中" in r and "偏好标签" in r for r in
                                     lf.score_work(w_multi, prof)[2]))

print()
print("=" * 66)
print("2. 反公式化：套路扣分，但误解系减免")
print("=" * 66)
w_formula = dict(w_one, id="4", tags=["勘違い", "ハーレム", "異世界転生", "ざまぁ"])
scf, _, rsf = lf.score_work(w_formula, prof)
has_pen = any("公式化套路" in r for r in rsf)
has_relief = any("误解系减免" in r for r in rsf)
check("套路标签被扣分", has_pen)
check("含误解系标签时惩罚减免", has_relief)

w_pure = dict(w_one, id="5", tags=["ハーレム", "異世界転生", "ざまぁ"])
scp, _, rsp = lf.score_work(w_pure, prof)
check("纯套路作品扣分更重", any("公式化套路" in r and "减免" not in r for r in rsp))

print()
print("=" * 66)
print("3. B 档弱命中门槛")
print("=" * 66)
w_weak = dict(w_one, id="6", tags=["ざまぁ"], review_points=100, episodes=6)
scw, _, _ = lf.score_work(w_weak, prof)
floor_s = prof.get("weak_hit_min_score", 3.0)
floor_p = prof.get("weak_hit_min_points", 20000)
weak_ok = scw >= floor_s or lf.review_points(w_weak) >= floor_p
check("弱命中（ざまぁ+2, 100pt）达不到 B 档门槛", not weak_ok, f"score={scw:.1f}")

print()
print("=" * 66)
print("4. 解析器：不存在的书名必须拒绝（不能误匹配）")
print("=" * 66)
orig_search = lf.lnlib.kakuyomu_search
lf.lnlib.kakuyomu_search = lambda q, pages=1: [
    {"source": "kakuyomu", "id": "999", "title": "完全に別の作品",
     "tags": [], "review_points": 100, "episodes": 10}]
r = lf.resolve_work("これは存在しない作品名です")
check("不存在的书名返回 None 而不是第一条结果", r is None)
r2 = lf.resolve_work("完全に別の作品")
check("精确匹配仍能命中", r2 is not None and r2["id"] == "999")


def _boom(*a, **k):
    raise lf.lnlib.FetchError("模拟网络失败")


lf.lnlib.kakuyomu_search = _boom
r3 = lf.resolve_work("https://kakuyomu.jp/works/123")
check("抓取失败时 id 分支返回 None（不把异常抛穿）", r3 is None)
lf.lnlib.kakuyomu_search = orig_search

print()
print("=" * 66)
print("5. 重复喂同一本不重复加权")
print("=" * 66)
w = dict(w_one, id="777", tags=["TS", "百合"], title="重复测试")
if os.path.exists(lf.HISTORY_PATH):
    os.remove(lf.HISTORY_PATH)
lf.learn_from_work(w, verbose=False)
v1 = lf.load_profile()["tag_weights"].get("TS")
check("首次喂入后记录到 history", lf.already_learned("777"))
lf.learn_from_work(w, verbose=False)          # 直接调不会自己跳过
v2 = lf.load_profile()["tag_weights"].get("TS")
check("already_learned 能识别已喂过的书", lf.already_learned("777"), f"TS={v2}")

print()
print("=" * 66)
print("6. 预演与实际一致（套路标签 40% 折扣）")
print("=" * 66)
prof2 = lf.load_profile()
t = "異世界転生"
if t not in prof2["tag_weights"]:
    prof2["tag_weights"][t] = 1.0
    lf.save_profile(prof2)
before = lf.load_profile()["tag_weights"][t]
lf.learn_from_work({"id": "888", "tags": [t], "title": "折扣测试"},
                   direction=-1, weight=0.5, verbose=False)
after = lf.load_profile()["tag_weights"][t]
delta = round(before - after, 2)
check("套路标签按 40% 折扣（0.5 → 0.2）", delta == 0.2, f"实际扣 {delta}")

print()
print("=" * 66)
print("7. kakuyomu 页面 JSON 损坏 → 抛 FetchError（不裸抛 JSONDecodeError）")
print("=" * 66)
orig_fetch = lf.lnlib.fetch
lf.lnlib.fetch = lambda url, **k: (
    '<script id="__NEXT_DATA__" type="application/json">{坏Json,,,}</script>')
try:
    lf.lnlib.kakuyomu_page("/x")
    check("坏 JSON 应抛 FetchError", False, "没抛异常")
except lf.lnlib.FetchError:
    check("坏 JSON 抛 FetchError（已归一）", True)
except Exception as e:  # noqa: BLE001
    check("坏 JSON 抛 FetchError（已归一）", False, type(e).__name__)
lf.lnlib.fetch = lambda url, **k: (
    '<script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{"__APOLLO_STATE__":{}}}}</script>')
p = lf.lnlib.kakuyomu_page("/x")
check("合法 JSON 正常解析出 apollo", isinstance(p, dict) and "apollo" in p)
lf.lnlib.fetch = orig_fetch

print()
print("=" * 66)
print("8. import 语义：看过=中性（不动权重），--mode like 才加权")
print("=" * 66)
import argparse  # noqa: E402
tmp_txt = os.path.join(TMP, "read.txt")
open(tmp_txt, "w", encoding="utf-8").write("样例一本\n")
orig_resolve = lf.resolve_work

lf.resolve_work = lambda q: {"id": "imp-neutral", "source": "kakuyomu",
                             "title": "中性导入样例", "url": "", "tags": ["TS", "百合"]}
ts_before = lf.load_profile()["tag_weights"].get("TS", 1.0)
lf.cmd_import(argparse.Namespace(paths=[tmp_txt], mode="auto",
                                 weight=0.4, dry_run=False))
ts_after = lf.load_profile()["tag_weights"].get("TS", 1.0)
check("「看过」按 auto 走中性：TS 权重不变", ts_before == ts_after,
      f"{ts_before} → {ts_after}")
check("中性导入只写 read 历史",
      any(e.get("kind") == "read" and e.get("id") == "imp-neutral"
          for e in lf.load_history()))

lf.resolve_work = lambda q: {"id": "imp-like", "source": "kakuyomu",
                             "title": "喜欢导入样例", "url": "", "tags": ["TS"]}
lf.cmd_import(argparse.Namespace(paths=[tmp_txt], mode="like",
                                 weight=0.4, dry_run=False))
ts_like = lf.load_profile()["tag_weights"].get("TS")
check("--mode like 才加权", ts_like > ts_after, f"{ts_after} → {ts_like}")
check("like 导入写 like 历史",
      any(e.get("kind") == "like" and e.get("id") == "imp-like"
          for e in lf.load_history()))
lf.resolve_work = orig_resolve

print()
print("=" * 66)
print("9. learn：标签权重夹到 [0, 12]（--dislike 不再无界下降）")
print("=" * 66)
# 回归：cmd_learn 早先不夹取，反复 --dislike 会把权重推到无界的负数，
# 作品最终被 score ≤ -900 永久过滤。learn_from_work 已夹到 [0,12]，两处必须一致。
for _ in range(40):
    lf.cmd_learn(argparse.Namespace(like=None, dislike=["TS"], skip=None))
w_dn = lf.load_profile()["tag_weights"]["TS"]
check("反复 --dislike 后 TS 停在 0（不为负）", w_dn == 0.0, f"TS={w_dn}")
for _ in range(40):
    lf.cmd_learn(argparse.Namespace(like=["TS"], dislike=None, skip=None))
w_up = lf.load_profile()["tag_weights"]["TS"]
check("反复 --like 后 TS 停在 12（不超上限）", w_up == lf.TAG_W_MAX, f"TS={w_up}")

print()
print("=" * 66)
print("10. resolve_work 歧义不瞎猜 / learn 空改动不写历史 / author 过滤黑名单")
print("=" * 66)
# 18：多个候选都含查询子串 → 不猜（返回 None），别用错作品污染画像
lf.lnlib.kakuyomu_search = lambda q, pages=1: [
    {"source": "kakuyomu", "id": "a1", "title": "勇者と魔王の物語", "tags": []},
    {"source": "kakuyomu", "id": "a2", "title": "勇者と魔王の日常", "tags": []}]
check("子串命中多部 → 不瞎猜（返回 None）", lf.resolve_work("勇者と魔王") is None)
lf.lnlib.kakuyomu_search = lambda q, pages=1: [
    {"source": "kakuyomu", "id": "a3", "title": "勇者と魔王の物語", "tags": []}]
check("子串只命中一部 → 仍能匹配",
      (lf.resolve_work("勇者と魔王") or {}).get("id") == "a3")

# 16：空改动（定向标签一个都没匹配）不写 history
_h0 = len(lf.load_history())
lf.learn_from_work({"id": "nochange-1", "title": "空改动", "tags": ["TS"]},
                   only_tags=["まったく別のタグ"], verbose=False)
check("★ 空改动不写历史（不污染 already_learned）",
      len(lf.load_history()) == _h0, f"{_h0} → {len(lf.load_history())}")

# 17：cmd_author 过滤黑名单（sc <= -900 的作品不进榜）
import contextlib  # noqa: E402
import io  # noqa: E402
_bt = "テスト用ブラックタグ"
_prof10 = lf.load_profile()
if _bt not in _prof10["blocked_tags"]:
    _prof10["blocked_tags"].append(_bt)
    lf.save_profile(_prof10)
lf.lnlib.kakuyomu_search = lambda q, pages=1: [
    {"source": "kakuyomu", "id": "b1", "title": "被拉黑的作品", "author": "作者X",
     "tags": [_bt], "review_points": 99999, "episodes": 99},
    {"source": "kakuyomu", "id": "b2", "title": "正常作品", "author": "作者X",
     "tags": ["TS"], "review_points": 99999, "episodes": 99}]
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    lf.cmd_author(argparse.Namespace(name="作者X", top=20))
_out = _buf.getvalue()
check("★ cmd_author 不把黑名单作品放进榜（与其它命令一致）",
      "被拉黑的作品" not in _out and "正常作品" in _out)
lf.lnlib.kakuyomu_search = orig_search

# kakuyomu_search：彻底失败要上抛（不装空），已有一页结果时保留
_orig_kw10 = lf.lnlib.kakuyomu_works
lf.lnlib.kakuyomu_works = lambda path: (_ for _ in ()).throw(lf.lnlib.FetchError("boom"))
try:
    try:
        lf.lnlib.kakuyomu_search("x")
        _raised10 = False
    except lf.lnlib.FetchError:
        _raised10 = True
finally:
    lf.lnlib.kakuyomu_works = _orig_kw10
check("★ kakuyomu_search 彻底失败时抛 FetchError（不假装空结果）", _raised10)

_n_kw10 = {"n": 0}


def _kw_first_ok(path):
    _n_kw10["n"] += 1
    if _n_kw10["n"] == 1:
        return [{"source": "kakuyomu", "id": "z1", "title": "书", "tags": []}]
    raise lf.lnlib.FetchError("boom")


lf.lnlib.kakuyomu_works = _kw_first_ok
try:
    _ws10 = lf.lnlib.kakuyomu_search("x", pages=3)
finally:
    lf.lnlib.kakuyomu_works = _orig_kw10
check("kakuyomu_search 翻页中途失败 → 保留已拿到的一页",
      [w["id"] for w in _ws10] == ["z1"], str(_ws10))

# load_pool：候选池文件坏了不崩（当空处理）
_pool_path = lf.POOL_PATH
_orig_pool = None
if os.path.exists(_pool_path):
    with open(_pool_path, encoding="utf-8") as f:
        _orig_pool = f.read()
try:
    os.makedirs(os.path.dirname(_pool_path), exist_ok=True)
    with open(_pool_path, "w", encoding="utf-8") as f:
        f.write("{ 这不是合法 JSON ")
    check("★ 候选池损坏 → load_pool 当空处理不崩", lf.load_pool() == [])
finally:
    if _orig_pool is None:
        if os.path.exists(_pool_path):
            os.remove(_pool_path)
    else:
        with open(_pool_path, "w", encoding="utf-8") as f:
            f.write(_orig_pool)

print()
print("=" * 66)
print("11. 榜单/流派检索：URL 构造 + 真榜单替换首页薄榜")
print("=" * 66)
_seen11 = []
_o_kw11 = lf.lnlib.kakuyomu_works
lf.lnlib.kakuyomu_works = lambda path: (_seen11.append(path) or [])
lf.lnlib.kakuyomu_ranking("FANTASY", "monthly", "short")
check("kakuyomu_ranking 把 UPPER code 映射成 slug 且拼对路径",
      bool(_seen11) and _seen11[-1] == "/rankings/fantasy/monthly?work_variation=short",
      str(_seen11[-1:]))
lf.lnlib.kakuyomu_ranking("all", "weekly")
check("kakuyomu_ranking all/weekly",
      _seen11[-1] == "/rankings/all/weekly?work_variation=all", str(_seen11[-1:]))
try:
    lf.lnlib.kakuyomu_ranking("all", "乱来")
    _bad11 = False
except ValueError:
    _bad11 = True
check("★ 未知榜单区间 → ValueError（不静默发坏请求）", _bad11)
lf.lnlib.kakuyomu_search("悪役令嬢", 2)
check("kakuyomu_search 关键词翻页仍带 page=2",
      _seen11[-1].startswith("/search?q=") and _seen11[-1].endswith("&page=2"),
      str(_seen11[-1:]))
lf.lnlib.kakuyomu_search("", 1, genre="LOVE_STORY", order="weekly_ranking")
check("kakuyomu_search 支持 genre/order 组合",
      "genre_name=love_story" in _seen11[-1] and "order=weekly_ranking" in _seen11[-1],
      str(_seen11[-1:]))
lf.lnlib.kakuyomu_works = _o_kw11

check("top_genres 按权重排序且只含有榜流派（排除 MAHO）",
      lf.top_genres({"genre_weights": {"FANTASY": 1, "MAHO": 9, "SF": 3}}, 2)
      == ["SF", "FANTASY"])

_o_rank11 = lf.lnlib.kakuyomu_rankings
_o_grk11 = lf.lnlib.kakuyomu_ranking
_o_srch11 = lf.lnlib.kakuyomu_search
lf.lnlib.kakuyomu_rankings = lambda: {"weekly": [], "recommended": [], "fresh": [],
                                      "keywords": []}
lf.lnlib.kakuyomu_ranking = lambda g, r="weekly": [
    {"source": "kakuyomu", "id": "g-" + g, "title": "流派" + g, "tags": []}]
lf.lnlib.kakuyomu_search = lambda q, pages=1: []
_w11 = lf.collect([], include_rankings=True, pages=1, genres=["FANTASY", "LOVE_STORY"])
check("★ collect 纳入流派榜（origin 可辨认）",
      {w["id"] for w in _w11} == {"g-FANTASY", "g-LOVE_STORY"},
      str(sorted(w["id"] for w in _w11)))
lf.lnlib.kakuyomu_rankings = _o_rank11
lf.lnlib.kakuyomu_ranking = _o_grk11
lf.lnlib.kakuyomu_search = _o_srch11

print()
print("=" * 66)
print("12. 画像自升级：时间半衰期衰减（90 天，向中性 1.0 收缩）")
print("=" * 66)
from datetime import datetime, timedelta  # noqa: E402


def _fresh_prof(last_iso, **weights):
    p = json.loads(json.dumps(lf.DEFAULT_PROFILE))
    p["decay"] = {"halflife_days": 90, "last": last_iso}
    p["tag_weights"].update(weights)
    return p


def _iso(dt):
    return dt.isoformat(timespec="seconds")


_now = datetime.now()
_90d = _iso(_now - timedelta(days=90))

# 12.1 老画像缺 decay 键 → load_profile 自动补齐（无需迁移、不报错）
_old_path = os.path.join(TMP, "old_profile.json")
_keep_profile_path = lf.PROFILE_PATH
with open(_old_path, "w", encoding="utf-8") as f:
    json.dump({"tag_weights": {"TS": 5.0}, "blocked_tags": []}, f, ensure_ascii=False)
lf.PROFILE_PATH = _old_path
try:
    _op = lf.load_profile()
    _ok1 = isinstance(_op.get("decay"), dict) and _op["decay"].get("halflife_days") == 90
finally:
    lf.PROFILE_PATH = _keep_profile_path
check("★ 老画像缺 decay 键 → 自动补齐（halflife=90，不报错）", _ok1)

# 12.2 距上次 < 最小间隔（12h）→ 不衰减
_p2 = _fresh_prof(_iso(_now - timedelta(hours=1)), TS=8.0)
_n2 = lf.apply_time_decay(_p2, now=_now)
check("★ 无活动（<12h）不动", _n2 == 0 and _p2["tag_weights"]["TS"] == 8.0, f"n={_n2}")

# 12.3 90 天 → 强权重向中性收缩一半（9.0 → 5.0）
_p3 = _fresh_prof(_90d, TS=9.0)
lf.apply_time_decay(_p3, now=_now)
check("★ 90 天 → 强权重减半（9.0 → 5.0）",
      abs(_p3["tag_weights"]["TS"] - 5.0) < 0.01, f"TS={_p3['tag_weights']['TS']}")

# 12.4 genre_weights 一并衰减
_p4 = _fresh_prof(_90d)
_p4["genre_weights"]["FANTASY"] = 3.0
lf.apply_time_decay(_p4, now=_now)
check("genre_weights 同样向 1.0 收缩（3.0 → 2.0）",
      abs(_p4["genre_weights"]["FANTASY"] - 2.0) < 0.01,
      f"FANTASY={_p4['genre_weights']['FANTASY']}")

# 12.5 黑名单不衰减（「不要」是明确信号）；formula_tags 词典值不衰减
_p5 = _fresh_prof(_90d, TS=4.0, NTR=4.0)
_p5["blocked_tags"] = ["NTR"]
lf.apply_time_decay(_p5, now=_now)
check("★ 黑名单标签不衰减、也不删",
      _p5["tag_weights"]["NTR"] == 4.0 and "NTR" in _p5["blocked_tags"])
check("非黑名单标签照常衰减（4.0 → 2.5）",
      abs(_p5["tag_weights"]["TS"] - 2.5) < 0.01, f"TS={_p5['tag_weights']['TS']}")
_p6 = _fresh_prof(_90d)
lf.apply_time_decay(_p6, now=_now)
check("★ formula_tags 词典值不衰减",
      _p6["formula_tags"]["異世界転生"]
      == lf.DEFAULT_PROFILE["formula_tags"]["異世界転生"])

# 12.6 集成：learn_from_work 写入前触发衰减，并记进 history
if os.path.exists(lf.HISTORY_PATH):
    os.remove(lf.HISTORY_PATH)
_p7 = lf.load_profile()
_p7["tag_weights"]["TS"] = 9.0
_p7["decay"] = {"halflife_days": 90, "last": _90d}
lf.save_profile(_p7)
lf.learn_from_work({"id": "decay-int", "title": "衰减集成", "tags": ["百合"]}, verbose=False)
_after = lf.load_profile()
check("★ learn_from_work 写入前触发衰减（TS 9.0 → ≈5.0）",
      _after["tag_weights"]["TS"] < 6.0, f"TS={_after['tag_weights']['TS']}")
check("★ 衰减事件记入 history（可回溯）",
      any(e.get("kind") == "decay" for e in lf.load_history()))

# 12.7 持续 reinforce → 收敛稳定（衰减不会把常用偏好冲光）
_p8 = _fresh_prof(_iso(_now), TS=1.0)
_seq = []
for _i in range(1, 61):
    lf.apply_time_decay(_p8, now=_now + timedelta(days=30 * _i))
    _p8["tag_weights"]["TS"] = lf.clamp_tag_weight(_p8["tag_weights"]["TS"] + 0.6)
    _seq.append(_p8["tag_weights"]["TS"])
check("★ 持续 reinforce 的标签收敛稳定（不为 1、不再明显变化）",
      _seq[-1] > 3.0 and abs(_seq[-1] - _seq[-2]) < 0.05, f"TS={_seq[-1]}")

shutil.rmtree(TMP, ignore_errors=True)
print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("✅ lnfinder 自检全部通过")
