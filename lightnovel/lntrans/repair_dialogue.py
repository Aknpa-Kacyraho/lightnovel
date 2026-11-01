#!/usr/bin/env python3
"""修复历史上"多行对白只译了第一行"的漏译段（会调用真实 LLM，花钱）。

为什么需要：实测某部作品有 152 段的引号对数比原文少（49 段少 2 处以上），
原文一个段落里连着三行对白，译文只剩第一行 —— 段数、编号、中文校验全都过，
界面上看着完全正常。这是"信"的底线问题，只能对着原文比才发现。

现在管线里已经有拦截（`_missing_dialogue` + 重试提示），这个脚本负责**存量**：
只重译那些"少了对白"的段落，同一章的坏段合并成一次请求（省 token），
译完就地替换对应的那一行，并同步补进段缓存，避免下次重译又用回坏译文。

安全：默认**干跑**只估算；`--write` 才真正调用模型，改前备份到工作区。
替换条件：新译文必须通过中文检测、且对白数不少于原文，否则这一行不动。

用法：
  python3 repair_dialogue.py               # 干跑：列出要修哪些段、估算 token
  python3 repair_dialogue.py --write       # 真修
  python3 repair_dialogue.py --write --book <slug>
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import shutil
import sys
import time

sys.path.insert(0, ".")
_REAL_ARGV = list(sys.argv)
_s = importlib.util.spec_from_file_location(
    "lt", os.path.join(os.path.dirname(os.path.abspath(__file__)), "lntrans.py"))
lt = importlib.util.module_from_spec(_s)
sys.argv = ["lntrans"]
_s.loader.exec_module(lt)

Q_OPEN = "「“‘"


def running_jobs() -> set:
    """看 8099 上有没有正在翻的书；维护脚本不能和 worker 同时写章节。"""
    import urllib.request
    busy = set()
    if not os.path.isdir(lt.NOVELS_DIR):
        return busy
    try:
        urllib.request.urlopen("http://127.0.0.1:8099/api/net", timeout=1).read()
    except Exception:
        return busy
    for slug in os.listdir(lt.NOVELS_DIR):
        try:
            u = f"http://127.0.0.1:8099/api/job?slug={slug}"
            d = json.loads(urllib.request.urlopen(u, timeout=1).read().decode("utf-8"))
            if (d or {}).get("status") in ("running", "queued"):
                busy.add(slug)
        except Exception:
            pass
    return busy


def load_chapter(slug: str, idx: int):
    """返回 (原文段, 译文行, 非空行下标, 原文段在 paras 里的下标)。段数不符返回 None。"""
    d = lt.novel_dir(slug)
    raw_p = os.path.join(d, "raw", f"{idx:04d}.txt")
    zh_p = os.path.join(d, "chapters", f"{idx:04d}.txt")
    if not (os.path.exists(raw_p) and os.path.exists(zh_p)):
        return None
    paras = lt.split_paragraphs(open(raw_p, encoding="utf-8").read().split("\n"))
    lines = open(zh_p, encoding="utf-8").read().split("\n")
    src_ne = [(i, p) for i, p in enumerate(paras) if p.strip()]
    idxs = [i for i, l in enumerate(lines) if l.strip()]
    if len(src_ne) != len(idxs):
        return None
    return paras, src_ne, lines, idxs


def find_damage(slug: str):
    """[(chapter_idx, [(line_i, para_i, src_para, zh_line)])]"""
    out = []
    for f in sorted(glob.glob(os.path.join(lt.novel_dir(slug), "chapters", "*.txt"))):
        idx = int(os.path.basename(f)[:4])
        got = load_chapter(slug, idx)
        if not got:
            continue
        paras, src_ne, lines, idxs = got
        bad = []
        for (pi, src), li in zip(src_ne, idxs):
            sc = lt._dialogue_count(src)
            if sc >= 2 and lt._dialogue_count(lines[li]) < sc:
                bad.append((li, pi, src, lines[li]))
        if bad:
            out.append((idx, bad))
    return out


def split_into_lines(src_para: str, zh: str) -> str:
    """原文是多行对白、译文挤成一行时，按对白边界把译文拆回多行。"""
    n_src = src_para.count("\n") + 1
    if n_src < 2 or zh.count("\n"):
        return zh
    opens = [i for i, c in enumerate(zh) if c in Q_OPEN]
    if len(opens) != lt._dialogue_count(src_para):
        return zh
    cuts = opens[1:]
    if not cuts:
        return zh
    parts, prev = [], 0
    for c in cuts:
        parts.append(zh[prev:c].strip())
        prev = c
    parts.append(zh[prev:].strip())
    return "\n".join(p for p in parts if p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--backup", default="")
    ap.add_argument("--model", default=lt.TRANSLATE_MODEL)
    ap.add_argument("--chapter", default="", help="只修某章（章号，从 1 起）")
    args = ap.parse_args(_REAL_ARGV[1:])

    if args.book:
        slugs = [args.book]
    elif os.path.isdir(lt.NOVELS_DIR):
        slugs = sorted(os.listdir(lt.NOVELS_DIR))
    else:
        slugs = []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_root = args.backup or os.path.join(
        os.path.dirname(lt.HERE), f"backup-dialogue-{stamp}")
    busy = running_jobs() if args.write else set()

    jobs = []
    for slug in slugs:
        if not os.path.isdir(lt.novel_dir(slug)):
            continue
        if slug in busy:
            print(f"⏭  {slug}: 正在翻译，跳过（稍后再跑）")
            continue
        dmg = find_damage(slug)
        if dmg:
            n = sum(len(b) for _, b in dmg)
            jobs.append((slug, dmg))
            print(f"{'✍ ' if args.write else '· '}{slug}: {len(dmg)} 章 / {n} 段漏译（章内合并成 {len(dmg)} 次请求）")

    if not jobs:
        print("没有需要修的段落 —— 全部与原文对白数一致 ✅")
        return 0

    # 估算：每请求 = system prompt(~2.5k tok) + 原文段；输出 ~ 中文段
    est = 0
    for slug, dmg in jobs:
        for idx, bad in dmg:
            est += 2500 + sum(len(b[2]) for b in bad) // 2 + sum(len(b[2]) for b in bad) // 2
    print(f"\n估算约 {est/1000:.0f}k token（每章一次请求，含 system prompt 复用）")
    if not args.write:
        print("（干跑）加 --write 才会真的调用模型")
        return 0

    args_llm = argparse.Namespace(model=args.model, temperature=0.3, allow_missing=False)
    fixed_total = fail_total = 0
    for slug, dmg in jobs:
        meta = lt.load_meta(slug)
        system = lt.build_system_prompt(meta)
        for idx, bad in dmg:
            if args.chapter and str(idx + 1) != str(args.chapter):
                continue
            got = load_chapter(slug, idx)
            if not got:
                continue
            paras, src_ne, lines, idxs = got
            srcs = [b[2] for b in bad]
            stats = {"tok": 0, "calls": 0}
            out, _used = lt.robust_translate_paras(
                meta, srcs, 0, system, args_llm, "", stats)
            fixed = 0
            for (li, pi, src, old), new in zip(bad, out):
                if not new or not lt.detect_chinese(new):
                    fail_total += 1
                    continue
                if lt._dialogue_count(new) < lt._dialogue_count(src):
                    fail_total += 1
                    continue
                lines[li] = split_into_lines(src, new)
                fixed += 1
            if not fixed:
                print(f"   {slug} 第{idx+1}话：0 段修好（{stats['tok']} tok）")
                continue
            # 备份 + 写
            zh_p = os.path.join(lt.novel_dir(slug), "chapters", f"{idx:04d}.txt")
            dst = os.path.join(backup_root, slug, "chapters", f"{idx:04d}.txt")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(zh_p, dst)
            lt.save_text(zh_p, "\n".join(lines))
            # 只重译了坏段，整章不能算「已按当前术语表对齐」。
            lt.refresh_chapter_meta(slug, idx, meta, update_glossary=False)
            # 同步段缓存（否则下次重译又用回坏译文）
            cache_p = os.path.join(lt.novel_dir(slug), "cache", f"{idx:04d}.json")
            if os.path.exists(cache_p):
                try:
                    cache = json.load(open(cache_p, encoding="utf-8"))
                    touched = False
                    for (li, pi, src, old), new in zip(bad, out):
                        for k, v in cache.items():
                            if k.startswith("_") or not isinstance(v, list) or "-" not in k:
                                continue
                            try:
                                a, b = (int(x) for x in k.split("-", 1))
                            except ValueError:
                                continue
                            if a <= pi < b and (pi - a) < len(v):
                                v[pi - a] = lines[li]
                                touched = True
                                break
                    if touched:
                        tmp = cache_p + ".tmp"
                        with open(tmp, "w", encoding="utf-8") as f:
                            json.dump(cache, f, ensure_ascii=False, indent=1)
                        os.replace(tmp, cache_p)
                except Exception as e:
                    print(f"   ⚠ 缓存补写失败（不影响章节）: {e}")
            fixed_total += fixed
            print(f"   {slug} 第{idx+1}话：修好 {fixed}/{len(bad)} 段（{stats['tok']} tok）")
        try:
            lt.rebuild_novel_md(slug, meta, force=True)
        except Exception:
            pass

    print(f"\n✅ 共修 {fixed_total} 段，失败/未达标 {fail_total} 段")
    print(f"   备份：{backup_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
