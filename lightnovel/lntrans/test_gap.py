#!/usr/bin/env python3
"""回归验证：翻译空洞下的行为（对应自检 2 和 3 暴露的问题）。

造一本假书：第 3 章缺、第 4 章为空，第 5~8 章有译文。
验证：
  · translated_count 仍返回连续前缀（用于"下一页从哪取"）
  · zh_chapters 能看到全部已译章（不再丢失后面 6 章）
  · next_targets 优先补第 3、4 章
  · 读者上报在第 5 章时，仍然优先翻第 5 章之后的内容
"""

import importlib.util
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 必须跟随 LNTRANS_DATA_ROOT 重定向（自检隔离靠它），
# 不能硬编码 HERE/novels —— 否则自检会写进真实书架。
_ROOT = os.environ.get("LNTRANS_DATA_ROOT") or HERE
NOVELS = os.path.join(_ROOT, "novels")
SLUG = "__gaptest__"

_s = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
mod = importlib.util.module_from_spec(_s)
sys.argv = ["lnserve"]
_s.loader.exec_module(mod)

d = os.path.join(NOVELS, SLUG)
shutil.rmtree(d, ignore_errors=True)
os.makedirs(os.path.join(d, "chapters"))
os.makedirs(os.path.join(d, "raw"))
meta = {
    "slug": SLUG, "source": "kakuyomu", "source_id": "1",
    "url": "https://kakuyomu.jp/works/1", "title": "空洞测试", "author": "t",
    "episodes": [{"id": str(i), "title": f"第{i+1}話"} for i in range(10)],
    "glossary": {}, "characters": {}, "summaries": {}, "style": {},
    "zh_titles": {}, "progress": {"translated_through": 0, "fetched_through": 0},
}
json.dump(meta, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False)

# 造空洞：1,2 有；3 缺；4 空文件；5~8 有
for c in (0, 1, 4, 5, 6, 7):
    open(os.path.join(d, "chapters", f"{c:04d}.txt"), "w").write(f"第{c+1}章译文")
open(os.path.join(d, "chapters", "0003.txt"), "w").write("")     # 空 = 失败残留

print("布局：", "1,2 有译 | 3 缺 | 4 空文件 | 5,6,7,8 有译 | 9,10 未译")
print()

have = mod.zh_chapters(SLUG, 10)
pref = mod.translated_count(SLUG, meta)
print(f"zh_chapters()      → {have}")
print(f"translated_count() → {pref}   (连续前缀，用于'下一页从哪取')")
ok1 = have == [1, 2, 5, 6, 7, 8]
print(f"  {'✅' if ok1 else '❌'} 后面 4 章不再被吞掉")

print()
t = mod.next_targets(SLUG, meta, 2)
print(f"next_targets(want=2)          → {t}")
ok2 = t == [3, 4]
print(f"  {'✅' if ok2 else '❌'} 优先补空洞（3、4），而不是重翻末尾")

t2 = mod.next_targets(SLUG, meta, 2, after=6)
print(f"next_targets(want=2, after=6) → {t2}")
ok3 = t2[0] > 6
print(f"  {'✅' if ok3 else '❌'} 读者在第 6 章时优先翻它后面的（9）")

print()
# 阅读页：上报读到第 5 章，应从第 5 章开始显示
st = mod.load_state()
slot = st.setdefault("progress", {})
# 直接用每书状态写，避免聚合层的干扰
bs = mod._read_book(SLUG)
bs["progress"] = {"chapter": 5, "at": "x"}
mod._write_book(SLUG, bs)
html = mod.page_reader(SLUG)
import re
chs = re.findall(r'data-ch="(\d+)"', html or "")
print(f"page_reader（上报读到第 5 章）→ 渲染章节 {chs}")
ok4 = chs[:1] == ["5"]
print(f"  {'✅' if ok4 else '❌'} 不再被空洞拽回前面")

print()
print("=" * 66)
print("翻译失败不得落盘（#4）：失败→不算已译/不落盘/可重试；原文不当译文")
print("=" * 66)
import argparse as _ap  # noqa: E402

open(os.path.join(d, "raw", "0008.txt"), "w", encoding="utf-8").write(
    "日本語のテスト文です。")                      # 第 9 章原文（原本未译）
_args = _ap.Namespace(force=False, dry_run=False, model="stub", temperature=0.0)
_orig_llm = mod.lt.call_llm

mod.lt.call_llm = lambda system, prompt, model, temperature, retries=3, role=None: (
    "#1:日本語のテスト文です。", {"total_tokens": 1})       # 模型把原文抄回来
try:
    ok_fail = mod.lt.translate_chapter(SLUG, 8, meta, _args)
finally:
    mod.lt.call_llm = _orig_llm
_meta_f = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
_prog_f = _meta_f["progress"]
ok5 = (ok_fail is False and not mod.has_zh(SLUG, 8)
       and _prog_f.get("translated_through", 0) < 9
       and 9 in (_prog_f.get("incomplete") or []))
print(f"  失败run → 返回 {ok_fail}，第9章落盘={mod.has_zh(SLUG, 8)}，"
      f"translated_through={_prog_f.get('translated_through')}，"
      f"incomplete={_prog_f.get('incomplete')}")
print(f"  {'✅' if ok5 else '❌'} 失败不落盘 / 不计已译 / 不推进，并标记 incomplete")

_cp = os.path.join(d, "cache", "0008.json")
_c_vals = (list(json.load(open(_cp, encoding="utf-8")).values())
           if os.path.exists(_cp) else [])
ok6 = not any("日本語" in "".join(map(str, v)) for v in _c_vals)
print(f"  {'✅' if ok6 else '❌'} 失败分段不写缓存（原文/坏译文不被永久复用）")

mod.lt.call_llm = lambda system, prompt, model, temperature, retries=3, role=None: (
    "#1:这是中文译文。", {"total_tokens": 1})              # 这次给中文
try:
    ok_ok = mod.lt.translate_chapter(SLUG, 8, meta, _args)
finally:
    mod.lt.call_llm = _orig_llm
_prog_ok = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))["progress"]
ok7 = (ok_ok is True and mod.has_zh(SLUG, 8)
       and 9 not in (_prog_ok.get("incomplete") or []))
print(f"  重试run → 返回 {ok_ok}，第9章落盘={mod.has_zh(SLUG, 8)}，"
      f"incomplete={_prog_ok.get('incomplete')}")
print(f"  {'✅' if ok7 else '❌'} 重试成功：落盘 + 清除 incomplete 标记")

shutil.rmtree(d, ignore_errors=True)
bp = mod.book_state_path(SLUG)
if os.path.exists(bp):
    os.remove(bp)
print()
_all = all([ok1, ok2, ok3, ok4, ok5, ok6, ok7])
print("回归结果：", "全部通过 ✅" if _all else "仍有失败 ❌")

# 失败必须反馈到退出码：run_selftests.py 只看 returncode，
# 不 sys.exit(1) 的话这个脚本无论如何都报"✅ 通过"（假绿）。
if not _all:
    sys.exit(1)
