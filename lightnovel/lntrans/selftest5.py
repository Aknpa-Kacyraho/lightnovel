#!/usr/bin/env python3
"""自检 5：翻译策略 + 书库（本轮新功能，必须有回归）。

用户要求：
  · 不要自动翻译没看过的小说
  · 看过的最多自动翻译到看到的后面第三章
  · 除非主动开启这本小说的翻译；可以选择翻译到多少
  · 爬过的书要留档进书库，以后想找还能找到
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 必须跟随 LNTRANS_DATA_ROOT 重定向（自检隔离靠它），
# 不能硬编码 HERE/novels —— 否则自检会写进真实书架。
_ROOT = os.environ.get("LNTRANS_DATA_ROOT") or HERE
NOVELS = os.path.join(_ROOT, "novels")
SLUG = "__t5__"
NOVEL_DIR = os.path.join(NOVELS, SLUG)

_s = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
mod = importlib.util.module_from_spec(_s)
sys.argv = ["x"]
_s.loader.exec_module(mod)

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def setup(translated=0, read=0, chapters=30):
    shutil.rmtree(NOVEL_DIR, ignore_errors=True)
    bp = mod.book_state_path(SLUG)
    if os.path.exists(bp):
        os.remove(bp)
    os.makedirs(os.path.join(NOVEL_DIR, "chapters"))
    os.makedirs(os.path.join(NOVEL_DIR, "raw"))
    json.dump({
        "slug": SLUG, "source": "kakuyomu", "source_id": "1",
        "url": "https://kakuyomu.jp/works/1", "title": "t5", "author": "a",
        "episodes": [{"id": str(i), "title": f"第{i+1}話"} for i in range(chapters)],
        "glossary": {}, "characters": {}, "summaries": {}, "style": {},
        "zh_titles": {"book": "t5"},
        "progress": {"translated_through": 0, "fetched_through": 0},
    }, open(os.path.join(NOVEL_DIR, "meta.json"), "w"), ensure_ascii=False)
    for c in range(translated):
        open(os.path.join(NOVEL_DIR, "chapters", f"{c:04d}.txt"), "w").write("译")
    if read:
        mod.set_progress(SLUG, read)
    mod.invalidate_cache(SLUG)
    return mod.novel_meta(SLUG)


print("=" * 68)
print("A. 默认不翻译任何书（用户：不要自动翻译没看过的小说）")
print("=" * 68)
meta = setup(translated=0, read=0)
cfg = mod.trans_cfg(SLUG)
check("默认 enabled=False", cfg["enabled"] is False)
check("未开启时 auto_ceiling=0", mod.auto_ceiling(SLUG, meta) == 0)
t, c = mod.allowed_targets(SLUG, meta, 5)
check("未开启时不给任何翻译目标（不会被自动翻）", t == [] and c == 0, f"targets={t}")

print()
print("=" * 68)
print("B. 开启后只翻到「读到 + ahead」")
print("=" * 68)
meta = setup(translated=0, read=0)
mod.set_trans_cfg(SLUG, enabled=True)
check("开启后默认 ahead=3", mod.trans_cfg(SLUG)["ahead"] == 3)
# 读第 10 章
mod.set_progress(SLUG, 10)
c = mod.auto_ceiling(SLUG, meta)
check("读到 10 → 天花板 13（10+3）", c == 13, f"ceiling={c}")
t, _ = mod.allowed_targets(SLUG, meta, 9999)
check("只允许翻 1~13 章", max(t) == 13 and 14 not in t, f"max={max(t)}")
# 用户自己调 ahead
mod.set_trans_cfg(SLUG, ahead=1)
c1 = mod.auto_ceiling(SLUG, meta)
check("ahead 改成 1 → 天花板 11", c1 == 11, f"ceiling={c1}")

print()
print("=" * 68)
print("C. 手动「翻到第 N 章」能突破自动上限")
print("=" * 68)
meta = setup(translated=0, read=5)
mod.set_trans_cfg(SLUG, enabled=True, ahead=3)
t_auto, c_auto = mod.allowed_targets(SLUG, meta, 9999)
check("自动上限 = 8", c_auto == 8, f"ceiling={c_auto}")
t_man, c_man = mod.allowed_targets(SLUG, meta, 9999, explicit_ceiling=20)
check("手动指定 20 章可突破", c_man == 20 and max(t_man) == 20, f"ceiling={c_man}")
t_cap, c_cap = mod.allowed_targets(SLUG, meta, 9999, explicit_ceiling=9999)
check("手动上限仍受总章数 30 限制", c_cap == 30, f"ceiling={c_cap}")

print()
print("=" * 68)
print("D. 上限规则（**改过一次，原因写在下面**）")
print("=" * 68)
# 旧规则是 ceiling = max(读到+ahead, 已译章数)，理由是"已花钱译出来的内容
# 不该被自己的策略挡住"。但它有个**花钱的副作用**：已译章数会随翻译增长，
# 于是上限自己往上爬 —— 一本从没读过的书在几分钟内被从头翻到尾
# （真实事故：读到第 1 章，23/23 全翻完）。用户原话「我没看的你就不要浪费 token」。
# 现在：**自动续译的上限只跟"读到哪"有关**；`已译章数` 只作为**手动**请求的地板
# （已花钱译出来的内容仍然不会被自己的策略挡住）。
meta = setup(translated=12, read=0)     # 没读过，但已译 12 章
mod.set_trans_cfg(SLUG, enabled=True, ahead=3)
c = mod.auto_ceiling(SLUG, meta)
t, ceil2 = mod.allowed_targets(SLUG, meta, 5)
check("auto_ceiling 按读到算（0+3=3）", c == 3, f"ceiling={c}")
check("★ 自动请求的天花板**不因已译 12 章**抬高（否则会自己往上爬）",
      ceil2 == 3, f"ceiling={ceil2}")
t_man2, c_man2 = mod.allowed_targets(SLUG, meta, 5, explicit_ceiling=12)
check("手动请求时已译章数当地板（已花钱的不会被策略挡住）",
      c_man2 == 12, f"ceiling={c_man2}")

print()
print("=" * 68)
print("E. 书库：爬过的书留档、去重、可搜、可标想看")
print("=" * 68)
_sr = importlib.util.spec_from_file_location("lnrecs", os.path.join(HERE, "lnrecs.py"))
recs = importlib.util.module_from_spec(_sr)
sys.argv = ["lnrecs"]
_sr.loader.exec_module(recs)
TMPL = tempfile.mkdtemp(prefix="lib-test-")
recs.LIB_PATH = os.path.join(TMPL, "library.json")
recs.RECS_PATH = os.path.join(TMPL, "recs.json")

sample = [
    {"id": "1", "title": "作品A", "author": "作者甲", "url": "u1",
     "tags": ["TS", "百合"], "review_points": 100, "episodes": 10,
     "last_episode_at": "2026-10-01"},
    {"id": "2", "title": "作品B", "author": "作者乙", "url": "u2",
     "tags": ["ざまぁ"], "review_points": 50, "episodes": 5,
     "last_episode_at": "2026-10-02"},
]
n1 = recs.merge_into_library(sample, source="测试")
check("首次并入 2 本", n1 == 2 and len(recs._load_lib()) == 2, f"n={n1}")
n2 = recs.merge_into_library(sample, source="测试2")
check("重复并入不增加（按 id 去重）", n2 == 0 and len(recs._load_lib()) == 2, f"n={n2}")
# 标签并集 + 字段更新
recs.merge_into_library([{"id": "1", "title": "作品A", "tags": ["勘違い"],
                          "review_points": 999, "episodes": 12}], source="再次")
lib = recs._load_lib()
check("标签取并集", set(lib["1"]["tags"]) >= {"TS", "百合", "勘違い"},
      str(lib["1"]["tags"]))
check("会变的字段被更新", lib["1"]["points"] == 999, f"points={lib['1']['points']}")
check("来源被记录", len(lib["1"]["sources"]) >= 2, str(lib["1"]["sources"]))
check("按标题能搜到", len(recs.library_items(query="作品A")) == 1)
check("按标签能搜到", len(recs.library_items(query="ざまぁ")) == 1)
check("搜不到时为空", recs.library_items(query="不存在的东西") == [])
check("标想看生效", recs.set_want("2", True) and
      len(recs.library_items(want_only=True)) == 1)
check("取消想看生效", recs.set_want("2", False) and
      recs.library_items(want_only=True) == [])
check("标不存在的 id 返回 False", recs.set_want("nope", True) is False)
# 标签 facet：精确命中（不是子串），且与分页"总数"同源
check("按标签 facet 筛得到", len(recs.library_items(tag="TS")) == 1)
check("facet 是精确标签，不是子串", recs.library_items(tag="T") == [],
      str(recs.library_items(tag="T")))
check("facet 计数与渲染同源", recs.library_count(tag="百合") == 1)
check("facet 无命中为空", recs.library_items(tag="不存在") == [])
check("library_tags 含频次", ("TS", 1) in recs.library_tags(min_count=1))
check("library_tags 默认过滤长尾(1 次的标签不列)", recs.library_tags() == [],
      str(recs.library_tags()))

print()
print("=" * 68)
print("F. 分页页数计算")
print("=" * 68)
for total, size, exp in ((0, 15, 1), (1, 15, 1), (15, 15, 1), (16, 15, 2), (107, 15, 8)):
    pages = max(1, (total + size - 1) // size)
    check(f"{total} 项 / 每页 {size} → {pages} 页", pages == exp, f"得到 {pages}")

recs.LIB_PATH = os.path.join(recs.DATA, "library.json")   # 复位，别影响真书库
recs.RECS_PATH = os.path.join(recs.DATA, "recs.json")
shutil.rmtree(TMPL, ignore_errors=True)

# 清理
mod.invalidate_cache()
shutil.rmtree(NOVEL_DIR, ignore_errors=True)
bp = mod.book_state_path(SLUG)
if os.path.exists(bp):
    os.remove(bp)
assert not os.path.exists(NOVEL_DIR), "自检目录没清干净！"
print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("✅ 自检 5 全部通过（已断言目录不存在）")
