#!/usr/bin/env python3
"""术语表「过期」/ 标题规则 / 候选术语 的纯逻辑回归。

学自 auto-novel 的三件事：
  1. 术语表变了，只把**该章实际用到的术语**算进指纹（不是全书重翻）；
  2. 纯编号标题直接规则映射，重复标题只翻一次；
  3. 按片假名频次找候选术语（0 token）。
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_ROOT = os.environ.get("LNTRANS_DATA_ROOT") or tempfile.mkdtemp(
    prefix="lntrans-stale-test-")
os.makedirs(os.path.join(_ROOT, "novels"), exist_ok=True)
os.environ["LNTRANS_DATA_ROOT"] = _ROOT

_s = importlib.util.spec_from_file_location("lt", os.path.join(HERE, "lntrans.py"))
lt = importlib.util.module_from_spec(_s)
sys.argv = ["x"]
_s.loader.exec_module(lt)

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


SLUG = "__stale__"
D = os.path.join(lt.NOVELS_DIR, SLUG)
shutil.rmtree(D, ignore_errors=True)
os.makedirs(os.path.join(D, "chapters"))
os.makedirs(os.path.join(D, "raw"))

RAW = [
    "アリスは魔法を使った。アリスは笑った。",
    "ミナはグランドールへ向かった。グランドールは遠い。",
]
ZH = ["爱丽丝用了魔法。爱丽丝笑了。", "米娜前往格兰多尔。格兰多尔很远。"]
meta = {
    "slug": SLUG, "source": "local", "source_id": "local-test",
    "url": "", "title": "测试", "author": "作者",
    "episodes": [{"id": f"{i + 1:04d}", "title": t}
                 for i, t in enumerate(
                     ["第1話", "第2話", "閑話", "同じ題", "同じ題", "別の題"])],
    "glossary": {"アリス": "爱丽丝"},
    "characters": {}, "summaries": {}, "style": {},
    "progress": {"translated_through": 2, "fetched_through": 2},
}
lt.save_meta(SLUG, meta)
for i, raw in enumerate(RAW):
    lt.save_text(os.path.join(D, "raw", f"{i:04d}.txt"), raw)
    lt.save_text(os.path.join(D, "chapters", f"{i:04d}.txt"), ZH[i])

args = argparse.Namespace(model="stub", temperature=0.0)
for i, raw in enumerate(RAW):
    rec = lt.chapter_meta_record(
        SLUG, i, meta, args, text=ZH[i],
        raw_sha=lt._sha256_file(os.path.join(D, "raw", f"{i:04d}.txt")),
        tokens_in=0, tokens_out=0, incomplete_paragraphs=[])
    if i == 0:
        # 模拟"上一版术语表里还没有 アリス"：指纹是空表。
        rec["glossary_revision"] = lt.glossary_fingerprint({}, raw)
    lt.save_json(lt.chapter_meta_path(SLUG, i), rec)

print("=" * 66)
print("A. 只让「真的用到了这个词」的章节过期")
print("=" * 66)
check("第 1 章用了旧术语表 → 过时",
      lt.chapter_glossary_stale(SLUG, 0, meta) is True)
check("第 2 章没这个词 → 不过时",
      lt.chapter_glossary_stale(SLUG, 1, meta) is False)
meta2 = dict(meta)
meta2["glossary"] = {"アリス": "艾丽丝"}
lt.save_meta(SLUG, meta2)
check("改了译名：含该词的章过时",
      lt.chapter_glossary_stale(SLUG, 0) is True)
check("改了译名：不含该词的章仍不过时",
      lt.chapter_glossary_stale(SLUG, 1) is False)
check("没有边车（没译过）不乱报",
      lt.chapter_glossary_stale(SLUG, 99) is False)
# 旧版边车没有 glossary_revision：即使术语表新增了该章用到的词，也不能报过期
_rec1 = lt.load_chapter_meta(SLUG, 1)
_rec1.pop("glossary_revision", None)
lt.save_json(lt.chapter_meta_path(SLUG, 1), _rec1)
_meta3 = dict(meta)
_meta3["glossary"] = {"アリス": "爱丽丝", "グランドール": "格兰多尔"}
lt.save_meta(SLUG, _meta3)
check("旧边车（无指纹）不乱报",
      lt.chapter_glossary_stale(SLUG, 1) is False)
lt.save_meta(SLUG, meta)

out = io.StringIO()
with contextlib.redirect_stdout(out):
    lt.cmd_stale(argparse.Namespace(
        slug=SLUG, term=None, retranslate=False, limit=3, model="stub"))
check("stale 默认只报告、不花钱", "1 章" in out.getvalue()
      and "没有花 token" in out.getvalue(), out.getvalue().strip())

print()
print("=" * 66)
print("B. 标题：规则映射 + 去重只翻一次")
print("=" * 66)
check("第１２話 → 第12话", lt.rule_translate_title("第１２話") == "第12话",
      str(lt.rule_translate_title("第１２話")))
check("閑話 → 闲话", lt.rule_translate_title("閑話") == "闲话")
check("带正文的标题不硬拆", lt.rule_translate_title("第1話　追放される") is None)

calls = []


def stub(system, prompt, model, temperature, retries=3, role=None):
    ids = re.findall(r"^#(\d+):", prompt, re.M)
    calls.append(ids)
    return "#1:相同的标题\n#2:另一个标题", {"total_tokens": 5}


_orig_call = lt.call_llm
lt.call_llm = stub
try:
    lt.cmd_titles(argparse.Namespace(slug=SLUG, model="stub", no_book=True))
finally:
    lt.call_llm = _orig_call
saved = lt.load_meta(SLUG)["zh_titles"]
check("纯编号标题 0 token 直接翻好",
      saved.get("1") == "第1话" and saved.get("3") == "闲话",
      str({k: saved.get(k) for k in ("1", "2", "3")}))
check("重复标题只发一次",
      len(calls) == 1 and calls[0] == ["1", "2"], str(calls))
check("同名章节拿到同一译名",
      saved.get("4") == saved.get("5") == "相同的标题",
      str({"4": saved.get("4"), "5": saved.get("5")}))
check("不同标题各自翻译", saved.get("6") == "另一个标题", str(saved.get("6")))

print()
print("=" * 66)
print("C. 候选术语：片假名频次（已进表的词不再列）")
print("=" * 66)
out = io.StringIO()
with contextlib.redirect_stdout(out):
    lt.cmd_terms(argparse.Namespace(
        slug=SLUG, top=20, count=1, min=2, json=True))
rows = json.loads(out.getvalue())
check("找到グランドール", "グランドール" in rows, str(list(rows)[:6]))
check("已进术语表的 アリス 不重复列", "アリス" not in rows)
check("频次是实数", rows.get("グランドール") == 2, str(rows))

print()
print("=" * 66)
print("D. stale --retranslate 的收尾 / 无关编辑不刷掉过期提示")
print("=" * 66)
_orig_tr = lt.translate_chapter
try:
    calls = []

    def fake_fail(slug, idx, meta, ns):
        calls.append(idx)
        return False

    lt.translate_chapter = fake_fail
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        lt.cmd_stale(argparse.Namespace(
            slug=SLUG, term=None, retranslate=True, limit=1, model="stub"))
    txt = out.getvalue()
    check("重翻失败：如实报 0/1，不打印「完成」",
          bool(calls) and "0/1" in txt and "未成功" in txt
          and "完成。" not in txt, txt.strip()[-160:])

    def fake_ok(slug, idx, meta, ns):
        calls.append(idx)
        return True

    lt.translate_chapter = fake_ok
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        lt.cmd_stale(argparse.Namespace(
            slug=SLUG, term=None, retranslate=True, limit=1, model="stub"))
    txt = out.getvalue()
    check("重翻成功：报 1/1 并提示复查",
          "1/1" in txt and "复查" in txt, txt.strip()[-120:])
finally:
    lt.translate_chapter = _orig_tr

# 引号对齐 / 修页脚这类编辑不碰人名，不能把「译名过时」静默刷掉。
check("无关编辑前：第 1 章确实是过期的",
      lt.chapter_glossary_stale(SLUG, 0, meta) is True)
lt.refresh_chapter_meta(SLUG, 0, meta, update_glossary=False)
check("update_glossary=False 保留旧指纹（过期提示还在）",
      lt.chapter_glossary_stale(SLUG, 0, meta) is True)
lt.refresh_chapter_meta(SLUG, 0, meta, update_glossary=True)
check("按当前术语表刷新后才不再过期",
      lt.chapter_glossary_stale(SLUG, 0, meta) is False)

# 清理
shutil.rmtree(D, ignore_errors=True)
if "lntrans-stale-test-" in _ROOT:
    shutil.rmtree(_ROOT, ignore_errors=True)

print()
if fails:
    print(f"❌ {len(fails)} 项失败：{fails}")
    sys.exit(1)
print("✅ 全部通过")
