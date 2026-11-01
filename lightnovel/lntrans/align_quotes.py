#!/usr/bin/env python3
"""把已有译文的引号字形**对齐到原文**（一次性维护脚本）。

为什么是这个方向（用户原话）：
「不要强制用「」，我说过忠于原著。我不希望我自己的意志影响翻译。信达雅，先是信。」

所以这里没有"选一种好看的字形"：原文用「」就「」，原文用“”就“”，
原文没引号的地方我们也不加。只把字形对齐，**绝不增删、绝不挪位置**。

安全措施：
  * 默认**干跑**，只打印会改什么；`--write` 才落盘；
  * 落盘前备份到工作区 `backup-quotes-<时间>/`；
  * 引号数量或开/闭角色序列与原文不一致的段，**整段不动**（那是译者的句子处理），
    只统计报出来；
  * 不变量：去掉全部引号字符后，新旧文本必须逐字相同。

用法：
  python3 align_quotes.py                 # 干跑
  python3 align_quotes.py --write         # 真改（自动备份）
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
# 加载 lntrans.py 会改写 sys.argv（它自己的 main 也读 argv），先把真实参数存下来。
_REAL_ARGV = list(sys.argv)
_s = importlib.util.spec_from_file_location(
    "lt", os.path.join(os.path.dirname(os.path.abspath(__file__)), "lntrans.py"))
lt = importlib.util.module_from_spec(_s)
sys.argv = ["lntrans"]
_s.loader.exec_module(lt)

QUOTES = "「」『』“”‘’"


def strip_quotes(s: str) -> str:
    return "".join(c for c in s if c not in QUOTES)


def _qcount(s: str) -> int:
    return sum(1 for c in s if c in QUOTES)


def chapter_pairs(slug: str, idx: int):
    """(原文段列表, 译文行列表, 译文非空行的下标)。段数对不上就返回 None。"""
    d = lt.novel_dir(slug)
    raw_p = os.path.join(d, "raw", f"{idx:04d}.txt")
    zh_p = os.path.join(d, "chapters", f"{idx:04d}.txt")
    if not (os.path.exists(raw_p) and os.path.exists(zh_p)):
        return None
    src = lt.split_paragraphs(open(raw_p, encoding="utf-8").read().split("\n"))
    lines = open(zh_p, encoding="utf-8").read().split("\n")
    src_ne = [p for p in src if p.strip()]
    idxs = [i for i, l in enumerate(lines) if l.strip()]
    if len(src_ne) != len(idxs):      # 段数对不上：不猜，跳过
        return None
    return src_ne, lines, idxs


def align_lines(src_ne, lines, idxs):
    """就地改 lines 里的非空行；返回 (改了行数, 结构不一致的段数)。"""
    changed = mismatch = 0
    for p, i in zip(src_ne, idxs):
        old = lines[i]
        new = lt.align_quotes_with_source(old, p)
        if new != old:
            assert strip_quotes(new) == strip_quotes(old), "只许动引号字符"
            lines[i] = new
            changed += 1
        elif _qcount(old) != _qcount(p):
            mismatch += 1
    return changed, mismatch


def plan_book(slug: str):
    d = lt.novel_dir(slug)
    work, mism, skipped = [], 0, 0
    for f in sorted(glob.glob(os.path.join(d, "chapters", "*.txt"))):
        idx = int(os.path.basename(f)[:4])
        got = chapter_pairs(slug, idx)
        if got is None:
            skipped += 1
            continue
        src_ne, lines, idxs = got
        n, m = align_lines(src_ne, lines, idxs)
        mism += m
        if n:
            work.append(("chapter", f, "\n".join(lines), n))
    # 段缓存：键是原文段范围 "a-b"，用同一份原文重算，逐段对齐
    for f in sorted(glob.glob(os.path.join(d, "cache", "*.json"))):
        idx = int(os.path.basename(f)[:4])
        raw_p = os.path.join(d, "raw", f"{idx:04d}.txt")
        if not os.path.exists(raw_p):
            continue
        try:
            cache = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(cache, dict):
            continue
        paras = lt.split_paragraphs(open(raw_p, encoding="utf-8").read().split("\n"))
        changed = False
        for k, v in list(cache.items()):
            if k.startswith("_") or not isinstance(v, list) or "-" not in k:
                continue
            try:
                a, b = (int(x) for x in k.split("-", 1))
            except ValueError:
                continue
            chunk = paras[a:b]
            if len(chunk) != len(v):
                continue
            nv = [lt.align_quotes_with_source(z, s) if isinstance(z, str) else z
                  for z, s in zip(v, chunk)]
            if nv != v:
                cache[k] = nv
                changed = True
        if changed:
            work.append(("cache", f, cache, 0))
    return work, mism, skipped


def running_jobs() -> set:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="", help="只处理某本（slug）")
    ap.add_argument("--write", action="store_true", help="真的落盘（默认干跑）")
    ap.add_argument("--backup", default="", help="备份目录")
    args = ap.parse_args(_REAL_ARGV[1:])

    if args.book:
        slugs = [args.book]
    elif os.path.isdir(lt.NOVELS_DIR):
        slugs = sorted(os.listdir(lt.NOVELS_DIR))
    else:
        slugs = []
    busy = running_jobs()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_root = args.backup or os.path.join(
        os.path.dirname(lt.HERE), f"backup-quotes-{stamp}")
    total_ch = total_files = total_lines = total_mism = 0

    for slug in slugs:
        if not os.path.isdir(lt.novel_dir(slug)):
            continue
        if slug in busy:
            print(f"⏭  {slug}: 正在翻译，跳过（稍后再跑）")
            continue
        work, mism, skipped = plan_book(slug)
        total_mism += mism
        if not work and not mism:
            continue
        nch = sum(1 for w in work if w[0] == "chapter")
        nl = sum(w[3] for w in work if w[0] == "chapter")
        print(f"{'✍ ' if args.write else '· '}{slug}: {nch} 章 / {nl} 段要改字形"
              f"（{sum(1 for w in work if w[0] == 'cache')} 份缓存）"
              + (f"，{mism} 段与原文引号结构不一致（保持原样）" if mism else ""))
        total_ch += nch
        total_files += len(work)
        total_lines += nl
        if not args.write:
            continue
        for kind, path, data, _n in work:
            dst = os.path.join(backup_root, slug, os.path.relpath(path, lt.novel_dir(slug)))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(path, dst)
        meta = lt.load_meta(slug)
        for kind, path, data, _n in work:
            if kind == "chapter":
                lt.save_text(path, data)
                lt.refresh_chapter_meta(
                    slug, int(os.path.splitext(os.path.basename(path))[0]), meta,
                    update_glossary=False)
            else:
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, path)
        if nch:
            try:
                lt.rebuild_novel_md(slug, meta, force=True)
            except Exception as e:
                print(f"   ⚠ novel.md 重建失败（不影响章节）: {e}")

    print()
    if args.write:
        print(f"✅ 对齐完成：{total_ch} 章 / {total_files} 个文件 / {total_lines} 段")
        print(f"   备份：{backup_root}")
    else:
        print(f"（干跑）会改 {total_ch} 章 / {total_files} 个文件 / {total_lines} 段；加 --write 落盘")
    print(f"   与原文引号结构不一致（未动）：{total_mism} 段")
    return 0


if __name__ == "__main__":
    sys.exit(main())
