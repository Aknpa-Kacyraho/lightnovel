#!/usr/bin/env python3
"""校对 / 多作品隔离 / 翻译经验回归测试。

全部在临时数据根里跑，不调用真实模型，不碰真实书架。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time

ROOT = tempfile.mkdtemp(prefix="lntrans-review-")
os.environ["LNTRANS_DATA_ROOT"] = ROOT
os.environ["DEEPSEEK_API_KEY"] = "stub"
sys.path.insert(0, ".")

_s = importlib.util.spec_from_file_location("lntrans", "lntrans.py")
lt = importlib.util.module_from_spec(_s)
sys.argv = ["lntrans"]
sys.modules["lntrans"] = lt
_s.loader.exec_module(lt)

_sr = importlib.util.spec_from_file_location("lnreview", "lnreview.py")
rv = importlib.util.module_from_spec(_sr)
sys.argv = ["lnreview"]
sys.modules["lnreview"] = rv
_sr.loader.exec_module(rv)

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def write_book(slug: str, glossary: dict, characters: dict,
               raw: str, zh: str, *, lessons=None) -> dict:
    d = os.path.join(ROOT, "novels", slug)
    os.makedirs(os.path.join(d, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(d, "raw"), exist_ok=True)
    meta = {
        "slug": slug, "work_id": slug, "source": "kakuyomu",
        "source_id": "1", "url": "https://kakuyomu.jp/works/1",
        "title": f"作品 {slug}", "author": "作者",
        "episodes": [{"id": "1", "title": "第1話"}],
        "glossary": glossary, "characters": characters,
        "summaries": {}, "style": {}, "lessons": lessons or [],
        "progress": {"translated_through": 1, "fetched_through": 1},
    }
    lt.save_meta(slug, meta)
    lt.save_text(lt.chapter_path(slug, 0, "raw"), raw)
    lt.save_text(lt.chapter_path(slug, 0, "zh"), zh)
    return meta


try:
    print("=" * 66)
    print("A. 规则校对能抓到术语、漏译、日文残留和情绪反义")
    print("=" * 66)
    meta_a = write_book(
        "book-a", {"魔法": "魔力"},
        {"アリス": {"desc": "女主角", "voice": "冷淡",
                    "address": "叫主角「笨蛋」"}},
        "アリスは魔法を使った。\n彼女は冷静だった。",
        "爱丽丝使用了法术。\n她怒吼着摔了杯子。",
        lessons=[{"text": "A 书经验：アリス说话短", "chapter": 0,
                  "source": "test"}])
    meta_a = lt.load_meta("book-a")
    meta_a["glossary_history"] = [
        {"jp": "魔法", "old": "法术", "new": "魔力", "source": "test"}]
    lt.save_meta("book-a", meta_a)

    raw = lt.chapter_path("book-a", 0, "raw")
    zh = lt.chapter_path("book-a", 0, "zh")
    issues = rv.rule_check(open(raw, encoding="utf-8").read(),
                           open(zh, encoding="utf-8").read(), meta_a)
    types = {x["type"] for x in issues}
    check("抓到旧译名", "term_old" in types, str(sorted(types)))
    check("抓到术语缺失", "term_missing" in types)
    check("抓到情绪反义候选", "emotion" in types)
    check("问题带原文依据", all(x.get("evidence") for x in issues))

    print("=" * 66)
    print("B. prompt 只含本书上下文（防止多书串译）")
    print("=" * 66)
    meta_b = write_book("book-b", {"剣": "剑"},
                        {"ボブ": {"desc": "剑士", "voice": "豪爽"}},
                        "ボブは剣を抜いた。", "鲍勃拔出了剑。",
                        lessons=[{"text": "B 书经验：剑士说话大声",
                                  "chapter": 0, "source": "test"}])
    sysp = lt.build_system_prompt(meta_a)
    cp, _used = lt.build_chunk_prompt(meta_a, ["アリスは魔法を使った。"], 0, "")
    check("系统 prompt 标明 work_id", "work_id=book-a" in sysp)
    check("系统 prompt 注入本书经验", "A 书经验" in sysp)
    check("系统 prompt 不含 B 书经验", "B 书经验" not in sysp)
    check("chunk prompt 不含 B 书术语", "剣 => 剑" not in cp)
    check("chunk prompt 不含 B 书人物", "ボブ" not in cp)
    check("chunk prompt 含 A 书术语", "魔法 => 魔力" in cp)
    check("chunk prompt 标明作品", "work_id=book-a" in cp)
    try:
        rv.assert_work(meta_a, "book-b")
        mismatch_ok = False
    except ValueError:
        mismatch_ok = True
    check("拿 A 书记忆去校对 B 书会被拒绝", mismatch_ok)
    check("两本书缓存目录不同",
          os.path.join(lt.novel_dir("book-a"), "cache")
          != os.path.join(lt.novel_dir("book-b"), "cache"))

    print("=" * 66)
    print("C. 校对报告/经验按书落盘，不污染另一本")
    print("=" * 66)
    rep = rv.review_chapter("book-a", 0, use_llm=False, learn=True, quiet=True)
    check("报告写到 A 书 qa/", os.path.exists(
        rv.report_paths("book-a", 1)[0]))
    check("报告记了 work_id", rep.get("work_id") == "book-a")
    a_after = lt.load_meta("book-a")
    b_after = lt.load_meta("book-b")
    check("A 书新增了经验", len(a_after.get("lessons") or []) >
          len(meta_a.get("lessons") or []))
    check("B 书没有收到 A 的经验",
          all("魔法" not in str(x) for x in (b_after.get("lessons") or [])))
    check("B 书没有被创建 qa 报告", not os.path.exists(
        rv.report_paths("book-b", 1)[0]))

    print("=" * 66)
    print("D. AI 校对只读本书，问题经过 schema 归一化")
    print("=" * 66)
    seen_prompts = []

    def fake_llm(system, user, model, temperature, retries=3, role=None):
        seen_prompts.append(user)
        return json.dumps([{
            "para": 1, "type": "voice", "severity": "blocker",
            "quote_jp": "冷静", "quote_zh": "怒吼",
            "evidence": "原文写冷静，译文写怒吼",
            "suggestion": "保持克制语气",
        }], ensure_ascii=False), {"total_tokens": 21}

    old_llm = lt.call_llm
    lt.call_llm = fake_llm
    try:
        rep2 = rv.review_chapter("book-a", 0, use_llm=True, learn=False,
                                 quiet=True)
    finally:
        lt.call_llm = old_llm
    check("AI 校对合并了来源问题",
          any(x.get("source") == "llm" and x.get("type") == "voice"
              for x in rep2.get("issues") or []))
    check("AI prompt 带 work_id", bool(seen_prompts) and
          "work_id=book-a" in seen_prompts[0])
    check("AI prompt 不含 B 书术语", all("剣 => 剑" not in p for p in seen_prompts))
    check("AI token 统计进入报告", rep2.get("tokens") == 21)

    print("=" * 66)
    print("D2. 校对 LLM 不持书锁；旧 meta 快照不覆盖新进度")
    print("=" * 66)
    snap = lt.load_meta("book-a")
    snap["lessons"] = []
    snap["progress"] = {
        "translated_through": 1, "fetched_through": 1, "incomplete": [1],
    }
    snap["zh_titles"] = {"book": "旧书名", "1": "第一章"}
    lt.save_meta("book-a", snap)

    started = threading.Event()
    release = threading.Event()

    def slow_review_llm(system, user, model, temperature, retries=3,
                        role=None):
        started.set()
        release.wait(timeout=5)
        return json.dumps([{
            "para": 1, "type": "voice", "severity": "suggestion",
            "quote_jp": "冷静", "quote_zh": "怒吼",
            "evidence": "角色在原文中保持冷静", "suggestion": "缩短反应句",
        }], ensure_ascii=False), {"total_tokens": 9}

    old_llm = lt.call_llm
    lt.call_llm = slow_review_llm
    review_done = {}

    def run_review():
        review_done["report"] = rv.review_chapter(
            "book-a", 0, snap, use_llm=True, learn=True, quiet=True)

    th = threading.Thread(target=run_review)
    try:
        th.start()
        check("校对确实进入 LLM 阶段", started.wait(timeout=3))
        t0 = time.monotonic()
        with lt.novel_lock("book-a"):
            pass
        lock_wait = time.monotonic() - t0
        check("LLM 校对期间其他 I/O 不必等模型返回",
              lock_wait < 0.5, f"{lock_wait:.3f}s")

        fresh = lt.load_meta("book-a")
        fresh["progress"] = {
            "translated_through": 9, "fetched_through": 9, "incomplete": [],
        }
        fresh["zh_titles"] = {"book": "新书名", "1": "新的第一章"}
        lt.save_meta("book-a", fresh)
    finally:
        release.set()
        th.join(timeout=10)
        lt.call_llm = old_llm

    merged = lt.load_meta("book-a")
    check("校对完成后保留翻译写下的新进度",
          merged.get("progress", {}).get("translated_through") == 9
          and merged.get("progress", {}).get("incomplete") == [],
          str(merged.get("progress")))
    check("校对只合并经验，不回退书名/章名",
          (merged.get("zh_titles") or {}).get("book") == "新书名"
          and (merged.get("zh_titles") or {}).get("1") == "新的第一章")
    check("经验仍成功写回", bool((review_done.get("report") or {})
                                 .get("lessons_added")))

    print("=" * 66)
    print("D3. 模型修订期间译文被别的任务改写 → 放弃覆盖")
    print("=" * 66)
    lt.save_text(zh, "爱丽丝使用了法术。\n\n她怒吼着摔了杯子。")
    before_fix = open(zh, encoding="utf-8").read()
    before_fix_sha = hashlib.sha256(before_fix.encode("utf-8")).hexdigest()
    fix_started = threading.Event()
    fix_release = threading.Event()

    def slow_fix_llm(system, user, model, temperature, retries=3,
                     role=None):
        fix_started.set()
        fix_release.wait(timeout=5)
        return json.dumps([{
            "para": 1, "before": "爱丽丝使用了魔力。",
            "after": "她冷静地放下杯子。", "evidence": "角色保持冷静",
        }], ensure_ascii=False), {"total_tokens": 8}

    stale_result = {}
    stale_report = {"issues": [
        {"para": 1, "type": "term_old", "severity": "blocker",
         "old": "法术", "term_zh": "魔力", "term": "魔法",
         "evidence": "术语已锁定"},
        {"para": 1, "type": "voice", "severity": "blocker",
         "evidence": "角色语气不符", "suggestion": "改得克制"},
    ]}
    old_llm = lt.call_llm
    lt.call_llm = slow_fix_llm
    th = threading.Thread(target=lambda: stale_result.update(
        fix=rv.apply_fixes(
            "book-a", 0, lt.load_meta("book-a"), stale_report,
            use_llm=True, model="review", expected_sha256=before_fix_sha)))
    try:
        th.start()
        check("AI 修订确实进入模型阶段", fix_started.wait(timeout=3))
        lt.save_text(zh, "另一任务写下的更新译文。\n\n不应被旧校对覆盖。")
    finally:
        fix_release.set()
        th.join(timeout=10)
        lt.call_llm = old_llm
    now_text = open(zh, encoding="utf-8").read()
    check("内容哈希变化时修订返回 stale",
          bool((stale_result.get("fix") or {}).get("stale")))
    check("旧校对没有覆盖较新的译文",
          now_text == "另一任务写下的更新译文。\n\n不应被旧校对覆盖。")

    print("=" * 66)
    print("D4. 整章校对期间内容变化 → 不写观察池/经验")
    print("=" * 66)
    snap = lt.load_meta("book-a")
    snap["lessons"] = []
    lt.save_meta("book-a", snap)
    review_started = threading.Event()
    review_release = threading.Event()

    def slow_stale_review(system, user, model, temperature, retries=3,
                          role=None):
        review_started.set()
        review_release.wait(timeout=5)
        return json.dumps([{
            "para": 1, "type": "voice", "severity": "suggestion",
            "quote_jp": "冷静", "quote_zh": "更新译文",
            "evidence": "旧快照里的问题", "suggestion": "改短",
        }], ensure_ascii=False), {"total_tokens": 6}

    old_llm = lt.call_llm
    lt.call_llm = slow_stale_review
    stale_review = {}
    th = threading.Thread(target=lambda: stale_review.update(
        report=rv.review_chapter(
            "book-a", 0, use_llm=True, learn=True, quiet=True)))
    try:
        th.start()
        check("整章校对确实进入模型阶段", review_started.wait(timeout=3))
        lt.save_text(zh, "校对开始后写入的全新译文。")
    finally:
        review_release.set()
        th.join(timeout=10)
        lt.call_llm = old_llm
    stale_rep = stale_review.get("report") or {}
    check("整章校对标记快照已过期", stale_rep.get("stale_snapshot") is True)
    check("过期快照不写经验",
          not stale_rep.get("lessons_added")
          and not (lt.load_meta("book-a").get("lessons") or []))
    check("过期快照不改写当前译文",
          open(zh, encoding="utf-8").read() == "校对开始后写入的全新译文。")

    print("=" * 66)
    print("E. --fix 只替换可验证旧译名，先备份，再重建汇总")
    print("=" * 66)
    # 重新放回旧译名，直接跑 fix。
    lt.save_text(zh, "爱丽丝使用了法术。\n她怒吼着摔了杯子。")
    fix_meta = lt.load_meta("book-a")
    fix_report = {"issues": [{
        "para": 1, "type": "term_old", "severity": "blocker",
        "old": "法术", "term_zh": "魔力", "term": "魔法",
        "evidence": "测试", "suggestion": "替换",
    }]}
    fx = rv.apply_fixes("book-a", 0, fix_meta, fix_report)
    text_now = open(zh, encoding="utf-8").read()
    check("旧译名被替换", "魔力" in text_now and "法术" not in text_now)
    check("写了备份文件", bool(fx.get("backup")) and os.path.exists(fx["backup"]))
    check("修订记录写到本书 qa/",
          os.path.exists(os.path.join(rv.qa_dir("book-a"), "fix-0001.json")))
    check("novel.md 同步重建",
          "魔力" in open(os.path.join(lt.novel_dir("book-a"), "novel.md"),
                        encoding="utf-8").read())

    print("=" * 66)
    print("F. 原文变了，旧段缓存不能继续复用")
    print("=" * 66)
    meta_c = write_book("book-c", {}, {}, "これは古い原文。", "这是旧译文。")
    cache_dir = os.path.join(lt.novel_dir("book-c"), "cache")
    os.makedirs(cache_dir, exist_ok=True)
    lt.save_json(os.path.join(cache_dir, "0000.json"), {
        "0-1": ["这是旧缓存译文。"],
        "_raw_sha256": hashlib.sha256("これは古い原文。".encode()).hexdigest(),
    })
    lt.save_text(lt.chapter_path("book-c", 0, "raw"), "これは新しい原文。")

    def fake_translate(system, user, model, temperature, retries=3, role=None):
        return "#1:这是新译文。", {"total_tokens": 5}

    old_llm = lt.call_llm
    lt.call_llm = fake_translate
    try:
        ok = lt.translate_chapter(
            "book-c", 0, meta_c,
            argparse.Namespace(force=False, dry_run=False,
                               allow_missing=False, model="stub",
                               temperature=0.0))
    finally:
        lt.call_llm = old_llm
    check("翻译成功", bool(ok))
    got = open(lt.chapter_path("book-c", 0), encoding="utf-8").read()
    check("没有复用旧缓存", "这是新译文" in got and "旧缓存" not in got, got)

    print("=" * 66)
    print("G. CLI review 默认校对最近一章（Namespace 字段完整）")
    print("=" * 66)
    cli_ok = True
    try:
        lt.cmd_review(argparse.Namespace(
            slug="book-a", all=False, chapter=None, from_chapter=None,
            count=1, llm=False, fix=False, fix_ai=False, no_learn=False,
            fail_on_blocker=False, model="stub", temperature=0.2))
    except Exception as e:  # noqa: BLE001
        cli_ok = False
        print(f"    异常：{type(e).__name__}: {e}")
    check("review CLI 能跑通默认路径", cli_ok)

    print("=" * 66)
    print("H. 两本书并发翻译，prompt/缓存不串")
    print("=" * 66)
    write_book("book-d", {"炎": "火焰"}, {}, "炎を使った。", "火焰。")
    write_book("book-e", {"氷": "冰"}, {}, "氷を使った。", "冰。")
    seen = []
    seen_lock = threading.Lock()

    def concurrent_llm(system, user, model, temperature, retries=3, role=None):
        with seen_lock:
            seen.append((system, user))
        import time as _time
        _time.sleep(0.15)
        return "#1:这是并发译文。", {"total_tokens": 3}

    old_llm = lt.call_llm
    lt.call_llm = concurrent_llm
    results = {}

    def run_one(slug):
        results[slug] = lt.translate_chapter(
            slug, 0, lt.load_meta(slug),
            argparse.Namespace(force=False, dry_run=False,
                               allow_missing=False, model="stub",
                               temperature=0.0))

    try:
        ts = [threading.Thread(target=run_one, args=(s,))
              for s in ("book-d", "book-e")]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=10)
    finally:
        lt.call_llm = old_llm
    check("两本书都翻译成功",
          all(results.get(s) for s in ("book-d", "book-e")), str(results))
    d_prompts = [u for s, u in seen if "work_id=book-d" in s]
    e_prompts = [u for s, u in seen if "work_id=book-e" in s]
    check("两本书各自发出请求", bool(d_prompts) and bool(e_prompts),
          f"D={len(d_prompts)} E={len(e_prompts)}")
    check("D 的 prompt 不含 E 的术语",
          all("氷 => 冰" not in p for p in d_prompts))
    check("E 的 prompt 不含 D 的术语",
          all("炎 => 火焰" not in p for p in e_prompts))
    check("D/E 缓存文件互不相同",
          os.path.exists(os.path.join(lt.novel_dir("book-d"), "cache", "0000.json"))
          and os.path.exists(os.path.join(lt.novel_dir("book-e"), "cache", "0000.json")))

finally:
    shutil.rmtree(ROOT, ignore_errors=True)

print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("✅ 校对 / 隔离 / 经验测试全部通过")
