#!/usr/bin/env python3
"""自检：从"定时轮询"改成"打开时检查"

按需检查的语义：
  · 用户打开某本 → 才去查这一本的更新（且当天重复打开不重复查）
  · 不打开 → 零请求、零 token
  · 书架上的"更新了"标记来自**上次打开时**的结果（不是后台偷偷查的）
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

_s = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
mod = importlib.util.module_from_spec(_s)
sys.argv = ["x"]
_s.loader.exec_module(mod)

SLUG = "__onopen__"
NOVEL_DIR = os.path.join(NOVELS, SLUG)   # 独立变量：d 后面会被 _read_book 覆盖
d = NOVEL_DIR
# 开跑前先清残留：上次若中途崩溃（如 AttributeError）会留下目录
shutil.rmtree(d, ignore_errors=True)
_bp0 = os.path.join(HERE, "data", "books", f"{SLUG}.json")
if os.path.exists(_bp0):
    os.remove(_bp0)
os.makedirs(os.path.join(d, "chapters"))
os.makedirs(os.path.join(d, "raw"))
json.dump({
    "slug": SLUG, "source": "kakuyomu", "source_id": "1",
    "url": "https://kakuyomu.jp/works/1", "title": "打开时检查测试", "author": "t",
    "episodes": [{"id": str(i), "title": f"第{i+1}話"} for i in range(5)],
    "glossary": {}, "characters": {}, "summaries": {}, "style": {},
    "zh_titles": {"book": "打开时检查测试"},
    "progress": {"translated_through": 0, "fetched_through": 0},
}, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False)
mod.set_flag(SLUG, "favorites", True)

print("=" * 66)
print("自检 A：打开时检查 —— 当天只查一次，不重复打源站")
print("=" * 66)

calls = {"n": 0}
orig = mod.lt.fetch_work


def fake_fetch(url):
    calls["n"] += 1
    return {"id": "1", "title": "打开时检查测试",
            "author": "t",
            "episodes": [{"id": str(i), "title": f"第{i+1}話",
                          "publishedAt": "2026-10-15"} for i in range(8)]}


mod.lt.fetch_work = fake_fetch

r1 = mod.check_on_open(SLUG)
print(f"  第 1 次打开 → 查了（calls={calls['n']}），结果：{r1}")
r2 = mod.check_on_open(SLUG)
print(f"  第 2 次打开 → calls={calls['n']}（应仍为 1，当天不重复查）")
r3 = mod.check_on_open(SLUG, force=True)
print(f"  强制检查   → calls={calls['n']}（应为 2）")
ok1 = calls["n"] == 2 and r1.get("checked") is True
print(f"  {'✅' if ok1 else '❌'} 打开才查 + 当天去重")

print()
print("=" * 66)
print("自检 B：未打开的书，零请求")
print("=" * 66)
calls["n"] = 0
mod.watch_list()          # 书架渲染
mod.library()
print(f"  渲染书架 / 计算 watch_list → calls={calls['n']}（必须为 0）")
ok2 = calls["n"] == 0
print(f"  {'✅' if ok2 else '❌'} 不打开就不打源站")

print()
print("=" * 66)
print("自检 C：更新检测正确性（先建 5 话基线，再变 8 话）")
print("=" * 66)
def reset_check(slug):
    """清掉"上次检查时间"，模拟"很久没打开过了"。"""
    d = mod._read_book(slug)
    d.pop("checked_at", None)
    d.pop("check_attempt_at", None)
    d.pop("has_update", None)
    d.pop("new_episodes", None)
    mod._write_book(slug, d)


# 第一次检查只建立基线（设计如此：没有历史就无从比较"更新"）
reset_check(SLUG)
b1 = mod.check_on_open(SLUG, force=True)
bs1 = mod._read_book(SLUG)
print(f"  建基线 → episodes_latest={bs1.get('episodes_latest')}, "
      f"has_update={bs1.get('has_update')}（首次不该报更新）")
ok_base = bs1.get("episodes_latest") == 8 and not bs1.get("has_update")

# 手工把基线压回 5 话，模拟"上次打开时只有 5 话，之后作者更了 3 话"
d = mod._read_book(SLUG)
d["episodes_latest"] = 5
d.pop("checked_at", None)
d.pop("check_attempt_at", None)
mod._write_book(SLUG, d)
b2 = mod.check_on_open(SLUG, force=True)
bs = mod._read_book(SLUG)
print(f"  再检查（8 话）→ episodes_latest={bs.get('episodes_latest')}, "
      f"has_update={bs.get('has_update')}, new_episodes={bs.get('new_episodes')}")
ok3 = bs.get("has_update") is True and bs.get("new_episodes") == 3
print(f"  {'✅' if ok3 else '❌'} 多出 3 话被正确识别")
print(f"  （基线检查也正确：{'✅' if ok_base else '❌'}）")

# ★ 复查确认还是 8 话 → 过期的「更新了」徽标必须消失。
#   踩过：has_update 置位后没人清，读者处理完更新它仍永远亮着。
b3 = mod.check_on_open(SLUG, force=True)
bs2 = mod._read_book(SLUG)
ok_clear = not bs2.get("has_update") and "new_episodes" not in bs2
print(f"  复查（仍 8 话）→ has_update={bs2.get('has_update')}, "
      f"new_episodes={bs2.get('new_episodes')}")
print(f"  {'✅' if ok_clear else '❌'} 没有新章时清掉过期的更新徽标")

# ★ 源站失败也要记「上次尝试时间」并退避。
#   踩过：失败只写 check_error、不更新 checked_at → 去重永远不生效，
#   源站宕机期间每次打开书都重新起线程、页面白等 1 秒、反复打源站。
calls["n"] = 0


def boom(url):
    calls["n"] += 1
    raise RuntimeError("net down")


mod.lt.fetch_work = boom
d = mod._read_book(SLUG)
d.pop("checked_at", None)
d.pop("check_attempt_at", None)
mod._write_book(SLUG, d)
rf = mod.check_on_open(SLUG)
print(f"  源站失败 → checked={rf.get('checked')}, calls={calls['n']}, "
      f"reason={rf.get('reason')}")
rf2 = mod.check_on_open(SLUG)
bsf = mod._read_book(SLUG)
ok_fail = (rf.get("checked") is False and calls["n"] == 1
           and bool(bsf.get("check_attempt_at"))
           and rf2.get("checked") is False)
print(f"  失败后再次打开 → calls={calls['n']}（应仍为 1）"
      f", check_attempt_at={bsf.get('check_attempt_at')}")
print(f"  {'✅' if ok_fail else '❌'} 失败也退避（不反复打已经宕掉的源站）")

mod.lt.fetch_work = orig
shutil.rmtree(NOVEL_DIR, ignore_errors=True)
assert not os.path.exists(NOVEL_DIR), "自检目录没清干净！"
bp = mod.book_state_path(SLUG)
if os.path.exists(bp):
    os.remove(bp)
print()
print("自检数据已清理（已断言目录不存在）。")

# 失败必须反馈到退出码：run_selftests.py 只看 returncode，
# 不 sys.exit(1) 的话这个脚本无论如何都报"✅ 通过"（假绿）。
if not (ok1 and ok2 and ok3 and ok_base and ok_clear and ok_fail):
    sys.exit(1)
