#!/usr/bin/env python3
"""回归：备份必须「能验、能恢复、只增不删」。

为什么专门给备份写测试：备份是唯一一个**平时看不出坏、出事才发现坏**的功能。
"导出成功"只证明 zip 写得出来，不证明能恢复；"恢复成功"若把本地新数据覆盖掉，
比不做备份更糟。所以每个断言都对着**磁盘上的真实字节**，而不是函数的返回值自说自话。

覆盖（全部在临时目录里，绝不碰真实数据根）：
  1. 导出 → 校验通过，三棵树都进去了，`*.log`/`*.tmp`/`__pycache__` 被排除，
     manifest 里没有绝对路径（换机可恢复）
  2. 恢复到空目录 → 逐字节一致
  3. 再恢复一次 → 幂等（0 新建 / 全未变）
  4. 本地改动过 → 先挪 .bak 再写，本地新内容仍能从 .bak 找回
  5. 本地多出来的文件 → 恢复不许删
  6. 包被改坏一个字节 → verify 失败、restore **一个文件都不动**
  7. 包里有 `../` 路径穿越 → 拒绝
  8. 默认干跑 → 盘上零变化
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


_s = importlib.util.spec_from_file_location("lnbackup", os.path.join(HERE, "lnbackup.py"))
bk = importlib.util.module_from_spec(_s)
_s.loader.exec_module(bk)

TMP = tempfile.mkdtemp(prefix="lnbackup-test-")
SRC = os.path.join(TMP, "src")
DST = os.path.join(TMP, "dst")
FINDER = os.path.join(TMP, "finder")


def put(base, rel, text):
    p = os.path.join(base, *rel.split("/"))
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


# 1) 造一棵有代表性的数据树 ────────────────────────────────────────────────
put(SRC, "novels/ts/meta.json", '{"id": 1, "zh_titles": {"book": "转生成了TS"}}')
put(SRC, "novels/ts/chapters/1.txt", "第一章译文\n「你好」")
put(SRC, "novels/ts/raw/1.txt", "第一章原文")
put(SRC, "novels/ts/cache/seg-1.txt", "缓存=钱")
put(SRC, "data/books/ts.json", '{"tracking": "reading"}')
put(SRC, "data/history.jsonl", '{"at": "2026-01-01"}\n')
put(SRC, "data/empty.txt", "")                      # 空文件也要能备份
put(SRC, "data/server.log", "噪音")                  # 必须被排除
put(SRC, "data/x.tmp", "噪音")                       # 必须被排除
put(SRC, "data/__pycache__/m.pyc", "噪音")            # 必须被排除
put(FINDER, "taste_profile.json", '{"tags": {"TS": 1.4}}')
put(FINDER, "reports/weekly.md", "本周口味报告")
put(FINDER, "lnfind.py", "print('这是代码，不是数据')")
put(FINDER, "taste_profile.json.bak-20260101", "旧副本")
put(SRC, "data/tool.py", "print('代码也不许进备份')")
# 空目录：zip 存不下目录，必须由 manifest 单独记下来，否则恢复出来的树会少一层。
os.makedirs(os.path.join(SRC, "novels", "ts", "illustrations"), exist_ok=True)

zip_path = os.path.join(TMP, "b.zip")
man = bk.build(zip_path, data_root=SRC, finder_root=FINDER)

check("导出后有 zip 文件", os.path.isfile(zip_path))
check("文件数与磁盘一致（9 个有效文件）", man["files"] == 9, f"manifest 说 {man['files']}")
check("三棵树计数正确",
      man["counts"] == {"novels": 4, "data": 3, "lnfinder": 2},
      f"{man['counts']}")

with zipfile.ZipFile(zip_path) as z:
    names = z.namelist()
    raw = z.read("manifest.json").decode("utf-8")
check("排除 *.log", not any(n.endswith(".log") for n in names))
check("排除 *.tmp", not any(n.endswith(".tmp") for n in names))
check("排除 __pycache__", not any("__pycache__" in n for n in names))
check("排除源码 *.py（lnfinder 是代码+数据混居）",
      not any(n.endswith(".py") for n in names),
      str([n for n in names if n.endswith(".py")][:3]))
check("排除 .bak- 旧副本（避免备份自吞）",
      not any(".bak-" in n for n in names))
check("保留 lnfinder/reports（真数据）",
      "lnfinder/reports/weekly.md" in names)
check("manifest 不写绝对路径", TMP not in raw and SRC not in raw)
check("manifest 没有 .. 路径", ".." not in raw)

rep = bk.verify(zip_path)
check("verify 通过", rep["ok"], rep.get("error") or "")
check("verify 统计 = 9 个文件", rep["files"] == 9, f"{rep['files']}")

# 2) 恢复到空目录：逐字节一致 ──────────────────────────────────────────────
out = bk.restore(zip_path, data_root=DST, finder_root=os.path.join(TMP, "finder2"), write=True)
check("恢复新建 9 个", out["created"] == 9 and out["updated"] == 0, f"{out}")
for rel, text in (("novels/ts/chapters/1.txt", "第一章译文\n「你好」"),
                  ("novels/ts/cache/seg-1.txt", "缓存=钱"),
                  ("data/empty.txt", ""),
                  ("data/books/ts.json", '{"tracking": "reading"}')):
    p = os.path.join(DST, *rel.split("/"))
    got = open(p, encoding="utf-8").read() if os.path.exists(p) else None
    check(f"恢复内容一致 {rel}", got == text)
check("画像也恢复了",
      open(os.path.join(TMP, "finder2", "taste_profile.json"), encoding="utf-8").read()
      == '{"tags": {"TS": 1.4}}')
check("恢复会写审计单", any(n.startswith("restore-") for n in os.listdir(os.path.join(DST, "data"))))
check("空目录也恢复了",
      os.path.isdir(os.path.join(DST, "novels", "ts", "illustrations")),
      f"目录数 {out['dirs']}")

# 3) 幂等：再恢复一次不许重复建 ───────────────────────────────────────────
out2 = bk.restore(zip_path, data_root=DST, finder_root=os.path.join(TMP, "finder2"), write=True)
check("重复恢复是幂等的", out2["created"] == 0 and out2["updated"] == 0
      and out2["unchanged"] == 9 and out2["dirs"] == 0, f"{out2}")

# 4) 本地改动 → 先挪 .bak 再写，新内容可从 .bak 找回 ──────────────────────
local = os.path.join(DST, "novels", "ts", "chapters", "1.txt")
with open(local, "w", encoding="utf-8") as f:
    f.write("本地手改过的新版")
out3 = bk.restore(zip_path, data_root=DST, finder_root=os.path.join(TMP, "finder2"), write=True)
check("改动过的文件被覆盖", open(local, encoding="utf-8").read() == "第一章译文\n「你好」")
check("覆盖前留了 .bak",
      len(out3["bak"]) == 1 and ".bak-" in out3["bak"][0]
      and out3["bak"][0].startswith("ts/chapters/1.txt"),
      f"{out3['bak']}")
baks = [n for n in os.listdir(os.path.dirname(local)) if ".bak-" in n]
check("本地新版还能从 .bak 找回",
      bool(baks) and open(os.path.join(os.path.dirname(local), baks[0]),
                          encoding="utf-8").read() == "本地手改过的新版")

# 5) 本地多出来的文件：恢复不许删 ────────────────────────────────────────
extra = put(DST, "data/mine-only.json", '{"本地": "新增"}')
bk.restore(zip_path, data_root=DST, finder_root=os.path.join(TMP, "finder2"), write=True)
check("恢复不删本地独有文件", os.path.exists(extra))

# 6) 包损坏 → verify 失败，restore 一个文件都不动 ─────────────────────────
bad = os.path.join(TMP, "bad.zip")
shutil.copyfile(zip_path, bad)
with zipfile.ZipFile(bad) as z:
    data = {n: z.read(n) for n in z.namelist()}
data["novels/ts/meta.json"] = data["novels/ts/meta.json"] + b"X"
with zipfile.ZipFile(bad, "w") as z:
    for n, b in data.items():
        z.writestr(n, b)
rep_bad = bk.verify(bad)
check("坏包 verify 失败", not rep_bad["ok"] and "novels/ts/meta.json" in rep_bad["bad"],
      f"{rep_bad['bad']}")

before = {os.path.join(dp, f): os.path.getmtime(os.path.join(dp, f))
          for dp, _, fs in os.walk(DST) for f in fs
          if f != ".lntrans.lock"}
blocked = False
try:
    bk.restore(bad, data_root=DST, finder_root=os.path.join(TMP, "finder2"), write=True)
except bk.BackupError:
    blocked = True
check("坏包恢复被拒绝", blocked)
after = {os.path.join(dp, f): os.path.getmtime(os.path.join(dp, f))
         for dp, _, fs in os.walk(DST) for f in fs
         if f != ".lntrans.lock"}
check("坏包恢复没动任何文件", before == after)

# 7) 路径穿越 → 拒绝 ────────────────────────────────────────────────────
evil = os.path.join(TMP, "evil.zip")
with zipfile.ZipFile(evil, "w") as z:
    z.writestr("manifest.json", json.dumps({
        "kind": bk.KIND, "format": bk.FORMAT, "created_at": "x",
        "counts": {}, "files": 1, "bytes": 4,
        "entries": [{"path": "../../evil.txt", "size": 4, "sha256": "0" * 64}]}))
    z.writestr("../../evil.txt", "evil")
rep_evil = bk.verify(evil)
check("穿越路径被标记为可疑", not rep_evil["ok"] and "../../evil.txt" in rep_evil["unsafe"])
blocked2 = False
try:
    bk.restore(evil, data_root=DST, finder_root=os.path.join(TMP, "finder2"), write=True)
except bk.BackupError:
    blocked2 = True
check("穿越包被拒绝恢复", blocked2)
check("穿越文件没被写到临时目录外", not os.path.exists(os.path.join(TMP, "evil.txt")))

# 7b) 运行控制文件（锁/状态）绝不能被旧包恢复回来 ─────────────────────
control = os.path.join(TMP, "control.zip")
control_blob = b"stale lock"
with zipfile.ZipFile(control, "w") as z:
    z.writestr("manifest.json", json.dumps({
        "kind": bk.KIND, "format": bk.FORMAT, "created_at": "x",
        "counts": {}, "files": 1, "bytes": len(control_blob),
        "entries": [{
            "path": "data/.lntrans.lock",
            "size": len(control_blob),
            "sha256": hashlib.sha256(control_blob).hexdigest(),
        }],
    }))
    z.writestr("data/.lntrans.lock", control_blob)
rep_control = bk.verify(control)
check("锁文件进入备份包会被拒绝",
      not rep_control["ok"] and "data/.lntrans.lock" in rep_control["unsafe"],
      f"{rep_control['unsafe']}")

# 7c) 旧包/伪造包带源码 → 不许恢复，本地源码一个字节都不动 ─────────────
code_zip = os.path.join(TMP, "code.zip")
code_blob = b"print('old lnfind code')\n"
with zipfile.ZipFile(code_zip, "w") as z:
    z.writestr("manifest.json", json.dumps({
        "kind": bk.KIND, "format": bk.FORMAT, "created_at": "x",
        "counts": {}, "files": 1, "bytes": len(code_blob),
        "entries": [{
            "path": "lnfinder/lnfind.py",
            "size": len(code_blob),
            "sha256": hashlib.sha256(code_blob).hexdigest(),
        }],
    }))
    z.writestr("lnfinder/lnfind.py", code_blob)
rep_code = bk.verify(code_zip)
check("备份包含 lnfind.py 会被判定为 unsafe",
      not rep_code["ok"] and "lnfinder/lnfind.py" in rep_code["unsafe"],
      f"{rep_code['unsafe']}")

code_root = os.path.join(TMP, "code-root")
code_finder = os.path.join(TMP, "code-finder")
os.makedirs(code_root, exist_ok=True)
os.makedirs(code_finder, exist_ok=True)
local_code = put(code_finder, "lnfind.py", "print('current newer code')\n")
code_blocked = False
try:
    bk.restore(code_zip, data_root=code_root, finder_root=code_finder, write=True)
except bk.BackupError:
    code_blocked = True
check("带源码的旧包恢复被拒绝", code_blocked)
check("本地 lnfind.py 未被旧包回退",
      open(local_code, encoding="utf-8").read() == "print('current newer code')\n")

# 8) 默认干跑：盘上零变化 ────────────────────────────────────────────────
dst2 = os.path.join(TMP, "dst2")
os.makedirs(dst2)
dry = bk.restore(zip_path, data_root=dst2, finder_root=os.path.join(TMP, "f3"))
check("干跑报告将要新建 9 个", dry["created"] == 9 and dry["written"] is False)
check("干跑不写盘", not os.path.exists(os.path.join(dst2, "novels")))

print()
_all = not fails
print("回归结果：", "全部通过 ✅" if _all else f"仍有失败 ❌ {fails}")
if _all:
    shutil.rmtree(TMP, ignore_errors=True)
if not _all:
    sys.exit(1)
