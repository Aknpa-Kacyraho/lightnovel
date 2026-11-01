#!/usr/bin/env python3
"""回归：数据文件损坏时**不许静默当成空**（保护真实书库 / 推荐缓存）。

数据层 lnrecs 原来对 `library.json` / `recs.json` 的解析失败一律
`return {}` / `{"at":0,"items":[]}` —— 用户视角就是"我的整座书架凭空没了"，
没有告警、也没法找回。现在：坏文件被挪到 `<name>.corrupt-<时间戳>` 留证
+ stderr 告警，再以空数据继续；挪走后下次保存写出全新的好文件。

断言（**只在隔离数据根里跑**）：
  1. library.json 损坏 → 返回空 + 生成 .corrupt-* 备份，原文件已被挪走
  2. recs.json    损坏 → 同样备份 + 返回默认空缓存
  3. 文件正常时**不产生**任何备份、数据原样返回（别把好文件也挪了）
  4. 损坏后仍能正常保存并再读回（自愈，不会永久卡在"空"）

失败必须反馈到退出码：run_selftests.py 只看 returncode（外加扫 ❌）。
"""

from __future__ import annotations

import glob
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


_s = importlib.util.spec_from_file_location("lnrecs", os.path.join(HERE, "lnrecs.py"))
recs = importlib.util.module_from_spec(_s)
_s.loader.exec_module(recs)

# 防呆：必须跑在隔离数据根里 —— 否则会挪走**真实**的 library.json / recs.json。
if os.environ.get("LNTRANS_TEST_SERVER") != "1" or not os.environ.get("LNTRANS_DATA_ROOT"):
    print("✗ 拒绝运行：需要 LNTRANS_DATA_ROOT 隔离 + LNTRANS_TEST_SERVER=1")
    sys.exit(2)

DATA = recs.DATA
RECS = recs.RECS_PATH
LIB = recs.LIB_PATH
os.makedirs(DATA, exist_ok=True)


def backups(path):
    return sorted(glob.glob(path + ".corrupt-*"))


for _p in (RECS, LIB):
    for _b in backups(_p):
        os.remove(_b)

# 1) library.json 损坏：返回空、备份留证、原文件挪走 ─────────────────────────
with open(LIB, "w", encoding="utf-8") as f:
    f.write("{ 不是合法 JSON ")
got = recs._load_lib()
b = backups(LIB)
check("library.json 损坏 → 返回空、不抛异常", got == {}, f"返回 {got!r}")
check("library.json 损坏 → 坏文件被挪走留证", len(b) == 1 and not os.path.exists(LIB),
      f"备份 {[os.path.basename(x) for x in b]}")
if b:
    with open(b[0], encoding="utf-8") as f:
        check("备份内容 = 原始坏内容（可人工找回）", "不是合法" in f.read())

# 2) recs.json 损坏：返回默认空缓存 + 备份留证 ──────────────────────────────
with open(RECS, "w", encoding="utf-8") as f:
    f.write("[[[")
c = recs._load_cache()
b = backups(RECS)
check("recs.json 损坏 → 返回默认空缓存", isinstance(c, dict) and c.get("items") == [],
      f"返回 {c!r}")
check("recs.json 损坏 → 坏文件被挪走留证", len(b) == 1 and not os.path.exists(RECS),
      f"备份 {[os.path.basename(x) for x in b]}")

# 3) 正常文件不该被挪 ───────────────────────────────────────────────────────
with open(LIB, "w", encoding="utf-8") as f:
    json.dump({"42": {"id": "42", "title": "好文件"}}, f, ensure_ascii=False)
before = len(backups(LIB))
lib = recs._load_lib()
check("正常文件 → 原样读回", (lib.get("42") or {}).get("title") == "好文件")
check("正常文件 → 不产生任何备份、文件仍在",
      len(backups(LIB)) == before and os.path.exists(LIB))

# 4) 自愈：损坏后再保存 / 读回 ──────────────────────────────────────────────
recs.merge_into_library([{"id": "7", "title": "自愈书", "tags": ["x"]}])
lib2 = recs._load_lib()
check("损坏后仍能保存并读回（自愈）",
      (lib2.get("7") or {}).get("title") == "自愈书" and "42" in lib2,
      f"读取 {sorted(lib2)}")

print()
_all = not fails
print("回归结果：", "全部通过 ✅" if _all else f"仍有失败 ❌ {fails}")
if not _all:
    sys.exit(1)
