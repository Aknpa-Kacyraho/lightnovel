#!/usr/bin/env python3
"""回归：已译章号缓存必须按章增量，不能每次新译后整本重哈希。

旧实现用「目录 mtime + 四个计数」当缓存键：每译完一章 sidecar mtime 必变，
键必变，下一次渲染就把整本每章再跑两遍 SHA-256；同时还在 GET 渲染路径
写 `books/<slug>.json`（纯写放大，读端根本不存在）。这里用受控的
`has_zh` 计数器守住「只重算变化的那一章」。
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


_s = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
sv = importlib.util.module_from_spec(_s)
_s.loader.exec_module(sv)

tmp = tempfile.mkdtemp(prefix="ln-zh-cache-")
old_novels = sv.NOVELS
sv.NOVELS = tmp
book = os.path.join(tmp, "cache-book")
os.makedirs(os.path.join(book, "chapters"))
os.makedirs(os.path.join(book, "raw"))
for i in range(3):
    with open(os.path.join(book, "chapters", f"{i:04d}.txt"), "w",
              encoding="utf-8") as f:
        f.write(f"第 {i + 1} 章译文\n")
    with open(os.path.join(book, "raw", f"{i:04d}.txt"), "w",
              encoding="utf-8") as f:
        f.write(f"第 {i + 1} 章原文\n")

calls = []
sv.has_zh = lambda slug, i: calls.append(i) or (i != 1)

check("首次扫描只算每章一次", sv.zh_chapters("cache-book", 3) == [1, 3]
      and calls == [0, 1, 2], f"{calls}")

calls.clear()
check("第二次命中缓存，零哈希", sv.zh_chapters("cache-book", 3) == [1, 3]
      and calls == [], f"{calls}")

# 模拟“刚译完第 2 章”：只改它的 mtime，不动目录结构（0-based 0001）。
p = os.path.join(book, "chapters", "0001.txt")
os.utime(p, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
sv.has_zh = lambda slug, i: calls.append(i) or True
calls.clear()
check("新译一章只重算那一章", sv.zh_chapters("cache-book", 3) == [1, 2, 3]
      and calls == [1], f"{calls}")

# 新增一章同样只算新章，不需要手工 invalidate 整本。
with open(os.path.join(book, "chapters", "0003.txt"), "w",
          encoding="utf-8") as f:
    f.write("第 4 章译文\n")
with open(os.path.join(book, "raw", "0003.txt"), "w", encoding="utf-8") as f:
    f.write("第 4 章原文\n")
calls.clear()
check("新增一章只算新章", sv.zh_chapters("cache-book", 4) == [1, 2, 3, 4]
      and calls == [3], f"{calls}")

# 跨进程正确性：命令行维护脚本用 save_text（临时文件 + os.replace）改章节，
# 而 exFAT/sdcardfs 的 mtime 只有 2 秒粒度、内容长度又可能不变。只比
# (mtime, size) 会让服务进程一直命中旧结论。原子替换一定换 inode。
p = os.path.join(book, "chapters", "0001.txt")
sv.lt.save_text(p, "第 2 章译文\n")          # 统一成 LF，保证两次等长
sv.has_zh = lambda slug, i: True
sv.zh_chapters("cache-book", 4)              # 让缓存记下当前签名
sigs_before = sv._dir_sigs(os.path.join(book, "chapters"))
st_before = os.stat(p)
sv.lt.save_text(p, "第 5 章译文\n")          # 等长替换
os.utime(p, ns=(st_before.st_atime_ns, st_before.st_mtime_ns))
sigs_after = sv._dir_sigs(os.path.join(book, "chapters"))
same_mtime_size = (sigs_before["0001.txt"][:2] == sigs_after["0001.txt"][:2])
ino_ok = sigs_before["0001.txt"][2] != sigs_after["0001.txt"][2]
if same_mtime_size and ino_ok:
    calls.clear()
    sv.has_zh = lambda slug, i: calls.append(i) or True
    sv.zh_chapters("cache-book", 4)
    check("原子替换换 inode：mtime/size 相同也会重算该章",
          calls == [1], f"{calls}")
else:
    print(f"  跳过 inode 断言（mtime_size_same={same_mtime_size}, "
          f"ino_changed={ino_ok}）：本文件系统不提供可用 inode")

sv.NOVELS = old_novels
shutil.rmtree(tmp, ignore_errors=True)

print()
_all = not fails
print("回归结果：", "全部通过 ✅" if _all else f"仍有失败 ❌ {fails}")
if not _all:
    sys.exit(1)
