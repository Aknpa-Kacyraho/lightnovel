#!/usr/bin/env python3
"""三项自检：实测当前实现在"书多起来"和"反馈"上的真实表现。

不猜，直接造数据跑：
  1. 批量建 N 本书 → 量首页体积、API 体积、状态文件读写成本
  2. 制造"翻译空洞" → 看 translated_count 还算不算得对
  3. 逆向阅读 → 看进度与续译逻辑会不会出错
"""

import importlib.util
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_s = importlib.util.spec_from_file_location("lntrans", os.path.join(HERE, "lntrans.py"))
lt = importlib.util.module_from_spec(_s)
sys.argv = ["x"]
_s.loader.exec_module(lt)

# 必须跟随 LNTRANS_DATA_ROOT 重定向（自检隔离靠它），
# 不能硬编码 HERE/novels —— 否则自检会写进真实书架。
_ROOT = os.environ.get("LNTRANS_DATA_ROOT") or HERE
NOVELS = os.path.join(_ROOT, "novels")
DATA = os.path.join(HERE, "data")
FAKE = os.path.join(NOVELS, "__selftest__")


def purge_fake_books() -> None:
    """清理自检造的书。

    踩过：build_fake_books 生成的是 bookNNN，而清理只删了 __selftest__，
    结果 20 本假书留在书架上（"在读 20 本"）。所以清理要按生成规则来。
    """
    import glob
    for p in glob.glob(os.path.join(NOVELS, "book0*")):
        shutil.rmtree(p, ignore_errors=True)
    for p in glob.glob(os.path.join(DATA, "books", "book0*.json")):
        os.remove(p)


def build_fake_books(n: int, chapters: int = 61) -> None:
    purge_fake_books()
    shutil.rmtree(FAKE, ignore_errors=True)   # FAKE 已不用，清掉历史残留
    os.makedirs(NOVELS, exist_ok=True)
    for i in range(n):
        slug = f"book{i:03d}"
        d = os.path.join(NOVELS, slug)
        os.makedirs(os.path.join(d, "chapters"), exist_ok=True)
        os.makedirs(os.path.join(d, "raw"), exist_ok=True)
        meta = {
            "slug": slug, "source": "kakuyomu", "source_id": str(10**15 + i),
            "url": f"https://kakuyomu.jp/works/{10**15+i}",
            "title": f"テスト作品 第{i}巻 とても長いタイトルのサンプル",
            "author": f"作者{i}",
            "episodes": [{"id": str(k), "title": f"第{k+1}話 サンプル"}
                         for k in range(chapters)],
            "glossary": {f"用語{k}": f"术语{k}" for k in range(40)},
            "characters": {}, "summaries": {}, "style": {},
            "zh_titles": {"book": f"测试作品 第{i}卷", **{str(k+1): f"第{k+1}话 样例" for k in range(chapters)}},
            "progress": {"translated_through": 8, "fetched_through": 8},
            "created_at": "2026-10-15 18:00:00",
        }
        json.dump(meta, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False)
        for c in range(8):
            open(os.path.join(d, "chapters", f"{c:04d}.txt"), "w").write(
                "这是一段样例译文。" * 200)
            open(os.path.join(d, "raw", f"{c:04d}.txt"), "w").write("サンプル原文。" * 200)


# ---------------------------------------------------------------- 1. 规模

print("=" * 66)
print("【自检 1 / 规模】书多起来会怎样")
print("=" * 66)

for n in (1, 5, 20):
    build_fake_books(n)
    t0 = time.time()
    sys.path.insert(0, HERE)
    sv = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
    mod = importlib.util.module_from_spec(sv)
    sys.argv = ["lnserve"]
    sv.loader.exec_module(mod)
    items = mod.library()
    t_lib = (time.time() - t0) * 1000

    t0 = time.time()
    html = mod.page_library(items, {})
    t_html = (time.time() - t0) * 1000

    t0 = time.time()
    st = mod.load_state()
    st.setdefault("progress", {})["book000"] = {"chapter": 3, "at": "x"}
    mod.save_state(st)
    t_state = (time.time() - t0) * 1000

    total_chars = sum(sum(len(open(os.path.join(NOVELS, f"book{i:03d}", "chapters", f"{c:04d}.txt")).read())
                          for c in range(8)) for i in range(n))
    print(f"  {n:>2} 本书：首页 HTML {len(html)/1024:7.1f} KB | "
          f"library() {t_lib:6.0f} ms | 渲染 {t_html:6.0f} ms | "
          f"状态写入 {t_state:5.1f} ms | 译文总量 {total_chars/1024:6.0f} KB")

purge_fake_books()

print()
print("  推论：")
print("   · library() 每次都遍历全书目录并 stat 每个章节文件 → O(书数 × 章节数)")
print("   · 首页无分页/搜索，书多了就是一张无限长的列表")
print("   · 状态已拆成 data/books/<slug>.json（每读一章只重写这一本）")

# ---------------------------------------------------------------- 2. 空洞

print()
print("=" * 66)
print("【自检 2 / 工程】翻译空洞（第 3 章失败但第 4 章成功）")
print("=" * 66)

build_fake_books(1)
d = os.path.join(NOVELS, "book000")
open(os.path.join(d, "chapters", "0003.txt"), "w").write("")      # 第4章为空=失败
os.remove(os.path.join(d, "chapters", "0002.txt"))                # 第3章干脆不存在
meta = json.load(open(os.path.join(d, "meta.json")))
sv = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
mod = importlib.util.module_from_spec(sv)
sys.argv = ["lnserve"]
sv.loader.exec_module(mod)

存在 = [c for c in range(8) if os.path.exists(os.path.join(d, "chapters", f"{c:04d}.txt"))
        and os.path.getsize(os.path.join(d, "chapters", f"{c:04d}.txt")) > 0]
have = mod.zh_chapters("book000", len(meta["episodes"]))
pref = mod.translated_count("book000", meta)
print(f"  实际有译文的章：{have}")
print(f"  translated_count()（连续前缀）：{pref} 章")
print(f"  zh_chapters()（全部已译）：{have}")
print(f"  next_targets(want=2)：{mod.next_targets('book000', meta, 2)}")
ok_gap = have == [1, 2, 5, 6, 7, 8] and mod.next_targets('book000', meta, 2) == [3, 4]
print("  " + ("✅ 空洞容忍正常：后面已译的章节仍可见，且优先补空洞"
              if ok_gap else "❌ 仍有问题"))

# ---------------------------------------------------------------- 3. 逆向阅读

print()
print("=" * 66)
print("【自检 3 / 用户】从第 5 章往回读、或跳到中间")
print("=" * 66)
st = mod.load_state()
st["progress"]["book000"] = {"chapter": 5, "at": "x"}
mod.save_state(st)
done = mod.translated_count("book000", meta)
import re as _re
html = mod.page_reader("book000") or ""
chs = _re.findall(r'data-ch="(\d+)"', html)
print(f"  上报读到第 5 章 → page_reader 渲染 {chs}")
ok_start = chs[:1] == ["5"]
print("  " + ("✅ 从上次读到的地方继续，不会被拽回前面"
              if ok_start else f"❌ 起始章不对：{chs[:1]}"))

# ---------------------------------------------------------------- 4. 反馈重复

print()
print("=" * 66)
print("【自检 4 / 工程】反馈写入是否重复累加")
print("=" * 66)
bs = mod._read_book("book000")
bs["feedback"] = []
mod._write_book("book000", bs)
for i in range(3):
    mod.append_feedback("book000", {"at": f"t{i}", "slug": "book000",
                                    "chapter": i + 1, "vote": "good", "note": f"n{i}"})
n = len(mod._read_book("book000")["feedback"])
ok_fb = (n == 3)
print(f"  提交 3 次 → 实际存 {n} 条")
print("  " + ("✅ 精确累加" if ok_fb else f"❌ 重复写入（应为 3，实际 {n}）"))
print("  说明：这里必须用 append_feedback()，"
      "用 save_state(整份聚合) 会把历史反馈重复追加。")

# ---------------------------------------------------------------- 5. slug 撞车

print()
print("=" * 66)
print("【自检 5 / 用户】加书时 slug 撞车（日文标题缩成同一个 ASCII 短名）")
print("=" * 66)
print("  背景：用户报「点加入书架永远失败」—— 两部作品的标题都只保留出 ASCII")
print("        「TS…」→ slugify 都得到 \"ts\"，后来那本被静默丢弃（既没建目录也没上架）。")
_real_fetch = lt.fetch_work


def _fake_work(wid: str, title: str):
    return {"id": wid, "title": title, "author": "作者",
            "episodes": [{"id": "1", "title": "第1話", "publishedAt": "2026-01-01"}]}


lt.fetch_work = lambda url: _fake_work(
    _re2.search(r"/works/(\d+)", url).group(1),
    "TS転生してたので、魔法少女達（曇らせ）を見に行きます。"
    if "111" in url else "TS変身！魔法少女☆ゆりゆりっ！")
import re as _re2
try:
    lt.cmd_init(lt.argparse.Namespace(url="https://kakuyomu.jp/works/111", slug=None, force=False))
    lt.cmd_init(lt.argparse.Namespace(url="https://kakuyomu.jp/works/222", slug=None, force=False))
finally:
    lt.fetch_work = _real_fetch
_dirs = sorted(d for d in os.listdir(NOVELS)
               if os.path.isdir(os.path.join(NOVELS, d)) and d.startswith(("ts", "kakuyomu-111", "kakuyomu-222")))
_ids = set()
for d in _dirs:
    try:
        _ids.add(str(json.load(open(os.path.join(NOVELS, d, "meta.json")))["source_id"]))
    except (OSError, ValueError, KeyError):
        pass
print(f"  建出来的目录：{_dirs}")
print(f"  对应的 source_id：{sorted(_ids)}")
ok_slug = len(_ids) == 2 and {"111", "222"} <= _ids
print("  " + ("✅ 撞车时另起目录，两部都在（不会被静默丢一部）"
              if ok_slug else "❌ 撞车处理仍有问题：有一部没建出来"))
# 再来一次同一部：必须命中的是"已存在"，不会新建第二个目录
_before = set(os.listdir(NOVELS))
import argparse as _ap
_real_fetch2 = lt.fetch_work
lt.fetch_work = lambda url: _fake_work("111", "TS転生してたので、魔法少女達（曇らせ）を見に行きます。")
try:
    lt.cmd_init(_ap.Namespace(url="https://kakuyomu.jp/works/111", slug=None, force=False))
finally:
    lt.fetch_work = _real_fetch2
ok_idem = set(os.listdir(NOVELS)) == _before
print("  " + ("✅ 同一部重复加入是幂等的（不新建目录）" if ok_idem else "❌ 重复加入又建了一个目录"))
for d in _dirs:
    shutil.rmtree(os.path.join(NOVELS, d), ignore_errors=True)

purge_fake_books()
purge_fake_books()
print()
print("自检数据已清理。")

# 失败必须反馈到退出码：run_selftests.py 只看 returncode，
# 不 sys.exit(1) 的话这个脚本无论如何都报"✅ 通过"（假绿）。
if not (ok_gap and ok_start and ok_fb and ok_slug and ok_idem):
    sys.exit(1)
