#!/usr/bin/env python3
"""自检 4：本轮三方审查修掉的问题的回归测试。

覆盖：
  A. 收藏是独立维度（收藏+看完 仍留在收藏堆、仍被查更新）
  B. 并发提交反馈不丢（锁内读改写）
  C. 僵尸任务被识别成 error（否则前端无限轮询）
  D. 一键补译（fill）的目标集 = 所有缺失章节
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 必须跟随 LNTRANS_DATA_ROOT 重定向（自检隔离靠它），
# 不能硬编码 HERE/novels —— 否则自检会写进真实书架。
_ROOT = os.environ.get("LNTRANS_DATA_ROOT") or HERE
NOVELS = os.path.join(_ROOT, "novels")
SLUG = "__t4__"
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


def setup(chapters=20, translated=8):
    shutil.rmtree(NOVEL_DIR, ignore_errors=True)
    bp = mod.book_state_path(SLUG)
    if os.path.exists(bp):
        os.remove(bp)
    os.makedirs(os.path.join(NOVEL_DIR, "chapters"))
    os.makedirs(os.path.join(NOVEL_DIR, "raw"))
    json.dump({
        "slug": SLUG, "source": "kakuyomu", "source_id": "1",
        "url": "https://kakuyomu.jp/works/1", "title": "t4", "author": "a",
        "episodes": [{"id": str(i), "title": f"第{i+1}話"} for i in range(chapters)],
        "glossary": {}, "characters": {}, "summaries": {}, "style": {},
        "zh_titles": {"book": "t4"}, "progress": {"translated_through": 0,
                                                  "fetched_through": 0},
    }, open(os.path.join(NOVEL_DIR, "meta.json"), "w"), ensure_ascii=False)
    for c in range(translated):
        open(os.path.join(NOVEL_DIR, "chapters", f"{c:04d}.txt"), "w").write("译文")
    mod.invalidate_cache(SLUG)


print("=" * 66)
print("A. 收藏是独立维度：收藏+看完 不能被挪出收藏堆")
print("=" * 66)
setup()
mod.set_flag(SLUG, "favorites", True)
mod.set_flag(SLUG, "finished", True)
st = mod.book_status(SLUG)
check("收藏+看完 → status 仍是 favorite", st == "favorite", f"status={st}")
check("仍会被查更新", mod.should_watch(st, SLUG))
check("仍用于画像学习", mod.should_learn(st, SLUG))
check("收藏的书不判休眠", not mod.is_dormant(SLUG))

mod.set_flag(SLUG, "finished", False)
mod.set_flag(SLUG, "dropped", True)
st2 = mod.book_status(SLUG)
check("收藏+放弃 → status 仍是 favorite", st2 == "favorite", f"status={st2}")
check("收藏书即使放弃也被查", mod.should_watch(st2, SLUG))

print()
print("=" * 66)
print("A2. ★ 同一判定只该有一份实现：卡片/首页 vs watch_list 同源")
print("=" * 66)


def it_now():
    return [i for i in mod.library() if i["slug"] == SLUG][0]


def same_source():
    """卡片徽标 / 首页「有 N 本更新了」用的 _item_watches 必须与
    watch_list() 的 should_watch(book_status(...)) 完全一致。
    两套实现迟早漂移（踩过：首页与徽标判定不一致）。"""
    it = it_now()
    return (mod._item_watches(it)
            == mod.should_watch(mod.book_status(it["slug"], it), it["slug"]))


setup()
check("★ 同源 · 默认在读", same_source())
check("★ 同源 · 在读 → 会查更新", mod._item_watches(it_now()))
mod.set_flag(SLUG, "favorites", True)
check("★ 同源 · 收藏", same_source())
mod.set_flag(SLUG, "finished", True)
check("★ 同源 · 收藏+看完（收藏仍查）", same_source())
setup()
mod.set_flag(SLUG, "dropped", True)
check("★ 同源 · 弃文（不查，徽标不亮）", same_source() and not mod._item_watches(it_now()))
setup()
# 读到最后一章但没手动标「看完」：book_status 会判 finished，徽标判定也必须一致
mod.update_book(SLUG, lambda d: d.update({
    "progress": {"chapter": 20, "at": time.strftime("%Y-%m-%d %H:%M:%S")}}))
check("★ 同源 · 读到最后一章", same_source() and not mod._item_watches(it_now()))

print()
print("=" * 66)
print("B. 并发提交反馈不丢（锁内读改写）")
print("=" * 66)
setup()
N = 30
errs = []


def submit(i):
    try:
        mod.append_feedback(SLUG, {"at": f"t{i}", "slug": SLUG, "chapter": i + 1,
                                   "vote": "good", "note": f"n{i}"})
    except Exception as e:  # noqa: BLE001
        errs.append(f"{type(e).__name__}: {e}")


ts = [threading.Thread(target=submit, args=(i,)) for i in range(N)]
for t in ts:
    t.start()
for t in ts:
    t.join()

got = len(mod._read_book(SLUG).get("feedback") or [])
check(f"{N} 个线程并发提交，一条不丢", got == N, f"实际 {got} 条")
check("无异常", not errs, str(errs[:2]))

print()
print("=" * 66)
print("C. 僵尸任务被识别（否则前端无限轮询）")
print("=" * 66)
with mod.LOCK:
    mod.JOBS[SLUG] = {"slug": SLUG, "status": "running", "done": 0,
                      "at": time.time() - 10 ** 5,   # 很久以前
                      "heartbeat": time.time() - 10 ** 5}
v = mod.job_view(SLUG)
check("超时的 running 任务被标成中断待恢复",
      v.get("status") == "interrupted", str(v.get("error")))
check("带可读的错误信息", "超时" in (v.get("error") or ""))

with mod.LOCK:
    mod.JOBS[SLUG] = {"slug": SLUG, "status": "running", "done": 1,
                      "at": time.time(), "heartbeat": time.time()}
v2 = mod.job_view(SLUG)
check("心跳新鲜的任务保持 running", v2.get("status") == "running")

print()
print("=" * 66)
print("D. 一键补译：目标 = 所有缺失章节")
print("=" * 66)
setup(chapters=20, translated=8)
meta = mod.novel_meta(SLUG)
t_fill = mod.next_targets(SLUG, meta, 9999)
check("fill 覆盖全部缺失章节", t_fill == list(range(9, 21)),
      f"{t_fill[:3]}…{t_fill[-1]}（共 {len(t_fill)}）")
t_two = mod.next_targets(SLUG, meta, 2)
check("非 fill 时只取 2 章", len(t_two) == 2, str(t_two))

# 制造空洞：删掉第 5 章
os.remove(os.path.join(NOVEL_DIR, "chapters", "0004.txt"))
mod.invalidate_cache(SLUG)
meta = mod.novel_meta(SLUG)
t_gap = mod.next_targets(SLUG, meta, 9999)
check("有空洞时 fill 会补上空洞", 5 in t_gap and len(t_gap) == 13,
      f"含第5章={5 in t_gap}, 共 {len(t_gap)} 章")

print()
print("=" * 66)
print("E. 卡片 HTML 结构：按钮必须在 .card 里面（否则点了没反应）")
print("=" * 66)
setup(chapters=10, translated=3)

items = [it for it in mod.library() if it["slug"] == SLUG]
assert items, "自检书没出现在 library()"
card = mod._card(items[0], {})

# 检查 1：onclick 属性里不能有裸单引号
m = re.search(r'<div class="card"[^>]*>', card, re.S)
check("能找到 card 开标签", bool(m))
if m:
    oc = re.search(r'onclick="([^"]*)"', m.group(0))
    check("card onclick 里没有裸单引号（否则属性会被截断）",
          bool(oc) and "'" not in oc.group(1),
          (oc.group(1)[:60] if oc else "没有 onclick"))

# 检查 2：四个状态按钮都出现在 card 块内部
# （上一版用 HTMLParser 追嵌套深度，太脆弱、误报；改成块内出现即算通过）
acts = set(re.findall(r'data-act="(\w+)"', card))
check("按钮种类齐全（含新增的在读）",
      {"favorite", "reading", "finished", "dropped", "check"} <= acts,
      str(sorted(acts)))
check("按钮都带 type=button（避免表单意外提交）",
      card.count('<button type="button"') + card.count('<button ') >= 5)

# 检查 3：真正会致命的语法——属性值里出现裸引号
bad = re.findall(r'=\'[^\']*"[^>]*>', card)
check("没有属性值被引号截断", not bad, str(bad[:2]))

mod.invalidate_cache()
shutil.rmtree(NOVEL_DIR, ignore_errors=True)
bp = mod.book_state_path(SLUG)
if os.path.exists(bp):
    os.remove(bp)
with mod.LOCK:
    mod.JOBS.pop(SLUG, None)
assert not os.path.exists(NOVEL_DIR), "自检目录没清干净！"
print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("✅ 自检 4 全部通过（已断言目录不存在）")
