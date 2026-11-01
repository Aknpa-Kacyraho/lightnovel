"""把本地 EPUB / TXT 导入成一部可翻译的作品。

为什么需要它：书架原来只能从源站（kakuyomu / 成为小说家）建书，用户手里
已经买到的日文 EPUB、或者别处下载的 TXT 根本进不来。导入后复用同一条
翻译管线（分段、术语、校验、二分、阅读页），不需要第二套实现。

零依赖：EPUB 就是 zip + XML + XHTML，全部用标准库解析。
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import time
import zipfile
from html.parser import HTMLParser


class ImportError_(ValueError):
    """导入失败（文件格式/编码/内容问题），文案直接给用户看。"""


# ---------------------------------------------------------------- EPUB 解析

_KANA = re.compile(r"[\u3040-\u30ff]")
_HIRA = re.compile(r"[\u3040-\u309f]")
_KATA_FULL = re.compile(r"[\u30a0-\u30ff]")
_KATA_HALF = re.compile(r"[\uff61-\uff9f]")
_KANJI = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# 高频汉字：用来把「GBK 被当成 cp932/euc_jp 解出来的假汉字」压下去。
_CN_COMMON = set("的了是在不我你他她它这那们有和就都而及与之其所以因为一个没有什么可以自己")
_HEAD_TAGS = {"h1", "h2", "h3"}
_BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "td", "blockquote", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "pre",
}
# rt/rp 是 ruby 注音（假名）。不剥掉的话正文会变成「亜里沙アリサ」——
# 源站抓取那边已经明确剥掉（见 references/backend.md），导入必须同样处理。
_SKIP_TAGS = {"script", "style", "head", "nav", "svg", "rt", "rp"}


class _Blocks(HTMLParser):
    """把 XHTML 拆成 (标签, 文本) 块；块之间天然就是段落边界。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self.title = ""
        self._buf: list[str] = []
        self._cur = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
            return
        if tag in _SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in _BLOCK_TAGS:
            self._flush()
            if tag != "br":
                self._cur = tag

    def handle_startendtag(self, tag, attrs):
        # <br/> / <img/> 这类自闭合：只当分隔。
        if tag.lower() in ("br",):
            self._flush()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
            return
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in _BLOCK_TAGS:
            self._flush()
            self._cur = ""

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self._buf.append(data)

    def _flush(self):
        text = re.sub(r"[ \t\r\f\v]+", " ", "".join(self._buf)).strip()
        if text:
            self.blocks.append((self._cur or "p", text))
        self._buf = []

    def close(self):
        super().close()
        self._flush()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_root(data: bytes):
    import xml.etree.ElementTree as ET
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise ImportError_(f"EPUB 里的 XML 解析失败：{e}") from e


def _text_of(root, name: str) -> str:
    for el in root.iter():
        if _local(el.tag) == name:
            return (el.text or "").strip()
    return ""


def _zip_names(zf: zipfile.ZipFile) -> dict[str, str]:
    """小写名 → 真实名：EPUB 里 href 大小写和 zip 条目常常不一致。"""
    return {n.lower(): n for n in zf.namelist()}


def _read_member(zf: zipfile.ZipFile, names: dict[str, str], path: str) -> bytes:
    real = names.get(path.lower())
    if real is None:
        raise ImportError_(f"EPUB 缺文件：{path}")
    try:
        size = zf.getinfo(real).file_size
    except KeyError:
        size = 0
    if size > 32 * 1024 * 1024:
        # 单文件解压超过 32MB：正常章节不可能这么大，按异常输入处理。
        raise ImportError_(f"EPUB 里的文件过大：{path}")
    return zf.read(real)


def _resolve(base_dir: str, href: str) -> str:
    import urllib.parse
    href = (href or "").replace("\\", "/")
    # manifest 的 href 允许带锚点/查询串（`ch1.xhtml#part1`）。不剥掉的话
    # 后面按 `.xhtml` 后缀判断时会整章跳过，而且**不报错**。
    # 先剥再 unquote：文件名里合法编码的 `%23` 不该被当成锚点。
    href = href.split("#", 1)[0].split("?", 1)[0].strip()
    href = urllib.parse.unquote(href)
    if not href:
        raise ImportError_("EPUB 内的路径为空")
    if href.startswith("/"):
        # 少数非标准 EPUB 用根相对路径；宽容处理，别因此整本导入失败。
        p = posixpath.normpath(href.lstrip("/"))
    else:
        p = posixpath.normpath(posixpath.join(base_dir, href))
    if p.startswith("../") or p == ".." or p.startswith("/"):
        raise ImportError_("EPUB 内的路径不合法")
    return p


def _decode_score(text: str) -> float:
    """给一种解码结果打分：假名是「这是日文」的最强证据。

    半角片假名（`ﾕ簗ﾇﾖ…`）几乎只会在 **GBK 文本被 cp932 解码**时出现，
    所以重罚；常用汉字加分用来区分「正确的 gb18030」和「被 euc_jp 解歪的
    假汉字」。只按「谁先不报错」选编码会把中文 TXT 变成乱码。
    """
    hira = len(_HIRA.findall(text))
    kata = len(_KATA_FULL.findall(text))
    half = len(_KATA_HALF.findall(text))
    kanji = len(_KANJI.findall(text))
    common = sum(text.count(ch) for ch in _CN_COMMON)
    return hira * 6 + kata * 3 - half * 6 + kanji * 0.2 + common * 1.2


def _decode(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    best: tuple[float, int, str] | None = None
    cp932_text = ""
    for order, enc in enumerate(("cp932", "euc_jp", "gb18030")):
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        if enc == "cp932":
            cp932_text = text
        cand = (_decode_score(text), -order, text)
        if best is None or cand[0] > best[0] or (
                cand[0] == best[0] and cand[1] > best[1]):
            best = cand
    # 真正的半角片假名文件（老 TXT 常见）解出来只有半角假名和 ASCII，
    # 没有汉字/平假名/全角片假名。GBK 被 cp932 解坏时一定夹着假汉字，
    # 用它把这两种情况分开，别把半角日文误判成中文。
    if (cp932_text and _KATA_HALF.search(cp932_text)
            and not _KANJI.search(cp932_text)
            and not _HIRA.search(cp932_text)
            and not _KATA_FULL.search(cp932_text)):
        return cp932_text
    if best is not None:
        return best[2]
    return data.decode("utf-8", errors="replace")


def parse_epub(data: bytes) -> tuple[str, str, list[tuple[str, str]]]:
    """返回 (书名, 作者, [(章节名, 正文)])。"""
    import io
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ImportError_(f"不是有效的 EPUB（zip 打不开）：{e}") from e
    with zf:
        names = _zip_names(zf)
        try:
            container = _xml_root(_read_member(
                zf, names, "META-INF/container.xml"))
        except ImportError_:
            opfs = [n for n in zf.namelist() if n.lower().endswith(".opf")]
            if not opfs:
                raise ImportError_("EPUB 里找不到 .opf（不是标准 EPUB？）")
            opf_path = opfs[0]
        else:
            opf_path = ""
            for el in container.iter():
                if _local(el.tag) == "rootfile":
                    opf_path = (el.attrib.get("full-path") or "").strip()
                    if opf_path:
                        break
            if not opf_path:
                raise ImportError_("EPUB 的 container.xml 没有 rootfile")

        opf = _xml_root(_read_member(zf, names, opf_path))
        base_dir = posixpath.dirname(opf_path)
        book_title = _text_of(opf, "title")
        author = _text_of(opf, "creator")

        manifest: dict[str, str] = {}
        media: dict[str, str] = {}
        for el in opf.iter():
            if _local(el.tag) == "item":
                iid = el.attrib.get("id") or ""
                href = el.attrib.get("href") or ""
                if iid and href:
                    manifest[iid] = _resolve(base_dir, href)
                    media[iid] = (el.attrib.get("media-type") or "").lower()
        spine: list[str] = []
        for el in opf.iter():
            if _local(el.tag) == "itemref":
                iid = el.attrib.get("idref") or ""
                if iid in manifest:
                    spine.append(iid)
        if not spine:
            spine = [i for i in manifest
                     if media.get(i, "").endswith(("html", "xml"))
                     or manifest[i].lower().endswith((".xhtml", ".html", ".htm"))]

        chapters: list[tuple[str, str]] = []
        total_bytes = 0
        for iid in spine:
            path = manifest[iid]
            if not path.lower().endswith((".xhtml", ".html", ".htm")):
                continue
            if path.lower() not in names:
                continue          # 引用了不存在的文件：跳过这一章，不毁整本
            blob = _read_member(zf, names, path)
            total_bytes += len(blob)
            if total_bytes > 80 * 1024 * 1024:
                raise ImportError_("EPUB 解压后过大（超过 80MB），不是单本小说？")
            raw = _decode(blob)
            parser = _Blocks()
            try:
                parser.feed(raw)
                parser.close()
            except Exception:  # noqa: BLE001 - 单个坏文件不该毁整本
                continue
            doc_title = (parser.title or "").strip()
            for title, body in _sections(parser.blocks, doc_title):
                if not body:
                    continue
                if (not title) or (book_title and title == book_title):
                    title = f"第{len(chapters) + 1}话"
                chapters.append((title, "\n\n".join(body)))
        if not chapters:
            raise ImportError_("EPUB 里没有可读的正文（可能只有图片）")
        return (book_title.strip(), author.strip(), chapters)


def _sections(blocks: list[tuple[str, str]], doc_title: str
              ) -> list[tuple[str, list[str]]]:
    """一篇 XHTML 可能只有一章，也可能把整本塞进一个文件。

    有 ≥2 个 h1/h2/h3 且正文够长时，按标题切章；否则整篇算一章。
    """
    total = sum(len(t) for _k, t in blocks)
    heads = [(i, t) for i, (k, t) in enumerate(blocks) if k in _HEAD_TAGS]
    if len(heads) >= 2 and total > 1200:
        out = []
        for j, (idx, text) in enumerate(heads):
            end = heads[j + 1][0] if j + 1 < len(heads) else len(blocks)
            body = [t for k, t in blocks[idx + 1:end] if k not in _HEAD_TAGS]
            if body:
                out.append((text, body))
        if out:
            return out
    body = [t for k, t in blocks if k not in _HEAD_TAGS]
    title = heads[0][1] if heads else doc_title
    return [(title, body)]


# ---------------------------------------------------------------- TXT 解析

_HEAD_LINE = re.compile(
    r"^\s*(?P<title>"
    r"(?:第\s*[0-9０-９一二三四五六七八九十百千零〇]+\s*[話话章節节部篇巻卷])"
    r"|(?:プロローグ|エピローグ|序章|終章|幕間|閑話|外伝|あとがき|後書き)"
    r"|(?:Chapter|CHAPTER)\s+\d+"
    r")(?:[\s　:：\-—].*)?\s*$"
)


def _looks_like_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 80:
        return False
    if s[-1] in "。！？!?…」』）)":
        return False
    return bool(_HEAD_LINE.match(s))


def split_txt_chapters(text: str) -> list[tuple[str, str]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    starts = [i for i, ln in enumerate(lines) if _looks_like_heading(ln)]
    if not starts:
        body = "\n".join(lines).strip()
        return [("", body)] if body else []
    out: list[tuple[str, str]] = []
    pre = "\n".join(lines[:starts[0]]).strip()
    # 第一个标题前的文字**不能按长度决定丢不丢**：短前言、作者的话也是正文。
    # 以前 <200 字直接消失（导入成功、内容少了一截，最难查）。
    if pre:
        out.append(("序", pre))
    for j, i in enumerate(starts):
        end = starts[j + 1] if j + 1 < len(starts) else len(lines)
        body = "\n".join(lines[i + 1:end]).strip()
        if body:
            out.append((lines[i].strip(), body))
    return out


_LONG_LINE = 3000       # 单行超过它就必须切开，否则整章会变成一个巨型段落
_SPLIT_TARGET = 1200    # 切开后每段的目标长度


def _split_long_line(text: str, limit: int = _SPLIT_TARGET) -> list[str]:
    """把超长单行按句末标点切成若干段。

    翻译管线的分段只能按「行」切，`split_paragraphs()` 还会把连续非空行合并；
    一个 2 万字的段落既超出单 chunk 上限，又因为只有 1 段而无法二分降级。
    优先在句末切，实在没有标点才硬切（硬切也比整章失败好）。
    """
    if len(text) <= limit * 2:
        return [text]
    parts: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if len(buf) >= limit and (
                ch in "。！？!?…」』" or len(buf) >= limit * 2):
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    return parts


def _normalize_txt_body(body: str) -> str:
    """让 TXT 正文符合管线对「段落」的约定。

    有空白行时保持原结构（空行 = 段落边界）；整章没有空行时把**每一行当成
    一段**，否则 `split_paragraphs()` 会把它们全并成一段 → 无法翻译。
    """
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    has_blank = any(not ln.strip() for ln in lines)
    out: list[str] = []
    for ln in lines:
        if len(ln) > _LONG_LINE:
            for chunk in _split_long_line(ln):
                out.append(chunk)
                out.append("")          # 切开处补空行，防止又被合并
        else:
            out.append(ln)
    if has_blank:
        return "\n".join(out)
    return "\n\n".join(x.strip() for x in out if x.strip())


def parse_txt(data: bytes, filename: str) -> tuple[str, str, list[tuple[str, str]]]:
    text = _decode(data)
    chapters = split_txt_chapters(text)
    if not chapters:
        raise ImportError_("TXT 是空的")
    title = os.path.splitext(os.path.basename(filename))[0].strip() or "本地小说"
    fixed = []
    for i, (t, body) in enumerate(chapters):
        fixed.append((t or f"第{i + 1}话", _normalize_txt_body(body)))
    return title, "", fixed


# ---------------------------------------------------------------- 建书

def sniff_format(filename: str, data: bytes) -> str:
    if data[:4] == b"PK\x03\x04":
        return "epub"
    if filename.lower().endswith(".epub"):
        return "epub"
    return "txt"





def _safe_meta(book_dir: str) -> dict:
    try:
        with open(os.path.join(book_dir, "meta.json"), encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _existing_by_source_id(novels_dir: str, source_id: str):
    try:
        names = os.listdir(novels_dir)
    except OSError:
        return ""
    for name in names:
        if name.startswith("."):
            continue
        try:
            with open(os.path.join(novels_dir, name, "meta.json"),
                      encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if str(meta.get("source_id") or "") == source_id:
            return name
    return ""


def import_bytes(data: bytes, filename: str, *, lt=None,
                 title: str = "", author: str = "", slug: str = "",
                 novels_dir: str = "", progress=None) -> dict:
    """把文件内容建成一部作品；返回 {slug, title, author, chapters, created}。

    已导入过（文件 sha256 相同）时不重复建书，返回原来的 slug。
    """
    if not data:
        raise ImportError_("文件是空的")
    if lt is None:
        import lntrans as lt  # noqa: PLC0415 - 避免循环导入
    novels_dir = novels_dir or lt.NOVELS_DIR
    fmt = sniff_format(filename, data)
    digest = hashlib.sha256(data).hexdigest()
    source_id = "local-" + digest[:16]

    existed = _existing_by_source_id(novels_dir, source_id)
    if existed:
        meta = lt.load_meta(existed)
        return {"slug": existed, "title": meta.get("title") or existed,
                "author": meta.get("author") or "",
                "chapters": len(meta.get("episodes") or []),
                "created": False}

    if progress:
        progress(0.12)
    if fmt == "epub":
        book_title, book_author, chapters = parse_epub(data)
    else:
        book_title, book_author, chapters = parse_txt(data, filename)
    if progress:
        progress(0.42)
    book_title = (title or book_title or
                  os.path.splitext(os.path.basename(filename))[0]).strip()
    book_author = (author or book_author or "").strip()
    if not chapters:
        raise ImportError_("没有解析出任何章节")
    if len(chapters) > 5000:
        raise ImportError_(f"章节太多（{len(chapters)}），不是单本小说？")

    slug = (slug or "").strip()
    if not slug:
        _aliases = lt.lncatalog.load_aliases(
            os.path.join(os.path.dirname(novels_dir), "data", "library.json"))
        slug = lt.lncatalog.choose_slug(
            lt.lncatalog.new_local_id(), _aliases)
        n = 2
        while os.path.isdir(os.path.join(novels_dir, slug)):
            slug = lt.lncatalog.choose_slug(
                f"{lt.lncatalog.new_local_id()}-{n}", _aliases)
            n += 1
    d = os.path.join(novels_dir, slug)
    if os.path.isdir(d) and _safe_meta(d).get("source_id") not in ("", source_id):
        raise ImportError_(f"slug「{slug}」已被另一部作品占用，换一个 --slug")
    os.makedirs(os.path.join(d, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(d, "raw"), exist_ok=True)

    meta = {
        "id": slug,
        "slug": slug,
        "source": "local",
        "source_id": source_id,
        "content_hash": digest,
        "hash_scheme": "file_sha256_v1",
        "url": "",
        "title": book_title,
        "author": book_author or "不明",
        "file_name": os.path.basename(filename),
        "format": fmt,
        "sha256": digest,
        "episodes": [{"id": f"{i + 1:04d}", "title": t}
                     for i, (t, _body) in enumerate(chapters)],
        "glossary": {},
        "characters": {},
        "summaries": {},
        "style": {},
        "progress": {"translated_through": 0,
                     "fetched_through": len(chapters)},
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    # 已经是中文（没有假名）的书名/章节名直接当译文，别再花 token 翻一遍，
    # 也避免模型把用户自己定的书名改掉。
    zh_titles = {}
    if book_title and not _KANA.search(book_title):
        zh_titles["book"] = book_title
    for i, (chap_title, _body) in enumerate(chapters):
        if chap_title and not _KANA.search(chap_title):
            zh_titles[str(i + 1)] = chap_title
    if zh_titles:
        meta["zh_titles"] = zh_titles
    # 先写原文、最后写 meta：中途失败不会留下“看得见但没正文”的半本书。
    # `.import.json` 是断点：只跳过「文件真的存在且非空」的章，重试不会重写
    # 已完成的前缀；schema 不兼容则从头导入，但旧文件保留。
    total = max(1, len(chapters))
    checkpoint_path = os.path.join(d, ".import.json")
    start_i = 0
    try:
        with open(checkpoint_path, encoding="utf-8") as f:
            cp = json.load(f)
        if (int(cp.get("schema_version") or 0) == 1
                and cp.get("sha256") == digest
                and int(cp.get("chapters_total") or 0) == len(chapters)):
            done = max(0, min(len(chapters), int(cp.get("chapters_done") or 0)))
            if all(os.path.getsize(os.path.join(d, "raw", f"{j:04d}.txt")) > 0
                   for j in range(done)):
                start_i = done
    except (OSError, ValueError, TypeError):
        start_i = 0
    checkpoint = {"schema_version": 1, "sha256": digest,
                  "filename": os.path.basename(filename),
                  "chapters_total": len(chapters),
                  "chapters_done": start_i, "state": "importing"}
    lt.save_json(checkpoint_path, checkpoint)
    zh_ready = 0
    for i, (_t, body) in enumerate(chapters):
        if i < start_i:
            continue
        lt.save_text(os.path.join(d, "raw", f"{i:04d}.txt"), body)
        # 本地中文/中日混合：假名极少时不再送翻译，直接把原文作为可读正文。
        # 纯日文章节仍走原来的翻译管线。
        if is_chinese_like(body):
            lt.save_text(os.path.join(d, "chapters", f"{i:04d}.txt"), body)
            zh_ready += 1
        checkpoint["chapters_done"] = i + 1
        lt.save_json(checkpoint_path, checkpoint)
        if progress:
            progress(0.45 + 0.5 * (i + 1) / total)
    lt.save_meta(slug, meta)
    checkpoint.update({"state": "done", "chapters_done": len(chapters)})
    lt.save_json(checkpoint_path, checkpoint)
    return {"slug": slug, "title": book_title,
            "author": meta["author"], "chapters": len(chapters),
            "chinese_chapters": zh_ready, "created": True}

def is_chinese_like(text: str) -> bool:
    """Pure Chinese or Chinese with only a few kana names -> no translation."""
    kana = len(_KANA.findall(text or ""))
    cjk = len(_KANJI.findall(text or ""))
    return cjk >= 20 and (kana == 0 or kana / max(1, cjk) < 0.01)


def backfill_chinese(novels_dir: str = "", *, write: bool = False) -> dict:
    """Mark already-imported local Chinese chapters as readable (no LLM)."""
    import lntrans as lt  # noqa: PLC0415
    root = novels_dir or lt.NOVELS_DIR
    scanned = copied = books = 0
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        d = os.path.join(root, name)
        meta = _safe_meta(d)
        if not meta or str(meta.get("source") or "") != "local":
            continue
        raw_dir = os.path.join(d, "raw")
        zh_dir = os.path.join(d, "chapters")
        if not os.path.isdir(raw_dir):
            continue
        changed = False
        for fn in sorted(os.listdir(raw_dir)):
            if not fn.endswith(".txt"):
                continue
            try:
                body = open(os.path.join(raw_dir, fn), encoding="utf-8").read()
            except OSError:
                continue
            scanned += 1
            if not is_chinese_like(body):
                continue
            target = os.path.join(zh_dir, fn)
            if os.path.exists(target) and os.path.getsize(target) > 0:
                continue
            if write:
                lt.save_text(target, body)
                changed = True
            copied += 1
        if changed:
            books += 1
    return {"scanned": scanned, "copied": copied, "books": books,
            "write": write}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="本地中文章回填（默认干跑）")
    ap.add_argument("--novels", default="")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    print(backfill_chinese(a.novels, write=a.write))
