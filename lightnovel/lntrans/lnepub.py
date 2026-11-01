#!/usr/bin/env python3
"""lnepub —— 把一部已译作品打包成 EPUB 3。

为什么值得做：Markdown 只能在本站读，**带不走**。EPUB 是"这本书属于读者"的
最小证明：能塞进任何阅读器、能离线、能进手机自带的书架，也不依赖这个容器活着。

设计取舍：

* **只放译文**，不放日文对照。EPUB 是"拿去读"的形态，不是校对工具；
  日中并排会让行高翻倍，且读者不读日文。
* **只收已译章**，缺译的章不生成空壳 —— 阅读器里突然出现一章"（未译）"
  比少一章更让人困惑。
* **标准库实现**（zipfile + 手写 XML），不引第三方依赖：这个项目从第一天起
  就只依赖 Python 标准库，包在别人机器上要能直接跑。
* mimetype 必须是**第一个条目且不压缩**，否则部分阅读器拒收（EPUB OCF 规范）。
* 标识符用 `uuid5(来源+源站 id)`：同一本书重复导出得到同一个 identifier，
  阅读器才会认成"同一本"而不是两本。
"""

from __future__ import annotations

import html
import json
import os
import sys
import time
import uuid
import zipfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lndata  # noqa: E402
import lncontracts  # noqa: E402
import lndedupe  # noqa: E402

LAYOUT = lndata.resolve_layout()
lndata.apply_environment(LAYOUT)
ROOT = LAYOUT.data_root
NOVELS = os.path.join(ROOT, "novels")

CSS = """@charset "utf-8";
body{font-family:serif;line-height:1.8;margin:1.2em;color:#1f1d1a;background:#f7f5f0}
h1,h2{font-family:sans-serif;line-height:1.4}
h2{font-size:1.15em;margin:1.6em 0 .8em;border-bottom:1px solid #e3dfd6;padding-bottom:.4em}
p{margin:0 0 .9em;text-indent:2em}
p.blank{height:.9em;margin:0}
.meta{font-family:sans-serif;font-size:.8em;color:#6c6760;margin-bottom:1.4em}
"""


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def _attr(s: str) -> str:
    return html.escape(s or "", quote=True)


def _xhtml(title: str, body: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN" xml:lang="zh-CN">\n'
            f'<head><meta charset="utf-8"/><title>{esc(title)}</title>'
            '<link rel="stylesheet" type="text/css" href="../style.css"/></head>\n'
            f'<body>{body}</body></html>\n')


def chapters(slug: str) -> tuple[dict, list[tuple[int, str, str, list[str]]]]:
    """读出一部作品的 meta 与**已译**章节：[(章号, 标题, 日文标题, 段落)]。"""
    ndir = os.path.join(NOVELS, slug)
    with open(os.path.join(ndir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    eps = meta.get("episodes") or []
    zh_titles = meta.get("zh_titles") or {}
    out = []
    for i in range(len(eps)):
        p = os.path.join(ndir, "chapters", f"{i:04d}.txt")
        rp = os.path.join(ndir, "raw", f"{i:04d}.txt")
        mp = os.path.join(ndir, "chapters", f"{i:04d}.meta.json")
        # 导出契约是“完整”，不是“可读”：partial 章里回填了日文原文，
        # 阅读页有折叠提示，EPUB 没有，混进去读者只会看到夹生日文。
        if not lncontracts.translation_paths_complete(p, rp, mp):
            continue
        text = open(p, encoding="utf-8").read()
        raw = open(rp, encoding="utf-8").read() if os.path.exists(rp) else ""
        text = lndedupe.dedupe_repeated_output(text, raw)
        paras = [x.strip() for x in text.split("\n")]
        title = (zh_titles.get(str(i + 1)) or (eps[i].get("title") if i < len(eps) else "")
                 or f"第{i + 1}章")
        jp = eps[i].get("title") if i < len(eps) else ""
        out.append((i + 1, title, jp, paras))
    return meta, out


def _epub_time(value: str) -> str:
    """把 sidecar 的本地时间（`...+0800`）规范成 EPUB 要求的 UTC `...Z`。"""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _latest_modified(slug: str, chs: list[tuple[int, str, str, list[str]]]) -> str:
    """取本次导出章节里最晚的翻译时间；没有 sidecar（v4 legacy）才用当前时间。"""
    latest = ""
    ndir = os.path.join(NOVELS, slug, "chapters")
    for num, _title, _jp, _paras in chs:
        try:
            with open(os.path.join(ndir, f"{num - 1:04d}.meta.json"),
                      encoding="utf-8") as f:
                at = _epub_time(str((json.load(f) or {}).get("translated_at") or ""))
        except (OSError, json.JSONDecodeError, AttributeError):
            at = ""
        if at > latest:
            latest = at
    return latest or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build(slug: str, out: str | None = None) -> tuple[str, dict]:
    """生成 EPUB，返回 (路径, 统计)。没有译文就抛 ValueError。"""
    meta, chs = chapters(slug)
    if not chs:
        raise ValueError("这本书还没有译文，无法导出 EPUB")
    title = (meta.get("zh_titles") or {}).get("book") or meta.get("title") or slug
    author = meta.get("author") or ""
    ident = "urn:uuid:" + str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"lntrans:{meta.get('source')}:{meta.get('source_id') or slug}"))
    if not out:
        safe = "".join(c for c in slug if c.isalnum() or c in "._-") or "book"
        out = os.path.join(os.getcwd(), f"{safe}.epub")

    # 章节文件 ID 固定 ch0001 起：OPF/nav/spine 三处引用同一套名字。
    items, navlis, spine = [], [], []
    for n, (num, ctitle, jp, paras) in enumerate(chs, 1):
        fid = f"ch{n:04d}"
        body = [f'<h2>{esc(ctitle)}</h2>']
        if jp and jp != ctitle:
            body.append(f'<p class="meta">{esc(jp)}</p>')
        for para in paras:
            if para == "":
                body.append('<p class="blank"></p>')
            else:
                body.append(f"<p>{esc(para)}</p>")
        items.append((f"text/{fid}.xhtml", fid,
                      _xhtml(ctitle, "\n".join(body))))
        navlis.append(f'<li><a href="text/{fid}.xhtml">{esc(ctitle)}</a></li>')
        spine.append(fid)

    nav = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<!DOCTYPE html>\n'
           '<html xmlns="http://www.w3.org/1999/xhtml" '
           'xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN" xml:lang="zh-CN">\n'
           f'<head><meta charset="utf-8"/><title>{esc(title)}</title></head><body>'
           '<nav epub:type="toc" id="toc"><h1>目录</h1><ol>'
           + "".join(navlis) + '</ol></nav></body></html>\n')

    ncx = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
           f'<head><meta name="dtb:uid" content="{_attr(ident)}"/>'
           f'<meta name="dtb:depth" content="1"/></head>'
           f'<docTitle><text>{esc(title)}</text></docTitle><navMap>'
           + "".join(
               f'<navPoint id="np{n}" playOrder="{n}"><navLabel>'
               f'<text>{esc(c[1])}</text></navLabel>'
               f'<content src="text/ch{n:04d}.xhtml"/></navPoint>'
               for n, c in enumerate(chs, 1))
           + '</navMap></ncx>\n')

    # id 必须是 XML NCName：用 ch0001 这类名字，**不能**用文件路径
    # （踩过：id 写成 "text/ch0001.xhtml" 时 OPF 能生成，spine 却找不到它，
    #  阅读器会把整本书当成空白 —— 这类错误不抛异常，只有结构测试抓得到）。
    manifest = "".join(
        f'<item id="{_attr(name)}" href="{_attr(href)}" '
        f'media-type="application/xhtml+xml"/>'
        for href, name, _ in items)
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           'unique-identifier="bookid" xml:lang="zh-CN">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'<dc:identifier id="bookid">{_attr(ident)}</dc:identifier>'
           f'<dc:title>{esc(title)}</dc:title>'
           f'<dc:creator>{esc(author)}</dc:creator>'
           '<dc:language>zh-CN</dc:language>'
           f'<dc:source>{_attr(meta.get("url") or "")}</dc:source>'
           '<dc:description>日文轻小说的中文按需翻译版本（机器翻译，仅供自用阅读）</dc:description>'
           f'<meta property="dcterms:modified">{_attr(_latest_modified(slug, chs))}</meta>'
           '</metadata><manifest>'
           '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
           'properties="nav"/>'
           '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
           '<item id="css" href="style.css" media-type="text/css"/>'
           + manifest +
           '</manifest><spine toc="ncx">'
           + "".join(f'<itemref idref="{fid}"/>' for fid in spine) +
           '</spine></package>\n')

    container = ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<container version="1.0" '
                 'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                 'media-type="application/oebps-package+xml"/></rootfiles></container>\n')

    tmp = out + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        # mimetype 必须第一个、且 STORED（OCF 规范；压缩了部分阅读器直接拒收）
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        z.writestr("OEBPS/toc.ncx", ncx)
        z.writestr("OEBPS/style.css", CSS)
        for href, _name, body in items:
            z.writestr("OEBPS/" + href, body)
    os.replace(tmp, out)
    return out, {"slug": slug, "title": title, "chapters": len(chs),
                 "bytes": os.path.getsize(out), "identifier": ident,
                 "path": out}


def main() -> int:
    import argparse
    import glob
    ap = argparse.ArgumentParser(description="把已译作品打包成 EPUB")
    ap.add_argument("slug", nargs="?", default="")
    ap.add_argument("-o", "--out", default="")
    ap.add_argument("--all", action="store_true", help="每部已译作品各导出一份")
    a = ap.parse_args()
    if a.all:
        ok = 0
        for d in sorted(glob.glob(os.path.join(NOVELS, "*"))):
            slug = os.path.basename(d)
            if not os.path.isdir(d) or slug.startswith("."):
                continue
            try:
                path, info = build(slug, os.path.join(os.getcwd(), f"{slug}.epub"))
            except (ValueError, OSError) as e:
                print(f"  {slug}: 跳过（{e}）")
                continue
            ok += 1
            print(f"  {slug}: {info['chapters']} 章 / {info['bytes'] / 1024:.0f} KB → {path}")
        print(f"完成：{ok} 本")
        return 0
    if not a.slug:
        ap.error("要么给 slug，要么 --all")
    path, info = build(a.slug, a.out or "")
    print(f"✅ {info['title']}：{info['chapters']} 章 / "
          f"{info['bytes'] / 1024:.0f} KB → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
