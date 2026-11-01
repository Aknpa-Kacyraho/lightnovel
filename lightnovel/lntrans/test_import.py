#!/usr/bin/env python3
"""本地导入回归：EPUB 拆章、TXT 拆章、去重、编码。

为什么单测：导入是"把用户手里已有的书接进来"的唯一入口，解析错了不会
报错 —— 只会安静地少几章、或者把整本塞进一章。这里用一个手工构造的
EPUB（container/OPF/spine 齐全）和几种 TXT 守住这些边界。
"""

from __future__ import annotations

import io
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_ROOT = os.environ.get("LNTRANS_DATA_ROOT") or tempfile.mkdtemp(
    prefix="lntrans-import-test-")
os.makedirs(os.path.join(_ROOT, "novels"), exist_ok=True)
os.environ["LNTRANS_DATA_ROOT"] = _ROOT

_s = importlib.util.spec_from_file_location("lt", os.path.join(HERE, "lntrans.py"))
lt = importlib.util.module_from_spec(_s)
sys.argv = ["x"]
_s.loader.exec_module(lt)

import lnimport  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def make_epub(single_doc: bool = False, hrefs: dict | None = None,
              doc1: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
        ch1 = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>第一章</title></head>
<body><h2>第一章　出会い</h2><p>アリスは魔法を使った。</p><p>「こんにちは」</p></body></html>"""
        if doc1 is not None:
            ch1 = doc1
        ch2 = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>第二章</title></head>
<body><h2>第二章　旅立ち</h2><p>次の町へ向かう。</p></body></html>"""
        if single_doc:
            ch1 = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>合集</title></head><body>
<h2>第一話　始まり</h2><p>""" + ("あ" * 700) + """</p>
<h2>第二話　続き</h2><p>""" + ("い" * 700) + """</p></body></html>"""
        z.writestr("OEBPS/ch1.xhtml", ch1)
        z.writestr("OEBPS/ch2.xhtml", ch2)
        spine = '<itemref idref="c1"/>' if single_doc else (
            '<itemref idref="c1"/><itemref idref="c2"/>')
        _hrefs = hrefs or {}
        z.writestr("OEBPS/content.opf", """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>テスト小説</dc:title><dc:creator>作者A</dc:creator>
  </metadata>
  <manifest>
    <item id="c1" href=\"""" + _hrefs.get(0, "ch1.xhtml") + """\" media-type="application/xhtml+xml"/>
    <item id="c2" href=\"""" + _hrefs.get(1, "ch2.xhtml") + """\" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>""" + spine + """</spine>
</package>""")
    return buf.getvalue()


print("=" * 66)
print("A. EPUB：spine 顺序、元数据、段落")
print("=" * 66)
info = lnimport.import_bytes(
    make_epub(), "测试本.epub", lt=lt, novels_dir=lt.NOVELS_DIR)
check("建了书", info["created"] is True, str(info))
check("书名取 OPF", info["title"] == "テスト小説", info["title"])
check("作者取 OPF", info["author"] == "作者A", info["author"])
check("2 章", info["chapters"] == 2, str(info["chapters"]))
meta = lt.load_meta(info["slug"])
check("source=local", meta.get("source") == "local", str(meta.get("source")))
check("source_id 带哈希", str(meta.get("source_id", "")).startswith("local-"))
check("本地 slug 是稳定 local UUID，不是标题",
      info["slug"].startswith("local-") and meta.get("id") == info["slug"])
check("本地内容哈希单独保存", meta.get("hash_scheme") == "file_sha256_v1"
      and bool(meta.get("content_hash")))
check("episodes 标题来自 h2", meta["episodes"][0]["title"] == "第一章　出会い",
      meta["episodes"][0]["title"])
check("fetched_through=章数", meta["progress"]["fetched_through"] == 2,
      str(meta["progress"]))
raw1 = open(os.path.join(lt.NOVELS_DIR, info["slug"], "raw", "0000.txt"),
            encoding="utf-8").read()
check("正文段落没丢", "アリスは魔法を使った。" in raw1 and "「こんにちは」" in raw1,
      raw1[:60])
check("段落之间是空行（不会被合并）", "\n\n" in raw1, repr(raw1[:80]))

print("=" * 66)
print("B. 同一个文件再导入：不重复建书")
print("=" * 66)
again = lnimport.import_bytes(
    make_epub(), "测试本.epub", lt=lt, novels_dir=lt.NOVELS_DIR)
check("created=False", again["created"] is False)
check("slug 不变", again["slug"] == info["slug"])

print("=" * 66)
print("C. 一篇 XHTML 里多个 h2：按标题拆章")
print("=" * 66)
info2 = lnimport.import_bytes(
    make_epub(single_doc=True), "合集.epub", lt=lt,
    novels_dir=lt.NOVELS_DIR)
check("拆成 2 章", info2["chapters"] == 2, str(info2))
m2 = lt.load_meta(info2["slug"])
check("章名是各自的 h2",
      m2["episodes"][0]["title"] == "第一話　始まり"
      and m2["episodes"][1]["title"] == "第二話　続き",
      str([e["title"] for e in m2["episodes"]]))

print("=" * 66)
print("D. TXT：按「第N話」拆章、CP932 也能读")
print("=" * 66)
txt = ("これは前書きです。" * 30 + "\n\n"
       "第1話　始まり\n" + " primeira " * 0 + "一行目。\n二行目。\n\n"
       "第2話　続き\n三行目。\n")
data = txt.encode("cp932")
info3 = lnimport.import_bytes(
    data, "テスト.txt", lt=lt, novels_dir=lt.NOVELS_DIR)
check("TXT 建书（序 + 2 章）",
      info3["created"] is True and info3["chapters"] == 3, str(info3))
m3 = lt.load_meta(info3["slug"])
check("TXT 章名保留", "第2話" in m3["episodes"][2]["title"],
      m3["episodes"][2]["title"])
raw3 = open(os.path.join(lt.NOVELS_DIR, info3["slug"], "raw", "0001.txt"),
            encoding="utf-8").read()
check("CP932 解码正确", "一行目。" in raw3 and " primeira " not in raw3,
      raw3[:40])

info4 = lnimport.import_bytes(
    txt.encode("utf-8"), "中文.txt", lt=lt, title="中文书名",
    novels_dir=lt.NOVELS_DIR)
m4 = lt.load_meta(info4["slug"])
check("中文书名直接当译文（不再花 token）",
      (m4.get("zh_titles") or {}).get("book") == "中文书名",
      str(m4.get("zh_titles")))

_zh_txt = "第1话 开始\n这是纯中文正文。" + "汉字测试内容。" * 40 + "\n"
_zh = lnimport.import_bytes(_zh_txt.encode("utf-8"), "纯中文.txt", lt=lt,
                            novels_dir=lt.NOVELS_DIR)
check("纯中文/中日混合章直接标记可读，不再送翻译",
      _zh.get("chinese_chapters", 0) >= 1
      and os.path.getsize(os.path.join(lt.NOVELS_DIR, _zh["slug"],
                                       "chapters", "0000.txt")) > 0,
      str(_zh))

print("=" * 66)
print("E. 本地书：ensure_raw 不联网、缺失时报清楚")
print("=" * 66)
lt.ensure_raw(info["slug"], lt.load_meta(info["slug"]), 2, quiet=True)
check("ensure_raw 对本地书是空操作",
      os.path.getsize(os.path.join(lt.NOVELS_DIR, info["slug"], "raw",
                                   "0001.txt")) > 0)
os.remove(os.path.join(lt.NOVELS_DIR, info["slug"], "raw", "0001.txt"))
try:
    lt.ensure_raw(info["slug"], lt.load_meta(info["slug"]), 2, quiet=True)
    check("缺原文必须报错（不许打源站）", False)
except RuntimeError as e:
    check("缺原文必须报错（不许打源站）", "缺少第 2 章" in str(e), str(e))

print("=" * 66)
print("F. 坏输入：空文件 / 不是 EPUB")
print("=" * 66)
try:
    lnimport.import_bytes(b"", "empty.txt", lt=lt, novels_dir=lt.NOVELS_DIR)
    check("空文件被拒绝", False)
except lnimport.ImportError_ as e:
    check("空文件被拒绝", "空" in str(e), str(e))
try:
    lnimport.import_bytes(b"PK\x03\x04broken", "bad.epub", lt=lt,
                          novels_dir=lt.NOVELS_DIR)
    check("坏 EPUB 被拒绝", False)
except lnimport.ImportError_:
    check("坏 EPUB 被拒绝", True)

print("=" * 66)
print("G. 编码 / ruby / href 锚点 / 短前言 / 无空行 TXT")
print("=" * 66)
# GBK 中文：cp932 也能「解码成功」，但会变成半角片假名乱码。
_gbk = ("第一章　开始\n这是中文测试。\n第二章　继续\n下一章内容。\n"
        ).encode("gb18030")
info5 = lnimport.import_bytes(
    _gbk, "中文书.txt", lt=lt, novels_dir=lt.NOVELS_DIR)
check("GBK 中文按内容判编码（不是谁先不报错）", info5["chapters"] == 2,
      str(info5))
raw5 = open(os.path.join(lt.NOVELS_DIR, info5["slug"], "raw", "0000.txt"),
            encoding="utf-8").read()
check("GBK 正文没变乱码", "这是中文测试。" in raw5 and "\uff61" not in raw5,
      repr(raw5[:40]))

_half = "ｺﾚﾊﾊﾝｶｸｶﾀｶﾅﾉﾃｷｽﾄﾃﾞｽ｡"
check("老式半角片假名日文不被误判成中文",
      lnimport._decode(_half.encode("cp932")) == _half,
      repr(lnimport._decode(_half.encode("cp932"))[:30]))

_ruby = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>第一章</title></head>
<body><h2>第一章　出会い</h2>
<p><ruby>亜里沙<rt>アリサ</rt></ruby>は魔法を使った。</p></body></html>"""
info6 = lnimport.import_bytes(
    make_epub(doc1=_ruby), "ruby.epub", lt=lt, novels_dir=lt.NOVELS_DIR)
raw6 = open(os.path.join(lt.NOVELS_DIR, info6["slug"], "raw", "0000.txt"),
            encoding="utf-8").read()
check("EPUB ruby 注音被剥掉（不混进正文）",
      "亜里沙は魔法" in raw6 and "アリサ" not in raw6, repr(raw6[:50]))

info7 = lnimport.import_bytes(
    make_epub(hrefs={0: "ch1.xhtml#top"}), "锚点.epub", lt=lt,
    novels_dir=lt.NOVELS_DIR)
check("manifest href 带锚点仍导入该章（不静默丢章）",
      info7["chapters"] == 2, str(info7))

_t, _a, _pre = lnimport.parse_txt(
    "很短的前言。\n\n第1話　始まり\n本文。\n".encode("utf-8"), "x.txt")
check("标题前的短前言保留为「序」",
      _pre[0][0] == "序" and "很短的前言。" in _pre[0][1], str(_pre))

_lines = "一行一段の本文です。\n" * 50
_t, _a, _ch = lnimport.parse_txt(_lines.encode("utf-8"), "x.txt")
_paras = [p for p in _ch[0][1].split("\n\n") if p.strip()]
check("无空行 TXT 按一行一段重排（整章不会并成一段）",
      len(_paras) == 50 and max(len(p) for p in _paras) < 100,
      f"{len(_paras)} 段 / 最长 {max(map(len, _paras))} 字")

_long = ("あ" * 9000) + "。"
_t, _a, _ch = lnimport.parse_txt(_long.encode("utf-8"), "x.txt")
_paras = [p for p in _ch[0][1].split("\n\n") if p.strip()]
check("超长单行被切开（分段器才能二分降级）",
      len(_paras) >= 3 and max(len(p) for p in _paras) <= 2500,
      f"{len(_paras)} 段 / 最长 {max(map(len, _paras))} 字")

# 清理
_cleanup = [info["slug"], info2["slug"], info3["slug"], info4["slug"],
            info5["slug"], info6["slug"], info7["slug"]]
for slug in _cleanup:
    shutil.rmtree(os.path.join(lt.NOVELS_DIR, slug), ignore_errors=True)
if "lntrans-import-test-" in _ROOT:
    shutil.rmtree(_ROOT, ignore_errors=True)

print()
if fails:
    print(f"❌ {len(fails)} 项失败：{fails}")
    sys.exit(1)
print("✅ 全部通过")
