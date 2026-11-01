#!/usr/bin/env python3
"""一键跑完所有自检，并在结束时断言"环境是干净的"。

为什么需要这个：单跑某个 selftest 容易漏掉残留
（曾因变量被覆盖 + ignore_errors=True，清理静默失败还打印"已清理"）。
所以这里做三件事：
  1. 跑之前先记录 novels/data 的快照
  2. 跑每个自检
  3. **跑完之后断言快照没变**——多了东西就报错并指出是什么

用法：python3 run_selftests.py
"""

from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NOVELS = os.path.join(HERE, "novels")
BOOKS = os.path.join(HERE, "data", "books")

TESTS = ["selftest.py", "selftest2.py", "selftest3.py", "selftest4.py",
         "selftest5.py", "test_gap.py", "test_flow.py", "test_pages.py",
         "test_ui.py", "test_state.py", "test_translate.py", "test_detail.py",
         "test_review.py", "test_recs.py", "test_click.py", "test_reader.py",
         "test_storage.py", "test_auth.py", "test_devices.py", "test_js_static.py",
         "test_quotes.py", "test_backup.py", "test_epub.py",
         "test_covers.py", "test_contracts.py", "test_data_safety.py",
         "test_jobs.py", "test_models.py", "test_zh_cache.py",
         "test_share_package.py", "test_sched.py", "test_syosetu.py",
         "test_import.py", "test_stale.py", "test_routes.py"]
# test_pages.py 需要服务在跑；没跑就跳过（不算失败）


VERBOSE = ("-v" in sys.argv[1:]) or (os.environ.get("LNTRANS_VERBOSE") == "1")
# -k a,b 只跑名字里含 a 或 b 的测试（调单个测试时不用等全套）
_ONLY = ""
for _i, _a in enumerate(sys.argv[1:]):
    if _a == "-k" and _i + 2 <= len(sys.argv) - 1:
        _ONLY = sys.argv[_i + 2]
    elif _a.startswith("-k="):
        _ONLY = _a[3:]
ONLY = [x for x in _ONLY.split(",") if x]


def snapshot() -> set[str]:
    out = set()
    for base, tag in ((NOVELS, "novel"), (BOOKS, "state")):
        if not os.path.isdir(base):
            continue
        for n in os.listdir(base):
            out.add(f"{tag}:{n}")
    return out


# 自检**绝不能**改这些文件：它们不在临时数据根里，rmtree 兜不住，
# 只能前后比指纹。
# taste_profile.json 尤其关键 —— /api/dislike 是**写画像**的接口，
# 测试一旦漏了 LNTRANS_LNFINDER，就会把用户真实口味画像改掉。
# 覆盖 AGENTS.md「真实资产，绝不写入」清单里**正常服务不会写**的部分；
# data/ 下会被服务并发写的动态文件（details/books/history）暂不纳入，
# 否则挂着服务时跑自检会假红。目录用「相对路径+大小+mtime」摘要。
_FINDER = os.path.join(os.path.dirname(HERE), "lnfinder")
REAL_FILES = [os.path.join(_FINDER, "taste_profile.json"),
              os.path.join(_FINDER, "history.jsonl"),
              os.path.join(_FINDER, "candidates.json"),
              os.path.join(_FINDER, "reports"),
              os.path.join(_FINDER, "recommend-latest.md"),
              os.path.join(HERE, "data", "recs.json"),
              os.path.join(HERE, "data", "library.json")]


def _file_fp(p: str) -> str:
    import hashlib
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()[:10]


def _dir_fp(d: str) -> str:
    """目录指纹：逐文件 相对路径+大小+mtime（不读内容，快且够发现增删改）。"""
    import hashlib
    rows = []
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in sorted(files):
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            rows.append(f"{os.path.relpath(p, d)}|{st.st_size}|{int(st.st_mtime)}")
    return hashlib.md5("\n".join(rows).encode()).hexdigest()[:10]


def fingerprints() -> dict:
    out = {}
    for p in REAL_FILES:
        try:
            out[p] = _dir_fp(p) if os.path.isdir(p) else _file_fp(p)
        except OSError:
            out[p] = "-"
    # 导出的整本译文（*-中文.md）也在「绝不写入」清单里，服务不会碰它们。
    import glob
    for p in glob.glob(os.path.join(HERE, "*-中文.md")):
        try:
            out[p] = _file_fp(p)
        except OSError:
            out[p] = "-"
    return out


# 自检会造出这些命名的作品；跑完必须消失。
TEST_PREFIXES = ("__", "book0")


def suspicious(items: set[str]) -> set[str]:
    """明显是自检产物却没被清掉的条目（不看基线，直接按命名识别）。"""
    out = set()
    for it in items:
        name = it.split(":", 1)[1]
        if name.startswith(TEST_PREFIXES):
            out.add(it)
    return out


def main() -> int:
    # === 隔离：每个自检跑在**临时数据根**里 ===
    # 踩过：自检直接写 novels/ 与 data/，把用户真实的 favorites 改成了 False。
    # 现在通过 LNTRANS_DATA_ROOT 把数据根指到临时目录，测试再怎么折腾都不影响
    # 真实书架。测试内部无需任何改动（NOVELS/DATA 在模块加载时读这个变量）。
    import tempfile
    tmp_root = tempfile.mkdtemp(prefix="lntrans-selftest-")
    os.makedirs(os.path.join(tmp_root, "novels"), exist_ok=True)
    os.makedirs(os.path.join(tmp_root, "data"), exist_ok=True)
    print(f"隔离数据根：{tmp_root}\n")

    before = snapshot()
    fp_before = fingerprints()
    pre_leak = suspicious(before)
    if pre_leak:
        print(f"⚠ 跑之前就有自检产物残留：{sorted(pre_leak)}")
        print("  （上一次自检没清干净；本次结束会一并报告）")
    print(f"跑前环境：{len(before)} 项  {sorted(before)}")
    print()

    # === 需要活服务的测试：自己起一个**隔离的测试服务** ===
    # 不要打真实 8099 —— test_ui.py 会真的改状态（踩过：把用户的收藏改掉了）。
    # 这里用临时数据根 + 备用端口跑一个测试实例，跑完关掉。
    import socket
    import subprocess as _sp
    import time as _t
    import urllib.request

    # 往临时根种一本最小可用的测试书：test_ui 要检查卡片/按钮与 API 行为，
    # 空书架会让它误报失败（而真实书架又不该被碰）。
    _seed_dir = os.path.join(tmp_root, "novels", "__ui_seed__")
    os.makedirs(os.path.join(_seed_dir, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(_seed_dir, "raw"), exist_ok=True)
    import json as _json
    with open(os.path.join(_seed_dir, "meta.json"), "w", encoding="utf-8") as f:
        _json.dump({
            "slug": "__ui_seed__", "source": "kakuyomu", "source_id": "seed-1",
            "url": "https://kakuyomu.jp/works/1", "title": "UI 种子作品",
            "author": "seed", "zh_titles": {"book": "UI 种子作品", "1": "第1话"},
            "episodes": [{"id": "1", "title": "第1話"}],
            "glossary": {}, "characters": {}, "summaries": {}, "style": {},
            "progress": {"translated_through": 0, "fetched_through": 0},
        }, f, ensure_ascii=False)
    with open(os.path.join(_seed_dir, "chapters", "0000.txt"), "w",
              encoding="utf-8") as f:
        f.write("这是种子章节的译文。")

    # 每次自己找一个**真正空闲**的端口，避免撞上遗留进程
    # （踩过：固定 8199 被残留服务占着，健康检查过了但其实连的是空实例，
    #   于是 test_ui 报"书架为空"，非常难查）。
    def _free_port() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    # 隔离一份 lnfinder 目录：/api/dislike 会**写口味画像**。
    # 不隔离的话，测试点一次「不感兴趣」就真的改掉了用户的 taste_profile.json
    # （和当初 lnrecs 没读 LNTRANS_DATA_ROOT 是同一类坑）。
    _lf_dir = os.path.join(tmp_root, "lnfinder")
    os.makedirs(_lf_dir, exist_ok=True)
    _real_lf = os.path.join(os.path.dirname(HERE), "lnfinder", "taste_profile.json")
    _seed_prof = {}
    try:
        import shutil as _sh3
        if os.path.exists(_real_lf):
            _sh3.copy2(_real_lf, os.path.join(_lf_dir, "taste_profile.json"))
        with open(os.path.join(_lf_dir, "taste_profile.json"), encoding="utf-8") as _f:
            _seed_prof = json.load(_f)
    except Exception:  # noqa: BLE001
        _seed_prof = {}
    if not _seed_prof:
        # 真实画像读不到也要能测：给一份最小可用的
        _seed_prof = {"tag_weights": {"百合": 2.0, "勘違い": 1.8, "異世界転生": 1.0},
                      "genre_weights": {}, "formula_tags": {"異世界転生": 1},
                      "misunderstanding_tags": {}, "blocked_tags": [],
                      "min_review_points": 0, "min_episodes": 0,
                      "min_tag_hits": 1, "weak_hit_min_score": 0,
                      "weak_hit_min_points": 0}
        with open(os.path.join(_lf_dir, "taste_profile.json"), "w",
                  encoding="utf-8") as _f:
            json.dump(_seed_prof, _f, ensure_ascii=False)
    for _fn in ("history.jsonl", "candidates.json"):
        p = os.path.join(_lf_dir, _fn)
        if not os.path.exists(p):
            open(p, "w", encoding="utf-8").close()
    os.makedirs(os.path.join(_lf_dir, "reports"), exist_ok=True)
    print(f"隔离画像目录：{_lf_dir}（tag_weights {len(_seed_prof.get('tag_weights') or {})} 项）")

    # 把**真实书库的只读副本**种进临时根：分页测试需要足够多的条目。
    # 注意：只是拷贝给测试用，绝不写回源文件。
    try:
        import shutil as _sh2
        _real_lib = os.path.join(HERE, "data", "library.json")
        if os.path.exists(_real_lib):
            _sh2.copy2(_real_lib, os.path.join(tmp_root, "data", "library.json"))
    except Exception:  # noqa: BLE001
        pass

    # 书库**太小就合成一份**（干净副本里没有 data/library.json）。
    #
    # 为什么必须合成，而不是跳过相关断言：一份刚拷出来的干净目录（就是分享给别人的
    # 第一份）没有真实书库，于是"书库分页 ≥2 页""搜索命中子集""推荐位换一批"
    # 这些断言会因为"书库只有 3 本"而全红 —— 接收方第一次跑自检就看到失败，
    # 会以为自己装错了。而"跳过"就是假绿（明文禁止）。
    # 合成的条目 id 用 `syn*`、source 写「自检合成」，一眼能认出不是真实数据；
    # 它们只活在临时数据根里。
    try:
        _libp_syn = os.path.join(tmp_root, "data", "library.json")
        _lib_syn = {}
        if os.path.exists(_libp_syn):
            with open(_libp_syn, encoding="utf-8") as _f:
                _lib_syn = json.load(_f) or {}
        if len(_lib_syn) < 40:
            _tagw = _seed_prof.get("tag_weights") or {}
            _blocked = set(_seed_prof.get("blocked_tags") or [])
            _syn_tags = [t for t, _w in sorted(_tagw.items(), key=lambda kv: -kv[1])
                         if t not in _blocked][:3] or ["テスト"]
            for _i in range(36):
                _wid = "syn%03d" % _i
                _syn_t = list(_syn_tags[:2])
                # 一半带「ざまぁ」：搜索断言要的是"命中一个子集"，
                # 而且命中数必须**超过一页**（>15）——否则分页控件不渲染，
                # 「共 N 项」那个数字压根不在页面上，断言读到 0 而误报
                # （踩过：只给 6 本命中 → 1 页 → 分页控件消失 → 断言红）。
                if _i % 2 == 0:
                    _syn_t.append("ざまぁ")
                _lib_syn[_wid] = {
                    "id": _wid, "title": "合成作品 %02d" % _i,
                    "author": "合成作者%d" % (_i % 5),
                    "url": "https://example.invalid/works/" + _wid,
                    "tags": _syn_t, "genre": "テスト",
                    "episodes": 40 + _i, "characters": 100000, "points": 3000,
                    "updated": "2099-01-01",
                    "first_seen": "2099-01-%02d 00:00:00" % (_i % 28 + 1),
                    "sources": ["自检合成"],
                }
            with open(_libp_syn, "w", encoding="utf-8") as _f:
                json.dump(_lib_syn, _f, ensure_ascii=False)
            print(f"书库种子：真实书库不可用 → 合成 {len(_lib_syn)} 本"
                  f"（标签取自隔离画像：{'、'.join(_syn_tags)}）")
        else:
            print(f"书库种子：真实书库只读副本 {len(_lib_syn)} 本")
    except Exception as _e:  # noqa: BLE001
        print(f"⚠ 书库种子失败：{type(_e).__name__}: {_e}")

    # 给书库副本**每一本**都种上详情，这样"书库中文优先"的断言有数据可测
    # （真实环境里中文来自 data/details/<id>.json）
    #
    # 踩过：原来只种"dict 顺序前 20 条"，而书库面板是按 `first_seen` **倒序**取前
    # 15 张卡（library_items）—— 种的正好是**最老的 20 本**，面板显示的却是**最新的 15 本**。
    # 之所以一直没炸：最初整个书库是一次性导入的（first_seen 全相同），
    # 稳定排序下"前 15 张卡"恰好就是 dict 前 15 条。
    # 用户自己点了一次「重新抓取」→ 新增 305 本（first_seen 变新）→ 排序一变，
    # 面板显示的全是没种详情的书 → 两条断言立刻红了。
    # 结论：断言不能依赖"种了哪几条"，全种上就不会再有顺序耦合。
    try:
        import json as _json2
        _libp = os.path.join(tmp_root, "data", "library.json")
        if os.path.exists(_libp):
            with open(_libp, encoding="utf-8") as _f:
                _lib2 = _json2.load(_f)
            _dd2 = os.path.join(tmp_root, "data", "details")
            os.makedirs(_dd2, exist_ok=True)
            for _wid2 in _lib2:
                with open(os.path.join(_dd2, str(_wid2) + ".json"), "w",
                          encoding="utf-8") as _f:
                    _json2.dump({"synopsis": "日语简介（种子）",
                                 "zh_title": "中文书名（种子）",
                                 "zh_synopsis": "这是种子的中文简介。"}, _f,
                                ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass

    # 书架上那两本种子作品也要有**详情缓存**：卡片上的中文书名来自
    # `data/details/<源站id>.json`，**不是** meta.json 里的 `zh_titles`
    # （`work_head` 读的是 det）。没有它，`work_head` 走"未翻译"分支、
    # 不渲染 `jp-sub` —— 于是"共用 head 输出中文标题 + 日文副标题"这条断言
    # 要么永远 skip、要么误报成产品 bug。这两本不在 library.json 里，
    # 所以上面"给书库每一本种详情"那一步覆盖不到它们。
    os.makedirs(os.path.join(tmp_root, "data", "details"), exist_ok=True)
    for _sid, _zht in (("888000222", "测试在读的书（中文名）"),
                       ("777000333", "流程确认用（中文名）")):
        with open(os.path.join(tmp_root, "data", "details", _sid + ".json"), "w",
                  encoding="utf-8") as _f:
            json.dump({"zh_title": _zht,
                       "zh_synopsis": "这是种子的中文简介。"}, _f,
                      ensure_ascii=False)

    # 种一本"在读"的书：让「接着读」banner 和状态 chip 的断言有数据可测
    _sh = os.path.join(tmp_root, "novels", "__resume_seed__")
    os.makedirs(os.path.join(_sh, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(_sh, "raw"), exist_ok=True)
    with open(os.path.join(_sh, "meta.json"), "w", encoding="utf-8") as f:
        _json.dump({
            "slug": "__resume_seed__", "source": "kakuyomu",
            "source_id": "888000222",
            "url": "https://kakuyomu.jp/works/888000222",
            "title": "テスト読書中の本", "author": "seed",
            "zh_titles": {"book": "测试在读的书", "1": "第1话", "2": "第2话",
                          "3": "第3话"},
            "episodes": [{"id": str(i), "title": "第%d話" % (i + 1)}
                         for i in range(6)],
            "glossary": {}, "characters": {}, "summaries": {}, "style": {},
            "progress": {"translated_through": 0, "fetched_through": 0},
        }, f, ensure_ascii=False)
    for _i in range(3):
        with open(os.path.join(_sh, "chapters", "%04d.txt" % _i), "w",
                  encoding="utf-8") as f:
            f.write("这是第 %d 章的译文。" % (_i + 1))
    os.makedirs(os.path.join(tmp_root, "data", "books"), exist_ok=True)
    with open(os.path.join(tmp_root, "data", "books", "__resume_seed__.json"),
              "w", encoding="utf-8") as f:
        _json.dump({"tracking": "reading", "favorites": "2026-01-01 00:00:00",
                    "progress": {"chapter": 2, "at": "2099-01-01 00:00:00",
                                 "scroll": 0.3}},
                   f, ensure_ascii=False)

    # 种一本「只在详情缓存里有中文名」的书：回归用户报的
    # 「书架里的书标题没翻译」——meta.zh_titles 里没有 book，但
    # data/details/<id>.json 有 zh_title（列表页翻译出来的就存在这儿）。
    # 书架卡必须能回退读到它；顺便保证未译时**不会把同一行日文显示两遍**。
    _zh = os.path.join(tmp_root, "novels", "__zh_title_seed__")
    os.makedirs(os.path.join(_zh, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(_zh, "raw"), exist_ok=True)
    with open(os.path.join(_zh, "meta.json"), "w", encoding="utf-8") as f:
        _json.dump({
            "slug": "__zh_title_seed__", "source": "kakuyomu",
            "source_id": "888000444",
            "url": "https://kakuyomu.jp/works/888000444",
            "title": "日本語だけのタイトル", "author": "seed",
            "zh_titles": {},          # ← 章节还没翻，所以没有中文书名
            "episodes": [{"id": "1", "title": "第1話"}],
            "glossary": {}, "characters": {}, "summaries": {}, "style": {},
            "progress": {"translated_through": 0, "fetched_through": 0},
        }, f, ensure_ascii=False)
    with open(os.path.join(tmp_root, "data", "details", "888000444.json"), "w",
              encoding="utf-8") as _f:
        _json.dump({"zh_title": "只有详情缓存里有中文名",
                    "zh_synopsis": "种子的中文简介。"}, _f, ensure_ascii=False)
    # has_update 是为了让「更新了 +2 话 · 点我翻译」这个徽标按钮出现在页面上：
    # 它**不在 .ctrls 里**，以前没人给它绑 handler（用户报"点了没反应"）。
    with open(os.path.join(tmp_root, "data", "books", "__zh_title_seed__.json"),
              "w", encoding="utf-8") as _f:
        _json.dump({"tracking": "reading", "has_update": True, "new_episodes": 2},
                   _f, ensure_ascii=False)

    # 种一本「本地有目录、但**不在书架上**」的书：用来端到端测
    # 「＋ 加入书架」→ 书架里出现 + 且**不是收藏**。
    # 用 existed 分支（source_id 命中）就能在**不联网**的情况下走完 /api/add。
    _sl = os.path.join(tmp_root, "novels", "__shelfless_seed__")
    os.makedirs(os.path.join(_sl, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(_sl, "raw"), exist_ok=True)
    with open(os.path.join(_sl, "meta.json"), "w", encoding="utf-8") as f:
        _json.dump({
            "slug": "__shelfless_seed__", "source": "kakuyomu",
            "source_id": "888000555",
            "url": "https://kakuyomu.jp/works/888000555",
            "title": "棚に載っていない本", "author": "seed",
            "zh_titles": {"book": "还没上架的书"},
            "episodes": [{"id": "1", "title": "第1話"}],
            "glossary": {}, "characters": {}, "summaries": {}, "style": {},
            "progress": {"translated_through": 0, "fetched_through": 0},
        }, f, ensure_ascii=False)

    # 前端专用：落地章（第 1 章）没译文、但已开启自动翻译。
    # 阅读页一进来就应该**自己去翻第 1 章**（用户报过"译好了还得手动刷新"）。
    # 单独一本是为了不和 __reader_seed__ 互相干扰（前者会被真的翻起来）。
    _need = os.path.join(tmp_root, "novels", "__need_seed__")
    os.makedirs(os.path.join(_need, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(_need, "raw"), exist_ok=True)
    with open(os.path.join(_need, "meta.json"), "w", encoding="utf-8") as f:
        _json.dump({
            "slug": "__need_seed__", "source": "kakuyomu",
            "source_id": "888000777",
            "url": "https://kakuyomu.jp/works/888000777",
            "title": "第一話だけまだの本", "author": "seed",
            "zh_titles": {"book": "落地章待译测试", "3": "第三章 中文名"},
            "episodes": [{"id": str(i), "title": f"第{i+1}話　テスト"} for i in range(5)],
            "glossary": {}, "characters": {}, "summaries": {}, "style": {},
            "progress": {"translated_through": 0, "fetched_through": 0},
        }, f, ensure_ascii=False)
    for _i in range(1, 5):          # chapters/0001..0004 = 第 2~5 章
        with open(os.path.join(_need, "chapters", f"{_i:04d}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(f"第{_i+1}章的译文。\n")
    with open(os.path.join(tmp_root, "data", "books", "__need_seed__.json"), "w",
              encoding="utf-8") as _f:
        _json.dump({"tracking": "reading",
                    "translate": {"enabled": True, "ahead": 3}}, _f,
                   ensure_ascii=False)

    # 种一本「第 1 章没译、第 2~7 章译好了」的书。
    # 用户的真实 bug（「我还没开始看，怎么就第二话了，我第一话呢？」）
    # 就长这样：落地章缺译文时，阅读页原来会偷偷跳过去渲染第 2 章。
    # 有空洞的书也是"已译数字不能骗人"的试金石（原来是 0，实际有 6 章）。
    _rd = os.path.join(tmp_root, "novels", "__reader_seed__")
    os.makedirs(os.path.join(_rd, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(_rd, "raw"), exist_ok=True)
    with open(os.path.join(_rd, "meta.json"), "w", encoding="utf-8") as f:
        _json.dump({
            "slug": "__reader_seed__", "source": "kakuyomu",
            "source_id": "888000666",
            "url": "https://kakuyomu.jp/works/888000666",
            "title": "第一話が抜けている本", "author": "seed",
            "zh_titles": {"book": "章节划分测试",
                          "2": "第二章 命运之日"},
            "episodes": [{"id": str(i), "title": f"第{i+1}話　テスト"} for i in range(10)],
            "glossary": {}, "characters": {}, "summaries": {}, "style": {},
            "progress": {"translated_through": 0, "fetched_through": 0},
        }, f, ensure_ascii=False)
    for _i in range(1, 7):          # chapters/0001..0006 = 第 2~7 章
        with open(os.path.join(_rd, "chapters", f"{_i:04d}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(f"第{_i+1}章的译文第一段。\n\n第二段。\n")
        with open(os.path.join(_rd, "raw", f"{_i:04d}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(f"第{_i+1}話の原文。\n\n二段落目。\n")

    # 预翻用：读者**正读到第 7 章**、已译 2~7、翻译开着、第 8 章还没译。
    # 自动上限是"读到 + ahead"，所以只有进度真的在第 7 章，预翻第 8 章才合法
    # （这也是线上真实情形：读到第 7 章时进度已经记成 7）。
    _la = os.path.join(tmp_root, "novels", "__lookahead_seed__")
    os.makedirs(os.path.join(_la, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(_la, "raw"), exist_ok=True)
    with open(os.path.join(_la, "meta.json"), "w", encoding="utf-8") as f:
        _json.dump({
            "slug": "__lookahead_seed__", "source": "kakuyomu",
            # 必须和 __shelfless_seed__ 的 source_id 不同：两本 fixture 若共用
            # source_id，/api/add 会按源站 id 选错目录，端到端"加入书架"就假失败。
            "source_id": "888000556",
            "url": "https://kakuyomu.jp/works/888000556",
            "title": "読み進め中の本", "author": "seed",
            "zh_titles": {"book": "预翻测试"},
            "episodes": [{"id": str(i), "title": f"第{i+1}話　テスト"} for i in range(10)],
            "glossary": {}, "characters": {}, "summaries": {}, "style": {},
            "progress": {"translated_through": 0, "fetched_through": 0},
        }, f, ensure_ascii=False)
    for _i in range(1, 7):          # chapters/0001..0006 = 第 2~7 章
        with open(os.path.join(_la, "chapters", f"{_i:04d}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(f"第{_i+1}章的译文。\n")
    with open(os.path.join(tmp_root, "data", "books", "__lookahead_seed__.json"),
              "w", encoding="utf-8") as _f:
        _json.dump({"tracking": "reading",
                    "progress": {"chapter": 7, "scroll": 0.0,
                                 "at": "2026-01-01 00:00:00"},
                    "translate": {"enabled": True, "ahead": 3}}, _f,
                   ensure_ascii=False)

    # 术语过期提示用：第 1 章是按**旧术语表**翻的（边车指纹=空表），
    # 而 meta 里已经有新译名。阅读页必须渲染提示 + 一键重翻。
    _st = os.path.join(tmp_root, "novels", "__stale_seed__")
    os.makedirs(os.path.join(_st, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(_st, "raw"), exist_ok=True)
    _raw_b = "アリスは魔法を使った。\n".encode("utf-8")
    _zh_b = "爱丽丝用了魔法。\n".encode("utf-8")
    with open(os.path.join(_st, "meta.json"), "w", encoding="utf-8") as f:
        _json.dump({
            "slug": "__stale_seed__", "source": "kakuyomu",
            "source_id": "888000888",
            "url": "https://kakuyomu.jp/works/888000888",
            "title": "用語が古い本", "author": "seed",
            "zh_titles": {"book": "术语过期测试", "1": "第一章 测试"},
            "episodes": [{"id": "1", "title": "第1話　テスト"}],
            "glossary": {"アリス": "艾丽丝"},
            "characters": {}, "summaries": {}, "style": {},
            "progress": {"translated_through": 1, "fetched_through": 1},
        }, f, ensure_ascii=False)
    with open(os.path.join(_st, "raw", "0000.txt"), "wb") as f:
        f.write(_raw_b)
    with open(os.path.join(_st, "chapters", "0000.txt"), "wb") as f:
        f.write(_zh_b)
    _sidecar = {
        "schema_version": 1, "status": "complete",
        "source_sha256": hashlib.sha256(_raw_b).hexdigest(),
        "content_sha256": hashlib.sha256(_zh_b).hexdigest(),
        "translation_config_hash": "0" * 64,
        "model_provider": "stub", "model_role": "translate",
        "model_id": "stub", "prompt_version": "seed",
        "translated_at": "2026-01-01T00:00:00",
        "tokens": {"input": 0, "output": 0},
        "cost": {"amount": 0, "currency": "USD", "estimated": True},
        "incomplete_paragraphs": [],
        # 空术语表的指纹：模拟「翻的时候还没有 アリス 这个词」。
        "glossary_revision": hashlib.sha256(b"").hexdigest()[:32],
    }
    with open(os.path.join(_st, "chapters", "0000.meta.json"), "w",
              encoding="utf-8") as f:
        _json.dump(_sidecar, f, ensure_ascii=False)
    with open(os.path.join(tmp_root, "data", "books", "__stale_seed__.json"),
              "w", encoding="utf-8") as _f:
        _json.dump({"tracking": "reading", "progress": {"chapter": 1}}, _f,
                   ensure_ascii=False)

    # 种一份"推荐缓存 + 详情缓存"，让详情页的在线断言有数据可测
    # （详情缓存命中时不会联网，所以测试不依赖外网）
    import time as _time
    _wid = "999000111"
    # 至少要有**三本**有重叠标签的书，相似作品那块才有东西可测。
    # 主作品同时带套路标签（異世界転生）和有辨识度的标签（勘違い），
    # 「太套路了只扣套路标签」那条断言才成立。
    _sim_items = [
        {"id": _wid, "title": "テスト作品", "author": "テスト作者",
         "url": "https://kakuyomu.jp/works/" + _wid,
         "tags": ["百合", "勘違い", "TS", "異世界転生"], "genre": "ROMANCE",
         "title_zh": "测试作品（中文名）",
         "status": "连载中", "episodes": 12, "characters": 123456,
         "points": 4321, "updated": "2026-01-02",
         # origins：推荐卡/书库卡「来源」chip 的唯一数据源。种上它，
         # 隔离服务的页面才**真的**渲染出 chip（否则 UI 断言拿到空 = 假绿）。
         "origins": ["百合", "流派:奇幻"]},
        {"id": "999000112", "title": "似ている作品", "author": "別の作者",
         "url": "https://kakuyomu.jp/works/999000112",
         "tags": ["百合", "勘違い", "異世界転生"], "genre": "ROMANCE",
         "status": "完結", "episodes": 30, "characters": 234567,
         "points": 9876, "updated": "2026-01-03",
         # 长关键词：验证窄屏（手机/平板）下来源 chip 能断行、不撑破卡片。
         "origins": ["悪役令嬢と婚約破棄されたので、もう一度やり直すことにしました"]},
        {"id": "999000113", "title": "少し似ている作品", "author": "三番目の作者",
         "url": "https://kakuyomu.jp/works/999000113",
         "tags": ["百合"], "genre": "ROMANCE",
         "status": "連載中", "episodes": 8, "characters": 34567,
         "points": 1234, "updated": "2026-01-04"},
    ]
    with open(os.path.join(tmp_root, "data", "recs.json"), "w", encoding="utf-8") as f:
        _json.dump({"at": int(_time.time()), "items": _sim_items}, f,
                   ensure_ascii=False)
    _dd = os.path.join(tmp_root, "data", "details")
    os.makedirs(_dd, exist_ok=True)
    with open(os.path.join(_dd, _wid + ".json"), "w", encoding="utf-8") as f:
        _json.dump({"synopsis": "これは测试用的简介。",
                    "zh_title": "测试作品（中文名）",
                    "zh_synopsis": "这是测试用的中文简介。",
                    "at": "2026-01-02 00:00:00",
                    "episode_count": 2,
                    "toc": [{"title": "第一章　始まり", "episodes": [
                        {"id": "1", "title": "第1話　出会い", "at": "2026-01-01"},
                        {"id": "2", "title": "第2話　別れ", "at": "2026-01-02"}]}]},
                   f, ensure_ascii=False)

    # 这本书也要进**书库档案**：推荐缓存和书库档案是两份数据。
    # 「不感兴趣」是两个动作 —— 藏起来 + 喂画像 —— 而"藏"写在档案上。
    # 档案里没有它，set_hidden 会如实返回 False（"没真正屏蔽"），
    # 于是"隐藏后不再出现"这条断言永远测不到真东西。
    _libp2 = os.path.join(tmp_root, "data", "library.json")
    try:
        with open(_libp2, encoding="utf-8") as _f:
            _lib3 = _json.load(_f) or {}
    except Exception:  # noqa: BLE001
        _lib3 = {}
    for _i3, _it3 in enumerate(_sim_items):
        _lib3[str(_it3["id"])] = dict(_it3, first_seen="2026-01-02 00:00:0%d" % _i3)
    with open(_libp2, "w", encoding="utf-8") as _f:
        _json.dump(_lib3, _f, ensure_ascii=False)


    # === 桩 LLM：让「读到哪翻到哪」的闭环可以**不花一分钱**地端到端测 ===
    # 踩过：test_flow.py 原来打真实 8099、真的调 DeepSeek、还 sleep 5 分钟轮询。
    # 它既没有 sys.exit（永远"通过"），又每次自检都在烧用户的 token。
    # 现在把 LLM 端点指到本地桩：按 prompt 里的 #N 编号原样回中文。
    import http.server as _hs
    import re as _re
    import threading as _th

    class _StubLLM(_hs.BaseHTTPRequestHandler):
        def log_message(self, *a):        # 静默：别把自检输出刷满
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            user = ""
            for msg in body.get("messages") or []:
                if msg.get("role") == "user":
                    user = msg.get("content") or ""
            # prompt 的格式是 "#1:原文"（见 lntrans.build_chunk_prompt）
            nums = _re.findall(r"^#(\d+):", user, _re.M)
            if nums:
                out = "\n".join(f"#{i}:这是第 {i} 段的中文译文。" for i in nums)
            else:
                out = "中文译文"
            payload = json.dumps({
                "choices": [{"message": {"content": out}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    _stub_port = _free_port()
    _stub = _hs.ThreadingHTTPServer(("127.0.0.1", _stub_port), _StubLLM)
    _th.Thread(target=_stub.serve_forever, daemon=True).start()
    _llm_base = f"http://127.0.0.1:{_stub_port}/chat/completions"
    print(f"桩 LLM：{_llm_base}（自检不再调用真实模型，不花 token）")

    # 种一本"有待译原文"的书，给读到哪翻到哪的闭环用
    _fl = os.path.join(tmp_root, "novels", "__flow_seed__")
    os.makedirs(os.path.join(_fl, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(_fl, "raw"), exist_ok=True)
    with open(os.path.join(_fl, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({
            "slug": "__flow_seed__", "source": "kakuyomu",
            "source_id": "777000333",
            "url": "https://kakuyomu.jp/works/777000333",
            "title": "フロー確認用", "author": "seed",
            "episodes": [{"id": str(i), "title": f"第{i + 1}話"} for i in range(4)],
            "glossary": {}, "characters": {}, "summaries": {}, "style": {},
            "progress": {"translated_through": 0, "fetched_through": 0},
        }, f, ensure_ascii=False)
    for _i in range(4):
        with open(os.path.join(_fl, "raw", "%04d.txt" % _i), "w",
                  encoding="utf-8") as f:
            f.write("これは第%d話の原文です。\n二行目の原文。\n" % (_i + 1))
    with open(os.path.join(tmp_root, "data", "books", "__flow_seed__.json"),
              "w", encoding="utf-8") as f:
        json.dump({"tracking": "reading", "progress": {"chapter": 1},
                   # 翻译策略必须显式开启，否则策略层会正确地拒绝翻译（那是另一个测试的职责）
                   "translate": {"enabled": True, "ahead": 10}}, f,
                  ensure_ascii=False)
    print(f"闭环种子作品：__flow_seed__（4 话原文，已开翻译）\n")

    from_net = {}
    for _attempt in range(3):
        port = _free_port()
        _log = None
        try:
            _log = open(os.path.join(tmp_root, f"srv-{port}.log"), "w")
            srv = _sp.Popen([sys.executable, os.path.join(HERE, "lnserve.py"),
                             "--port", str(port)],
                            cwd=HERE, stdout=_log, stderr=_sp.STDOUT,
                            env=dict(
                                os.environ, LNTRANS_DATA_ROOT=tmp_root,
                                LNTRANS_LNFINDER=_lf_dir,
                                LNTRANS_LLM_BASE=_llm_base,
                                LNTRANS_TEST_SERVER="1",
                                # 桩 LLM 已把 base 指向本地，但服务仍要求一个
                                # 非空 key 才走翻译路径。没设真 key 就兜一个假值
                                # —— 否则接收方第一次跑 test_flow 必然失败（假红，
                                # 他会以为自己装错了）。只在缺省时兜底，不覆盖真 key。
                                DEEPSEEK_API_KEY=(
                                    os.environ.get("DEEPSEEK_API_KEY") or "stub")))
        except Exception:  # noqa: BLE001
            if _log:
                _log.close()
            continue
        # 父进程这份句柄必须**立刻**关掉：Windows 下它会把 srv-*.log 一直锁着，
        # 于是收尾的 rmtree(ignore_errors=True) 静默跳过该文件 → 每次自检都漏一个
        # lntrans-selftest-* 目录（Linux/Android 上删打开的文件没问题，只有 Windows 会漏）。
        # 子进程持有自己的副本，关掉父进程这份不影响它继续写日志。
        _log.close()
        ok = False
        for _ in range(40):
            _t.sleep(0.25)
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/library", timeout=2):
                    ok = True
                    break
            except Exception:  # noqa: BLE001
                if srv.poll() is not None:
                    break
        if ok:
            from_net = {"port": port, "proc": srv}
            print(f"隔离测试服务：127.0.0.1:{port}（数据根 {tmp_root}）\n")
            break
        try:
            srv.kill()
        except Exception:  # noqa: BLE001
            pass

    need_server = {"test_pages.py", "test_ui.py", "test_detail.py",
                   "test_flow.py", "test_recs.py", "test_click.py",
                   "test_reader.py", "test_epub.py", "test_sched.py"}
    server_up = bool(from_net)
    if not server_up:
        print("⚠ 没能起隔离测试服务，相关测试将跳过")
        for _fn in os.listdir(tmp_root):
            if _fn.startswith("srv-"):
                print(f"  --- {_fn} ---")
                try:
                    with open(os.path.join(tmp_root, _fn), encoding="utf-8") as _f:
                        for _ln in _f.read().strip().splitlines()[-6:]:
                            print("   " + _ln)
                except OSError:
                    pass
        print()

    failed = []
    skipped = []
    ran = 0
    # 这些文案 = 「因为环境变量/隔离服务缺失而跳过了核心断言」。
    # runner 一定会注入 LNTRANS_TEST_SERVER / LNTRANS_SERVER_ROOT，所以正常
    # 全套里它们不该出现；出现就是假绿（曾经 test_click 书库为空直接 exit 0，
    # 整套仍报绿，而那些按钮断言一条没跑）。数据形态导致的合理跳过
    # （如「所有作品都已翻译」）不在此列。
    SKIP_AS_FAIL = (
        "缺 LNTRANS_TEST_SERVER",
        "未在隔离服务下运行",
        "这是真实环境，没有 fixture 书",
        "没有隔离测试服务",
        "HTTP 层跳过（服务未运行）",
        # 隔离环境里种子书库一定有内容；这两句出现 = 种子/服务坏了，
        # 对应的按钮/分页断言一条没跑（另一种假绿）。
        "书架为空，跳过",
        "书库不足 2 页",
        # 隔离服务/种子/画像都在，以下文案出现即环境坏了，不是"数据形态"：
        "拿不到书库",
        "没有推荐缓存，跳过",
        "推荐缓存为空，跳过",
        "没有推荐卡，跳过",
        "没有书库面板，跳过",
        "服务里还没有任何作品，跳过",
        "没有在读的书，跳过",
        "没有作品可测，跳过",
        "读不到画像",
    )
    for t in TESTS:
        if ONLY and not any(x in t for x in ONLY):
            continue
        ran += 1
        p = os.path.join(HERE, t)
        if not os.path.exists(p):
            # 核心测试文件缺失也是"没跑"，不能算通过。
            print(f"  {t:<16} ❌ 不存在（核心测试文件缺失，不能跳过）")
            failed.append(t)
            continue
        if t in need_server and not server_up:
            print(f"  {t:<16} ❌ 跳过（隔离服务未启动，核心断言没跑）")
            failed.append(t)
            continue
        print(f"  {t:<16} 运行中…", flush=True)
        # 每个测试**各自一个数据根**，避免互相污染
        # （踩过：隔离服务与 test_state 共用同一根 → 服务在跑时写文件，
        #   导致 test_state 偶发失败，单独跑却通过 = 典型竞态）
        _own = tempfile.mkdtemp(prefix="lntrans-case-", dir=tmp_root)
        os.makedirs(os.path.join(_own, "novels"), exist_ok=True)
        os.makedirs(os.path.join(_own, "data"), exist_ok=True)
        env = dict(os.environ, LNTRANS_DATA_ROOT=_own,
                   LNTRANS_LNFINDER=_lf_dir,
                   # 隔离服务用的数据根。有些断言要**直接调生产函数**（而不是绕 HTTP），
                   # 就得让本进程能读到那份数据，否则断言永远跳过 = 假绿。
                   LNTRANS_SERVER_ROOT=tmp_root,
                   LNTRANS_TEST_SERVER="1",
                   # 子进程 stdio 钉成 utf-8：否则 Windows 下按 gbk 解码，
                   # 下面的 ❌ 输出扫描会因编码错乱而失效。
                   PYTHONIOENCODING="utf-8")
        cmd = [sys.executable, p]
        if t in need_server and from_net:
            cmd.append(f"http://127.0.0.1:{from_net['port']}")
        if t == "test_flow.py" and from_net:
            cmd.append("__flow_seed__")
        r = subprocess.run(cmd, cwd=HERE, env=env,
                           capture_output=True, encoding="utf-8",
                           errors="replace", timeout=900)
        ok = r.returncode == 0
        # 退出码之外再扫一眼输出：脚本若打印了失败标记 ❌ 却仍 exit 0，
        # 说明它没把失败反馈到退出码（曾害 4 个测试常年假绿）——一律判失败。
        _fake_green = ok and ("❌" in (r.stdout or ""))
        if _fake_green:
            ok = False
        _txt = (r.stdout or "") + "\n" + (r.stderr or "")
        _skip_hits = [s for s in SKIP_AS_FAIL if s in _txt]
        _skip_reason = ""
        if ok and _skip_hits:
            ok = False
            _skip_reason = "；环境缺失导致断言被跳过：" + "、".join(_skip_hits)
        print(f"  {t:<16} {'✅ 通过' if ok else '❌ 失败'}"
              + ("（退出码 0 但输出含 ❌：脚本没把失败反馈到退出码）"
                 if _fake_green else "")
              + _skip_reason)
        # -v / LNTRANS_VERBOSE=1：把每个测试的完整输出打出来。
        # 需要它是因为"通过"太笼统了 —— 得能确认**断言真的被走到**，
        # 而不是因为拿不到数据 skip 掉（那种"假绿"害过我好几次）。
        if VERBOSE:
            print("    ---- 完整输出 ----")
            for line in (r.stdout or "").strip().splitlines():
                print("    " + line)
            for line in (r.stderr or "").strip().splitlines():
                print("    ! " + line)
        if not ok:
            failed.append(t)
            print("    ---- 输出尾部 ----")
            for line in (r.stdout or "").strip().splitlines()[-12:]:
                print("    " + line)
            for line in (r.stderr or "").strip().splitlines()[-6:]:
                print("    " + line)
            # 隔离服务的 traceback 是查"页面打不开/接口 500"的唯一线索。
            # 之前它只在服务起不来时才打印，于是偶发 500 查不出原因。
            _slog = os.path.join(tmp_root, "data", "server.log")
            if os.path.exists(_slog):
                try:
                    _tail = open(_slog, encoding="utf-8").read().strip().splitlines()[-25:]
                except OSError:
                    _tail = []
                if _tail:
                    print("    ---- 隔离服务 server.log 尾部 ----")
                    for line in _tail:
                        print("    | " + line)
            for _fn in sorted(os.listdir(tmp_root)):
                if _fn.startswith("srv-"):
                    try:
                        _t = open(os.path.join(tmp_root, _fn), encoding="utf-8")
                        _tail2 = _t.read().strip().splitlines()[-20:]
                    except OSError:
                        _tail2 = []
                    if _tail2:
                        print(f"    ---- {_fn} 尾部 ----")
                        for line in _tail2:
                            print("    | " + line)

    after = snapshot()
    leaked = after - before                 # 新增的（相对基线）
    left = suspicious(after)                # 按命名识别的自检产物（更可靠）
    fp_after = fingerprints()
    # 必须比较并集：指纹列表会随 `*-中文.md` 的实际存在而变，
    # 只遍历 fp_before 会漏掉「自检新建了导出文件」这种污染。
    touched = {p for p in set(fp_before) | set(fp_after)
               if fp_before.get(p) != fp_after.get(p)}
    print()
    # 服务与临时根必须**无论成败都收掉**。
    # 踩过：清理写在"全部通过"之后，一旦有测试失败就直接 return 1 ——
    # 隔离服务没人杀，于是每次失败都漏一个后台 python 在跑。
    # （发现时机器上挂着 6 个遗留 lnserve，端口各占一个。）
    if from_net.get("proc"):
        try:
            from_net["proc"].terminate()
            from_net["proc"].wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                from_net["proc"].kill()
            except Exception:  # noqa: BLE001
                pass
        if from_net["proc"].poll() is None:
            print(f"⚠ 隔离服务（pid {from_net['proc'].pid}）没能停下")
    import shutil as _sh
    _sh.rmtree(tmp_root, ignore_errors=True)

    if touched:
        print("❌ 自检改动了真实文件（这些不在临时数据根里）：")
        for p in sorted(touched):
            # touched 是**前后并集**：新建的 `*-中文.md` 只存在于 fp_after，
            # 直接 fp_before[p] 会 KeyError —— 偏偏在"该报污染"时把自检自己弄崩。
            print(f"   {p}  {fp_before.get(p, '-')} → {fp_after.get(p, '-')}")
        print("   → 新模块必须读 LNTRANS_DATA_ROOT / LNTRANS_LNFINDER，别写死路径")
        return 1
    if left:
        print(f"❌ 运行后仍存在自检产物：{sorted(left)}")
        print("   （清理逻辑可能又静默失败了——检查 rmtree 的变量有没有被覆盖、"
              "或 ignore_errors=True 吞掉了错误）")
        return 1
    if leaked:
        print(f"❌ 自检留下了残留：{sorted(leaked)}")
        return 1
    if failed:
        print(f"❌ 失败的自检：{failed}")
        return 1
    tail = f"（跳过 {len(skipped)} 个）" if skipped else ""
    print(f"✅ 全部 {ran - len(skipped)} 个自检通过{tail}，"
          f"且**真实书架 / 真实画像未被触碰**（残留检查 {len(after)} 项，"
          f"指纹 {len(fp_after)} 项不变）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
