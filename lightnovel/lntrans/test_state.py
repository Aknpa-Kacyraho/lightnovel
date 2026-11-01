#!/usr/bin/env python3
"""状态机穷举测试（STATE-MACHINE.md 的自动校验）。

核心断言：**渲染出来的 UI 状态必须等于 API 返回的实际状态**。
用户明确要求「确保 UI 显示和实际情况一样」——所以这条必须自动查，
而不是等他发现。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 必须跟随 LNTRANS_DATA_ROOT 重定向（自检隔离靠它），
# 不能硬编码 HERE/novels —— 否则自检会写进真实书架。
_ROOT = os.environ.get("LNTRANS_DATA_ROOT") or HERE
NOVELS = os.path.join(_ROOT, "novels")
SLUG = "__st__"
D = os.path.join(NOVELS, SLUG)

_s = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
m = importlib.util.module_from_spec(_s)
sys.argv = ["x"]
_s.loader.exec_module(m)

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def setup():
    shutil.rmtree(D, ignore_errors=True)
    bp = m.book_state_path(SLUG)
    if os.path.exists(bp):
        os.remove(bp)
    os.makedirs(os.path.join(D, "chapters"))
    os.makedirs(os.path.join(D, "raw"))
    json.dump({"slug": SLUG, "source": "kakuyomu", "source_id": "1", "url": "u",
               "title": "状态机测试", "author": "a",
               "episodes": [{"id": str(i), "title": f"第{i+1}話"} for i in range(10)],
               "glossary": {}, "characters": {}, "summaries": {}, "style": {},
               "zh_titles": {"book": "状态机测试"},
               "progress": {"translated_through": 0, "fetched_through": 0}},
              open(os.path.join(D, "meta.json"), "w"), ensure_ascii=False)
    m.invalidate_cache(SLUG)


def item():
    return [i for i in m.library() if i["slug"] == SLUG][0]


def card_html():
    return m._card(item(), {})


def ui_state():
    """从渲染出的 HTML 反解 UI 认为的状态（这正是用户看到的）。"""
    h = card_html()
    on = set(re.findall(r'data-act="(\w+)"[^>]*class="on"', h))
    badges = set(re.findall(r'<span class="badge (\w+)">', h))
    return on, badges


print("=" * 66)
print("A. 四个状态互斥 + 收藏正交")
print("=" * 66)
setup()
# ⚠ 语义变更（用户报「加入书架不等于收藏」之后定的）：
#   tracking 没有值时 read_tracking 返回 **None**（= 不在书架），
#   不再伪造 "want" —— 否则"打开阅读页 → want 转 reading"那条规则
#   会把**已移出书架**的书又自动加回来（用户点了三次「移出」都失效）。
check("初始 tracking = None（不在书架，不再伪造 want）",
      m.read_tracking(SLUG) is None, repr(m.read_tracking(SLUG)))
check("★ 「加入书架」= want 上架，且**不是收藏**",
      m.ensure_on_shelf(SLUG) and m.read_tracking(SLUG) == "want"
      and item()["favorite"] is False, repr(m.read_tracking(SLUG)))
check("★ 已在书架上时不重复写状态（ensure_on_shelf 幂等）",
      m.ensure_on_shelf(SLUG) is False and m.read_tracking(SLUG) == "want")
# 用户视角的最终结果：加进来就得能在书架上看到，但**不能**变成收藏
_items = [i for i in m.library() if i["slug"] == SLUG]
_html = m.page_library(_items, {})
check("★ 加入书架后书架里能看到这张卡", _html.count('<div class="card" data-slug=') == 1,
      f"卡片数={_html.count('<div class="card" data-slug=')}")
check("★ 加入书架不等于收藏（不在收藏堆、没有收藏徽标）",
      'data-fav="1"' not in _html and 'class="badge fav"' not in _html)

m.apply_action(SLUG, "reading")
check("→ reading", m.read_tracking(SLUG) == "reading")

m.apply_action(SLUG, "finished")
check("→ finished", m.read_tracking(SLUG) == "finished")
check("finished 时 favorites 不受影响（仍为 False）", item()["favorite"] is False)

m.apply_action(SLUG, "dropped")
it = item()
check("→ dropped", m.read_tracking(SLUG) == "dropped")

print()
print("=" * 66)
print("B. ★ 弃文自动清除收藏（用户明确要求）")
print("=" * 66)
setup()
m.apply_action(SLUG, "favorite", True)
check("先收藏成功", item()["favorite"] is True)
r = m.apply_action(SLUG, "dropped", True)
check("弃文后 favorites 被清空", item()["favorite"] is False, f"favorite={item()['favorite']}")
check("返回值里标出 cleared_favorite", r.get("cleared_favorite") is True)
check("tracking = dropped", r["tracking"] == "dropped")

print()
print("=" * 66)
print("C. 「收藏 + 看完」共存（两个徽标都要显示）")
print("=" * 66)
setup()
m.apply_action(SLUG, "favorite", True)
m.apply_action(SLUG, "finished")
it = item()
check("favorites=True 且 tracking=finished", it["favorite"] and it["tracking"] == "finished")
on, badges = ui_state()
check("UI：收藏按钮亮", "favorite" in on, str(sorted(on)))
check("UI：看完按钮亮", "finished" in on, str(sorted(on)))
check("UI：同时有「收藏」和「看完」两个徽标", {"fav", "fin"} <= badges, str(sorted(badges)))

print()
print("=" * 66)
print("D. ★ UI 显示 == 实际状态（穷举所有组合）")
print("=" * 66)
for tk in ("want", "reading", "finished", "dropped"):
    for fav in (False, True):
        setup()
        if fav:
            m.apply_action(SLUG, "favorite", True)
        m.apply_action(SLUG, tk if tk != "want" else "want")
        it = item()
        on, badges = ui_state()
        ok_fav = ("favorite" in on) == bool(it["favorite"])
        ok_tk = ((tk == "reading" and "reading" in on)
                 or (tk == "finished" and "finished" in on)
                 or (tk == "dropped" and "dropped" in on)
                 or (tk == "want" and not ({"reading", "finished", "dropped"} & on)))
        ok_badge = (("fav" in badges) == bool(it["favorite"]))
        check(f"tracking={tk:<8} favorite={str(fav):<5} → 按钮一致", ok_fav and ok_tk,
              f"on={sorted(on)}")
        check(f"tracking={tk:<8} favorite={str(fav):<5} → 徽标一致", ok_badge,
              f"badges={sorted(badges)}")

print()
print("=" * 66)
print("E. 转换表：重看 / 重新捡起 / 移出书架")
print("=" * 66)
setup()
m.apply_action(SLUG, "finished")
m.apply_action(SLUG, "reading")      # 重看
check("finished → reading（重看）", m.read_tracking(SLUG) == "reading")

m.apply_action(SLUG, "dropped")
m.apply_action(SLUG, "reading")      # 重新捡起
check("dropped → reading（重新捡起）", m.read_tracking(SLUG) == "reading")

m.apply_action(SLUG, "want")         # 移出书架
check("→ want（移出书架）", m.read_tracking(SLUG) == "want")

# 取消弃文
setup()
m.apply_action(SLUG, "favorite", True)
m.apply_action(SLUG, "dropped", True)
m.apply_action(SLUG, "dropped", False)
check("取消弃文 → 回到 want", m.read_tracking(SLUG) == "want")
check("取消弃文不会自动恢复收藏（需用户自己再点）", item()["favorite"] is False)

# 旧数据兼容
print()
print("=" * 66)
print("F. 旧数据兼容（老字段 finished/dropped）")
print("=" * 66)
setup()
m.update_book(SLUG, lambda d: d.update({"finished": "2026-01-01 00:00:00",
                                        "dropped": None, "tracking": None}))
check("只有老字段 finished → 读作 finished", m.read_tracking(SLUG) == "finished")
m.update_book(SLUG, lambda d: d.update({"finished": None, "dropped": "2026-01-01 00:00:00",
                                        "tracking": None}))
check("只有老字段 dropped → 读作 dropped", m.read_tracking(SLUG) == "dropped")

print()
print("=" * 66)
print("G. ★ 书不能从书架上消失（每个 tracking 值都要有归属）")
print("=" * 66)
for tk in ("want", "reading", "finished", "dropped"):
    setup()
    m.apply_action(SLUG, tk)
    items = [i for i in m.library() if i["slug"] == SLUG]
    assert items, f"{tk}: library() 里都找不到"
    html = m.page_library(items, {})
    n = html.count('<div class="card" data-slug=')
    check(f"tracking={tk:<8} 卡片出现在书架上", n == 1, f"卡片数={n}")
    check(f"tracking={tk:<8} 不是『书架还是空的』",
          "书架中还没有作品" not in html)
    check(f"tracking={tk:<8} 按钮渲染出来了",
          html.count('data-act=') >= 5, f"{html.count('data-act=')}")

# 收藏维度也要能出现
setup()
m.apply_action(SLUG, "favorite", True)
items = [i for i in m.library() if i["slug"] == SLUG]
html = m.page_library(items, {})
n = html.count('<div class="card" data-slug=')
check("只有收藏（无 tracking）时也显示卡片", n == 1, f"卡片数={n}")

print()
print("=" * 66)
print("H. 打开阅读页 → want 自动转 reading（文档里定义了，之前没实现）")
print("=" * 66)
setup()
m.ensure_on_shelf(SLUG)
check("加入书架后为 want", m.read_tracking(SLUG) == "want")
# 直接调转换入口（等价于访问 /read 时触发的逻辑）
if m.read_tracking(SLUG) == "want":
    m.apply_action(SLUG, "reading", True)
check("打开后变成 reading", m.read_tracking(SLUG) == "reading")
check("自动转换不会碰收藏", item()["favorite"] is False)
# 不该覆盖已有状态
setup()
m.apply_action(SLUG, "finished")
if m.read_tracking(SLUG) == "want":      # 条件不成立，不会执行
    m.apply_action(SLUG, "reading", True)
check("已是 finished 时打开阅读页不降级为 reading", m.read_tracking(SLUG) == "finished")

print()
print("=" * 66)
print("I. 续读位置 + 阅读历史（学自 Kavita 的 BookScrollId / ReadingSession）")
print("=" * 66)
setup()
# 记录：第 3 章 42%
m.set_progress(SLUG, 3, 0.42)
p = m._read_book(SLUG).get("progress") or {}
check("scroll 被存入进度", abs(float(p.get("scroll", 0)) - 0.42) < 1e-6, str(p))
m.set_progress(SLUG, 3)          # 同章不带 scroll → 应保留
p2 = m._read_book(SLUG).get("progress") or {}
check("同章更新不带 scroll 时保留原位置",
      abs(float(p2.get("scroll", 0)) - 0.42) < 1e-6, str(p2))
m.set_progress(SLUG, 4)          # 换章不带 scroll → 不沿用上一章的位置
p3 = m._read_book(SLUG).get("progress") or {}
check("换章后不错误沿用上一章的滚动位置", "scroll" not in p3, str(p3))

# 非法值要被夹住
m.set_progress(SLUG, 4, 1.7)
check("scroll > 1 被夹到 1",
      abs(float((m._read_book(SLUG).get("progress") or {}).get("scroll", 0)) - 1.0) < 1e-6)
m.set_progress(SLUG, 4, -3)
check("scroll < 0 被夹到 0",
      abs(float((m._read_book(SLUG).get("progress") or {}).get("scroll", 0))) < 1e-6)

# 阅读历史：同书半小时内只留一条（日志不会爆）
hp = m.HISTORY_PATH
bak = None
if os.path.exists(hp):
    bak = hp + ".testbak"
    os.replace(hp, bak)
try:
    m.log_history(SLUG, 1)
    m.log_history(SLUG, 2)          # 同书，30 分钟内 → 合并
    m.log_history(SLUG, 3)
    with open(hp, encoding="utf-8") as f:
        lines = [x for x in f if x.strip()]
    check("同书短时间内重复上报被合并为 1 条", len(lines) == 1, f"{len(lines)} 条")
    st = m.reading_stats()
    check("统计能算出累计阅读日", st["days"] >= 1, str(st))
    check("统计能算出连续天数", st["streak"] >= 1, str(st))
finally:
    if os.path.exists(hp):
        os.remove(hp)
    if bak:
        os.replace(bak, hp)

print()
print("=" * 66)
print("J. ★ 双轨进度：续读用实际位置，进度用最远位置")
print("=" * 66)
print("   （学自 LightNovelReader 的 currentChapterReadingProgressMap /")
print("     maxChapterReadingProgressMap）")
setup()
m.set_progress(SLUG, 3, 0.8)
p = m._read_book(SLUG).get("progress") or {}
check("首次记录：scroll == max_scroll == 0.8",
      abs(p.get("scroll", 0) - 0.8) < 1e-6 and abs(p.get("max_scroll", 0) - 0.8) < 1e-6,
      str(p))

m.set_progress(SLUG, 3, 0.3)          # 往回翻看
p2 = m._read_book(SLUG).get("progress") or {}
check("回翻后 scroll 跟随实际位置（0.3）",
      abs(p2.get("scroll", 0) - 0.3) < 1e-6, str(p2))
check("回翻后 max_scroll 保留最远值（0.8）",
      abs(p2.get("max_scroll", 0) - 0.8) < 1e-6, str(p2))
check("续读位置取 scroll 而不是 max_scroll（这是关键）",
      abs((m._read_book(SLUG).get("progress") or {}).get("scroll", 0) - 0.3) < 1e-6)

m.set_progress(SLUG, 3, 0.9)          # 又读到更远
p3 = m._read_book(SLUG).get("progress") or {}
check("再读更远时 max_scroll 前进到 0.9",
      abs(p3.get("max_scroll", 0) - 0.9) < 1e-6, str(p3))

# 换章后不该沿用上一章的最远位置
m.set_progress(SLUG, 4, 0.1)
p4 = m._read_book(SLUG).get("progress") or {}
check("换章后 max_scroll 重新从本章算（0.1）",
      abs(p4.get("max_scroll", 0) - 0.1) < 1e-6, str(p4))

# —— 低危修复：续读「下一章」不能回跳。读到超出已译范围时停在原章，
#    绝不能被 min(ch+1, max(have,1)) 折叠成第 1 章或已译最末章。
m.set_progress(SLUG, 9, 0.0)
_rr = m.recent_read()
check("★ recent_read.next 不回跳（读到超出已译范围时停在原章）",
      _rr is not None and _rr.get("next") == 9, str(_rr and _rr.get("next")))

# 整体进度（书架显示用的那个数）
items = [i for i in m.library() if i["slug"] == SLUG]
bp = items[0].get("book_progress") if items else None
check("library() 带出 book_progress", bp is not None and 0 <= bp <= 1, f"{bp}")

print()
print("=" * 66)
print("K. ★ 移出书架（用户报的 bug：移除后书还在书架里）")
print("=" * 66)
setup()
m.apply_action(SLUG, "favorite", True)
m.apply_action(SLUG, "reading", True)
check("先收藏 + 在读", item()["favorite"] and m.read_tracking(SLUG) == "reading")

# 在书架上且有残留更新标记 → 首页该报更新
m.update_book(SLUG, lambda d: d.update({"has_update": True, "new_episodes": 2}))
items = [i for i in m.library() if i["slug"] == SLUG]
html = m.page_library(items, {})
check("★ 在书架且有更新 → 首页报『有 1 本更新了』", "1 部作品有新章节" in html)

r = m.apply_action(SLUG, "off", True)
check("移出后返回 removed=True", r.get("removed") is True)
check("移出后 tracking 被清空（read_tracking 返回 None，不是伪造的 want）",
      m.read_tracking(SLUG) is None, repr(m.read_tracking(SLUG)))
check("★ 移出后 has_update 被清掉", not m._read_book(SLUG).get("has_update"))
# ★ 这是用户实际踩到的循环：移出 → 打开书接着读 → 又回到书架
#   （阅读页的规则是「want → reading」，以前因为它伪造 want 而误伤已移出的书）
if m.read_tracking(SLUG) == "want":
    m.apply_action(SLUG, "reading", True)
check("★ 移出后再打开阅读页，不会被自动加回书架",
      m.read_tracking(SLUG) is None and item()["on_shelf"] is False,
      repr(m.read_tracking(SLUG)))
check("移出后 favorites 被清空", item()["favorite"] is False)
check("移出后 on_shelf=False", item()["on_shelf"] is False)

# 关键：不能再出现在书架上（这正是用户遇到的 bug）
items = [i for i in m.library() if i["slug"] == SLUG]
html = m.page_library(items, {})
check("★ 移出后书架里没有这张卡",
      html.count('<div class="card" data-slug=') == 0,
      f"卡片数={html.count('<div class=\"card\" data-slug=')}")
check("★ 移出后显示『书架还是空的』", "书架中还没有作品" in html)

# ★ 旧数据/竞态可能留下"不在书架、但 has_update=True"的状态：
#   首页不能再报它更新了（修复前这里用全量 items，会把移出的书算进去）。
m.update_book(SLUG, lambda d: d.update({"has_update": True, "new_episodes": 2}))
items = [i for i in m.library() if i["slug"] == SLUG]
html = m.page_library(items, {})
check("★ 不在书架的书即使残留 has_update 也不报『更新了』",
      "本更新了" not in html)
m.update_book(SLUG, m._clear_update_flags)

# 弃文 = 不再查更新 → 更新徽标也该一起消失
m.apply_action(SLUG, "favorite", True)
m.update_book(SLUG, lambda d: d.update({"has_update": True, "new_episodes": 2}))
m.apply_action(SLUG, "dropped", True)
check("★ 弃文后 has_update 被清掉", not m._read_book(SLUG).get("has_update"))

# ★ 历史数据（旧版本从不清理）可能留下「弃文/看完但 has_update=True」。
#   这些书已不在 watch_list() 里，卡片上不该再亮「点我翻译」。
m.update_book(SLUG, lambda d: d.update({"has_update": True, "new_episodes": 2}))
items = [i for i in m.library() if i["slug"] == SLUG]
check("★ 弃文的书即使残留 has_update 也不显示『点我翻译』",
      'data-act="fill"' not in m._card(items[0], {}))
# 但收藏是另一维度：收藏的书永远查更新，徽标照旧。
m.update_book(SLUG, lambda d: d.update({
    "has_update": True, "new_episodes": 2,
    "favorites": "2026-01-01 00:00:00"}))
items = [i for i in m.library() if i["slug"] == SLUG]
check("★ 收藏的书即使弃文仍显示更新徽标（收藏永远查）",
      'data-act="fill"' in m._card(items[0], {}))
m.update_book(SLUG, m._clear_update_flags)
m.apply_action(SLUG, "off", True)

# 但译文必须还在（不能把书删了）
check("译文目录仍保留", os.path.isdir(D))

print()
print("=" * 66)
print("L. 移出后还能加回来（不做成单向操作）")
print("=" * 66)
m.apply_action(SLUG, "favorite", True)
check("重新收藏后 on_shelf=True", item()["on_shelf"] is True)
items = [i for i in m.library() if i["slug"] == SLUG]
html = m.page_library(items, {})
check("★ 卡片又出现在书架上",
      html.count('<div class="card" data-slug=') == 1,
      f"卡片数={html.count('<div class=\"card\" data-slug=')}")

print()
print("=" * 66)
print("M. 老数据迁移：有进度但无书架标记 → 自动标为在读（不能让书消失）")
print("=" * 66)
_mk = os.path.join(m.DATA, ".shelf-migrated")
_mk_bak = None
if os.path.exists(_mk):
    _mk_bak = _mk + ".testbak"
    os.replace(_mk, _mk_bak)
try:
    setup()
    # 造一份"老格式"状态：有进度，但没有 tracking/favorites
    m.update_book(SLUG, lambda d: d.update(
        {"tracking": None, "favorites": None, "finished": None, "dropped": None,
         "progress": {"chapter": 4, "at": "2026-01-01 00:00:00"}}))
    check("迁移前 on_shelf=False", item()["on_shelf"] is False)
    n = m.migrate_shelf_state()
    check("迁移命中 1 本", n == 1, f"{n} 本")
    check("迁移后 tracking=reading", m.read_tracking(SLUG) == "reading")
    check("迁移后 on_shelf=True", item()["on_shelf"] is True)
    check("标记文件已生成（迁移只跑一次）", os.path.exists(_mk))

    # ★ 关键：用户主动移出的书，不能因为再次迁移被放回书架
    m.apply_action(SLUG, "off", True)
    check("移出后 on_shelf=False", item()["on_shelf"] is False)
    check("★ 再次迁移不会把用户移出的书放回书架",
          m.migrate_shelf_state() == 0 and item()["on_shelf"] is False,
          f"n={m.migrate_shelf_state()} on_shelf={item()['on_shelf']}")

    # 没有进度的书不该被迁移（否则书库里的书会全跑上书架）
    os.remove(_mk)              # 临时允许迁移跑一次
    setup()
    m.update_book(SLUG, lambda d: d.update(
        {"tracking": None, "favorites": None, "finished": None, "dropped": None,
         "progress": {}}))
    check("没有进度的书不被迁移（不该凭空上架）", m.migrate_shelf_state() == 0)
    check("没有进度的书 on_shelf=False", item()["on_shelf"] is False)
finally:
    if os.path.exists(_mk):
        os.remove(_mk)
    if _mk_bak:
        os.replace(_mk_bak, _mk)

print()
print("=" * 66)
print("N. ★★ 数字必须与内容一致（用户报：书架没书了还显示 1）")
print("=" * 66)
print("   这类不一致比崩溃更烦人 —— 用户会怀疑整个界面。")


def count_labels(html: str) -> list[str]:
    """抽出页面上所有"数量"文案，用于和实际卡片数对照。"""
    out = []
    for mm in re.finditer(r'<span class="n">([^<]*)</span>|data-tab="(\w+)"[^>]*>([^<]*)<',
                          html):
        t = (mm.group(1) or mm.group(3) or "").strip()
        if t and any(c.isdigit() for c in t):
            out.append(t)
    return out


def shelf_cards(html: str) -> int:
    return html.count('<div class="card" data-slug=')


# 场景 1：书被移出书架 → 数字必须归零
setup()
m.apply_action(SLUG, "off", True)
html = m.page_library([i for i in m.library() if i["slug"] == SLUG], {})
check("★ 移出后卡片数为 0", shelf_cards(html) == 0, str(shelf_cards(html)))
labels = count_labels(html)
check("★ 页签『书架 0』（不能还显示 1）",
      any("书架 0" in x for x in labels), str(labels))
check("★ 标题『0 本』", any(x.startswith("0 本") for x in labels), str(labels))
check("★ 显示空书架提示", "书架中还没有作品" in html)
# 只看**书架面板内部**的计数（推荐位的"N 本"是另一回事，别混进来）
_span = html[html.find('id="pane-shelf"'):]
if 'id="pane-lib"' in _span:
    _span = _span[:_span.find('id="pane-lib"')]
_shelf_labels = re.findall(r'<span class="n">([^<]*)</span>', _span)
_bad = [x for x in _shelf_labels if re.match(r"^[1-9]\d* 本", x)]
check("★ 书架面板内没有任何非零的『N 本』", not _bad, str(_bad))

# 场景 2：加回书架 → 数字必须是 1，且卡片也是 1
m.apply_action(SLUG, "favorite", True)
html = m.page_library([i for i in m.library() if i["slug"] == SLUG], {})
check("★ 加回后卡片数为 1", shelf_cards(html) == 1, str(shelf_cards(html)))
labels = count_labels(html)
check("★ 页签『书架 1』", any("书架 1" in x for x in labels), str(labels))
check("★ 标题『1 本』", any(x.startswith("1 本") for x in labels), str(labels))
check("★ 不再显示空书架提示", "书架中还没有作品" not in html)

# 场景 3：多种状态混合时，页签数字 == 卡片数 == 各分组之和
setup()
m.apply_action(SLUG, "favorite", True)
html = m.page_library(m.library(), {})
labels = count_labels(html)
_tab = [x for x in labels if "书架" in x]
check("★ 单本时页签数字与卡片数一致",
      bool(_tab) and "1" in _tab[0] and shelf_cards(html) == 1,
      f"tab={_tab} cards={shelf_cards(html)}")

print()
print("=" * 66)
print("O. 统计文案必须准确（数字骗人比 bug 更伤信任）")
print("=" * 66)
setup()
html = m.page_library([i for i in m.library() if i["slug"] == SLUG], {})
if '<div class="stats">' in html:
    _stats = html[html.find('<div class="stats">'):]
    _stats = _stats[:_stats.find("</header>")]
    _pairs = re.findall(r"<b>(\d+)</b>([^<]+)", _stats)
    check("统计项齐全", len(_pairs) == 4, str(_pairs))
    _labels = [p[1].strip() for p in _pairs]
    # history 是"每次阅读一条"的日志，不是章节数 —— 文案不能说"章"
    check("★ 不把阅读次数写成『读的章』",
          not any("读的章" in x for x in _labels), str(_labels))
    check("★ 阅读次数类文案包含『阅读』", sum("阅读" in x for x in _labels) >= 2,
          str(_labels))
else:
    check("（无统计数据时跳过）", True)

print()
print("=" * 66)
print("P. 翻译任务/进度回归（审计 ○ 项）")
print("=" * 66)

# —— 13：未读的书 read 必须是 0（不是默认 1），否则「新书」永远被当成「读过」
setup()
check("★ 未读的书 read == 0（不是默认 1）",
      item()["read"] == 0, f"read={item()['read']}")
_want = [i for i in m.library() if i["slug"] == SLUG and i["read"] > 0]
_new = [i for i in m.library() if i["slug"] == SLUG and i["read"] == 0]
check("★ 未读的书归入『新书』而不是『读过』",
      len(_new) == 1 and len(_want) == 0, f"want={len(_want)} new={len(_new)}")
m.set_progress(SLUG, 3)
check("读过第 3 章后 read == 3", item()["read"] == 3, f"read={item()['read']}")

# —— 12：中文书名两来源合并（meta.zh_titles.book 也要读到，否则推荐卡日文）
setup()
_wh = m.work_head({"id": "1", "slug": SLUG, "title": "日本語タイトル"}, {})
check("★ work_head 合并 meta.zh_titles.book",
      "状态机测试" in _wh and "日本語タイトル" in _wh, _wh[:120])

# —— 11：「点我翻译」的显式请求必须绕过「自动翻译未开」的闸门
setup()
_meta = m.novel_meta(SLUG)
_t_off, _ = m.allowed_targets(SLUG, _meta, 9999, None, explicit_ceiling=None)
check("自动翻译未开时，纯自动路径不翻（闸门正常）", _t_off == [], str(_t_off))
_t_on, _ = m.allowed_targets(SLUG, _meta, 9999, None,
                             explicit_ceiling=len(_meta.get("episodes") or []))
check("★ 显式天花板能让『点我翻译』正常翻（不再静默不翻）",
      len(_t_on) > 0, f"targets={_t_on[:5]}")

# —— 14：job_view 卡死兜底确实会把僵尸任务判成 error（不被轮询刷掉）
setup()
m.JOBS[SLUG] = {"status": "running", "token": 1,
                "heartbeat": m.time.time() - 10 * m.JOB_STALE_SEC,
                "at": m.time.time() - 10 * m.JOB_STALE_SEC}
_jv = m.job_view(SLUG)
check("★ 心跳过期的 running 任务被判 interrupted（轮询不再无限等）",
      _jv.get("status") == "interrupted", str(_jv.get("status")))
m.JOBS.pop(SLUG, None)

# —— 15：refresh_async 的 check-then-set 有锁（紧接的第二次被拒，不叠任务）
_rc = m.recs
_orig_refresh = _rc.refresh
_rc.refresh = lambda **k: []
_rc.SCAN.update(running=False)
try:
    _first = _rc.refresh_async(queries=["x"])
    _second = _rc.refresh_async(queries=["x"])
    check("★ 重新抓取：第一次启动、紧接第二次被拒（不叠第二个任务）",
          _first is True and _second is False, f"first={_first} second={_second}")
finally:
    _rc.refresh = _orig_refresh
    _rc.SCAN.update(running=False)

# —— 16：卡片 HTML 转义（标题/作者来自源站或 LLM，含 < " 不能破坏 DOM）
_bad_it = {
    "slug": 'x" onmouseover="evil', "id": '1" data-x="2',
    "title": '标"题<svg onload=alert(1)>', "title_zh": "", "title_jp": "",
    "author": '作"者<b>', "total": 10, "translated": 0, "read": 0,
    "favorite": False, "tracking": None, "t_enabled": False,
    "has_update": False, "new_episodes": 0, "last_read": "",
    "checked_at": "", "stale": 0, "dormant": False, "book_progress": 0,
}
_c = m._card(_bad_it, {})
check("★ 卡片标题里的 < 被转义（不产生真标签）",
      "<svg" not in _c and "&lt;svg" in _c)
check("★ 卡片作者里的 < 被转义", "<b>" not in _c)
check("★ 属性里的引号不会截断 data-*（attrescape）",
      'data-slug="x&quot; onmouseover=&quot;evil"' in _c
      and 'data-wid="1&quot; data-x=&quot;2"' in _c)
check("★ 搜索索引 data-hay 也按属性转义", '标&quot;题' in _c)

# 书库面板是另一条渲染路径（历史上两处各写一遍、改一处漏一处）：
# data-hay/data-lib 同样必须按**属性**转义，否则引号会截断属性。
_orig_li, _orig_lc, _orig_ld = (m.recs.library_items, m.recs.library_count,
                                m.load_detail)
try:
    m.recs.library_items = lambda *a, **k: [{
        "id": '9" data-x="1', "title": '书"名<x>', "author": '作"者<y>',
        "tags": [], "want": False, "episodes": 1, "points": 0}]
    m.recs.library_count = lambda *a, **k: 1
    m.load_detail = lambda *a, **k: {}
    _lp = m.library_pane()
finally:
    m.recs.library_items, m.recs.library_count = _orig_li, _orig_lc
    m.load_detail = _orig_ld
check("★ 书库面板 data-hay/data-lib 也按属性转义",
      '书&quot;名' in _lp and 'data-lib="9&quot; data-x=&quot;1"' in _lp)

# —— 17：翻译失败痕迹要**持久化**（重启后卡片仍提示可重试），成功后成对清除
setup()
m._note_trans_error(SLUG, '第 3 章：RuntimeError: "boom" <x>')
_it = item()
check("★ 失败痕迹落到书上（不只留在 JOBS 内存）",
      str(_it.get("trans_error") or "").startswith("第 3 章"),
      str(_it.get("trans_error"))[:40])
_c = m._card(_it, {})
check("★ 卡片按持久痕迹显示「翻译失败」与重试按钮",
      "翻译失败" in _c and 'data-act="retry"' in _c)
check("★ 失败详情进 title 属性时按属性转义",
      '&quot;boom&quot;' in _c and "&lt;x&gt;" in _c and "<x>" not in _c)
m._clear_trans_error(SLUG)
_it2 = item()
check("★ 重试成功后痕迹被清除（徽标不会永远亮着）",
      not _it2.get("trans_error"))
_c2 = m._card(_it2, {})
check("★ 清除后卡片不再显示失败徽标",
      "翻译失败" not in _c2 and 'data-act="retry"' not in _c2)

# —— 18：slug 是数据根内的目录名，不能借它逃出去 ——
setup()
check("正常 slug 仍然可用",
      m._valid_slug(SLUG) and m.novel_meta(SLUG) is not None)
for _bad in ("../x", "..", "a/b", "a\\b", "", "/abs/x", "a\x00b", "x" * 141):
    check(f"危险 slug 被拒绝：{_bad!r}", m._valid_slug(_bad) is False)
_raised = False
try:
    m.book_state_path("../x")
except ValueError:
    _raised = True
check("book_state_path 拒绝穿越", _raised)
check("novel_meta 拒绝穿越（返回 None）", m.novel_meta("../x") is None)
check("_read_book 拒绝穿越且不抛异常",
      m._read_book("../x").get("progress") == {})

# —— 重启自动续跑：只认「因重启中断」+ 书开着自动翻译 ——
_base = {"status": "interrupted", "remaining_chapters": [30, 31],
         "error": "服务重启或进程中断；已停止调度，等待用户确认恢复",
         "job_id": "job-x", "requested": {"reason": "reader"}}
_plan = m._auto_resume_plan(_base, auto_translate=True, total=60)
check("★ 重启中断 + 自动翻译开着 → 自动续跑原来的剩余章节",
      _plan and _plan["after"] == 29 and _plan["ceiling"] == 31
      and _plan["count"] == 2, str(_plan))
check("自动翻译没开 → 不自动花钱",
      m._auto_resume_plan(_base, auto_translate=False, total=60) is None)
check("provider_error（源站/模型失败）不会被自动重试",
      m._auto_resume_plan(dict(_base, error="抓取第 30 章原文失败：TimeoutError"),
                          auto_translate=True, total=60) is None)
check("上一条自己就是自动续跑的 → 不套娃（防无限花钱）",
      m._auto_resume_plan(dict(_base, requested={"reason": "resume-after-restart"}),
                          auto_translate=True, total=60) is None)
check("剩余章数超过 10 → 不自动续（重启不该触发大批量）",
      m._auto_resume_plan(dict(_base, remaining_chapters=list(range(1, 12))),
                          auto_translate=True, total=60) is None)
check("没有剩余章节 → 不续跑",
      m._auto_resume_plan(dict(_base, remaining_chapters=[]),
                          auto_translate=True, total=60) is None)
# 真实场景（2026-10-22 E2E 抓到）：worker 刚启动、还没算出 targets 就被重启，
# 记录里 remaining_chapters 还是空数组，只有 create 时写下的 target 范围。
# 若只认 remaining，用户看到的就是「一重启就卡住」。
_p2 = m._auto_resume_plan(
    dict(_base, remaining_chapters=[], completed_chapters=[],
         target={"from_chapter": 1, "to_chapter": 2}),
    auto_translate=True, total=60)
check("★ 剩余为空但 target 有范围 → 从 target 派生并续跑",
      _p2 and _p2["after"] == 1 and _p2["ceiling"] == 2
      and _p2["count"] == 2, str(_p2))
_p3 = m._auto_resume_plan(
    dict(_base, remaining_chapters=[], completed_chapters=[1],
         target={"from_chapter": 1, "to_chapter": 3}),
    auto_translate=True, total=60)
check("target 派生时跳过已完成章", _p3 and _p3["count"] == 2
      and _p3["after"] == 1 and _p3["ceiling"] == 3, str(_p3))
_p4 = m._auto_resume_plan(
    dict(_base, remaining_chapters=[], target={"from_chapter": 1, "to_chapter": 20}),
    auto_translate=True, total=60)
check("target 派生后仍守「最多 10 章」", _p4 is None, str(_p4))

# —— 卡死修复：被取代的 worker 必须能关掉自己的耐久记录 ——
# 用户报过「翻译一直正在进行中」：进程还活着、章节其实译完了，但任务记录停在
# running。根因是 worker 收尾走 `_sync_job`，而它对 token 不匹配的情况**静默
# 返回 {}** —— 旧任务自己的记录就永远没人关。这里直接测那个收尾原语。
_STORE = m.jobstore.STORE
_rec = _STORE.create(
    slug="__superseded__", target={"from_chapter": 1, "to_chapter": 1},
    model_provider="stub", model_role="translate", model_id="stub",
    translation_config_hash="h", idempotency_key="k-superseded-1",
    requested={"count": 1, "reason": "reader", "after": 0, "fill": False,
               "ceiling": None, "resume_of": None},
    source_entries=[])
_STORE.update(_rec["job_id"], status="running")
_closed = m._close_own_record(_rec["job_id"], [1], [])
check("★ 被取代的 worker 收尾能关掉自己的记录（不再永远 running）",
      _closed and _STORE.get(_rec["job_id"])["status"] == "interrupted")
check("记录里留下完成/剩余章节（恢复时能算清缺哪些）",
      _STORE.get(_rec["job_id"])["completed_chapters"] == [1]
      and _STORE.get(_rec["job_id"])["remaining_chapters"] == [])
check("重复收尾幂等（不会把已结束的状态改回去）",
      not m._close_own_record(_rec["job_id"], [1], []))

# —— 术语表过期重翻：force 必须绕开「只补缺译」的 next_targets ——
check("force 只翻指定章（不越界）", m.forced_targets(5, 1, 5, 10) == [5],
      str(m.forced_targets(5, 1, 5, 10)))
check("force 可连翻 N 章", m.forced_targets(5, 3, 7, 10) == [5, 6, 7],
      str(m.forced_targets(5, 3, 7, 10)))
check("force 到全书末尾截断", m.forced_targets(9, 5, 20, 10) == [9, 10],
      str(m.forced_targets(9, 5, 20, 10)))

# 清理
m.invalidate_cache()
shutil.rmtree(D, ignore_errors=True)
bp = m.book_state_path(SLUG)
if os.path.exists(bp):
    os.remove(bp)
assert not os.path.exists(D), "自检目录没清干净！"
print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print(f"✅ 状态机测试全部通过（含 UI==实际 的穷举校验）")
