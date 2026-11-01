#!/usr/bin/env python3
"""EPUB 导出回归：结构对不对、内容少没少、能不能被阅读器吃下去。

为什么单开一个测试：EPUB 是"这本书能带走"的唯一形态，坏了读者不会来报错，
他只会打不开、然后放弃。而它的错误大多**不会让 Python 抛异常** ——
zip 顺序错、mimetype 被压缩、OPF 里的 id 对不上 spine，都能正常生成一个
"看起来像 epub"的文件，只有阅读器知道它是废的。

这里守住五件事（都是规范里写死、错了要命的）：
1. `mimetype` 是**第一个**条目且**不压缩**（OCF；错了部分阅读器直接拒收）；
2. 所有 XML 都能解析（手写 XML 最容易漏转义）；
3. 只收**已译**章，spine 顺序 = 章序，目录里每一章的链接都真实存在；
4. identifier 稳定（同一本书两次导出必须同一个，否则阅读器当成两本）；
5. 书里的中文文本、引号、HTML 特殊字符都原样且被转义（不许丢段、不许变标签）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_ROOT = os.environ.get("LNTRANS_DATA_ROOT") or HERE
NOVELS = os.path.join(_ROOT, "novels")
SLUG = "__ep__"
BASE = sys.argv[1] if len(sys.argv) > 1 else ""

_s = importlib.util.spec_from_file_location("lnepub", os.path.join(HERE, "lnepub.py"))
ep = importlib.util.module_from_spec(_s)
sys.argv = ["lnepub"]
_s.loader.exec_module(ep)

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def write_book(root: str, slug: str, translated: list[int], total: int = 6) -> str:
    d = os.path.join(root, "novels", slug)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "chapters"))
    os.makedirs(os.path.join(d, "raw"))
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({
            "slug": slug, "source": "kakuyomu", "source_id": "999",
            "url": "https://example.invalid/works/999",
            "title": "テスト作品", "author": "作者名",
            "zh_titles": {"book": "测试作品"},
            "episodes": [{"id": str(i), "title": f"第{i + 1}話　テスト"}
                         for i in range(total)],
            "glossary": {}, "characters": {}, "summaries": {}, "style": {},
            "progress": {"translated_through": 0, "fetched_through": 0},
        }, f, ensure_ascii=False)
    for ch in translated:
        i = ch - 1
        with open(os.path.join(d, "chapters", f"{i:04d}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(f"第{ch}章第一段，「引号」保留。\n\n"
                    f"这里有 <标签> 与 & 符号，必须被转义。\n\n最后一段。\n")
        with open(os.path.join(d, "raw", f"{i:04d}.txt"), "w", encoding="utf-8") as f:
            f.write(f"第{ch}話の原文。\n")
    return d


def add_chapter(d: str, ch: int) -> None:
    i = ch - 1
    with open(os.path.join(d, "chapters", f"{i:04d}.txt"), "w",
              encoding="utf-8") as f:
        f.write(f"第{ch}章第一段，「引号」保留。\n\n最后一段。\n")
    with open(os.path.join(d, "raw", f"{i:04d}.txt"), "w", encoding="utf-8") as f:
        f.write(f"第{ch}話の原文。\n")


def write_sidecar(d: str, ch: int, status: str, incomplete: list[int],
                  translated_at: str) -> None:
    i = ch - 1
    with open(os.path.join(d, "chapters", f"{i:04d}.meta.json"), "w",
              encoding="utf-8") as f:
        json.dump({
            "schema_version": 1, "status": status,
            "source_sha256": hashlib.sha256(
                open(os.path.join(d, "raw", f"{i:04d}.txt"), "rb").read()
            ).hexdigest(),
            "content_sha256": hashlib.sha256(
                open(os.path.join(d, "chapters", f"{i:04d}.txt"), "rb").read()
            ).hexdigest(),
            "translation_config_hash": hashlib.sha256(b"test").hexdigest(),
            "model_provider": "test", "model_role": "translate",
            "model_id": "test", "prompt_version": "v1",
            "translated_at": translated_at,
            "tokens": {"input": 0, "output": 0},
            "cost": {"amount": 0, "currency": "CNY", "estimated": True},
            "incomplete_paragraphs": incomplete,
            **({"incomplete_reason": "provider_incomplete"}
               if status == "partial" else {}),
        }, f, ensure_ascii=False)


def main() -> int:
    print("EPUB 导出：")
    _d = write_book(_ROOT, SLUG, [1, 2, 4])     # 第 3 章缺译：必须被跳过（[1,2,4] 是 3 章）
    # 第 1 章有完整 sidecar（提供 dcterms:modified 的真实来源）
    write_sidecar(_d, 1, "complete", [], "2026-10-21T12:34:56Z")
    # 第 5 章是 partial：可读，但正文里有回填的日文原文 → EPUB 不许收
    add_chapter(_d, 5)
    write_sidecar(_d, 5, "partial", [1], "2026-10-22T00:00:00Z")
    out = os.path.join(tempfile.mkdtemp(prefix="epub-"), "t.epub")
    path, info = ep.build(SLUG, out)
    check("能生成 .epub", os.path.exists(path) and info["bytes"] > 0, str(info["bytes"]))
    check("只收已译章（本书译了 1/2/4 章 → 3 章）", info["chapters"] == 3,
          f"{info['chapters']} 章")

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        first = z.infolist()[0]
        check("★ mimetype 是第一个条目（OCF 硬要求）", first.filename == "mimetype")
        check("★ mimetype 不压缩（压缩了部分阅读器拒收）",
              first.compress_type == zipfile.ZIP_STORED)
        check("mimetype 内容正确",
              z.read("mimetype") == b"application/epub+zip")
        check("container.xml 指向 OEBPS/content.opf",
              b"OEBPS/content.opf" in z.read("META-INF/container.xml"))
        check("有 nav.xhtml 与 toc.ncx（新老阅读器都认）",
              "OEBPS/nav.xhtml" in names and "OEBPS/toc.ncx" in names)

        # 所有 XML 必须能解析 —— 手写 XML 最容易漏转义
        xmls = [n for n in names if n.endswith((".opf", ".xhtml", ".ncx", ".xml"))]
        bad = []
        for n in xmls:
            try:
                ET.fromstring(z.read(n))
            except ET.ParseError as e:
                bad.append(f"{n}: {e}")
        check(f"★ 全部 {len(xmls)} 个 XML 能解析（转义没漏）", not bad,
              "; ".join(bad[:2]))

        # spine 顺序 = 章序，且每章文件真的存在
        opf = z.read("OEBPS/content.opf").decode()
        order = re.findall(r'<itemref idref="([^"]+)"/>', opf)
        manifest = dict(re.findall(
            r'<item id="([^"]+)" href="([^"]+)"', opf))
        # 先确认 idref 真的能在 manifest 里找到：这里**不许**用 `if i in manifest`
        # 过滤掉找不到的 —— 那会把"spine 指向不存在的 id"（整本书空白）变成假绿。
        check("★ spine 的每个 idref 都能在 manifest 里找到",
              bool(order) and all(i in manifest for i in order),
              f"找不到：{[i for i in order if i not in manifest][:3]}")
        hrefs = [manifest.get(i, "?") for i in order]
        check("spine 顺序 = 章序",
              hrefs == ["text/ch0001.xhtml", "text/ch0002.xhtml",
                        "text/ch0003.xhtml"], str(hrefs))
        check("spine 引用的文件都存在",
              all(("OEBPS/" + h) in names for h in hrefs))
        allt = "".join(z.read(n).decode() for n in names
                       if n.startswith("OEBPS/text/"))
        check("缺译的第 3 章正文没有被塞进书里（内容级，不是文件名）",
              "第3章第一段" not in allt)
        check("partial 第 5 章（夹日文原文）不许进 EPUB",
              "第5章第一段" not in allt)
        check("dcterms:modified 用实际翻译时间，不再硬编码 2026-01-01",
              "2026-10-21T12:34:56Z" in opf
              and "2026-01-01T00:00:00Z" not in opf)
        check("OPF 的 item id 是 NCName（不能是文件路径）",
              all(not i.startswith("text/") for i in manifest), str(list(manifest)[:3]))

        # 目录链接都指向真实文件
        nav = z.read("OEBPS/nav.xhtml").decode()
        links = re.findall(r'href="(text/[^"]+)"', nav)
        check("目录里每个链接都真实存在",
              links and all(("OEBPS/" + x) in names for x in links), str(links))

        # 正文内容：中文在、引号在、HTML 特殊字符被转义
        ch1 = z.read("OEBPS/text/ch0001.xhtml").decode()
        check("正文含第 1 章中文段落", "第1章第一段" in ch1)
        check("引号原样保留（不重排）", "「引号」保留" in ch1)
        check("★ < > & 被转义（不能变真标签）",
              "&lt;标签&gt;" in ch1 and "&amp; 符号" in ch1
              and "<标签>" not in ch1)
        check("日文原名作为小字副标题保留", "第1話" in ch1)
        check("标题用中文名", "测试作品" in opf)
        check("语言标成 zh-CN", "zh-CN" in opf)

    # identifier 必须稳定：同一本书两次导出 → 同一个 id
    path2 = path + ".2"
    _, info2 = ep.build(SLUG, path2)
    check("★ identifier 稳定（两次导出同一个，阅读器才认成同一本）",
          info["identifier"] == info2["identifier"], info["identifier"])

    # 没有译文时：明确报错，不许生成空书
    write_book(_ROOT, SLUG + "2", [], total=2)
    try:
        ep.build(SLUG + "2", path + ".3")
        ok = False
    except ValueError:
        ok = True
    check("没有译文时拒绝导出（不生成空壳）", ok)

    # ---------- HTTP 层 ----------
    # 服务读的是**它自己的数据根**（LNTRANS_SERVER_ROOT），不是本进程的
    # LNTRANS_DATA_ROOT —— 所以 fixture 必须写进服务那份，否则 404 = 假红。
    sroot = os.environ.get("LNTRANS_SERVER_ROOT") or ""
    if sroot:
        write_book(sroot, SLUG + "_http", [1, 2])
    if BASE:
        url = BASE.rstrip("/") + f"/export/{SLUG}_http.epub"
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                status, body = r.status, r.read()
                ctype = r.headers.get("Content-Type", "")
                disp = r.headers.get("Content-Disposition", "")
        except urllib.error.HTTPError as e:
            status, body, ctype, disp = e.code, e.read(), "", ""
        check("HTTP /export/<slug>.epub 返回 200", status == 200, f"status={status}")
        check("Content-Type 是 application/epub+zip", "epub+zip" in ctype, ctype)
        check("是附件下载，文件名带书名（RFC 5987）",
              "attachment" in disp and "filename*=" in disp, disp[:60])
        check("下载到的确实是 zip（PK 开头）", body[:2] == b"PK")
    else:
        print("  ⚠ HTTP 层跳过（没有隔离测试服务）")

    print()
    ok = not fails
    print("回归结果：", "全部通过 ✅" if ok else f"仍有失败 ❌ {fails}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
