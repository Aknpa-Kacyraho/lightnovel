#!/usr/bin/env python3
"""自检：分类 / 更新检测 / 学习信号

对应本轮三个需求：
  1. 看完的书能不能自动归堆、能不能手动标
  2. 在读和收藏的书更新了，系统知不知道
  3. "在读" 该不该当正向学习信号（用户明确说：不该）
"""

import importlib.util
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 必须跟随 LNTRANS_DATA_ROOT 重定向（自检隔离靠它），
# 不能硬编码 HERE/novels —— 否则自检会写进真实书架。
_ROOT = os.environ.get("LNTRANS_DATA_ROOT") or HERE
NOVELS = os.path.join(_ROOT, "novels")
DATA = os.path.join(HERE, "data")

_s = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
mod = importlib.util.module_from_spec(_s)
sys.argv = ["lnserve"]
_s.loader.exec_module(mod)

SLUGS = ["__c_reading__", "__c_finished__", "__c_abandoned__", "__c_fav__"]


def make(slug, chapters=10, translated=10, state=None):
    d = os.path.join(NOVELS, slug)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "chapters"))
    os.makedirs(os.path.join(d, "raw"))
    meta = {
        "slug": slug, "source": "kakuyomu", "source_id": "1",
        "url": "https://kakuyomu.jp/works/1", "title": f"测试-{slug}",
        "author": "t", "episodes": [{"id": str(i), "title": f"第{i+1}話"}
                                    for i in range(chapters)],
        "glossary": {}, "characters": {}, "summaries": {}, "style": {},
        "zh_titles": {"book": f"中文名-{slug}"},
        "progress": {"translated_through": 0, "fetched_through": 0},
    }
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False)
    for c in range(translated):
        open(os.path.join(d, "chapters", f"{c:04d}.txt"), "w").write("译文")
    if state:
        bp = mod.book_state_path(slug)
        json.dump(state, open(bp, "w"), ensure_ascii=False)


print("=" * 68)
print("自检 A：分类逻辑（在读 / 看完 / 放弃 该不该分清）")
print("=" * 68)

# 各种典型状态
make("__c_reading__", 10, 10, {"progress": {"chapter": 4, "at": "2026-10-15 18:00:00"},
                               "favorites": None, "feedback": []})
make("__c_finished__", 10, 10, {"progress": {"chapter": 10, "at": "2026-10-15 18:00:00"},
                                "favorites": None, "feedback": [], "finished": "2026-10-15"})
# 用"相对现在 120 天前"，避免测试数据随时间失效
_old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 120 * 86400))
make("__c_abandoned__", 10, 10, {"progress": {"chapter": 1, "at": _old},
                                 "favorites": None, "feedback": []})
make("__c_fav__", 10, 10, {"progress": {"chapter": 2, "at": "2026-09-20 10:00:00"},
                           "favorites": "2026-09-20", "feedback": []})

items = mod.library()
for it in items:
    if not it["slug"].startswith("__c_"):
        continue
    st = mod.book_status(it["slug"], it)
    print(f"  {it['slug']:<18} 进度 {it['read']}/{it['total']} "
          f"收藏={bool(it['favorite'])} → 归类：{st}")
print()
print("  期望：__c_finished__ → finished，__c_fav__ → favorite（收藏优先于其它标记）")
print("        __c_reading__ / __c_abandoned__ → 都是 reading（搁置靠 stale 标注，不自动挪走）")

print()
print("=" * 68)
print("自检 B：更新检测（哪些书该查、哪些不该浪费 token）")
print("=" * 68)

# 这是关键：只查 收藏 ∪ 在读，不查 放弃/看完
# 直接调生产用的 watch_list()，避免"测试里重新拼一遍逻辑"这种假验证
watch = [s for s in mod.watch_list() if s.startswith("__c_")]
print(f"  __c_abandoned__ 上次阅读：{_old}（120 天前，超 60 天门槛）")
print(f"  需要定时查更新的书：{watch}")
print()
print("  期望：只含 __c_fav__（收藏永远查）和 __c_reading__（近期读过）")
print("        收藏优先后，__c_fav__ 的 status 仍是 favorite ✓")
print("        __c_abandoned__ 超 60 天未打开 → 休眠不查（用户：没看的别浪费 token）")
ok_watch = ("__c_fav__" in watch and "__c_reading__" in watch
            and "__c_abandoned__" not in watch)
print(f"  {'✅' if ok_watch else '❌'} 收藏永远查 / 近期读过要查 / 久未打开休眠")

print()
print("=" * 68)
print("自检 C：学习信号（用户明确说：在读 ≠ 喜欢）")
print("=" * 68)
print("  用户原话：『我收藏的才值得你去学习画像，我看的不代表我喜欢，")
print("             可能我只看一点点就放弃了』")
print()
for it in items:
    if not it["slug"].startswith("__c_"):
        continue
    st = mod.book_status(it["slug"], it)
    learn = mod.should_learn(st)
    print(f"  {it['slug']:<18} 归类 {st:<10} → 用于画像学习：{learn}")
print()
print("  期望：只有 favorite 为 True。reading/abandoned 都不该自动进画像，")
print("        因为『点开看过』不构成喜欢。")

# 清理
for s in SLUGS:
    shutil.rmtree(os.path.join(NOVELS, s), ignore_errors=True)
    bp = mod.book_state_path(s)
    if os.path.exists(bp):
        os.remove(bp)
print()
print("自检数据已清理。")

# 失败必须反馈到退出码：run_selftests.py 只看 returncode，
# 不 sys.exit(1) 的话这个脚本无论如何都报"✅ 通过"（假绿）。
if not ok_watch:
    sys.exit(1)
