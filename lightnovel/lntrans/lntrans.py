#!/usr/bin/env python3
"""lntrans —— 按需、增量、带故事记忆的日文轻小说翻译器。

解决三个真实问题：

1. **token 不够，不能一次翻完**
   → 只在你要看的时候翻你要看的那几章（`prefetch N`），译文与进度落盘，
     下次接着翻。分段缓存保证已翻过的段落永不重复翻译。

2. **普通翻译不知道故事，专有名词前后不一致**
   → 每部作品维护一份"故事记忆"：
     `glossary`（术语/人名对照）+ `characters`（人物）+ `summaries`（每章梗概）
     + `style`（说话风格/称谓）。翻译每一段时只注入**该段实际出现**的术语和
     相关人物，既准确又不爆 token。术语表刻意保持稳定后缀 → 命中 prompt cache。

3. **翻译质量要能进化**
   → `learn` 记录你的纠正（术语、风格），永久生效；
     `note` 记录逐条经验；每次纠正都写进 history，可回溯。

参考实现：auto-novel/auto-novel 的 packages/translator
（按行分段、每行加 #编号、术语表按需注入、段级缓存）。
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lndata  # noqa: E402
import lncontracts  # noqa: E402
import lncatalog  # noqa: E402
from lndedupe import dedupe_repeated_output as _dedupe_repeated_output  # noqa: E402

# 复用 lnfinder 的抓页/解析（syosetu 适配器也在那里），与 lnserve 同一份实现。
import importlib.util as _ilu  # noqa: E402
_spec_lib = _ilu.spec_from_file_location(
    "lnlib", os.path.join(os.path.dirname(HERE), "lnfinder", "lnlib.py"))
try:
    lnlib = _ilu.module_from_spec(_spec_lib)
    _spec_lib.loader.exec_module(lnlib)
except Exception:  # noqa: BLE001
    lnlib = None

# LNTRANS_HOME 使用 v5 代际数据根；未设置时仍兼容 v4 的
# LNTRANS_DATA_ROOT / 代码目录布局。自检继续通过后者隔离真实书架。
LAYOUT = lndata.resolve_layout()
lndata.apply_environment(LAYOUT)
_ROOT = LAYOUT.data_root
NOVELS_DIR = os.path.join(_ROOT, "novels")
import lnmodels  # noqa: E402

LLM_BASE = lnmodels.base_url()
CRED = os.path.expanduser(os.environ.get("LNTRANS_CRED")
                          or "~/.dsh/.credentials.yaml")
CRED_KEYS = ("LNTRANS_LLM_API_KEY", "DEEPSEEK_API_KEY",
             "DSHA_DEEPSEEK_OFFICIAL_API_KEY")
TRANSLATE_MODEL = lnmodels.model_for("translate")
AUX_MODEL = lnmodels.model_for("auxiliary")
REVIEW_MODEL = lnmodels.model_for("review")
SEG_MAX_CHARS = 1500      # 单段最大字符数（参考 auto-novel 默认）
# 单段最大段落数。小参数本地模型（7B 级）一次盯 60 个编号会漏段，重试又烧光
# 整章预算 —— 这类部署把它调小（如 20），用更多次请求换「每一段都对得上」。
SEG_MAX_LINES = int(os.environ.get("LNTRANS_SEG_LINES", "60") or 60)
PROMPT_VERSION = "ln-prompt-v5.0-20261021"

# ── Sakura-GalTransl 这类"句子级"模型有**自己的输入格式** ────────────────
# 它的 system 是固定的模型自述，user 只给「将下面的日文文本翻译成中文：{原文}」，
# 输出就是译文本身：没有编号、没有「每段一行」。把它塞进本项目的批量编号协议，
# 实测 20 行漏 7 行、60 行漏 28 行（模型按句子习惯把几行并成一句）——
# 所以给它单独一条路径：一次一段、原文直入、缓存也按段存。
SAKURA_SYSTEM = (
    "你是一个轻小说翻译模型，可以流畅通顺地以日本轻小说的风格将日文翻译成简体中文，"
    "并联系上下文正确使用人称代词，不擅自添加原文中没有的代词。"
)
SAKURA_USER_PREFIX = "将下面的日文文本翻译成中文："


CHAPTER_CHARS = int(os.environ.get("LNTRANS_CHAPTER_CHARS", "4000") or 4000)
# 云端大模型（DeepSeek）上下文 64k、输出给到 32k，一块可以大得多；
# 实测 3.8k 字一章整块毫无问题，留足余量按 6000 字切。
DEEPSEEK_CHAPTER_CHARS = int(
    os.environ.get("LNTRANS_DEEPSEEK_CHAPTER_CHARS", "6000") or 6000)


def build_chapter_prompt(meta: dict, block: str,
                        prev_context: str = "") -> tuple[str, list[str], str]:
    """通用"整章"格式（DeepSeek 这类通用对话模型用；Sakura 用自己的模板）。

    user 只放这一章原文；system 带作品设定/术语/前情，并明确要求保留段落与空行、
    只输出译文。这样一次请求译完一章，语义连贯，也不需要编号对齐。
    """
    used: list[str] = []
    hints: list[str] = []
    for jp, zh in (meta.get("glossary") or {}).items():
        if jp and zh and jp in block:
            hints.append(f"{jp}={zh}")
            used.append(jp)
    system = build_system_prompt(meta)
    if hints:
        system += (" 本章术语译名（必须照用）：" + "；".join(hints[:12]) + "。")
    if prev_context:
        system += (" 上一块的译文结尾（仅供衔接人称/语气，不要重复输出）："
                   + prev_context.replace("\n", " ")[-200:])
    system += (" 保留原文的段落与空行结构；只输出简体中文译文，不要编号、"
               "不要解释、不要输出原文。")
    return f"将下面的日文文本翻译成中文：\n{block}", used, system


def _block_ranges(paras: list[str], limit: int) -> list[tuple[int, int]]:
    """按字符预算把段落切成**连续整块**（默认整章一块）。

    为什么不再按段/按 60 行切：一段一段翻会丢上下文（人称、省略主语、
    对白归属全靠上文），读者一眼能看出"句子接不上"。Sakura 这类模型
    一次吃整章最自然。只有超长章节才在段落边界切成 2~3 块，块与块之间
    把上文尾巴塞进 system 续上下文。
    """
    out: list[tuple[int, int]] = []
    a = 0
    n = 0
    for i, para in enumerate(paras):
        ln = len(para) + 1
        if i > a and n + ln > limit:
            out.append((a, i))
            a = i
            n = 0
        n += ln
    if a < len(paras):
        out.append((a, len(paras)))
    return out


def translate_mode() -> str:
    """翻译协议：batch（默认，自己的 #N 编号批量）| sakura（模型自带单段格式）。"""
    return (os.environ.get("LNTRANS_TRANSLATE_MODE") or "").strip().lower()


def build_sakura_prompt(meta: dict, text: str,
                        prev_context: str = "") -> tuple[str, list[str], str]:
    """Sakura 格式：user 只放这一段原文；术语/上文塞进 system（不改它的 user 模板）。

    返回 (user_prompt, 注入的术语, system_prompt)。
    """
    used: list[str] = []
    hints: list[str] = []
    for jp, zh in (meta.get("glossary") or {}).items():
        if jp and zh and jp in text:
            hints.append(f"{jp}={zh}")
            used.append(jp)
    system = SAKURA_SYSTEM
    if hints:
        system += " 术语译名：" + "；".join(hints[:10]) + "。"
    if prev_context:
        system += (" 上文译文片段（仅供理解人称，不要重复输出）："
                   + prev_context.replace("\n", " ")[-160:])
    return f"{SAKURA_USER_PREFIX}{text}", used, system
_CHAPTER_RESULT = threading.local()
_CHAPTER_ROUTE = threading.local()


def die(msg: str) -> None:
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(1)


def api_key() -> str:
    """取 LLM key：环境变量优先，其次凭据文件。

    优先级：
      1. `LNTRANS_LLM_API_KEY`
      2. 兼容旧变量 `DEEPSEEK_API_KEY`
      3. `LNTRANS_CRED` 指向的凭据文件
      4. 默认凭据文件 `~/.dsh/.credentials.yaml`
    **key 绝不写进代码里**，也绝不出现在任何日志/输出中。
    """
    k = lnmodels.api_key()
    if k:
        return k
    die("找不到 API key。请设置 LNTRANS_LLM_API_KEY 或 DEEPSEEK_API_KEY，"
        f"或用 LNTRANS_CRED 指定凭据文件（当前找的是 {CRED}）；"
        "本地回环端点可不配 key；"
        "只想看分段结果可以加 --dry-run。")


# ------------------------------------------------------------------ 存储

def novel_dir(slug: str) -> str:
    return os.path.join(NOVELS_DIR, slug)


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".",
        suffix=".tmp",
        dir=os.path.dirname(path) or ".",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        # 写端显式失效：exFAT / sdcardfs 的 mtime 只有 2 秒精度，刚写的文件
        # 可能带着与旧版本完全相同的签名 —— 只靠 stat 比对会把新内容当成旧的。
        lncontracts.invalidate_file_hash(path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)


def save_text(path: str, text: str) -> None:
    """原子写文本文件：先写 .tmp 再 os.replace。

    踩过：译文/原文直接 open("w") 直写，进程中途被杀会留下半截文件，
    而 has_translation() 只判 size>0 → 截断的章节被永久当成"已译"跳过，
    静默丢内容。改成原子写后半截文件根本不会出现。
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".",
        suffix=".tmp",
        dir=os.path.dirname(path) or ".",
    )
    # newline="" prevents Windows from writing CRLF while the sidecar hash was
    # computed from the in-memory LF string.  A byte-level mismatch here would
    # make every new chapter look corrupt immediately after a successful write.
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        lncontracts.invalidate_file_hash(path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)


def load_meta(slug: str) -> dict:
    d = novel_dir(slug)
    if not os.path.isdir(d):
        die(f"作品不存在：{slug}（先跑 init）")
    return load_json(os.path.join(d, "meta.json"), {})


def save_meta(slug: str, meta: dict) -> None:
    save_json(os.path.join(novel_dir(slug), "meta.json"), meta)


def chapter_path(slug: str, idx: int, kind: str = "zh") -> str:
    sub = "chapters" if kind == "zh" else "raw"
    return os.path.join(novel_dir(slug), sub, f"{idx:04d}.txt")


def chapter_meta_path(slug: str, idx: int) -> str:
    return os.path.join(novel_dir(slug), "chapters", f"{idx:04d}.meta.json")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: str) -> str:
    """全文 SHA-256；委托契约层（带签名缓存，同一文件不重复读）。"""
    return lncontracts.file_sha256(path)


def _revision(value) -> str:
    raw = json.dumps(value or {}, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def glossary_fingerprint(glossary, raw_text: str) -> str:
    """这一章**真正用到**的术语指纹（只算原文里出现的条目）。

    学自 auto-novel 的 expired 判定：术语表整体变了不代表每章都过期。
    只把该章实际出现的术语算进来，改一个词不会让全书都亮「译名过时」。
    """
    hits = sorted(f"{k}\t{v}" for k, v in (glossary or {}).items()
                  if k and str(k) in (raw_text or ""))
    return hashlib.sha256("\n".join(hits).encode("utf-8")).hexdigest()[:32]


def chapter_glossary_revision(slug: str, idx: int, meta: dict | None = None) -> str:
    """按**当前**术语表算出的本章应有指纹（idx 为 0-based）。"""
    meta = meta if meta is not None else load_meta(slug)
    try:
        with open(chapter_path(slug, idx, "raw"), encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return ""
    return glossary_fingerprint(meta.get("glossary") or {}, raw)


def chapter_glossary_stale(slug: str, idx: int, meta: dict | None = None) -> bool:
    """这一章的译文是否是用**旧术语表**翻的（idx 为 0-based）。

    旧边车（没有 glossary_revision）一律返回 False：我们不知道它当时用了什么
    术语表，乱报「过时」会让整个书架全亮。新翻/刷新过的章节才有这个字段。
    """
    rec = load_chapter_meta(slug, idx)
    if not rec:
        return False
    old = str(rec.get("glossary_revision") or "")
    if not old:
        return False
    return old != chapter_glossary_revision(slug, idx, meta)


def model_provider() -> str:
    return lnmodels.provider()


def _estimated_cost(tokens_in: int, tokens_out: int,
                    provider_name: str | None = None) -> dict:
    return lnmodels.estimate_cost(
        tokens_in, tokens_out, "translate", provider_name=provider_name)


def job_identity(slug: str, chapters: list[int], meta: dict, args) -> dict:
    """Durable identity for a planned range.

    Before a chapter is fetched, its stable episode id/title identifies the
    source.  Once raw text exists, its SHA-256 replaces that placeholder and
    the identity is refreshed by the worker.
    """
    import lnjobs

    chapters = sorted(set(int(c) for c in chapters if int(c) >= 1))
    if not chapters:
        raise ValueError("任务没有目标章节")
    eps = meta.get("episodes") or []
    sources: list[dict] = []
    source_hashes: list[str] = []
    for ch in chapters:
        ep = eps[ch - 1] if ch - 1 < len(eps) else {}
        raw = chapter_path(slug, ch - 1, "raw")
        item = {"chapter": ch,
                "episode_id": str(ep.get("id") or ""),
                "title": str(ep.get("title") or "")}
        if os.path.isfile(raw) and os.path.getsize(raw) > 0:
            item["source_sha256"] = _sha256_file(raw)
        else:
            item["source_identity"] = _sha256_text(
                f"{ep.get('id') or ''}\n{ep.get('title') or ''}")
        source_hashes.append(item.get("source_sha256")
                             or item["source_identity"])
        sources.append(item)
    model_id = str(getattr(args, "model", "") or "unknown")
    revisions = {
        "glossary_revision": _revision(meta.get("glossary")),
        "characters_revision": _revision(meta.get("characters")),
        "style_revision": _revision(meta.get("style")),
    }
    cfg_hash = lnjobs.composite_config_hash(
        source_hashes=source_hashes,
        model_provider=model_provider(),
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        **revisions,
    )
    target = {"from_chapter": chapters[0], "to_chapter": chapters[-1]}
    return {
        "target": target,
        "chapters": chapters,
        "sources": sources,
        "model_provider": model_provider(),
        "model_role": "translate",
        "model_id": model_id,
        "translation_config_hash": cfg_hash,
        "idempotency_key": lnjobs.idempotency_key(
            slug=slug, target=target, sources=sources,
            translation_config_hash=cfg_hash),
    }


def chapter_meta_record(slug: str, idx: int, meta: dict, args, *,
                        text: str, raw_sha: str, tokens_in: int,
                        tokens_out: int, incomplete_paragraphs: list[int],
                        incomplete_reason: str | None = None,
                        provider_name: str | None = None,
                        model_id: str | None = None,
                        cost: dict | None = None) -> dict:
    content_sha = _sha256_text(text)
    provider_name = provider_name or model_provider()
    model_id = model_id or str(getattr(args, "model", "") or "unknown")
    cfg_hash = lncontracts.translation_config_hash(
        source_sha256=raw_sha,
        model_provider=provider_name,
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        glossary_revision=_revision(meta.get("glossary")),
        characters_revision=_revision(meta.get("characters")),
        style_revision=_revision(meta.get("style")),
    )
    try:
        with open(chapter_path(slug, idx, "raw"), encoding="utf-8") as f:
            raw_text = f.read()
    except OSError:
        raw_text = ""
    incomplete = sorted(set(int(x) for x in incomplete_paragraphs))
    rec = {
        "schema_version": lncontracts.CHAPTER_META_SCHEMA_VERSION,
        "status": "partial" if incomplete else "complete",
        "source_sha256": raw_sha,
        "content_sha256": content_sha,
        "translation_config_hash": cfg_hash,
        "model_provider": provider_name,
        "model_role": "translate",
        "model_id": model_id,
        "prompt_version": PROMPT_VERSION,
        "translated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tokens": {"input": int(tokens_in), "output": int(tokens_out)},
        "cost": cost or _estimated_cost(
            int(tokens_in), int(tokens_out), provider_name),
        "incomplete_paragraphs": incomplete,
        # 这一章实际用到的术语（按原文命中的条目算）。术语表改了以后，
        # 只有指纹变了的章节才提示「译名可能过时」。
        "glossary_revision": glossary_fingerprint(
            meta.get("glossary") or {}, raw_text),
    }
    if incomplete_reason:
        rec["incomplete_reason"] = incomplete_reason
    return lncontracts.validate_chapter_meta(rec)


def load_chapter_meta(slug: str, idx: int) -> dict | None:
    path = chapter_meta_path(slug, idx)
    if not os.path.isfile(path):
        return None
    try:
        return lncontracts.load_record(path, "chapter_meta")
    except (lncontracts.ContractError, OSError):
        return None


def refresh_chapter_meta(slug: str, idx: int, story_meta: dict | None = None,
                         *, update_glossary: bool = True) -> bool:
    """Refresh a sidecar after a deterministic edit to the translated text.

    Review fixes, global renames and maintenance scripts do not make new model
    calls, but they do change ``content_sha256``.  Leave legacy sidecar-less
    chapters alone; only an existing v5 record can be refreshed safely.

    ``update_glossary=False`` is for edits that do **not** touch names
    (quote alignment, chrome repair, partial dialogue repair): claiming the
    chapter now matches the current glossary would silently clear a real
    "译名过时" warning without retranslating it.
    """
    rec = load_chapter_meta(slug, idx)
    if rec is None:
        return False
    text_path = chapter_path(slug, idx)
    raw_path = chapter_path(slug, idx, "raw")
    try:
        rec["content_sha256"] = _sha256_file(text_path)
        raw_sha = _sha256_file(raw_path)
        with open(raw_path, encoding="utf-8") as f:
            raw_text = f.read()
    except OSError:
        return False
    story = story_meta if story_meta is not None else load_meta(slug)
    rec["source_sha256"] = raw_sha
    if update_glossary:
        # 确定性改动（改名/校对）之后，这一章已经按**当前**术语表对齐，
        # 因此指纹也刷新到当前值 —— 否则改完名还会一直亮「译名过时」。
        rec["glossary_revision"] = glossary_fingerprint(
            story.get("glossary") or {}, raw_text)
        rec["translation_config_hash"] = lncontracts.translation_config_hash(
            source_sha256=raw_sha,
            model_provider=rec["model_provider"],
            model_id=rec["model_id"],
            prompt_version=rec["prompt_version"],
            glossary_revision=_revision(story.get("glossary")),
            characters_revision=_revision(story.get("characters")),
            style_revision=_revision(story.get("style")),
        )
    rec["translated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    save_json(chapter_meta_path(slug, idx), lncontracts.validate_chapter_meta(rec))
    return True


def has_translation(slug: str, idx: int) -> bool:
    return translation_available(
        chapter_path(slug, idx),
        chapter_path(slug, idx, "raw"),
        chapter_meta_path(slug, idx),
    )


def translation_available(zh_path: str, raw_path: str,
                          sidecar_path: str) -> bool:
    """Validate one chapter using explicit paths (root-independent)."""
    return lncontracts.translation_paths_available(
        zh_path, raw_path, sidecar_path)


def has_complete_translation(slug: str, idx: int) -> bool:
    return lncontracts.translation_paths_complete(
        chapter_path(slug, idx),
        chapter_path(slug, idx, "raw"),
        chapter_meta_path(slug, idx),
    )


def last_chapter_result() -> dict:
    return dict(getattr(_CHAPTER_RESULT, "value", {}) or {})


# ------------------------------------------------------------------ 采集

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def http_get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://kakuyomu.jp/",
        "Accept-Language": "ja,zh;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_work(slug_url: str) -> dict:
    """抓作品页，返回标题、作者、章节列表（含每话正文）。

    支持 kakuyomu 与成为小说家吧（ncode.syosetu.com / novel18.syosetu.com）。
    """
    got = lnlib.syosetu_source(slug_url) if lnlib else None
    if got:
        w = lnlib.syosetu_work(slug_url)
        return {
            "id": w["source_id"], "source": w["source"], "url": w["url"],
            "title": w["title"], "author": w["author"],
            "episodes": w["episodes"], "synopsis": w["synopsis"],
            "toc": w["toc"],
        }
    html = http_get(slug_url)
    m = NEXT_DATA.search(html)
    if not m:
        die("作品页没有 __NEXT_DATA__，可能被反爬或页面结构变了。")
    apollo = json.loads(m.group(1))["props"]["pageProps"]["__APOLLO_STATE__"]

    wid = re.search(r"/works/(\d+)", slug_url).group(1)
    work = apollo.get(f"Work:{wid}") or {}
    title = work.get("title") or ""
    author = ""
    a = work.get("author") or {}
    if isinstance(a, dict) and "__ref" in a:
        author = (apollo.get(a["__ref"]) or {}).get("activityName") or ""

    # 目录：按章节顺序取 Episode
    toc = work.get("tableOfContentsV2") or work.get("tableOfContents") or []
    episodes: list[dict] = []
    for sec_ref in toc:
        sec = apollo.get(sec_ref.get("__ref")) if isinstance(sec_ref, dict) else None
        if not sec:
            continue
        for ep_ref in (sec.get("episodeUnions") or []):
            ep = apollo.get(ep_ref.get("__ref")) if isinstance(ep_ref, dict) else None
            if ep and ep.get("id"):
                episodes.append({
                    "id": str(ep["id"]),
                    "title": ep.get("title") or "",
                    "publishedAt": (ep.get("publishedAt") or "")[:10],
                })
    # 目录为空时退回页面上的链接顺序
    if not episodes:
        seen, links = set(), []
        for eid in re.findall(r"/works/\d+/episodes/(\d+)", html):
            if eid not in seen:
                seen.add(eid)
                links.append(eid)
        episodes = [{"id": e, "title": "", "publishedAt": ""} for e in links]

    return {"id": wid, "title": title, "author": author,
            "source": "kakuyomu", "url": slug_url,
            "episodes": episodes}


def fetch_episode_text(wid: str, eid: str, source: str = "kakuyomu") -> str:
    """抓一话正文，返回按行切分的纯文本。"""
    if source in ("syosetu", "novel18") and lnlib:
        return lnlib.syosetu_episode_text(wid, eid, r18=(source == "novel18"))
    html = http_get(f"https://kakuyomu.jp/works/{wid}/episodes/{eid}")
    m = NEXT_DATA.search(html)
    if m:
        apollo = json.loads(m.group(1))["props"]["pageProps"].get("__APOLLO_STATE__", {})
        body = None
        for k, v in apollo.items():
            if k.startswith("Episode:") and isinstance(v, dict):
                body = v.get("body") or v.get("paragraphs")
                break
        if isinstance(body, str) and body:
            return body
        if isinstance(body, list) and body:
            return "\n".join(str(x) for x in body)

    # 退回 HTML 解析。
    # 踩过（用户报「你应该学习章节划分」）：原来是"从 widget-episodeBody 起切 200KB
    # 再正则抓 <p>"，把页脚、注册引导（新規ユーザー登録/今はしない）、
    # 安卓字体提示、応援コメント 区全当正文抓了进来 —— 而且 LLM 老老实实
    # 把「点击滚动」「部分安卓设备上字体设置不会生效」也翻译成了中文，
    # 读者在**每一章末尾**都能看到网站的注册广告。
    # 现在按标签深度扫描，只取 episodeBody 这**一个 div** 的内容。
    inner = _div_inner(html, "widget-episodeBody")
    if inner:
        ps = re.findall(r"<p[^>]*>(.*?)</p>", inner, re.S)
        lines = []
        for p in ps:
            t = re.sub(r"<rp>.*?</rp>|<rt>.*?</rt>", "", p, flags=re.S)
            t = re.sub(r"<[^>]+>", "", t)
            lines.append(t.replace("&nbsp;", " ").strip())
        if lines:
            return "\n".join(lines)
    die(f"取不到正文：episode {eid}")


def _div_inner(html: str, marker: str) -> str | None:
    """取 marker 所在那个 <div …> 的**内容**（扫到配对的 </div> 为止）。

    比"往后切 N 字节"可靠：不会把 div 之后的页脚整块算进来。
    """
    i = html.find(marker)
    if i < 0:
        return None
    gt = html.find(">", i)
    if gt < 0:
        return None
    depth, k = 1, gt + 1
    while depth > 0:
        nd, nc = html.find("<div", k), html.find("</div", k)
        if nc < 0:
            return None
        if 0 <= nd < nc:
            depth += 1
            k = nd + 4
        else:
            depth -= 1
            if depth == 0:
                return html[gt + 1:nc]
            k = nc + 5
    return None


# ------------------------------------------------------------------ 分段

def segment(lines: list[str]) -> list[tuple[int, int]]:
    """按行切成 (start, end) 半开区间。参考 auto-novel 的 createLineSegmenter。"""
    if not lines:
        return []
    out: list[tuple[int, int]] = []
    start = 0
    chars = 0
    for i, line in enumerate(lines):
        ln = len(line) + 1
        if chars + ln > SEG_MAX_CHARS or (i - start) >= SEG_MAX_LINES:
            if i > start:
                out.append((start, i))
                start = i
                chars = 0
        chars += ln
    if start < len(lines):
        out.append((start, len(lines)))
    return out


# ------------------------------------------------------------------ 提示词

def split_paragraphs(lines: list[str]) -> list[str]:
    """把连续的非空行合并成"段落"，独立空行保留为标记。

    日文小说正文常把一句话拆成很多行；按段落翻译能显著提升流畅度，
    同时用空行标记还原原文的段落结构。
    """
    paras, buf = [], []
    for ln in lines:
        if ln.strip() == "":
            if buf:
                paras.append("\n".join(buf))
                buf = []
            paras.append("")
        else:
            buf.append(ln)
    if buf:
        paras.append("\n".join(buf))
    return paras


def build_system_prompt(meta: dict) -> str:
    style = meta.get("style") or {}
    rules = [
        "你是一位资深日文轻小说译者，把日文轻小说翻译成简体中文。",
        "目标：让中文读者读得顺，同时让每个角色还是他自己。",
        "",
        "【文体】",
        "- 轻小说是短句多、对话驱动、节奏快的通俗小说；叙述者的吐槽、偏见和自嘲是文本的一部分。",
        "- 不要写成书面腔、成语堆砌或过度文艺化；不要把吐槽改成正经陈述，也不要乱加网络流行语。",
        "- 叙述铺陈可以简洁，但对话和反应句里的关系、情绪转折、伏笔不能丢。",
        "",
        "【忠实与节奏】",
        "- 不漏译、不增写、不解释、不总结；不要替角色补原文没有的心理或环境描写。",
        "- 保留原文的段落、换行、短句、感叹号/问号/省略号/破折号节奏；不要把碎句合并成一大段。",
        "- 原文的重复和口语冗余如果是角色犹豫、拖延、撒娇或节奏的一部分，保留或压缩；",
        "  纯填充才理顺。明显病句和指代不清可以理顺，但不改人物关系和信息。",
        "",
        "【角色声音】",
        "- 同一句话会因角色和对谁说话而不同：冷淡、乖巧、傲娇、敬语角色要有不同的称呼、语气词、句式和礼貌程度。",
        "- 不要只按“性格类型”定语气；要按“角色×对象×场景”判断。用称呼、语气词、句式完整度体现关系，不硬译“桑/酱/君”。",
        "- 注意角色的词汇习惯（四字词/外来语/古语/比喻/口头禅）和句法习惯（长短句/省略/重复/紧张时变化）；",
        "  同一角色前后要一致。系列角色按本卷时间点判断，合理的成长不是语气跳变。",
        "- 第一人称叙述者的偏见、自嘲、吐槽和误解要保留，不要改成客观旁白。",
        "",
        "【术语与文化】",
        "- 人名、地名、技能名、组织名、称号、货币、等级格式严格按术语表；术语表是锁定译名，不要擅自改动。",
        "- 文化词（前辈、委员长、文化祭、便当、社办、学生会等）保留日式风味，不过度本地化。",
        "- 双关/谐音优先功能对等改写；必要时才加短注。注释只解释文化背景、双关机制或术语，",
        "  不解释剧情、不总结人物关系；同一术语首次出现加注，后文不重复。",
        "- 加注时优先改写正文，避免打断阅读节奏；具体加注方式按本书的发布媒介设定。",
        "- 拟声拟态词按语境动作化/感受化，不逐字硬搬；吐槽要短、准、有反应速度。",
        "- ruby/旁注：双关优先保留或改写；吐槽式旁注用括号/破折号嵌入；不要为了保留注音把中文句子拆碎。",
        "",
        "【对话】",
        "- 日式长敬语拆成自然中文短句；正式度靠词汇和句式完整度，不靠堆“您/请”。角色本来郑重，就保留相应正式度。",
        "- 保持每个角色的说话方式；不要把所有角色译成同一个腔调。",
        "- 原文一个段落里可能连着好几行对白（行间没有空行）：**每一行都要译出来**，"
        "不许只译第一句、不许合并成一句；译文保持同样的分行。漏句比译得不准更严重。",
        "- **不许留假名**：译文里不能出现任何日文假名（平假名/片假名）—— 敬语（ございました）、"
        "语气词、助词、专有名词都不行，一律音译或意译成中文。"
        "唯一例外：引号内**刻意引用原文日语**（例如解释某个日语词）时照抄。",
        "- **英文跟原文**：原文用英文/品牌名/缩写（BGM、VTuber、VIP）就照抄；"
        "原文是日文的地方不要自己换成英文单词。",
        "- **引号跟着原文**：原文用「」就照用「」，原文用『』就用『』，原文用中文弯引号“”才用“”。"
        "**不要为了统一而替换引号体系**，也不要自己增删引号 —— 引号是作者的排版，属于原文。"
        "原文同一段里有几处引号、分别开在哪儿，译文就在对应位置用同样的字形。",
        "",
        "【版本与文体边界】",
        "- 只译给定版本的原文，不要用 web 版/文库版内容补全或纠正；版本差异写进本书备注。",
        "- 后记按作者本人语气处理，可更随意；标题/宣传语单独处理，不要强行与正文同调。",
        "- 没有插图信息时不要臆造画面；如果故事记忆/角色卡提供了插图线索，按它判断情绪。",
        "",
        "【输出】",
        "- 输出前自检：人称/视角、称谓关系、角色是否同腔、术语是否一致、有没有漏译或过度意译、段落节奏是否被合并。",
        "- 只输出与输入相同编号、相同段数的简体中文译文，每段一行；不要输出说明、标题、总结或额外注释列表。",
    ]
    book_rules = []
    medium = str(style.get("medium") or "").strip().lower()
    if medium == "paper":
        book_rules.append("发布媒介：纸质书。必须加注时优先脚注，其次括号夹注；"
                          "页边注有空间时可用。正文保持流畅。")
    elif medium == "ebook":
        book_rules.append("发布媒介：电子书。优先改写正文；必须加注时用括号夹注或章末注，"
                          "避免每页跳转。")
    elif medium == "web":
        book_rules.append("发布媒介：网络连载。优先改写正文；必须加注时用半行以内的括号短注，"
                          "不要让读者跳转。")
    if style.get("general"):
        book_rules.append(f"全篇风格：{style['general']}")
    if style.get("narrator"):
        book_rules.append(f"叙述者滤镜：{style['narrator']}")
    if style.get("honorifics"):
        book_rules.append(f"称谓处理：{style['honorifics']}")
    if style.get("notes"):
        book_rules.append(f"特别注意：{style['notes']}")
    if style.get("guide"):
        book_rules.append("本书补充翻译准则（优先执行；不得违反忠实原文）：\n"
                          + str(style["guide"])[:3000])
    if book_rules:
        rules += ["", "【本书专属设定】"] + book_rules

    # 作品隔离必须写进提示词，并且经验只取本书 meta 里的条目。
    # 这是软约束；调用层还有 ensure_work_id() 的硬校验。
    work_id = str(meta.get("work_id") or meta.get("slug") or "")
    if work_id:
        head = f"【作品隔离】本次请求只属于 work_id={work_id}"
        if meta.get("title"):
            head += f"（{meta['title']}）"
        head += "；不得引用其它作品的术语、人物、剧情或经验。"
        rules.insert(0, head)
        rules.insert(1, "")
    lessons = []
    raw_lessons = meta.get("lessons") or []
    if not isinstance(raw_lessons, list):
        raw_lessons = []
    for x in raw_lessons[-8:]:
        text = x.get("text") if isinstance(x, dict) else str(x)
        if text:
            lessons.append("- " + str(text)[:240])
    if lessons:
        rules += ["", "【本书经验（只适用于本书，不得套用到其它作品）】"] + lessons
    return "\n".join(rules)


def _character_names(name: str, info) -> list[str]:
    """角色在主名之外还允许 aliases（昵称/称号/不同写法）。"""
    names = [str(name)] if name else []
    if isinstance(info, dict):
        for a in info.get("aliases") or []:
            if isinstance(a, str) and a.strip():
                names.append(a.strip())
    return names


def _character_card(name: str, info) -> str:
    """把角色卡压成一行，只注入当前段落实际出场的人。"""
    if not isinstance(info, dict):
        return f"{name}：{info}"
    labels = (("desc", "设定"), ("voice", "语气"), ("address", "称呼"),
              ("lexicon", "词汇习惯"), ("syntax", "句法习惯"),
              ("volume", "本卷时间点"), ("notes", "注意"))
    parts = []
    for key, label in labels:
        value = info.get(key)
        if value:
            parts.append(f"{label}：{value}")
    return f"{name}：" + ("；".join(parts) if parts else "")


def build_chunk_prompt(meta: dict, paras: list[str], start: int,
                       prev_context: str) -> tuple[str, list[str]]:
    """构造这一段的 prompt，并返回本次实际注入的术语（用于统计）。"""
    glossary = meta.get("glossary") or {}
    characters = meta.get("characters") or {}
    body_text = "\n".join(paras)

    used: list[str] = []
    lines: list[str] = []

    work_id = str(meta.get("work_id") or meta.get("slug") or "")
    if work_id:
        title = str(meta.get("title") or "")
        lines.append(f"【当前作品 work_id={work_id}】{title}")
        lines.append("下面的术语、人物、前情只属于本书；不要混入其它作品的设定。")
        lines.append("")

    # 前情：上一段译文尾部（跨段语气与指代连贯），保持在稳定的前缀位置
    if prev_context:
        lines.append("【前文译文（仅供衔接，不要重复翻译）】")
        lines.append(prev_context[-400:])
        lines.append("")

    # 故事记忆：只注入"提到了本段登场人物"的前情梗概。
    # 这是"了解故事再翻译"的核心——不是靠整本上下文，而是按需检索。
    summaries = meta.get("summaries") or {}
    if summaries:
        # 本段日文里出现了哪些人物？同时取"日文名"和"中文名"两种写法：
        # 梗概是用中文写的，用日文名去匹配永远匹配不上（踩过这个坑）。
        names: list[str] = []
        for jp, info in (meta.get("characters") or {}).items():
            if jp and jp in body_text:
                names.append(jp)
                zh = glossary.get(jp)
                if zh:
                    names.append(zh)
        if names:
            picks = []
            for k in sorted(summaries, key=lambda x: int(x)):
                s = summaries[k]
                if any(n in s for n in names):
                    picks.append((k, s))
                if len(picks) >= 3:
                    break
            if picks:
                lines.append("【前情梗概（保持人物与设定连贯）】")
                for k, s in picks:
                    lines.append(f"第{k}话：{s}")
                lines.append("")

    # 术语表：只注入本次真正出现的（省 token，提高准确率）
    hit_terms = [(jp, zh) for jp, zh in glossary.items() if jp and jp in body_text]
    if hit_terms:
        lines.append("【术语表（必须遵守）】")
        lines.extend(f"{jp} => {zh}" for jp, zh in sorted(hit_terms))
        used.extend(jp for jp, _ in hit_terms)
        lines.append("")

    # 相关人物：只注入本段提到的人。支持结构化角色卡，避免只有一句
    # "desc" 导致全员一个腔调。
    hit_chars = []
    for name, info in characters.items():
        names = _character_names(name, info)
        if not any(n and n in body_text for n in names):
            continue
        hit_chars.append(_character_card(name, info))
    if hit_chars:
        lines.append("【登场人物（按角色卡保持声音；同一场景内必须可区分）】")
        lines.extend(hit_chars)
        lines.append("")

    lines.append("【原文段落（每段前的编号必须保留）】")
    for i, p in enumerate(paras):
        if p == "":
            lines.append(f"#{start + i + 1}:")
        else:
            lines.append(f"#{start + i + 1}:{p}")
    lines.append("")
    body = [x for x in paras if x.strip()]
    if len(body) == 1:
        # 单段还要求"带编号"是白费要求：模型多半只回一句译文（或者干脆把
        # 说明抄回来），校验就会一直判"编号缺失"直到把整章预算烧光。
        # 踩过：某章一段一句「何を言っているんだこいつは…」二分到 1 段仍失败，
        # 该章永远翻不出来、整本书卡在 48/54。
        lines.append("只输出这段的简体中文译文：不要编号、不要解释、不要重复原文。")
    else:
        lines.append("翻译时先判断每句是谁说的、对谁说；保持该角色的词汇和句法习惯。")
        lines.append("请输出同样段数、同样编号的简体中文译文，每段一行。")
    return "\n".join(lines), used


def _reset_chapter_route() -> None:
    _CHAPTER_ROUTE.value = {
        "providers": [], "models": [], "fallback": False, "cost": 0.0,
    }


def _note_route(role: str, route, cost: dict | None) -> None:
    if role != "translate":
        return
    info = getattr(_CHAPTER_ROUTE, "value", None)
    if info is None:
        return
    if route.provider not in info["providers"]:
        info["providers"].append(route.provider)
    if route.model not in info["models"]:
        info["models"].append(route.model)
    info["fallback"] = info["fallback"] or bool(route.fallback)
    info["cost"] = round(float(info.get("cost") or 0)
                         + float((cost or {}).get("amount") or 0), 8)


def _chapter_route_summary() -> tuple[str | None, str | None, dict]:
    info = dict(getattr(_CHAPTER_ROUTE, "value", None) or {})
    provider = "+".join(info.get("providers") or []) or None
    model_id = "+".join(info.get("models") or []) or None
    return provider, model_id, info


def call_llm(system: str, user: str, model: str, temperature: float,
             retries: int | None = None, *,
             role: str | None = None) -> tuple[str, dict]:
    role = role or lnmodels.role_for_model(model)
    routes = lnmodels.routes_for(role, model)
    tries = max(1, int(retries or lnmodels.request_retries()))
    last = None
    for route in routes:
        lnmodels.ensure_budget()
        if not route.local and not route.api_key:
            last = "未配置 API key"
            continue
        if not route.fallback and not lnmodels.probe(route, timeout=5.0):
            # 主端点端口都不通（PC 关机/断网）：别等 10 分钟的 socket 超时，
            # 立刻判失败并切兜底，否则界面就是"GPU 没了、进度也不动"。
            # 但 2 秒太紧：PC 正忙/模型重载时握手偶尔要 1~3 秒，会误判"关机"
            # （踩过：上一章本地刚成功，下一章探测超时被切去 DeepSeek）。
            # 所以 5 秒 + 隔 1.5 秒再试一次，两次都不通才切。
            time.sleep(1.5)
            if not lnmodels.probe(route, timeout=5.0):
                lnmodels.mark_primary_failed(role)
                last = f"{route.base_url} 不可达（两次 TCP 探测失败）"
                nxt = routes[-1]
                if nxt is not route:
                    print(f"  ⚠ {role} 主端点不可达（{route.base_url}），"
                          f"120 秒内改用 {nxt.provider}/{nxt.model}", flush=True)
                continue
        # deepseek-flash 会把「思考」算进 completion：max_tokens 给小了时
        # 内容可能被思考吃光 → 返回空回复（实测 3 次全空，整章翻不出来）。
        # 云端给它留足；本地模型沿用配置（7B 上下文本来就小）。
        _max_tok = lnmodels.max_output_tokens()
        if route.provider == "deepseek":
            # deepseek-flash 的「思考」也算 completion：实测整章翻译思考 ~11k、
            # 内容 ~2.5k，给小了内容会被截断甚至为空（回复只剩思考）。
            _max_tok = max(_max_tok, int(os.environ.get(
                "LNTRANS_DEEPSEEK_MAX_TOKENS", "32000")))
        payload = {
            "model": route.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": _max_tok,
        }
        headers = {"Content-Type": "application/json"}
        if route.api_key:
            headers["Authorization"] = f"Bearer {route.api_key}"
        for attempt in range(1, tries + 1):
            last_code = 0
            req = urllib.request.Request(
                route.base_url,
                data=json.dumps(payload).encode(),
                headers=headers,
            )
            try:
                with urllib.request.urlopen(
                        req, timeout=lnmodels.timeout_seconds()) as r:
                    d = json.loads(r.read().decode())
                parsed = d
            except urllib.error.HTTPError as e:
                last_code = e.code
                last = f"HTTP {e.code}: {e.read().decode()[:200]}"
                if e.code in (400, 422):
                    break
            except (OSError, ValueError, KeyError, TypeError) as e:
                last = f"{type(e).__name__}: {e}"
            else:
                reply = parsed["choices"][0]["message"]["content"]
                usage = dict(parsed.get("usage") or {})
                total = int(usage.get("total_tokens", 0) or 0)
                tok_in = int(usage.get("prompt_tokens",
                                       usage.get("input_tokens", 0)) or 0)
                tok_out = int(usage.get("completion_tokens",
                                        usage.get("output_tokens", 0)) or 0)
                if total == 0 and tok_in == 0 and tok_out == 0:
                    tok_in = lnmodels.estimate_tokens(system + "\n" + user)
                    tok_out = lnmodels.estimate_tokens(reply)
                    total = tok_in + tok_out
                    usage.update({
                        "prompt_tokens": tok_in,
                        "completion_tokens": tok_out,
                        "total_tokens": total,
                        "estimated": True,
                    })
                elif total == 0:
                    total = tok_in + tok_out
                    usage["total_tokens"] = total
                elif tok_in == 0 and tok_out == 0:
                    tok_out = total
                    usage["completion_tokens"] = tok_out
                cost = lnmodels.estimate_cost(
                    tok_in, tok_out, role, provider_name=route.provider)
                lnmodels.record_usage(
                    role=role, model=route.model, usage=usage, cost=cost,
                    source="translation" if role == "translate" else role,
                    provider_name=route.provider,
                )
                if not route.fallback:
                    lnmodels.clear_primary_failed(role)
                _note_route(role, route, cost)
                return reply, usage
            if attempt < tries:
                time.sleep(2 * attempt)
        if last_code in (400, 422):
            die(f"{role} 请求被拒绝（HTTP {last_code}），"
                f"不自动切换：{last}")
        if route.fallback:
            last = f"{route.provider}/{route.model}: {last}"
            continue
        if len(routes) > 1:
            lnmodels.mark_primary_failed(role)
            print(f"  ⚠ {role} 主端点失败（{last}），120 秒内改用 "
                  f"{routes[1].provider}/{routes[1].model}", flush=True)
            continue
        break
    die(f"{role} 模型请求失败（重试 {tries} 次）：{last}")


_META_LINE = re.compile(r"(以上|说明|译注|备注|注[:：]|※|P\.S\.|ps[:：])")


_PROMPT_TAIL_LINES = {
    "翻译时先判断每句是谁说的、对谁说；保持该角色的词汇和句法习惯。",
    "请输出同样段数、同样编号的简体中文译文，每段一行。",
    "只输出这段的简体中文译文：不要编号、不要解释、不要重复原文。",
}


def _plain_reply(reply: str, src: str) -> str:
    """把"没带编号"的回复还原成一段译文（只给单段场景用）。

    模型对单段请求经常：①只回一句译文；②把 prompt 尾部的说明抄回来；
    ③把原文也贴一遍。三种都见过，所以逐行过滤：去编号、去说明、去原文、
    去 work_id 头，剩下的按行拼起来。
    """
    keep: list[str] = []
    for line in reply.split("\n"):
        t = line.strip()
        if not t:
            continue
        t = re.sub(r"^#\s*\d+\s*[:：]?\s*", "", t).strip()
        if not t or t == src.strip() or "work_id=" in t:
            continue
        if t in _PROMPT_TAIL_LINES or _META_LINE.match(t):
            continue
        keep.append(t)
    return " ".join(keep).strip()


def _align_block(zh: str, paras: list[str]) -> str:
    """整块译文把引号字形对齐到原文（一章作为一个整体比，不逐段硬配）。

    ① 先走精确对齐（数量与开/闭角色序列完全一致才换，结构不同就不动）。
    ② 数量对不上时（模型多包了一处心理描写之类）退一步做**纯字形映射**：
       原文通篇用「」而译文通篇用“”（或反过来）且两种引号各自配对时，
       把字形换成原文的那种 —— 这只改字形、不改模型在哪加引号的决定。
       踩过：整章翻译时 DeepSeek 默认用“”，一本「」风格的书里混进一章弯引号。
    """
    if not zh:
        return zh
    src = "\n".join(paras)
    out = align_quotes_with_source(zh, src)
    if out != zh or "「" not in src:
        return out
    # 源文用「」、译文里**混着**几个“”（大部分是「」、个别是“”）时也要换：
    # 只判断"译文里有没有「"会漏掉这种混用，成品就一半「」一半“”。
    if "“" not in zh or "”" not in zh:
        return out
    if zh.count("“") != zh.count("”"):
        return out
    return zh.replace("“", "「").replace("”", "」")


def _plain_block(reply: str, src: str) -> str:
    """整块回复直接当译文：只去掉 prompt 回声/说明，保留段落与空行结构。"""
    lines: list[str] = []
    for line in reply.split("\n"):
        t = line.strip()
        if not t:
            lines.append("")
            continue
        if t in _PROMPT_TAIL_LINES or "work_id=" in t:
            continue
        if t.startswith(SAKURA_USER_PREFIX):
            # 有的模型会把 user 提示词连同译文一起回一行（前缀 + 译文）：
            # 整行丢掉 = 把唯一的译文也丢了（踩过：兜底到 DeepSeek 后一直
            # 判"编号缺失"、反复重试，其实回复里就是完整译文）。
            t = t[len(SAKURA_USER_PREFIX):].strip()
            if not t:
                continue
            line = t
        if t == src.strip():
            continue
        lines.append(line.rstrip())
    text = "\n".join(lines).strip("\n")
    if not text and reply.strip():
        # 兜底：所有行都被过滤掉时，宁可把原文回复（去掉提示词前缀）当译文，
        # 也别判"空回复→编号缺失→重试到把预算烧光"。
        text = reply.strip()
        for _line in list(_PROMPT_TAIL_LINES):
            text = text.replace(_line, "")
        text = text.replace(SAKURA_USER_PREFIX, "").strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def parse_chunk_reply(reply: str, paras: list[str], start: int) -> tuple[list[str], list[str]]:
    """解析译文，按编号对齐。返回 (译文段落, 缺失编号)。"""
    got: dict[int, str] = {}
    cur: int | None = None
    after_blank = False
    for line in reply.split("\n"):
        t = line.strip()
        if not t:
            after_blank = True
            continue
        # 容忍 `#1:``/#1：``#1 `# 1 : ` 等写法（模型输出经常走样）
        m = re.match(r"^#\s*(\d+)\s*[:：]?\s*(.*)$", t)
        if m:
            cur = int(m.group(1))
            seg = m.group(2).strip()
            after_blank = False
            if cur in got:
                # 重复编号：内容不同则并入（模型可能把一段拆成两块），相同视为抖动忽略
                if seg and seg != got[cur]:
                    got[cur] = f"{got[cur]} {seg}".strip()
            else:
                got[cur] = seg
        elif cur is not None:
            # 没有编号的行 = 当前段的续行（模型把一段折了行）。直接丢掉会截断译文。
            # **但空行之后的散行多半是模型附言**（"（以上）""多余的说明"）：
            # 它们会被拼进正文，成为读者看见的最后一句 —— 必须挡掉。
            # 例外：以对话/括号开头的行仍算续行（有的模型把对白单独起行）。
            if after_blank and not t[:1] in "「『“‘（(【《〈":
                continue
            # 空行之外，模型还常把附言**紧贴**在最后一段后面（没有空行）。
            # 这类行几乎都带"以上/说明/译注/备注"字样且很短，直接丢；
            # 真续行是正文/对白，不会去说"以下是译文"。
            if len(t) <= 60 and _META_LINE.search(t):
                continue
            got[cur] = f"{got[cur]} {t}".strip()
            after_blank = False
    body_idx = [i for i, p in enumerate(paras) if p.strip()]
    plain = ""
    if not got and len(body_idx) == 1:
        # 单段：没解析到编号不算失败，按纯文本收（见 _plain_reply）
        plain = _plain_reply(reply, paras[body_idx[0]])
    out, missing = [], []
    for i, p in enumerate(paras):
        n = start + i + 1
        if p == "":
            out.append("")
        elif n in got and got[n].strip():
            # 空正文（模型给了编号却没内容）当缺失，别把空白段静默塞进译文
            out.append(got[n].strip())
        elif body_idx and i == body_idx[0]:
            if plain:
                out.append(plain)
            else:
                out.append("")
                missing.append(n)
        else:
            out.append("")
            missing.append(n)
    return out, missing


# ---------------------------------------------------------------- 译校
# 以下学自 auto-novel 的 translator（详见 PRIOR-ART.md）：
#   1. detect_chinese —— 校验译文真的是中文，而不是把日文原文抄回来
#   2. 二分翻译       —— 行数反复对不齐时把段落拆两半递归翻
#   3. Semaphore      —— 控制并发，避免打爆 API

_KANA = re.compile(r"[\u3041-\u3096]|[\u30A1-\u30FA]")
_HANZI = re.compile(r"[\u4E00-\u9FAF]")
_URLRE = re.compile(r"h?ttps?://\S+", re.I)
_PUNCT_ZH = "。？！，、；：“”‘’（）《》〈〉【】…—～￥"


def detect_chinese(text: str) -> bool:
    """判断文本是否已主要是中文（对应 auto-novel utils.ts 的 detectChinese）。

    为什么需要：模型有时会把日文原文**原样抄回来**，或只翻一半。
    只校验"行数是否相等"发现不了——行数完全正确，整段却还是日文。

    注意：纯汉字串（如「日本語原文」）中日同形，**仅凭字形无法**与中文区分；
    这类回抄只能靠在调用处与原文比对兜住（见 robust_translate_paras）。
    """
    if not text:
        return False
    t = _URLRE.sub("", text)
    zh = jp = en = 0
    for c in t:
        # 只把汉字与**中文倾向**的标点算作"中文证据"。
        # 空格 / 数字 / # | 是中英日共用的中性字符，把"日文原文里恰好数字多"
        # 也累进 zh 会让日文冒充中文 —— 一律不计（既不帮中文也不帮日文）。
        # 「」『』是日式引号，同样不计，避免对白密集的日文蒙混过关。
        if _HANZI.match(c) or c in _PUNCT_ZH:
            zh += 1
        elif _KANA.match(c):
            jp += 1
        elif c.isascii() and c.isalpha():
            en += 1
    n = max(len(t), 1)
    pzh, pjp, pen = zh / n, jp / n, en / n
    # 假名是中文里绝不会出现的字符，**成规模**出现即判日文（整段没翻 / 回抄原文）。
    # 但**零星**假名往往只是没译的人名/术语（例：「祀ろわぬ教会」），
    # 旧规则 `jp >= 3` 会因此把整段好译文判成日文 —— 实测代价：一章反复重试 + 二分，
    # 19 次请求、3.8 万 token 全白花，读者那边看起来就是"翻译卡住"。
    # 所以改成看**比例**：≥15% 假名（或 8 个以上假名且超过 5%）才判日文。
    if pjp > 0.15 or (jp >= 8 and pjp > 0.05):
        return False
    # 判定为"已中文"：汉字占多数，或明显压过假名，且假名极少。
    # 加上「中文 > 英文」是为了容忍译文里固有的拉丁词
    # （技能名、人名罗马音、拟声词），它们不该把结论翻成"没翻译"。
    return (pzh > 0.75
            or (pzh > pjp and pjp < 0.1 and pzh > pen)          # 中文压过日文
            or (pzh > 0.15 and pjp < 0.05 and pzh > pen * 0.5))  # 中英混排但仍以中文为主


# 引号**跟着原文走**，不做任何"统一"。用户原话：「不要强制用「」，我说过忠于原著。
# 我不希望我自己的意志影响翻译。信达雅，先是信。」
# 所以这里没有"选一种好看的字形"的余地：原文用「」就「」，原文用“”就“”，
# 原文没加引号的地方我们也不加。机械层只做一件事 —— **把译文引号字形对齐到
# 原文引号序列**（角色结构不同就整段不动，绝不为了对齐去增删引号）。
# 为什么还要机械层：翻译是逐 chunk 独立请求的，模型会对每个 chunk 各自决定用哪种
# 引号（实测 19 章里 11 章同一章内就在两种之间漂移），prompt 压不住。
_QUOTE_OPEN = "「『“‘"
_QUOTE_CLOSE = "」』”’"


def _quote_seq(s: str) -> str:
    """抽出引号序列，开引号记 o、闭引号记 c（不含字形，只判角色）。"""
    return "".join("o" if c in _QUOTE_OPEN else "c"
                   for c in s if c in _QUOTE_OPEN or c in _QUOTE_CLOSE)


def _dialogue_count(s: str) -> int:
    """段落里有几处"开口"的引号（= 几段话）。日式与中文引号都算。"""
    return sum(1 for c in s if c in "「“‘")


def _missing_dialogue(paras: list[str], out: list[str]) -> list[int]:
    """找出"原文这段有多处对白、译文却更少"的段落下标（疑似漏译）。

    为什么需要它：实测某部作品有 152 段如此（49 段少了 2 处以上），
    原文一个段落里连着三行对白，模型只译了第一行 —— 而**段数、编号、中文
    校验、回抄比对全都过**，界面上看着完全正常，只有对着原文才发现少了话。
    漏句是"信"的底线问题，必须有一道能自动拦的检查。
    """
    bad: list[int] = []
    for i, (s, z) in enumerate(zip(paras, out)):
        if not s or not z:
            continue
        sc = _dialogue_count(s)
        if sc >= 2 and _dialogue_count(z) < sc:
            bad.append(i)
    return bad


def align_quotes_with_source(zh: str, src: str) -> str:
    """把译文的引号**字形**对齐到原文，忠实于作者的排版。

    例（左边原文、右边译文，箭头后是修正结果）：
      「呼……」   + “呼……”      → 「呼……」      原文用方角，译文跟着方角
      “呼……”    + 「呼……」      → “呼……”       原文用弯引号，译文跟着弯引号
      「a「b」」 + 「a『b』」     → 「a「b」」      嵌套层级与字形都照原文
      （原文没有引号）+ （译文有引号）→ 原样不动，不去增删，由报告列出

    只在**引号数量与开/闭角色序列都完全一致**时才替换字形 —— 这样绝不会
    因为"想对齐"而把两个说话合成一处、或把引号挪到别的句子上去。
    结构不一致就整段不动（那是译者对句子的处理，机械层不该碰）。
    """
    if not zh or not src:
        return zh
    sq = [c for c in src if c in _QUOTE_OPEN or c in _QUOTE_CLOSE]
    zq = [c for c in zh if c in _QUOTE_OPEN or c in _QUOTE_CLOSE]
    if not sq or not zq or len(sq) != len(zq):
        return zh
    if _quote_seq(src) != _quote_seq(zh):
        return zh
    out: list[str] = []
    i = 0
    for c in zh:
        if c in _QUOTE_OPEN or c in _QUOTE_CLOSE:
            out.append(sq[i])
            i += 1
        else:
            out.append(c)
    return "".join(out)


# 常见假名残留的确定性对照（**模型漏译的重灾区**：敬语/客套话）。
# 这些不是"猜"，是固定短语：落盘前直接换掉，不用为同一个词反复花 token 重试。
# 表里只放**整词**，且只在没有别的中文可替换时使用（见 clean_residual）。
KANA_RESIDUE = {
    "ございました": "非常感谢",
    "ありがとうございます": "非常感谢",
    "ありがとう": "谢谢",
    "すみません": "不好意思",
    "ごめんなさい": "对不起",
    "いただきます": "我开动了",
    "ごちそうさま": "多谢款待",
    "おはようございます": "早上好",
    "おやすみなさい": "晚安",
    "はじめまして": "初次见面",
    "よろしくお願いします": "请多关照",
    "ええと": "那个",
    "あの": "那个",
}

_QUOTE_SPAN = re.compile(r"[「『“‘《]([^」』”’》]*)[」』”’》]")


def strip_quoted(text: str) -> str:
    """去掉引号/书名号**里面**的部分，只留引号外的正文。

    为什么需要：引号里可能是**刻意保留的日文引用**（例：用日语来说就是「贈り物」），
    那是内容不是残留；引号外出现假名才是没译干净。
    """
    return _QUOTE_SPAN.sub("", text)


# 括号块放宽到 60 字：长一点的颜文字/拟声（`（……妈゛妈゛……！太帅了，我已经不行了……！）`）
# 也要能被识别，否则指标永远有假红。
_KAOMOJI = re.compile(r"[（(][^（()）\n]{0,60}[）)]")
# 装饰性符号：浊点 ゛゜、单独的长音符 ーーー 是"喊叫/颤音"的排版，不是日文词。
# 只在**只由这些字符组成**的连续段里去掉，避免误伤 ケーキ 这类真外来语。
_DECOR = re.compile(r"[゛゜ー]+")


def strip_kaomoji(text: str) -> str:
    """去掉颜文字 `(つд⊂)`、`（妈゛妈゛）` 这类括号块。

    这些是**刻意保留的表情/拟声**（原文就是颜文字），不是"没译干净"。
    不豁免的话 `residue` 永远是红的，指标就没人看了。
    """
    return _KAOMOJI.sub("", text)


_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z]{2,}")


def has_translatable(text: str) -> bool:
    """这段有没有"需要翻译的文字"（假名或汉字）。

    装饰分隔线（`――――――`）、纯符号、纯数字、颜文字都没有。把这种段落发给模型，
    它只会**原样抄回**；而"输出必须是中文"的校验会把这种照抄判成"抄回原文"，
    重试 3 次后**整章不落盘** —— 用户看到的就是"翻译卡住/失败"。
    踩过：第 31 章末尾一条 `――――――` 让它白烧 3 次请求（约 4.7k tok）还整章失败。
    """
    if not text:
        return False
    if _KANA_RE.search(text) or _CJK_RE.search(text):
        return True
    # 英文成句（歌词/引文）也要翻：只有 1~2 个英文词的多半是符号里的缩写
    # （Lyrical Lily、BGM），整段送给模型只会被原样抄回来 —— 那是"不可翻"。
    # 纯 URL/编号/分隔线仍然穿透。
    # URL 先剥掉：一条链接里就含好几个英文"词"，剥之前会被误判成成句英文，
    # 发给模型后原样抄回 → 又变成"不是中文"的重试。
    return len(_WORD_RE.findall(_URLRE.sub(" ", text))) >= 3


def kana_outside_quotes(text: str) -> int:
    """引号外、颜文字外、装饰符号外还剩多少假名 = 真正的残留。"""
    body = strip_kaomoji(strip_quoted(text))
    body = _DECOR.sub("", body)
    return count_kana(body)


def clean_residual(text: str) -> str:
    """落盘前把常见的假名客套话换成中文（确定性、零 token）。

    只处理**引号外**的整词命中：引号内是作者引用原文的地方，不动。
    """
    if not text or not any("\u3040" <= c <= "\u30ff" for c in text):
        return text
    for jp, zh in KANA_RESIDUE.items():
        if jp in text:
            text = text.replace(jp, zh)
    return text


def english_drift(zh: str, src: str) -> list[str]:
    """找出译文里"原文没有的连续英文"（模型语言漂移）。

    为什么不一律禁止英文：这些书里 BGM / VTuber / VIP / Discord 本来就该保留，
    一禁就会把正常译文反复打回（正是上一次"误判→放大器"的老路）。
    判据是**跟原文比**：整段英文里没有一个词出现在原文，才算漂移。
    """
    if not zh:
        return []
    low = (src or "").lower()
    bad: list[str] = []
    for m in re.finditer(r"[A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*)+", zh):
        words = m.group(0).split()
        if not any(w.lower() in low for w in words):
            bad.append(m.group(0))
    return bad


def count_kana(text: str) -> int:
    """文本里的假名个数（平假名 + 片假名）。

    用途：**残留指标**。管线允许"以中文为主、夹零星日文"的译文落地并标未译全，
    这个计数就是那个取舍的度量 —— `lntrans residue <slug>` 按章汇总，
    超过阈值标 ⚠。没有指标的"接受"迟早变成"没人管"。
    """
    return sum(1 for c in text if "\u3040" <= c <= "\u30ff")


def chinese_share(text: str) -> float:
    """汉字 + 中文标点的占比（和 detect_chinese 同一套计数）。

    用来判断"这段虽然夹了零星日文，但整体已经是中文"——那种情况**收下**比
    反复重试、二分重翻划算得多（钱和时间都花在重翻已经翻好的段落上）。
    """
    if not text:
        return 0.0
    t = _URLRE.sub("", text)
    zh = sum(1 for c in t if _HANZI.match(c) or c in _PUNCT_ZH)
    return zh / max(len(t), 1)


class Semaphore:
    """简单信号量（对应 auto-novel utils.ts 的 Semaphore）。

    我们逐段串行翻译，但"二分翻译"会产生并发子请求，
    用它把在途请求压住，避免触发 API 限流。
    """

    def __init__(self, maximum: int):
        if maximum <= 0:
            raise ValueError("Semaphore max 必须 > 0")
        self._max = maximum
        self._cur = 0
        self._waiters = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        ev = None
        with self._lock:
            if self._cur < self._max:
                self._cur += 1
                return
            ev = threading.Event()
            self._waiters.append(ev)
        ev.wait()

    def release(self) -> None:
        with self._lock:
            if self._waiters:
                self._waiters.pop(0).set()
            else:
                self._cur -= 1

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


_GLOBAL_SEM = Semaphore(3)     # 最多 3 个在途 LLM 请求


# 同一本书的翻译/校对必须串行，避免两个任务同时写 meta.json / cache /
# 章节文件时互相覆盖。不同书各有一把锁，仍然可以并行。
_NOVEL_LOCKS: dict[str, threading.RLock] = {}
_NOVEL_LOCKS_GUARD = threading.Lock()


def _novel_lock(slug: str) -> threading.RLock:
    with _NOVEL_LOCKS_GUARD:
        lock = _NOVEL_LOCKS.get(slug)
        if lock is None:
            lock = threading.RLock()
            _NOVEL_LOCKS[slug] = lock
        return lock


@contextlib.contextmanager
def novel_lock(slug: str):
    """本书级互斥锁。RLock 允许 review_chapter 内部再次进入。"""
    lock = _novel_lock(slug)
    with lock:
        yield


# ------------------------------------------------------------------ 命令

def slugify(s: str) -> str:
    """生成 URL/目录友好的短名。

    只用 ASCII：日文标题直接进 slug 会让 URL 变成一长串百分号编码
    （`/read/%E8%B2%A0%E3%81%91...`），既难读又容易在分享时出错。
    取不到 ASCII 时回退到作品 id，稳定且短。
    """
    s = re.sub(r"[^A-Za-z0-9]+", "-", s or "").strip("-").lower()
    return s[:48] or ""


def _meta_source_id(slug: str) -> str:
    """本地这部的源站 id（读不到返回空串）。用来判断「同名目录」是不是同一部作品。"""
    try:
        with open(os.path.join(novel_dir(slug), "meta.json"), encoding="utf-8") as f:
            return str(json.load(f).get("source_id") or "")
    except (OSError, ValueError):
        return ""


def cmd_init(args) -> None:
    info = fetch_work(args.url)
    source = info.get("source") or "kakuyomu"
    _aliases = lncatalog.load_aliases(
        os.path.join(_ROOT, "data", "library.json"))
    slug = args.slug or lncatalog.choose_slug(
        lncatalog.source_slug(source, str(info["id"])), _aliases)
    d = novel_dir(slug)
    if os.path.isdir(d) and not args.force:
        # 稳定 id 就是目录名；同名目录属于不同 source_id 时是硬冲突，
        # 不能再退回标题 slug（那会重新产生不可追踪的身份）。
        if _meta_source_id(slug) == str(info["id"]):
            print(f"已存在：{d}（要重建用 --force）")
            return
        die(f"稳定 slug「{slug}」已被另一部作品占用"
            f"（source_id={_meta_source_id(slug) or '未知'}）")
    meta = {
        "id": slug,
        "slug": slug,
        "source": source,
        "source_id": info["id"],
        "url": info.get("url") or args.url,
        "title": info["title"],
        "author": info["author"],
        "episodes": info["episodes"],
        "glossary": {},
        "characters": {},
        "summaries": {},
        "style": {},
        "progress": {"translated_through": 0, "fetched_through": 0},
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_meta(slug, meta)
    os.makedirs(os.path.join(d, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(d, "raw"), exist_ok=True)
    print(f"已创建作品：{slug}")
    print(f"  标题：{info['title']}")
    print(f"  作者：{info['author']}")
    print(f"  章节数：{len(info['episodes'])}")
    print(f"  目录：{d}")
    print("\n下一步：python3 lntrans.py next {n}   （抓下一批原文）".format(n=slug))


_SHELF_TRACKING = ("want", "reading", "finished", "dropped")


def mark_on_shelf(slug: str) -> bool:
    """把作品放进「想读」。这不是收藏（与 Web 端 ensure_on_shelf 同义）。

    为什么 CLI 导入必须做：书架只渲染 on_shelf 的书；只建目录不上架，
    导入完成后书在 novels/ 里但 UI 里**完全看不到**。
    """
    path = os.path.join(_ROOT, "data", "books", f"{slug}.json")
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("状态文件不是对象")
    except FileNotFoundError:
        d = {}
    except (OSError, ValueError) as e:
        # 已有状态文件坏了：宁可不动，也不要用空对象覆盖用户的进度/收藏。
        print(f"  ⚠ 读不了书架状态（{type(e).__name__}: {e}），未自动上架",
              file=sys.stderr)
        return False
    if d.get("favorites") or d.get("tracking") in _SHELF_TRACKING:
        return False
    d["tracking"] = "want"
    d.setdefault("progress", {})
    d.setdefault("feedback", [])
    d.setdefault("opened", {})
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lndata.atomic_write_json(path, d)
    except OSError as e:
        print(f"  ⚠ 自动上架失败（{type(e).__name__}: {e}）", file=sys.stderr)
        return False
    return True


def cmd_import(args) -> None:
    """导入本地 EPUB/TXT（建书 + 原文落盘，复用同一条翻译管线）。"""
    import lnimport
    try:
        with open(args.path, "rb") as f:
            data = f.read()
    except OSError as e:
        die(f"读不了文件：{e}")
        return
    try:
        info = lnimport.import_bytes(
            data, os.path.basename(args.path), lt=sys.modules[__name__],
            title=args.title or "", author=args.author or "",
            slug=args.slug or "")
    except lnimport.ImportError_ as e:
        die(str(e))
        return
    meta = load_meta(info["slug"])
    added = mark_on_shelf(info["slug"])
    if info["created"]:
        print(f"已导入：{info['title']}")
        print(f"  作者：{info['author']}")
        print(f"  章节：{info['chapters']} 章")
        print(f"  slug：{info['slug']}")
        print(f"  目录：{novel_dir(info['slug'])}")
    else:
        print(f"这部书之前已经导入过：{info['slug']}"
              f"（{len(meta.get('episodes') or [])} 章）")
    print("  书架：" + ("已放进「想读」" if added else "已在书架（保持原状态）"))
    print(f"\n打开阅读页：/read/{info['slug']}")
    print("（服务起来后浏览器访问 http://127.0.0.1:<端口>"
          f"/read/{info['slug']}，默认端口 8099；翻译仍走「读到哪翻到哪」）")
    if not info["created"]:
        return
    print(f"\n下一步：`python3 lntrans.py next {info['slug']} 3` 开始翻译。")


def cmd_fetch(args) -> None:
    meta = load_meta(args.slug)
    eps = meta["episodes"]
    start = meta["progress"].get("fetched_through", 0)
    end = min(start + args.count, len(eps))
    if start >= len(eps):
        print("已经抓到最后一章了。")
        return
    for i in range(start, end):
        ep = eps[i]
        p = chapter_path(args.slug, i, "raw")
        if os.path.exists(p) and os.path.getsize(p) > 0:
            continue
        text = fetch_episode_text(meta["source_id"], ep["id"],
                                  meta.get("source") or "kakuyomu")
        save_text(p, text)
        print(f"  抓到 #{i+1} {ep['title'][:32]}")
        time.sleep(0.7)
    meta["progress"]["fetched_through"] = end
    save_meta(args.slug, meta)
    print(f"原文已到第 {end} 章（共 {len(eps)}）。")


# 整本 Markdown 的增量构建缓存：章号 -> (签名, 是否有可读译文, 正文)。
# `rebuild_novel_md` 每译完一章就会调用一次，而它要读**全书**已译章节 ——
# 不做缓存就是 O(章数²) 次文件读与哈希校验（185 章时累计上万次 open）。
# 签名来自一次目录扫描（`lncontracts.dir_sigs`），只有真正变过的章才重新
# 校验并重读正文。上限按书数控制：缓存正文是纯内存优化，不该无限增长。
_NOVEL_MD_CACHE: dict[str, dict[int, tuple[tuple, bool, str]]] = {}
_NOVEL_MD_CACHE_MAX = 8


def rebuild_novel_md(slug: str, meta: dict, *, force: bool = False,
                     override_chapter: int | None = None,
                     override_text: str | None = None) -> str:
    """由已译分章文件重建 novel.md。幂等，重译/乱序翻译都不会产生重复。

    `override_chapter` / `override_text` 用于**刚翻译完**的那一章：正文还在
    内存里，直接用它，不依赖文件签名（exFAT / sdcardfs 的 mtime 只有 2 秒
    精度，刚写的文件签名可能还没变）。`force=True` 给维护脚本用：它们改了
    文件再来重建，宁可重读一遍也不要复用进程内的旧正文。
    """
    cache = _NOVEL_MD_CACHE.setdefault(slug, {})
    total = len(meta["episodes"])
    for key in [k for k in cache if k >= total]:
        cache.pop(key, None)
    if len(_NOVEL_MD_CACHE) > _NOVEL_MD_CACHE_MAX:
        _NOVEL_MD_CACHE.clear()
        cache = _NOVEL_MD_CACHE.setdefault(slug, {})
    base = novel_dir(slug)
    c_sigs = lncontracts.dir_sigs(os.path.join(base, "chapters")) or {}
    r_sigs = lncontracts.dir_sigs(os.path.join(base, "raw")) or {}
    parts = [f"# {meta.get('title','')}\n"]
    if meta.get("author"):
        parts.append(f"作者：{meta['author']}\n")
    n = 0
    for i in range(total):
        name = f"{i:04d}"
        zh = chapter_path(slug, i)
        sig = (c_sigs.get(f"{name}.txt"), c_sigs.get(f"{name}.meta.json"),
               r_sigs.get(f"{name}.txt"))
        if override_chapter is not None and i == override_chapter:
            ok, body = True, (override_text or "").strip()
            cache[i] = (sig, ok, body)
        else:
            hit = None if force else cache.get(i)
            if hit is not None and hit[0] == sig:
                ok, body = hit[1], hit[2]
            else:
                ok = has_translation(slug, i)
                body = ""
                if ok:
                    try:
                        with open(zh, encoding="utf-8") as f:
                            body = f.read().strip()
                    except OSError:
                        ok = False
                cache[i] = (sig, ok, body)
        if not ok:
            continue
        title = meta["episodes"][i].get("title") or f"第{i+1}话"
        parts.append(f"\n## {i+1}. {title}\n\n{body}\n")
        n += 1
    md = os.path.join(base, "novel.md")
    save_text(md, "\n".join(parts))
    return md


def ensure_raw(slug: str, meta: dict, upto: int, quiet: bool = False) -> None:
    """确保前 upto 章的原文已抓到本地（服务端 worker 也要用这一步）。

    踩过：worker 直接调 translate_chapter，而原文还没抓，
    于是 FileNotFoundError。CLI 的 next 自带抓取，worker 没有。
    """
    eps = meta["episodes"]
    fetched = meta["progress"].get("fetched_through", 0)
    if (meta.get("source") or "") == "local":
        # 本地书没有源站可抓。原文在导入时已经全部落盘；缺了就是导入不完整，
        # 报清楚，别让 `fetch_episode_text` 拿一个 "local-xxx" 去请求源站。
        missing = [i + 1 for i in range(min(upto, len(eps)))
                   if not (os.path.exists(chapter_path(slug, i, "raw"))
                           and os.path.getsize(chapter_path(slug, i, "raw")) > 0)]
        if missing:
            raise RuntimeError(
                f"本地书缺少第 {missing[0]} 章原文（导入不完整），请重新导入")
        if min(upto, len(eps)) > fetched:
            meta["progress"]["fetched_through"] = min(upto, len(eps))
            save_meta(slug, meta)
        return
    if upto <= fetched:
        return
    for i in range(fetched, min(upto, len(eps))):
        p = chapter_path(slug, i, "raw")
        if os.path.exists(p) and os.path.getsize(p) > 0:
            continue
        text = fetch_episode_text(meta["source_id"], eps[i]["id"],
                                  meta.get("source") or "kakuyomu")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        save_text(p, text)
        if not quiet:
            print(f"  #{i+1} {eps[i]['title'][:30]}")
        time.sleep(0.7)
    meta["progress"]["fetched_through"] = min(upto, len(eps))
    save_meta(slug, meta)


def _llm_guard(system, prompt, args, stats):
    """带信号量与计数的 LLM 调用（对应 auto-novel 的 Semaphore 限流）。"""
    with _GLOBAL_SEM:
        reply, usage = call_llm(
            system, prompt, args.model, args.temperature, role="translate")
    total = int(usage.get("total_tokens", 0) or 0)
    tok_in = int(usage.get("prompt_tokens",
                           usage.get("input_tokens", 0)) or 0)
    tok_out = int(usage.get("completion_tokens",
                            usage.get("output_tokens", 0)) or 0)
    if tok_in == 0 and tok_out == 0:
        tok_out = total
    stats["tok"] += total
    stats["input"] = int(stats.get("input", 0) or 0) + tok_in
    stats["output"] = int(stats.get("output", 0) or 0) + tok_out
    stats["calls"] += 1
    return reply, usage


# 每个**分段（chunk）**内容级调用的宽松安全帽：translate_chapter 对每个分段
# 新建 stats（calls 归零），所以这是「每 chunk」的上限，不是整章的上限。
# > 最深可恢复成本 61，故不误伤"最终能成"的段；只掐"纯毒段"尾部（原最坏 93 → 64）。
MAX_SEG_CALLS = 64

# 重试/二分/递归的**三维**硬上限。为什么是三维而不是一张：
# 次数与深度各自有用，但**代价由 token 决定** —— 一次请求就可能上万 token，
# 只有"本章已花多少"能真正给钱包兜底。
#   次数  MAX_SEG_CALLS=64   （每 chunk）
#   深度  depth < 4          （二分递归，见 robust_translate_paras）
#   预算  MAX_CHAPTER_TOK    （每章累计，跨 chunk 共享）
# 踩过的放大器：一个错判 → 3 次重试 → 二分 → 两半各自再二分 → 19 次请求 / 3.8 万
# token，仍然一个字的译文都没多。规则再准，下一次误判（标点/数字/模型抽风）
# 还会走同一条链 —— 所以必须在**链上**装保险，而不是只把误判源修准。
MAX_CHAPTER_TOK = int(os.environ.get("LNTRANS_CHAPTER_TOK", "30000"))


def _log_guard(event: str, **kv) -> None:
    """失败的**结构化**记录（一行 JSON，带 `[trans_guard]` 前缀）。

    为什么要结构化：上一次定位"翻译卡住"是靠人肉翻几十行日志拼出来的
    （假名数、占比、到了第几次、二分到第几层、已经花了多少）。一条 JSON
    能直接 grep/求和，下次不用再拼。
    """
    rec = {"ev": event}
    rec.update({k: v for k, v in kv.items() if v is not None})
    try:
        print("[trans_guard] " + json.dumps(rec, ensure_ascii=False), flush=True)
    except Exception:  # noqa: BLE001 —— 日志绝不能影响翻译
        pass


def _budget_left(budget: dict | None) -> int:
    """本章还剩多少 token 预算（没有预算时给个很大的数）。"""
    if not budget:
        return 10 ** 9
    return int(budget.get("limit", MAX_CHAPTER_TOK)) - int(budget.get("tok", 0))


def robust_translate_paras(meta: dict, paras: list[str], start: int, system: str,
                           args, prev_context: str, stats: dict,
                           depth: int = 0,
                           budget: dict | None = None) -> tuple[list[str], list[str]]:
    """翻译一段，带**两项校验 + 二分降级**（学自 auto-novel translator）。

    校验（auto-novel 是行数 + detectChinese，我们对应成段落数 + 中文检测）：
      1. 段落数必须与原文一致（编号能对齐）
      2. 合起来必须是中文 —— 否则模型可能把日文原样抄回来了

    连续 3 次段落数对不齐 → **二分**：把这一段的段落拆两半分别翻再拼起来。
    长段/对话密集的段落最容易对不齐，二分比整段硬重试成功率高得多。

    每个分段（chunk）有宽松上限（MAX_SEG_CALLS）：只在"纯毒段"上触发，截断后保留原文。
    """
    glossary = meta.get("glossary") or {}
    _mode = translate_mode()
    _sakura = _mode in ("sakura", "chapter")
    MAX_TRY = 3
    bad_lines = 0
    # 「不可翻」的段落（分隔线/纯符号/纯数字）：不送给模型，原样穿透。
    # 整段都不可翻时一次模型调用都不发（省 token，也不会因"不是中文"而失败）。
    passthru = {i for i, p in enumerate(paras) if not has_translatable(p)}
    if passthru and len(passthru) == len(paras):
        return list(paras), []
    _src_all = "".join(" ".join(paras).split())   # 原文（去空白），用于回抄比对
    hint = ""
    used: list[str] = []      # 本段注入的术语（build_chunk_prompt 会覆盖）
    best_out: list[str] | None = None      # 到目前为止"最像中文"的一版
    best_missing: list[int] = []
    best_share = 0.0
    _quality_tried = False     # 质量原因**只重试一次**（用户要求，也别再放大）
    for attempt in range(MAX_TRY):
        # ---- 预算守门员：这一章已经花掉的 token 到顶了，就**不再重试、不二分** ----
        if _budget_left(budget) <= 0:
            _log_guard("budget_exhausted", start=start, paras=len(paras), depth=depth,
                       calls=stats.get("calls"), tok=stats.get("tok"),
                       budget_tok=(budget or {}).get("tok"),
                       best_share=round(best_share, 3))
            if best_out is not None and best_share > 0.5:
                # 有"以中文为主"的一版 → 收下并标未译全（待校对补），绝不继续放大
                stats["partial"] = stats.get("partial", 0) + 1
                stats["budget_exhausted"] = True
                missing_now = best_missing or [
                    start + i + 1 for i, (src, out) in enumerate(
                        zip(paras, best_out))
                    if src and i not in passthru
                    and (not out or out.strip() == src.strip())
                ]
                stats.setdefault("incomplete_paragraphs", []).extend(missing_now)
                if budget is not None:
                    budget["degraded"] = budget.get("degraded", 0) + 1
                print(f"    · 本章 token 预算用尽（{(budget or {}).get('tok')} tok），"
                      f"收下现有译文并标「未译全」", flush=True)
                if _sakura:
                    return [_align_block(best_out[0], paras)], used
                return [align_quotes_with_source(z, s) for z, s in zip(best_out, paras)], used
            if budget is not None:
                budget["degraded"] = budget.get("degraded", 0) + 1
            stats["failed"] = stats.get("failed", 0) + 1
            return list(paras), []
        if stats["calls"] >= MAX_SEG_CALLS:
            if not stats.get("_capped"):
                print(f"    · 已达本段调用上限 {MAX_SEG_CALLS}，停止重试，暂留原文",
                      flush=True)
                stats["_capped"] = True
            stats["failed"] = stats.get("failed", 0) + 1
            return list(paras), []
        if _sakura:
            _block = "\n".join(paras)
            # 按**实际要用的端点**选模板：本地 Sakura 用它自己的格式；
            # DeepSeek（含兜底）用通用整章格式。这样同一套"整章"流程
            # 两种模型都能用，不需要用户切模式。
            _prov = (lnmodels.routes_for("translate") or [None])[0]
            _prov = getattr(_prov, "provider", "") if _prov else ""
            if _mode == "sakura" and _prov != "deepseek":
                prompt, used, sys_prompt = build_sakura_prompt(
                    meta, _block, prev_context)
            else:
                prompt, used, sys_prompt = build_chapter_prompt(
                    meta, _block, prev_context)
            if attempt > 0:
                prompt += "\n\n只输出译文：不要编号、不要解释、不要重复原文。"
            if hint:
                prompt += "\n\n" + hint
        else:
            prompt, used = build_chunk_prompt(meta, paras, start, prev_context)
            sys_prompt = system
            if attempt > 0:
                prompt += "\n\n注意：必须输出全部编号，一段不能少，也不要增加说明。"
            if hint:
                prompt += "\n\n" + hint
        _tok0 = stats["tok"]
        reply, _ = _llm_guard(sys_prompt, prompt, args, stats)
        if budget is not None:
            budget["tok"] = budget.get("tok", 0) + (stats["tok"] - _tok0)
        if _sakura:
            _txt = _plain_block(reply, "\n".join(paras))
            if not _txt:
                print(f"    · 空回复（{len(reply)} 字，前 60 字：{reply[:60]!r}）",
                      flush=True)
            out = [_txt]
            missing = [] if _txt else [start + 1]
        else:
            out, missing = parse_chunk_reply(reply, paras, start)
        # 先把"常见客套话残留"确定性换掉（零成本、零 token），再判质量。
        out = [clean_residual(x) if x else x for x in out]
        if passthru and not _sakura:
            # 分隔线这类段落：模型抄回什么不算数，一律用原文（对齐编号后再判质量）。
            out = [paras[i] if i in passthru and i < len(out) else v
                   for i, v in enumerate(out)]
            missing = [m for m in missing if (m - start - 1) not in passthru]
        if _sakura:
            joined = " ".join(v for v in out if v)
        else:
            joined = " ".join(v for i, v in enumerate(out)
                              if v and i not in passthru)
        # 记住"最像中文"的一版：预算用尽或最终失败时，宁可交付它 + 标未译全，
        # 也不要把整章打回原文（读者看到的是"整章没翻"，代价更大）。
        _sh = chinese_share(joined) if joined else 0.0
        if _sh > best_share:
            best_share, best_out, best_missing = _sh, list(out), list(missing)

        if missing:
            if getattr(args, "allow_missing", False):
                # --allow-missing：接受这次输出，缺失的段暂留日文原文，不再重试。
                # 记 partial（而不是 failed）：本章仍要写出给用户读，但不能冒充"译全"。
                print(f"    · 编号缺失 {len(missing)} 段（--allow-missing：接受，缺失处暂留原文）",
                      flush=True)
                for j, p in enumerate(paras):
                    if not out[j]:
                        out[j] = p          # 原文照留（不转引号，让人一眼看出这段没译）
                    else:
                        out[j] = align_quotes_with_source(out[j], p)
                stats["partial"] = stats.get("partial", 0) + 1
                stats.setdefault("incomplete_paragraphs", []).extend(missing)
                return out, used
            bad_lines += 1
            print(f"    · 第{attempt+1}次：编号缺失 {len(missing)} 段", flush=True)
            _log_guard("missing_ids", start=start, paras=len(paras), missing=len(missing),
                       depth=depth, calls=stats.get("calls"), tok=stats.get("tok"))
            continue
        # 除了字形（detect_chinese），再跟原文比一次：纯汉字串中日同形，
        # 只看字形分不出，但"和原文一模一样"就是回抄的铁证。
        _echoed = bool(joined) and "".join(joined.split()) == _src_all
        if not detect_chinese(joined) or _echoed:
            # 末次仍"不是中文"，但整段已以中文为主（只有零星的日文词没译）：
            # 收下。以前这里会继续二分重翻，实测能把一章烧成 19 次请求 / 3.8 万 token，
            # 而在读者眼里只是"卡住了"。译文里那点日文会在校对报告里露出来。
            if (not _echoed and attempt == MAX_TRY - 1
                    and chinese_share(joined) > 0.6):
                print(f"    · 第{attempt+1}次：仍有零星日文未译，但整段以中文为主，接受",
                      flush=True)
            else:
                print(f"    · 第{attempt+1}次：输出不是中文（可能抄回原文）", flush=True)
                _kana = count_kana(joined)
                _log_guard("not_chinese", start=start, paras=len(paras), depth=depth,
                           kana=_kana, kana_share=round(_kana / max(len(joined), 1), 4),
                           zh_share=round(chinese_share(joined), 3),
                           echoed=bool(_echoed), tok=stats.get("tok"),
                           calls=stats.get("calls"))
                bad_lines += 1
                hint = ("译文里混进了日文（人名/术语没翻）。请把每个日文词都译成中文；"
                        "人名/技能名按术语表，表里没有就音译或意译，不要留假名。")
                continue
        # ---- 质量兜底（引号外假名 / 原文没有的英文）----
        # 用户报的三个问题里两个属于这里：ございました 这类敬语残留、
        # 以及"突然冒出原文没有的英文"。只重试**一次**并给明确指令，
        # 且不进入二分（二分对付的是段落对不齐，不是用词残留）。
        _kana_out = kana_outside_quotes(joined)
        _eng = english_drift(joined, _src_all)
        # 英文只在**成句**时才算漂移（3 词以上）：品牌名/歌名/缩写（Lyrical Lily、
        # Premium Malts）本来就该保留，两词就重试会白白多花钱（老路的放大器）。
        _eng_bad = [e for e in _eng if len(e.split()) >= 3]
        if (_kana_out or _eng_bad) and not _quality_tried and attempt < MAX_TRY - 1:
            _quality_tried = True
            _log_guard("quality_retry", start=start, kana=_kana_out,
                       english=(_eng_bad or _eng)[:3], attempt=attempt + 1,
                       tok=stats.get("tok"))
            hint = ("译文里还有没翻译的日文" if _kana_out else "") + \
                   ("，以及原文里没有的英文" if _eng_bad else "") + \
                   "。要求：不要保留任何日文假名（敬语、语气词、助词、专有名词都不行，"
            hint += "必须音译或意译成中文）；原文没有的英文单词请译成中文，"
            hint += "原文本来就用英文的（品牌名/缩写）照抄即可。"
            print(f"    · 第{attempt+1}次：残留假名 {_kana_out} 个 / 英文漂移 {len(_eng)} 处，重试",
                  flush=True)
            bad_lines += 1
            continue

        # 「多行对白只译了第一行」是最难发现的漏译：段数、编号、中文校验全都过。
        # 用引号对数兜一层：原文这段有 N 处对白，译文却少于 N 处 → 重试一次，
        # 并在下一次的 prompt 里点名哪一段。仍然不满意就照实返回 + 打警告（不假装）。
        if _sakura:
            # 整块翻译没法逐段比对；退一层：对白总数少于原文 → 说明有对白被吞了。
            _sq = sum(p.count("「") for p in paras)
            # 输出可能用 “ ” / 『 』：只数「」会把正常译文误判成"漏光对白"，
            # 于是白重试（踩过：DeepSeek 兜底时对白 0/21，其实一句没少）。
            _oq = sum(v.count("「") + v.count("『") + v.count("“")
                      for v in out)
            if _oq < _sq and attempt < MAX_TRY - 1:
                # 本地小模型连续漏对白：别再拿同一块反复试（免费但永远不齐），
                # 直接让本章后续重试走云端（有兜底时）。这样"免费先试、真不行
                # 才花钱"，而不是把缺对白的译文献给读者。
                if (_prov and _prov != "deepseek" and attempt >= 1
                        and lnmodels.fallback_enabled()):
                    lnmodels.mark_primary_failed("translate")
                    print("    · 本地连续漏对白，本次重试改用云端", flush=True)
                hint = ("原文有多处对白，必须逐句全部译出，不许合并、不许省略。")
                print(f"    · 第{attempt+1}次：对白 {_oq}/{_sq} 处，疑似漏译，重试",
                      flush=True)
                bad_lines += 1
                continue
        susp = _missing_dialogue(paras, out)
        if susp and attempt < MAX_TRY - 1:
            _names = "、".join(str(start + i + 1) for i in susp)
            hint = (f"第 {_names} 段原文里有好几处对白（或好几行），必须**逐句全部译出**，"
                    f"不许省掉后几句、也不许压成一句。")
            print(f"    · 第{attempt+1}次：第 {_names} 段疑似漏译对白，重试", flush=True)
            bad_lines += 1
            continue

        # 校验通过后把引号**字形对齐到原文**（不统一、不替换体系）：每个 chunk
        # 是独立请求，模型会在这里漂移，而原文用哪种引号是作者的排版，译文照抄。
        if _sakura:
            return [_align_block(out[0], paras)], used
        return [align_quotes_with_source(z, s) for z, s in zip(out, paras)], used

    # 二分降级：拆两半分别翻（递归），只有多段时才做
    if len(paras) > 1 and depth < 4 and stats["calls"] < MAX_SEG_CALLS:
        mid = len(paras) // 2
        print(f"    · 连续失败，二分为 {mid} + {len(paras)-mid} 段", flush=True)
        left, used1 = robust_translate_paras(meta, paras[:mid], start, system,
                                             args, prev_context, stats, depth + 1,
                                             budget=budget)
        right, used2 = robust_translate_paras(meta, paras[mid:], start + mid, system,
                                              args, prev_context, stats, depth + 1,
                                              budget=budget)
        return left + right, list(dict.fromkeys(used1 + used2))

    if _sakura and best_out is not None and best_share > 0.5:
        # 整章翻译最后一次仍不完美（多半是某几行对白被合掉）：与其把整块
        # 打回日文原文（读者直接读不懂），不如收下这版中文并标「未译全」，
        # 下次重试只补这一块。质量下限由 chinese_share 把着。
        print("    · ⚠ 仍不完美（见上面的对白计数），但已是中文：收下并标「未译全」",
              flush=True)
        stats["partial"] = stats.get("partial", 0) + 1
        stats.setdefault("incomplete_paragraphs", []).extend(
            start + i + 1 for i, p in enumerate(paras) if p)
        return list(best_out), []

    # 单段还失败：保留原文并明确告知，不静默塞进译文
    print("    · ⚠ 该段翻译失败，暂留原文（可稍后重试该章）", flush=True)
    stats["failed"] = stats.get("failed", 0) + 1
    stats.setdefault("incomplete_paragraphs", []).extend(
        start + i + 1 for i, p in enumerate(paras)
        if p and i not in passthru)
    return list(paras), []


def _translate_chapter_impl(slug: str, idx: int, meta: dict, args,
                            progress=None) -> bool:
    _reset_chapter_route()
    raw = open(chapter_path(slug, idx, "raw"), encoding="utf-8").read()
    lines = raw.split("\n")
    paras = split_paragraphs(lines)
    if translate_mode() in ("sakura", "chapter"):
        # 整章一块（超长才在段落边界切块）：上下文完整，译文才接得上；
        # 缓存按块存，重试只补没译出来的那一块。
        _prov0 = (lnmodels.routes_for("translate") or [None])[0]
        _limit = (DEEPSEEK_CHAPTER_CHARS
                  if getattr(_prov0, "provider", "") == "deepseek"
                  else CHAPTER_CHARS)
        ranges = _block_ranges(paras, _limit)
    else:
        ranges = segment(paras)
    system = build_system_prompt(meta)
    glossary = meta.setdefault("glossary", {})

    cache_path = os.path.join(novel_dir(slug), "cache", f"{idx:04d}.json")
    cache = load_json(cache_path, {})
    # 原文更新后旧段缓存必须失效：缓存 key 只有段范围，光看 a-b 会把
    # 旧版本原文的译文继续套到新原文上（不是跨书，但同样是“错配”）。
    # Hash the actual source bytes.  The decoded string normalizes CRLF to LF,
    # but availability checks later hash the file itself; mixing those two
    # representations made every CRLF source look changed on Windows.
    raw_sha = _sha256_file(chapter_path(slug, idx, "raw"))
    old_sha = cache.get("_raw_sha256")
    if old_sha and old_sha != raw_sha and not getattr(args, "force", False):
        print("  · 原文已更新，旧段缓存失效，本章重新翻译", flush=True)
        cache = {}
    cache["_raw_sha256"] = raw_sha
    out_parts: list[str] = []
    added_terms: list[str] = []
    usage_total = 0
    usage_in = 0
    usage_out = 0
    incomplete_paragraphs: list[int] = []
    budget_exhausted = False
    prev_context = ""
    failed_chunks = 0
    partial_chunks = 0
    # 三维守门员的第三维：整章 token 预算（跨 chunk、跨二分递归共享）。
    budget = {"tok": 0, "limit": MAX_CHAPTER_TOK, "degraded": 0}

    for ci, (a, b) in enumerate(ranges):
        chunk = paras[a:b]
        if all(x == "" for x in chunk):
            out_parts.append("\n" * (b - a))
            continue
        if progress is not None:
            try:
                progress(ci + 1, len(ranges))
            except Exception:  # noqa: BLE001 — 上报失败绝不影响翻译
                pass
        ck = f"{a}-{b}"
        # force 时忽略段级缓存：--force 是"重译"，命中旧缓存等于没重译
        # （踩过：改了术语后 --force，内容全是旧缓存，术语没生效还以为生效了）
        if ck in cache and not args.force:
            # 旧缓存里的引号可能与原文不一致（各 chunk 各写各的），读出来对齐一遍，
            # 随后 save_json 会把缓存写成与原文一致的版本。
            if translate_mode() in ("sakura", "chapter"):
                translated = [_align_block(v, chunk) for v in cache[ck]]
            else:
                translated = [align_quotes_with_source(z, s)
                              for z, s in zip(cache[ck], chunk)]
            prev_context = "".join(translated).replace("\n", " ")[-400:]
        elif args.dry_run:
            print(f"  [dry-run] 段 {ci+1}/{len(ranges)} 行 {a+1}-{b} 共 {sum(len(x) for x in chunk)} 字")
            prev_context = ""
            continue
        else:
            prompt, used = build_chunk_prompt(meta, chunk, a, prev_context)
            print(f"  段 {ci+1}/{len(ranges)}（{sum(len(x) for x in chunk)} 字"
                  f"，注入术语 {len(used)} 个）…", end="", flush=True)
            stats = {"tok": 0, "calls": 0, "input": 0, "output": 0}
            translated, used2 = robust_translate_paras(
                meta, chunk, a, system, args, prev_context, stats, budget=budget)
            added_terms.extend(used2)
            usage_total += stats["tok"]
            usage_in += int(stats.get("input", 0) or 0)
            usage_out += int(stats.get("output", 0) or 0)
            incomplete_paragraphs.extend(stats.get("incomplete_paragraphs") or [])
            budget_exhausted = budget_exhausted or bool(stats.get("budget_exhausted"))
            if stats.get("failed"):
                # 有分段失败 → **不缓存**（否则原文/坏译文会被永久复用、永不重译）
                if translate_mode() in ("sakura", "chapter"):
                    # 逐段模式下失败已经是"单段"粒度（别的一段都好好的）：
                    # 为一行卡住整章不值得 —— 保留原文、标「未译全」、本章照常写出，
                    # 下次重试只补这一段（段缓存里其余段都在）。
                    # 踩过：148/158 段都译好了，只因「排除。」回抄被判失败，
                    # 整章永不落盘，读者干等。
                    partial_chunks += 1
                    incomplete_paragraphs.extend(x + 1 for x in range(a, b))
                    print(f" ⚠（{stats['tok']} tok，{stats['calls']} 次请求，"
                          f"该段暂留原文，本章仍写出并标「未译全」）")
                else:
                    failed_chunks += 1
                    print(f" ⚠（{stats['tok']} tok，{stats['calls']} 次请求，"
                          f"有段落失败，暂不缓存）")
            elif stats.get("partial"):
                # --allow-missing 留了缺号段：本章仍写出，但**不缓存**该段，
                # 以便下次重试能补齐（缓存了 = 缺号永久化）。
                partial_chunks += 1
                print(f" ⚠（{stats['tok']} tok，{stats['calls']} 次请求，"
                      f"{stats['partial']} 段缺号暂留原文，暂不缓存）")
            else:
                cache[ck] = translated
                print(f" ok（{stats['tok']} tok，{stats['calls']} 次请求）")
            added_terms.extend(used)
            prev_context = "".join(translated).replace("\n", " ")[-400:]
        out_parts.append("\n".join(translated))

    if args.dry_run:
        _CHAPTER_RESULT.value = {"ok": True, "dry_run": True}
        return True

    out_dir = novel_dir(slug)
    name = meta["episodes"][idx]["title"] or f"第{idx+1}话"

    if failed_chunks:
        # 有分段失败：**不落盘**、不推进 translated_through、不记成功历史。
        # 只把成功分段写进缓存（下次重试少花钱），并标记本章"部分失败"待重试。
        # 踩过：失败时返回日文原文当译文 → 落盘 + 缓存 + 计入"已译"，
        # 之后哪怕修好也不会重译，坏译文被永久复用。
        save_json(cache_path, cache)
        prog = meta.setdefault("progress", {})
        inc = list(prog.get("incomplete") or [])
        if idx + 1 not in inc:
            inc.append(idx + 1)
        prog["incomplete"] = inc
        save_meta(slug, meta)
        print(f"  ⚠ 第 {idx+1} 章有 {failed_chunks} 个分段翻译失败：本章暂不落盘"
              f"（原文保留），成功分段已缓存，稍后重试只补失败段。", flush=True)
        with open(os.path.join(out_dir, "history.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "at": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "translate_failed",
                "chapter": idx + 1, "title": name, "failed_chunks": failed_chunks,
                "tokens": usage_total}, ensure_ascii=False) + "\n")
        _fail_provider, _fail_model, _fail_route = _chapter_route_summary()
        _CHAPTER_RESULT.value = {
            "ok": False,
            "chapter": idx + 1,
            "failed_chunks": failed_chunks,
            "tokens": {"input": usage_in, "output": usage_out},
            "incomplete_paragraphs": sorted(set(incomplete_paragraphs)),
            "budget_exhausted": budget_exhausted,
            "cost": {
                "amount": round(float(_fail_route.get("cost") or 0), 8),
                "currency": "CNY",
                "estimated": True,
            },
        }
        return False

    text = "\n".join(out_parts)
    _before_dedupe = text
    text = _dedupe_repeated_output(text, raw)
    if text != _before_dedupe:
        print("  · 已去掉模型复读的句子/段落", flush=True)
    # 残留假名：允许"夹着零星日文"是权衡，但必须**可计量** —— 否则"接受"
    # 会悄悄退化成"没人管"。这个数字进 meta（`progress.kana_residue`）、
    # 进 history、并在 >0 时打一行结构化日志，`residue` 子命令可直接汇总。
    kana_left = kana_outside_quotes(text)
    if kana_left:
        _res = meta.setdefault("progress", {}).setdefault("kana_residue", {})
        _res[str(idx + 1)] = kana_left
        _log_guard("kana_residue", chapter=idx + 1, kana=kana_left,
                   tok=usage_total, chars=len(text))
        print(f"  · 本章残留假名 {kana_left} 个（已标记，可校对时补）", flush=True)
    else:
        _res = meta.setdefault("progress", {}).setdefault("kana_residue", {})
        _res.pop(str(idx + 1), None)
    # 先写旁车，再原子替换正文。若进程死在这两步之间，旧/新正文都会与
    # 旁车里的 content_sha256 对不上，于是被判为不可读待修，而不会冒充完成。
    partial_reason = None
    if incomplete_paragraphs:
        partial_reason = ("budget_exhausted" if budget_exhausted
                          else "provider_incomplete")
    _route_provider, _route_model, _route_info = _chapter_route_summary()
    _route_cost = None
    if _route_provider:
        _route_cost = {"amount": round(
            float(_route_info.get("cost") or 0), 8),
            "currency": lnmodels.currency(), "estimated": True}
    meta_record = chapter_meta_record(
        slug, idx, meta, args,
        text=text,
        raw_sha=raw_sha,
        tokens_in=usage_in,
        tokens_out=usage_out,
        incomplete_paragraphs=incomplete_paragraphs,
        incomplete_reason=partial_reason,
        provider_name=_route_provider,
        model_id=_route_model,
        cost=_route_cost,
    )
    save_json(chapter_meta_path(slug, idx), meta_record)
    save_text(chapter_path(slug, idx), text)

    # 成功：清掉可能残留的"部分失败"标记；但 --allow-missing 的缺号段要**保留**
    # incomplete（写出 ≠ 译全），与 #4 一致——原文不许冒充"译全"。
    prog = meta.setdefault("progress", {})
    inc = list(prog.get("incomplete") or [])
    if partial_chunks:
        if idx + 1 not in inc:
            inc.append(idx + 1)
        prog["incomplete"] = inc
        print(f"  ⚠ 第 {idx+1} 章有 {partial_chunks} 个分段缺号（暂留原文）：已写出并标记"
              f"「未译全」，稍后重试可补齐。", flush=True)
    elif idx + 1 in inc:
        prog["incomplete"] = [c for c in inc if c != idx + 1]

    # 汇总文件由分章文件重建（幂等）——直接 append 会在重译时产生重复章节。
    # 刚写的这一章用内存正文，不依赖文件签名（低精度 mtime 可能尚未变化）。
    rebuild_novel_md(slug, meta, override_chapter=idx, override_text=text)

    save_json(cache_path, cache)
    meta["progress"]["translated_through"] = max(
        meta["progress"].get("translated_through", 0), idx + 1)
    save_meta(slug, meta)

    with open(os.path.join(out_dir, "history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": "translate_partial" if partial_chunks else "translate",
            "chapter": idx + 1, "title": name, "tokens": usage_total,
            "kana_residue": kana_left,
            "tokens_input": usage_in,
            "tokens_output": usage_out,
            "incomplete_reason": partial_reason,
            "glossary_terms_injected": sorted(set(added_terms)),
        }, ensure_ascii=False) + "\n")
    _CHAPTER_RESULT.value = {
        "ok": True,
        "chapter": idx + 1,
        "partial": bool(incomplete_paragraphs),
        "budget_exhausted": budget_exhausted,
        "incomplete_paragraphs": sorted(set(incomplete_paragraphs)),
        "tokens": {"input": usage_in, "output": usage_out},
        "cost": dict(meta_record["cost"]),
    }
    return True


def translate_chapter(slug: str, idx: int, meta: dict, args,
                      progress=None) -> bool:
    """公共入口：先做作品身份硬校验，再按书加锁执行翻译。

    `progress(done, total)` 只用于把"章内进度"报给调用方（Web 服务显示
    「第 N 章 · 段 x/y」，让读者知道长章还在动）。核心翻译不依赖它。
    """
    import lnreview  # 延迟导入：lnreview 也会延迟导入本模块
    lnreview.ensure_work_id(meta, slug)
    with novel_lock(slug):
        return _translate_chapter_impl(slug, idx, meta, args, progress=progress)


def cmd_next(args) -> None:
    """按需翻译：从上次翻到的地方往后翻 N 章（增量）。"""
    meta = load_meta(args.slug)
    eps = meta["episodes"]
    done = meta["progress"].get("translated_through", 0)
    start = done
    if args.from_chapter:
        start = max(0, args.from_chapter - 1)
    end = min(start + args.count, len(eps))
    if start >= len(eps):
        print("全部译完了。")
        return

    if args.dry_run:
        print("干跑：只展示分段，不调用模型、不抓原文、不写盘。")
        for i in range(start, end):
            if has_complete_translation(args.slug, i) and not args.force:
                print(f"#{i+1} 已有完整译文，正式运行时会跳过")
                continue
            if not os.path.exists(chapter_path(args.slug, i, "raw")):
                print(f"#{i+1} 尚无原文；正式运行时会先抓取")
                continue
            print(f"#{i+1} {eps[i]['title'][:34]}")
            translate_chapter(args.slug, i, meta, args)
        print("干跑完成（未调用模型、未写盘）。")
        return

    durable = None
    store = None
    if not args.dry_run:
        import lnjobs
        store = lnjobs.STORE
        store.reconcile_startup()
        planned = [i + 1 for i in range(start, end)
                   if args.force or not has_complete_translation(args.slug, i)]
        if planned:
            identity = job_identity(args.slug, planned, meta, args)
            durable = store.create(
                slug=args.slug,
                target=identity["target"],
                model_provider=identity["model_provider"],
                model_role=identity["model_role"],
                model_id=identity["model_id"],
                translation_config_hash=identity["translation_config_hash"],
                idempotency_key=identity["idempotency_key"],
                requested={"count": args.count, "reason": "cli-next",
                           "after": start + 1, "fill": False,
                           "ceiling": end},
                source_entries=identity["sources"],
            )
            durable = store.update(
                durable["job_id"], status="running",
                chapter_numbers=planned,
                remaining_chapters=planned,
                completed_chapters=[],
                partial_chapters=[],
            )

    # 需要就先抓原文（与服务端 worker 共用同一实现）
    try:
        if end > meta["progress"].get("fetched_through", 0):
            print(f"先抓原文到第 {end} 章…")
            ensure_raw(args.slug, meta, end)
    except (Exception, SystemExit) as ex:
        if durable and store:
            store.update(
                durable["job_id"], status="provider_error",
                error=f"抓取原文失败：{type(ex).__name__}: {ex}")
        raise

    completed: list[int] = []
    remaining = list((durable or {}).get("remaining_chapters") or [])
    partials: list[int] = []
    terminal = ("done", None)
    usage = {"input": 0, "output": 0}
    cost = {"amount": 0, "currency": "CNY", "estimated": True}
    try:
        for i in range(start, end):
            if has_complete_translation(args.slug, i) and not args.force:
                print(f"#{i+1} 已有译文，跳过")
                if i + 1 in remaining:
                    remaining.remove(i + 1)
                continue
            print(f"翻译 #{i+1} {eps[i]['title'][:34]}")
            if durable and store:
                store.update(durable["job_id"],
                             message=f"正在翻译第 {i+1} 章")
            if translate_chapter(args.slug, i, meta, args):
                result = last_chapter_result()
                meta = load_meta(args.slug)      # 重新读，translate_chapter 写过
                completed.append(i + 1)
                if i + 1 in remaining:
                    remaining.remove(i + 1)
                if result.get("partial"):
                    partials.append(i + 1)
                tokens = result.get("tokens") or {}
                usage["input"] += int(tokens.get("input", 0) or 0)
                usage["output"] += int(tokens.get("output", 0) or 0)
                cost["amount"] = round(
                    float(cost["amount"])
                    + float((result.get("cost") or {}).get("amount", 0) or 0),
                    8)
                if durable and store:
                    durable = store.update(
                        durable["job_id"], status="running",
                        completed_chapters=completed,
                        remaining_chapters=remaining,
                        partial_chapters=partials,
                        usage=usage, cost=cost,
                        message=f"已译第 {i+1} 章，继续")
                if result.get("budget_exhausted"):
                    terminal = (
                        "budget_exhausted",
                        f"第 {i+1} 章触发 token 预算上限；已有译文可读")
                    break
                _job_limit = lnmodels.job_budget()
                if (_job_limit > 0
                        and float(cost.get("amount", 0)) >= _job_limit):
                    terminal = (
                        "budget_exhausted",
                        f"本任务费用已达 {float(cost['amount']):.4f} "
                        f"{cost['currency']}（上限 {_job_limit:.2f}）")
                    break
            else:
                terminal = (
                    "provider_error",
                    f"第 {i+1} 章有段落翻译失败（原文保留，可重试）")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        if durable and store:
            store.update(
                durable["job_id"], status="interrupted",
                error="命令行翻译被中断；等待确认恢复",
                completed_chapters=completed,
                remaining_chapters=remaining,
                partial_chapters=partials)
        print("\n翻译已中断；进度和已完成章节已保留。", file=sys.stderr)
        raise SystemExit(130)
    except (Exception, SystemExit) as ex:
        if durable and store:
            status = ("budget_exhausted"
                      if isinstance(ex, lnmodels.BudgetExceeded)
                      else "provider_error")
            store.update(
                durable["job_id"], status=status,
                error=f"{type(ex).__name__}: {ex}",
                completed_chapters=completed,
                remaining_chapters=remaining,
                partial_chapters=partials)
        raise
    if durable and store:
        final_status = terminal[0]
        if final_status == "done" and partials:
            final_status = "partial"
        store.update(
            durable["job_id"], status=final_status, error=terminal[1],
            completed_chapters=completed,
            remaining_chapters=remaining,
            partial_chapters=partials,
            usage=usage, cost=cost,
            message=(terminal[1] or
                     ("部分译完，可稍后补齐" if final_status == "partial"
                      else "命令翻译完成")))
    if terminal[0] in ("provider_error", "budget_exhausted"):
        print(f"\n未完成：{terminal[1]}", file=sys.stderr)
        if remaining:
            print("待处理章节：" + "、".join(str(c) for c in remaining),
                  file=sys.stderr)
    else:
        print(f"\n完成。当前进度：已译到第 {meta['progress']['translated_through']} 章"
              f" / 共 {len(eps)} 章")
    print(f"译文：{os.path.join(novel_dir(args.slug), 'novel.md')}")

    if terminal[0] in ("provider_error", "budget_exhausted"):
        return
    if args.summary:
        # Namespace 必须带 force：cmd_summary 会读 args.force，
        # 漏了它 `next --summary` 会 AttributeError（踩过）。
        cmd_summary(argparse.Namespace(slug=args.slug, model=AUX_MODEL,
                                       from_chapter=start + 1, count=end - start,
                                       force=args.force))


def cmd_summary(args) -> None:
    """为已翻译的章节生成梗概，供后续章节注入上下文。"""
    meta = load_meta(args.slug)
    eps = meta["episodes"]
    start = max(0, args.from_chapter - 1)
    end = min(start + args.count, len(eps))
    system = ("你在为一部日文轻小说的中文译本整理'故事记忆'，供后续翻译保持连贯。"
              "请输出简洁的中文梗概，200 字以内，只写剧情要点："
              "出现的人物、关键事件、地点、新出现的专有名词。不要评价，不要剧透后文。")
    for i in range(start, end):
        if not has_translation(args.slug, i):
            continue
        if str(i + 1) in (meta.get("summaries") or {}) and not args.force:
            continue
        text = open(chapter_path(args.slug, i), encoding="utf-8").read()
        user = f"第{i+1}话《{eps[i]['title']}》译文：\n\n{text[:6000]}"
        print(f"  梗概 #{i+1} …", end="", flush=True)
        reply, usage = call_llm(
            system, user, args.model, 0.3, role="auxiliary")
        meta.setdefault("summaries", {})[str(i + 1)] = reply.strip()
        save_meta(args.slug, meta)
        print(f" ok（{usage.get('total_tokens',0)} tok）")


def cmd_review(args) -> None:
    """校对已译章节：默认只报告，--fix 才写回。"""
    import lnreview
    meta = load_meta(args.slug)
    total = len(meta.get("episodes") or [])
    if args.all:
        todo = [i for i in range(total) if has_translation(args.slug, i)]
    elif args.chapter:
        todo = [max(0, min(args.chapter - 1, total - 1))]
    else:
        if args.from_chapter is None:
            # 不带范围时校对“最近译好的一章”，这是用户最可能想复查的对象。
            have = [i for i in range(total) if has_translation(args.slug, i)]
            todo = have[-1:] if have else []
        else:
            start = max(0, args.from_chapter - 1)
            todo = [i for i in range(start, min(start + (args.count or 1), total))
                    if has_translation(args.slug, i)]
    if not todo:
        die("没有可校对的已译章节（先翻译，或用 --chapter 指定）")
    print(f"校对《{meta.get('title') or args.slug}》：{len(todo)} 章"
          f"（{'AI + ' if args.llm else ''}规则）")
    blockers = 0
    for i in todo:
        try:
            rep = lnreview.review_chapter(
                args.slug, i, meta, use_llm=(args.llm or args.fix_ai),
                model=args.model, temperature=args.temperature,
                fix=args.fix or args.fix_ai,
                learn=not args.no_learn)
        except (FileNotFoundError, ValueError) as e:
            print(f"  ⚠ 第 {i+1} 章跳过：{e}")
            continue
        c = rep["counts"]
        blockers += c["blocker"]
        print(f"  第 {i+1} 章：阻断 {c['blocker']} · 建议 {c['suggestion']}"
              f" · 观察 {c['observation']}"
              + (f" · 新增经验 {len(rep.get('lessons_added') or [])}" if
                 rep.get("lessons_added") else ""))
        if rep.get("fix"):
            f = rep["fix"]
            if f.get("changed"):
                print(f"    已修订 {len(f.get('actions') or [])} 处，"
                      f"备份：{f.get('backup')}")
            else:
                print(f"    {f.get('note') or '没有可自动修复项'}")
        print(f"    报告：{lnreview.report_paths(args.slug, i + 1)[1]}")
    if blockers:
        print(f"\n仍有 {blockers} 个阻断项；报告里已列出原文依据。")
        if args.fail_on_blocker:
            sys.exit(2)


def cmd_lessons(args) -> None:
    """查看本书已经沉淀的翻译经验。"""
    meta = load_meta(args.slug)
    items = meta.get("lessons") or []
    if not isinstance(items, list):
        items = []
    if not items:
        print("这本书还没有沉淀经验。用 review 或 learn --lesson 添加。")
        return
    print(f"《{meta.get('title') or args.slug}》翻译经验（{len(items)} 条，"
          f"只适用于本书）")
    for i, x in enumerate(items[-args.limit:], max(1, len(items) - args.limit + 1)):
        if isinstance(x, dict):
            print(f"  {i}. {x.get('text','')}")
            print(f"     第{x.get('chapter') or '?'}章 · {x.get('source','')}")
        else:
            print(f"  {i}. {x}")


def cmd_learn(args) -> None:
    """记录一条术语/风格纠正，永久生效。"""
    meta = load_meta(args.slug)
    term_changes = []
    glossary_history = meta.setdefault("glossary_history", [])
    if args.term:
        glossary = meta.setdefault("glossary", {})
        for pair in args.term:
            if "=" not in pair:
                die(f"术语要写成 日文=中文 的形式，收到：{pair}")
            jp, zh = pair.split("=", 1)
            jp, zh = jp.strip(), zh.strip()
            old = glossary.get(jp)
            glossary[jp] = zh
            term_changes.append({"jp": jp, "old": old, "new": zh})
            if old and old != zh:
                glossary_history.append({
                    "jp": jp, "old": old, "new": zh,
                    "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "learn",
                })
                print(f"  ⚠ 术语变更：{jp} {old} → {zh}（已记入 history）")
            print(f"  术语：{jp.strip()} => {zh.strip()}")
    if args.character:
        for pair in args.character:
            if "=" not in pair:
                die(f"人物要写成 名字=描述 的形式，收到：{pair}")
            n, d = pair.split("=", 1)
            name = n.strip()
            bits = d.split("|")
            info = {"desc": bits[0].strip()}
            keymap = {"语气": "voice", "称呼": "address", "词汇": "lexicon",
                      "词汇习惯": "lexicon", "句法": "syntax", "句法习惯": "syntax",
                      "本卷": "volume", "本卷时间点": "volume", "别名": "aliases",
                      "注意": "notes"}
            for bit in bits[1:]:
                if ":" not in bit:
                    continue
                k, v = bit.split(":", 1)
                k, v = keymap.get(k.strip(), k.strip()), v.strip()
                if k == "aliases":
                    info["aliases"] = [x.strip() for x in v.split(",") if x.strip()]
                elif k in ("voice", "address", "lexicon", "syntax", "volume", "notes"):
                    info[k] = v
            meta.setdefault("characters", {})[name] = info
            print(f"  人物：{name} = {info}")
    if args.style:
        meta.setdefault("style", {})["general"] = args.style
        print(f"  风格：{args.style}")
    if getattr(args, "narrator", None):
        meta.setdefault("style", {})["narrator"] = args.narrator
        print(f"  叙述者滤镜：{args.narrator}")
    if args.honorifics:
        meta.setdefault("style", {})["honorifics"] = args.honorifics
        print(f"  称谓：{args.honorifics}")
    if args.note:
        meta.setdefault("style", {})["notes"] = args.note
        print(f"  注意：{args.note}")
    if getattr(args, "medium", None):
        meta.setdefault("style", {})["medium"] = args.medium
        print(f"  发布媒介：{args.medium}")
    if getattr(args, "guide", None):
        try:
            with open(args.guide, encoding="utf-8") as f:
                guide = f.read().strip()
        except OSError as e:
            die(f"读不了准则文件：{args.guide}（{e}）")
        if not guide:
            die(f"准则文件是空的：{args.guide}")
        meta.setdefault("style", {})["guide"] = guide
        print(f"  补充准则：已载入 {len(guide)} 字（{args.guide}）")
    if getattr(args, "lesson", None):
        import lnreview
        added = lnreview.add_lessons(args.slug, meta, args.lesson,
                                     source="manual")
        for x in added:
            print(f"  经验：{x}")
    save_meta(args.slug, meta)
    with open(os.path.join(novel_dir(args.slug), "history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "learn",
                            "term": args.term, "character": args.character,
                            "term_changes": term_changes,
                            "style": args.style, "honorifics": args.honorifics,
                            "narrator": getattr(args, "narrator", None),
                            "medium": getattr(args, "medium", None),
                            "guide": getattr(args, "guide", None),
                            "lesson": getattr(args, "lesson", None),
                            "note": args.note}, ensure_ascii=False) + "\n")
    print("\n已保存。之后的翻译会自动带上这些设定。")


_TITLE_NUM = re.compile(
    r"^第\s*([0-9０-９]+)\s*([話话章節节部篇巻卷])$")
_TITLE_FIXED = {
    "閑話": "闲话", "幕間": "幕间", "外伝": "外传",
    "プロローグ": "序章", "エピローグ": "终章",
    "あとがき": "后记", "後書き": "后记",
    "序章": "序章", "終章": "终章",
}


def _to_han_digits(s: str) -> str:
    table = {ord("０") + i: str(i) for i in range(10)}
    return (s or "").translate(table)


def rule_translate_title(title: str) -> str | None:
    """纯编号/固定词的章节名直接映射（不花 token）。

    只处理**整条标题**就是「第12話」「閑話」这种情况。带正文的标题
    （「第1話　追放される」）仍交给模型 —— 硬拆前缀再拼回去只会让编号
    和标题错位，省下的那点 token 不值这个风险。
    """
    s = (title or "").strip()
    if not s:
        return None
    m = _TITLE_NUM.match(s)
    if m:
        n = _to_han_digits(m.group(1))
        try:
            n = str(int(n))
        except ValueError:
            return None
        kind = {"話": "话", "话": "话", "節": "节", "节": "节",
                "巻": "卷", "卷": "卷"}.get(m.group(2), m.group(2))
        return f"第{n}{kind}"
    return _TITLE_FIXED.get(s)


def cmd_stale(args) -> None:
    """列出（并可按需重翻）用旧术语表翻过的章节。

    为什么不是「术语表一变就全书重翻」：那会花掉整本书的钱。auto-novel 的
    做法是把**该章实际用到的术语**算进指纹，只有指纹变了的章才算过期。
    """
    meta = load_meta(args.slug)
    total = len(meta.get("episodes") or [])
    rows: list[int] = []
    for i in range(total):
        if not has_translation(args.slug, i):
            continue
        if not chapter_glossary_stale(args.slug, i, meta):
            continue
        if args.term:
            try:
                with open(chapter_path(args.slug, i, "raw"),
                          encoding="utf-8") as f:
                    if args.term not in f.read():
                        continue
            except OSError:
                continue
        rows.append(i + 1)
    if not rows:
        print("没有译名过时的章节。")
        return
    head = "、".join(str(x) for x in rows[:30])
    print(f"译名可能过时：{len(rows)} 章" +
          (f"（{head}{'…' if len(rows) > 30 else ''}）" if head else ""))
    if not args.retranslate:
        print(f"\n只报告，没有花 token。要重翻：加 --retranslate"
              f"（默认最多 {args.limit} 章，--limit 可调）。")
        return
    todo = rows[:max(1, int(args.limit))]
    print(f"\n开始重翻 {len(todo)} 章（force，新译文覆盖旧译文）…")
    ok: list[int] = []
    failed: list[int] = []
    for ch in todo:
        print(f"\n=== 第 {ch} 章 ===")
        ns = argparse.Namespace(
            slug=args.slug, count=1, from_chapter=ch, force=True,
            summary=False, dry_run=False, allow_missing=False,
            model=args.model, temperature=0.3)
        try:
            done = translate_chapter(
                args.slug, ch - 1, load_meta(args.slug), ns)
        except SystemExit:
            raise                       # die() 的退出要原样向上传
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ 第 {ch} 章重翻异常：{type(e).__name__}: {e}")
            done = False
        (ok if done else failed).append(ch)
    print(f"\n重翻结束：成功 {len(ok)}/{len(todo)} 章。")
    if failed:
        # 不能报「完成」：失败章的旧译文还在盘上，过期提示也还会亮。
        print("未成功：" + "、".join(f"第 {x} 章" for x in failed)
              + "（旧译文保留）。可稍后重试："
              f"python3 lntrans.py stale {args.slug} --retranslate")
    else:
        print(f"复查：python3 lntrans.py stale {args.slug}")


_KATAKANA = re.compile(r"[\u30A0-\u30FF]{2,}")
_TERM_STOP = {
    "プロローグ", "エピローグ", "サー", "アー", "オー", "ハー", "フー",
    "ドキ", "キュン", "ゴゴゴ", "ザワ", "ワイ", "ヤバ",
}


def cmd_terms(args) -> None:
    """按片假名频次找候选术语（0 token，学自 auto-novel 的工具箱）。

    我们的 `names` 找的是「同一个日文名被译成多种写法」；这个命令补的是
    「哪些词值得进术语表」—— 技能名、地名、组织名往往模型不会主动报。
    """
    meta = load_meta(args.slug)
    counter: dict[str, int] = {}
    scanned = 0
    for i, _ep in enumerate(meta.get("episodes") or []):
        try:
            with open(chapter_path(args.slug, i, "raw"),
                      encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            continue
        scanned += 1
        for word in _KATAKANA.findall(raw):
            if len(word) < max(2, int(args.min)):
                continue
            if word in _TERM_STOP:
                continue
            if word in (meta.get("glossary") or {}):
                continue
            counter[word] = counter.get(word, 0) + 1
    rows = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    rows = [r for r in rows if r[1] >= max(1, int(args.count))]
    rows = rows[:max(1, int(args.top))]
    if args.json:
        print(json.dumps(dict(rows), ensure_ascii=False, indent=2))
        return
    print(f"扫描 {scanned} 章，出现 ≥{args.count} 次的片假名词："
          f"{len(rows)} 个")
    for word, n in rows:
        print(f"{n:5d}  {word}")
    if rows:
        print("\n加进术语表（之后新翻的章节生效；旧章节用 stale 查）：")
        print(f"  python3 lntrans.py learn {args.slug} --term "
              f"{rows[0][0]}=中文译名")


def cmd_titles(args, upto: int | None = None) -> None:
    """批量把日文章节名翻成中文（一次请求搞定，很便宜）。

    目录里是「第1話　包丁しか作れないおっさん、工房を追放される」这种日文，
    对不懂日语的读者毫无意义，必须给出中文标题。

    `upto`：只翻前 N 章的标题（Web 服务自动翻译时用 —— 读都没读到第 200 章，
    没必要一次把 200 个标题都翻了）。None = 全翻（CLI 默认）。
    """
    meta = load_meta(args.slug)
    eps = meta["episodes"]
    zh = meta.setdefault("zh_titles", {})
    if "book" not in zh and meta.get("title") and not args.no_book:
        # 书名也一起翻——书架/阅读页显示日文长标题对中文读者没有意义
        print("→ 翻译书名 …", end="", flush=True)
        bt, bu = call_llm(
            "把下面的日文轻小说书名翻成简体中文。只输出中文书名，"
            "不要书名号、不要引号、不要解释。",
            meta["title"], args.model, 0.2, role="auxiliary")
        zh["book"] = bt.strip().strip('《》「」"\'')
        save_meta(args.slug, meta)
        print(f" ok → {zh['book']}")

    scope = eps[:upto] if upto else eps
    todo = [(i, e) for i, e in enumerate(scope)
            if e.get("title") and str(i + 1) not in zh]
    if not todo:
        print("章节名都已翻译。")
        return

    # 两笔省 token（学自 auto-novel 的元数据翻译）：
    #   1) 「第12話」「閑話」这类纯编号/固定词直接规则映射，0 token；
    #   2) 同名标题只翻一次，再映射回所有章。网文里重复标题非常多。
    by_title: dict[str, list[int]] = {}
    for i, e in todo:
        by_title.setdefault(e["title"], []).append(i)
    remaining: dict[str, list[int]] = {}
    for title, idxs in by_title.items():
        fixed = rule_translate_title(title)
        if fixed:
            for i in idxs:
                zh[str(i + 1)] = fixed
        else:
            remaining[title] = idxs
    if not remaining:
        save_meta(args.slug, meta)
        print(f"章节名全部按规则译好（0 token，{len(todo)} 章）。")
        return

    uniq = list(remaining)
    system = ("你在为一部日文轻小说翻译章节标题。"
              "输出简体中文标题，保留「第N话」的编号格式，"
              "不要加书名号、不要加引号、不要解释。每行一个，编号与输入一致。")
    lines = [f"#{k + 1}:{t}" for k, t in enumerate(uniq)]
    user = "\n".join(lines) + "\n\n请输出同样编号的中文标题，每行一个。"
    print(f"→ 翻译 {len(todo)} 个章节名（去重后 {len(uniq)} 个）…",
          end="", flush=True)
    reply, usage = call_llm(
        system, user, args.model, 0.2, role="auxiliary")
    got_titles: dict[str, str] = {}
    for line in reply.split("\n"):
        # 宽松一点：模型可能输出 "#1:标题"、"1.标题"、"1、标题"、"**1. 标题**"。
        # 踩过：只认 "#N:" 时，模型换个写法就整批丢掉 —— 而且命令**照样报 ok**，
        # 看起来像成功（用户看到的是"目录还是日文"）。
        line = line.strip().lstrip("*#-• ").strip()
        m = re.match(r"^(\d+)\s*[.、:：)）]?\s*(.+)$", line)
        if not m:
            # 模型经常直接抄输入里的"第1話"编号风格（实测就是这样）
            m = re.match(r"^第\s*(\d+)\s*[話话]\s*[　 :：]*\s*(.+)$", line)
        if m:
            k, v = m.group(1), m.group(2).strip().strip("「」“”\"'`《》 ")
            try:
                n = int(k)
            except ValueError:
                continue
            if 1 <= n <= len(uniq) and v:
                got_titles[uniq[n - 1]] = v
    for title, value in got_titles.items():
        for i in remaining[title]:
            zh[str(i + 1)] = value
    if not got_titles:
        # 千万别静默失败：把模型原样输出留一行线索（截断，别把整篇打出来）
        head = " / ".join(reply.strip().splitlines()[:3])[:240]
        print(f" ⚠ 解析不出标题（{usage.get('total_tokens',0)} tok）。模型输出开头：{head}")
    save_meta(args.slug, meta)
    print(f" ok（{usage.get('total_tokens',0)} tok，"
          f"{len(got_titles)}/{len(uniq)} 个不重复标题）")
    for k in sorted((x for x in zh if x.isdigit()), key=int)[:8]:
        print(f"  {k}. {zh[k]}")
    print("\n重新渲染阅读页即可生效：python3 lnrender.py", args.slug)


def cmd_fix(args) -> None:
    """修改已译章节里的译名，并同步术语表。

    为什么需要它：术语表只对"之后的"翻译生效，已经翻好的章节不会自动改。
    如果发现前面某章把名字译错了，用这个批量替换比重新翻译便宜得多
    （按字符替换，不花 token）。
    """
    meta = load_meta(args.slug)
    pairs = []
    for pair in args.rename or []:
        if "=" not in pair:
            die(f"要写成 旧译名=新译名，收到：{pair}")
        old, new = pair.split("=", 1)
        pairs.append((old.strip(), new.strip()))
    if not pairs:
        die("没有要改的内容。用 --rename 旧=新，可多个。")

    changed_files, total = 0, 0
    for i in range(len(meta["episodes"])):
        p = chapter_path(args.slug, i)
        if not os.path.exists(p):
            continue
        text = open(p, encoding="utf-8").read()
        orig = text
        n = 0
        for old, new in pairs:
            cnt = text.count(old)
            if cnt:
                text = text.replace(old, new)
                n += cnt
        if text != orig:
            save_text(p, text)
            refresh_chapter_meta(args.slug, i, meta)
            changed_files += 1
            total += n

    # novel.md 是汇总，一起改
    md = os.path.join(novel_dir(args.slug), "novel.md")
    if os.path.exists(md):
        text = open(md, encoding="utf-8").read()
        for old, new in pairs:
            text = text.replace(old, new)
        save_text(md, text)

    # 同步术语表的"中文侧"：找到译法等于旧译名的条目，改成新译名
    glossary = meta.setdefault("glossary", {})
    synced = []
    glossary_changes = []
    for old, new in pairs:
        for jp, zh in list(glossary.items()):
            if zh == old:
                glossary[jp] = new
                synced.append(f"{jp} => {new}")
                glossary_changes.append({"jp": jp, "old": old, "new": new})
                meta.setdefault("glossary_history", []).append({
                    "jp": jp, "old": old, "new": new,
                    "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "fix",
                })
        # 也允许直接指定日文=新译名
        if "—" not in old and "=" in old:
            pass
    save_meta(args.slug, meta)

    print(f"替换完成：{total} 处，涉及 {changed_files} 个章节文件")
    for old, new in pairs:
        print(f"  {old} → {new}")
    if synced:
        print("术语表已同步：")
        for s in synced:
            print(f"  {s}")
    print("\n提示：如果新译名对应某个日文词，建议再用 learn 确认一遍术语表。")
    with open(os.path.join(novel_dir(args.slug), "history.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "fix",
                            "rename": args.rename, "count": total,
                            "glossary_changes": glossary_changes},
                           ensure_ascii=False) + "\n")


_CJK_STOP = set("""不过 但是 然后 可是 所以 如果 因为 这个 那个 什么 我们 你们 他们
自己 已经 现在 还是 只是 真的 还有 而且 或是 就是 不是 没有 可以 时候 这样 那样
一样 这么 那么 怎么 为了 一下 一直 起来 出来 过来 回来 知道 觉得 看到 听到 说道
啊啊 哈哈 嘿嘿 呜呜 哇啊 咦呀 嗯嗯 是啊 对吧 好的 不要 不能 不会 可能 应该 一定
其他 别的 其他 之类 之类 里面 外面 上面 下面 前面 后面 旁边 中间 地方 东西 事情""".split())


_CJK_STOP = set("""不过 但是 然后 可是 所以 如果 因为 这个 那个 什么 我们 你们 他们
自己 已经 现在 还是 只是 真的 还有 而且 或是 就是 不是 没有 可以 时候 这样 那样
一样 这么 那么 怎么 为了 一下 一直 起来 出来 过来 回来 知道 觉得 看到 听到 说道
啊啊 哈哈 嘿嘿 呜呜 哇啊 咦呀 嗯嗯 是啊 对吧 好的 不要 不能 不会 可能 应该 一定
其他 别的 之类 里面 外面 上面 下面 前面 后面 旁边 中间 地方 东西 事情""".split())

# 名字里几乎不会出现虚词/代词：带这些字的候选直接踢掉（否则噪声占九成）
_BAD_CH = set("的了是我你他她它这那不也就都而和与被把很太又再才却还并或但如果"
              "因为所以么吗呢吧啊呀哦嗯之其于以及将并且虽然然后于是还是什么")


def cmd_names(args) -> None:
    """用一次小模型调用，建/查这本书的**人名译名表**（一名多译的克星）。

    为什么不用正则猜：试过两版纯规则（章节集合 + 频次 + 编辑距离），噪声 200~700 组，
    真名字还被漏掉（名字嵌在句子里、子串互相套）。这个问题的可靠信号是
    "原文这个片假名，在译文里被写成了哪几种中文" —— 只有模型能给出对应关系。

    成本：一次请求（抽 30~40 段原文+译文），约 2~4k token；每本书跑一次即可。
    """
    meta = load_meta(args.slug)
    if not meta:
        die(f"没有这本：{args.slug}")
    total = len(meta.get("episodes") or [])
    kana_re = re.compile(r"[\u30a1-\u30fa\u30fc]{3,8}")
    pairs = []
    bucket: dict[str, list] = {}
    for i in range(total):
        rp = chapter_path(args.slug, i, "raw")
        zp = chapter_path(args.slug, i)
        if not (os.path.exists(rp) and os.path.exists(zp)):
            continue
        src = [x for x in split_paragraphs(open(rp, encoding="utf-8").read().split("\n")) if x.strip()]
        zh = [x for x in open(zp, encoding="utf-8").read().split("\n") if x.strip()]
        if len(src) != len(zh):
            continue                      # 段落数对不齐（修过漏译的章），跳过不猜
        for a, b in zip(src, zh):
            if len(a) < 12 or len(a) > 320:
                continue
            for m in kana_re.finditer(a):
                bucket.setdefault(m.group(0), []).append((a, b))
        if sum(len(v) for v in bucket.values()) > 4000:
            break
    # 按**名字轮询**取样：每个高频片假名挑 1~2 段，保证主角/主要组织都能覆盖到
    # （只取"最前面 35 段"会全落在第一章，ローラ 这种中段才密集的名字一条都抽不到）。
    order = sorted(bucket.items(), key=lambda kv: -len(kv[1]))
    picked: list[tuple[str, str]] = []
    seen = set()
    for _name, items in order:
        for a, b in items[:2]:
            if a in seen:
                continue
            seen.add(a)
            picked.append((a, b))
            if len(picked) >= args.sample:
                break
        if len(picked) >= args.sample:
            break
    pairs = picked
    if not pairs:
        print("没有可用于提取名字的段落（先翻一点再跑）")
        return
    body = "\n".join(f"{n+1}. 日文：{a}\n   中文：{b}" for n, (a, b) in enumerate(pairs))
    prompt = (f"下面是同一部轻小说 {len(pairs)} 段原文与译文。请找出**人名、地名、组织/称号**"
              f"这类专有名词：给出日文原名，以及译文里出现过的**所有中文写法**"
              f"（同一个名字被译成两三种写法时全部列出）。\n"
              f"只输出 JSON 数组，元素形如 "
              f'{{"jp":"ローラ","zh":["萝拉","罗拉"],"count":"各出现约 70/50 次"}}，'
              f"不要解释、不要 markdown 代码块。只列真正的专有名词，不要列普通名词。\n\n{body}")
    print(f"抽取 {len(pairs)} 段，请求模型中…（约 2~4k token）")
    reply, usage = call_llm(
        "你是日译中术语审校。只输出 JSON。", prompt,
        args.model, 0.0, role="auxiliary")
    tok = (usage or {}).get("total_tokens", 0)
    raw = reply.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        items = json.loads(raw)
    except Exception:
        print(f"模型输出不是 JSON（{tok} tok）：\n{raw[:400]}")
        return
    # 去掉三类"假冲突"：
    #   1) 同一个写法重复列出；
    #   2) 一个是另一个的**子串**（ベルベット 常被写成「贝尔贝特」和「贝尔贝」——
    #      后者其实是前者的前缀，不是第二种译法）；
    #   3) 只差称呼后缀（千岁 / 千岁酱、莉莉卡 / 莉莉卡前辈）—— 那是原文在变换称呼，
    #      不是译名不统一，锁成一个反而会丢信息。
    _HONOR = ("酱", "君", "桑", "小姐", "大人", "前辈", "同学", "妹妹", "姐姐", "哥哥")
    def _bare(v: str) -> str:
        for s in _HONOR:
            if v.endswith(s) and len(v) > len(s):
                return v[:-len(s)]
        return v
    conflicts = []
    for x in items:
        if not isinstance(x, dict):
            continue
        vs = list(dict.fromkeys(v for v in (x.get("zh") or []) if v))
        vs = [v for v in vs if not any(v != w and v in w for w in vs)]
        bare = {_bare(v) for v in vs}
        if len(bare) > 1:
            x["zh"] = vs
            conflicts.append(x)
    print(f"\n名字 {len(items)} 个（{tok} tok），其中**一名多译** {len(conflicts)} 个：")
    for x in conflicts:
        jp = str(x.get("jp") or "")
        # 同一角色的"全名/姓氏/外号"是**分别**列出来的（ローラ 与 ローラ・スミス），
        # 这里标一下关系，免得只锁了名字、全名照旧乱。
        rel = [str(y.get("jp")) for y in items
               if isinstance(y, dict) and y is not x and y.get("jp")
               and (str(y["jp"]).startswith(jp) or jp.startswith(str(y["jp"])))]
        print(f"  {jp} → " + " / ".join(x.get("zh") or [])
              + (f"  （{x['count']}）" if x.get("count") else "")
              + (f"  ／同角色变体：{'、'.join(rel[:3])}" if rel else ""))
    if args.apply and conflicts:
        g = meta.setdefault("glossary", {})
        for x in conflicts:
            jp, variants = x.get("jp"), x.get("zh") or []
            if jp and variants:
                g[jp] = variants[0]
                print(f"  · 锁定 {jp} = {variants[0]}（只影响之后新翻的章节）")
        save_meta(args.slug, meta)
        print("\n已有译文请用：fix --rename 旧译名=新译名")
    elif conflicts:
        print("\n加 --apply 可把每种的主流写法写进术语表；"
              "已有译文用 fix --rename 旧=新 全局替换。")


# ---------------------------------------------------------------- 润色（polish）
# 翻译准了之后，"机翻味"是最后一层。但润色比翻译更容易出事：它**重写**文本，
# 一次手滑就能把术语改掉、把两句对白并成一句、把信息删掉。
# 所以这里的规矩是"宁可不动，也不改坏"：
#   * 只润色够长的段（短句/纯语气词跳过，改了也没收益）；
#   * 不进入二分/重试链（失败就保留原译），每批一次请求；
#   * 通过四道校验才替换：还是中文 / 对白数不变 / 术语没丢 / 长度没有离谱；
#   * 术语表作为硬约束写进 prompt，并在校验里逐条比对。
POLISH_MIN_LEN = 24          # 短于此不润色（"是啊。"这种改了没意义）
POLISH_BATCH = 6             # 一次请求最多几段
POLISH_MAX_CHARS = 1400      # 一批最多多少字，超了就缩批


def _polish_prompt(meta: dict, paras: list[str]) -> tuple[str, str]:
    gl = meta.get("glossary") or {}
    terms = "、".join(f"{jp}={zh}" for jp, zh in list(gl.items())[:80] if zh)
    sys = ("你是资深中文轻小说润色编辑。输入是日译中的中文初稿，你只做润色，"
           "不改变任何事实、人物、情节、语气归属。")
    rules = [
        "任务：消除翻译腔、拆开长难句、让对话更像中文口语（例：「是这样吗」→「这样啊」、"
        "「不、不要」→「不……不要」），但**不要**改成网络梗或方言。",
        "硬约束 1：人名、地名、组织名、称号、技能名**一个字都不许改**，"
        "特别是术语表里的：" + (terms or "（本书暂无术语）"),
        "硬约束 2：引号体系跟原文初稿一致（「」『』或“”），不要换；"
        "对白处数与先后顺序不变，不要把两句对白并成一句。",
        "硬约束 3：不增删信息，不加解释、不加动作描写、不概括；"
        "不改变叙述人称与视角。",
        "对白同样要润色：更口语、该断句就断句（例：「我不要，绝对不要」→「不要。绝对不要。」），"
        "但引号内的文字不能加解释、不能改说话人。",
        "要求：**必须真的改写句子**（拆长句、换更自然的中文表达、按说话人调整语气）；"
        "原样抄回等于没完成任务。但改写只动表达，不动信息。",
        "格式：每段一行，写成 `#1: 润色后的文本`（编号与输入一一对应，段数不变），"
        "不要输出说明、不要空行、不要加粗或引用符号。",
    ]
    body = "\n".join(f"#{i+1}: {p}" for i, p in enumerate(paras))
    return sys, "\n".join(f"- {r}" for r in rules) + "\n\n" + body


def _parse_polish(reply: str, n: int) -> list[str]:
    """解析 `#N: 文本`；缺号返回空串（调用方保留原译）。"""
    got: dict[int, str] = {}
    cur = None
    for line in reply.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^#\s*[>＞]?\s*(\d+)\s*[<＜]?\s*[:：]?\s*(.*)$", line)
        if m:
            cur = int(m.group(1))
            got[cur] = m.group(2).strip()
        elif cur is not None:
            got[cur] = (got.get(cur, "") + " " + line).strip()
    return [got.get(i + 1, "") for i in range(n)]


def _polish_ok(old: str, new: str, meta: dict) -> str:
    """能不能替换。返回空串=可以，否则返回拒绝原因（便于统计）。"""
    if not new or new == old:
        return "空/未变"
    if not detect_chinese(new):
        return "不是中文"
    if _dialogue_count(new) != _dialogue_count(old):
        return "对白数变了"
    if kana_outside_quotes(new) > kana_outside_quotes(old):
        return "多出日文"
    # 术语硬约束：原文出现的锁定译名，润色后必须还在
    for _jp, zh in (meta.get("glossary") or {}).items():
        if zh and zh in old and zh not in new:
            return f"术语丢了：{zh}"
    lo, hi = len(old) * 0.6, len(old) * 1.7 + 10
    if not (lo <= len(new) <= hi):
        return f"长度异常 {len(old)}→{len(new)}"
    return ""


def cmd_polish(args) -> None:
    """润色已译章节（默认干跑，只报会改哪些段）。"""
    meta = load_meta(args.slug)
    if not meta:
        die(f"没有这本：{args.slug}")
    total_ch = len(meta.get("episodes") or [])
    idxs = _pick_chapters(args, total_ch)
    if not idxs:
        print("没有可润色的章节（先翻译，或用 --chapter/--all 指定）")
        return
    budget = args.budget
    spent = 0
    changed_ch = 0
    kept = 0
    reasons: dict[str, int] = {}
    samples: list[str] = []
    print(f"润色《{meta.get('title') or args.slug}》：{len(idxs)} 章"
          f"{'（干跑）' if not args.write else ''}")
    stub_args = argparse.Namespace(model=args.model, temperature=args.temperature,
                                   allow_missing=False)
    for idx in idxs:
        path = chapter_path(args.slug, idx)
        if not os.path.exists(path):
            continue
        lines = open(path, encoding="utf-8").read().split("\n")
        cand = [i for i, l in enumerate(lines)
                if len(l.strip()) >= POLISH_MIN_LEN and not l.strip().startswith("<!--")]
        if not cand:
            continue
        new_lines = list(lines)
        n_changed = 0
        for s in range(0, len(cand), POLISH_BATCH):
            if spent >= budget:
                print(f"  · 本轮预算用完（{spent} tok），停止")
                break
            batch = []
            chars = 0
            for i in cand[s:s + POLISH_BATCH]:
                if chars + len(lines[i]) > POLISH_MAX_CHARS and batch:
                    break
                batch.append(i)
                chars += len(lines[i])
            sysp, prompt = _polish_prompt(meta, [lines[i] for i in batch])
            try:
                reply, usage = call_llm(
                    sysp, prompt, args.model, args.temperature,
                    role="auxiliary")
            except (Exception, SystemExit) as e:  # 润色失败绝不影响原译
                print(f"    · 第 {idx+1} 章：请求失败（{type(e).__name__}），保留原译")
                continue
            spent += (usage or {}).get("total_tokens", 0)
            outs = _parse_polish(reply, len(batch))
            for i, new in zip(batch, outs):
                why = _polish_ok(lines[i], new, meta)
                if why:
                    kept += 1
                    reasons[why.split(" ")[0]] = reasons.get(why.split(" ")[0], 0) + 1
                    continue
                lines[i] = align_quotes_with_source(new, lines[i])
                n_changed += 1
                if len(samples) < args.samples:
                    samples.append(f"  第 {idx+1} 章\n   旧：{new_lines[i][:90]}\n   新：{lines[i][:90]}")
        if n_changed:
            changed_ch += 1
            print(f"  第 {idx+1} 章：润色 {n_changed} 段"
                  + ("（干跑，未落盘）" if not args.write else ""))
            if args.write:
                bak = os.path.join(novel_dir(args.slug), "cache",
                                   f"polish-backup-{idx+1:04d}.txt")
                save_text(bak, "\n".join(new_lines))
                save_text(path, "\n".join(lines))
                # 润色只改了部分段落，不能声称整章已经按当前术语表对齐。
                refresh_chapter_meta(args.slug, idx, meta, update_glossary=False)
        else:
            print(f"  第 {idx+1} 章：无需改动")
    if samples:
        print("\n示例：")
        print("\n".join(samples))
    if reasons:
        print("\n保留原译的原因：" + "、".join(f"{k}×{v}" for k, v in
                                          sorted(reasons.items(), key=lambda kv: -kv[1])))
    print(f"\n共润色 {changed_ch} 章 / 保留原译 {kept} 段 / 花费约 {spent} tok")
    if args.write and changed_ch:
        try:
            rebuild_novel_md(args.slug, meta, force=True)
        except Exception:
            pass
        print("已落盘（原文件备份在 novels/<slug>/cache/polish-backup-*.txt）")
    elif changed_ch:
        print("加 --write 才会真正落盘。")


def _pick_chapters(args, total: int) -> list[int]:
    """选章：--chapter N / --all / 默认最后一章有译文的。"""
    if getattr(args, "chapter", None):
        return [max(0, min(total - 1, args.chapter - 1))]
    if getattr(args, "all", False):
        return list(range(total))
    done = [i for i in range(total) if os.path.exists(chapter_path(args.slug, i))]
    return done[-1:] if done else []


def cmd_residue(args) -> None:
    """看每章残留了多少假名（"接受带日文的译文"这个权衡的**指标**）。

    背景：为了不让一次误判把整章烧成几万 token，管线允许"以中文为主、
    夹着零星日文词"的译文落地并标「未译全」。这个取舍必须可观测 ——
    否则今天的"接受"就是明天的"没人管"。
    """
    meta = load_meta(args.slug)
    if not meta:
        die(f"没有这本：{args.slug}")
    total = len(meta.get("episodes") or [])
    rows = []
    for i in range(total):
        p = chapter_path(args.slug, i)
        if not os.path.exists(p):
            continue
        full = open(p, encoding="utf-8").read()
        n = kana_outside_quotes(full)
        if n:
            rows.append((i + 1, n))
    rows.sort(key=lambda r: -r[1])
    if not rows:
        print(f"《{meta.get('title') or args.slug}》所有已译章节都没有残留假名 ✅")
        return
    if args.context:
        # 把每一处残留连同上下文打出来（前后各 20 字）：光有章号没法判断
        # 该"加词表/锁术语/直接改"，只有看到句子才好定。
        print(f"《{meta.get('title') or args.slug}》残留上下文：")
        for ch, _n in sorted(rows):
            txt = open(chapter_path(args.slug, ch - 1), encoding="utf-8").read()
            # 逐段扫，只报引号外的（引号内是刻意引用）
            for para in txt.split("\n"):
                if not para.strip():
                    continue
                body = strip_quoted(para)
                for m in re.finditer(r"[\u3040-\u30ff]+", body):
                    s = m.start()
                    left = body[max(0, s - 20):s]
                    right = body[m.end():m.end() + 20]
                    print(f"  第 {ch:>4} 章 | …{left}【{m.group(0)}】{right}…")
        print()
    over = sum(1 for _, n in rows if n > args.limit)
    print(f"《{meta.get('title') or args.slug}》残留假名：{len(rows)} 章（共 "
          f"{sum(n for _, n in rows)} 个），超过 {args.limit} 个的有 {over} 章")
    for ch, n in rows[:args.top]:
        print(f"  第 {ch:>4} 章  {n} 个" + ("  ⚠" if n > args.limit else ""))
    if len(rows) > args.top:
        print(f"  …其余 {len(rows) - args.top} 章略（--top 调整）")


def cmd_status(args) -> None:
    meta = load_meta(args.slug)
    eps = meta["episodes"]
    done = meta["progress"].get("translated_through", 0)
    print(f"《{meta['title']}》 / {meta.get('author')}")
    print(f"  进度：已译 {done} / {len(eps)} 章")
    print(f"  术语表：{len(meta.get('glossary') or {})} 条"
          f" | 人物：{len(meta.get('characters') or {})} 个"
          f" | 梗概：{len(meta.get('summaries') or {})} 章"
          f" | 经验：{len(meta.get('lessons') or {})} 条")
    print(f"  风格：{meta.get('style') or '（未设置）'}")
    if done:
        print(f"  已译章节：{', '.join(str(i) for i in range(1, done + 1) if has_translation(args.slug, i-1))}")

    # token 消耗统计（从 history 汇总）
    hp = os.path.join(novel_dir(args.slug), "history.jsonl")
    if os.path.exists(hp):
        tok = sum(json.loads(l).get("tokens", 0)
                  for l in open(hp, encoding="utf-8") if l.strip())
        if tok:
            avg = tok / max(done, 1)
            rest = len(eps) - done
            print(f"  已消耗 {tok:,} token（平均 {avg:,.0f}/章）")
            print(f"  剩余 {rest} 章预计还需约 {rest * avg:,.0f} token")
            _avg_cost = lnmodels.estimate_cost(
                avg / 2, avg / 2, "translate")["amount"]
            print(f"  粗估费用：已用约 {_avg_cost * done:.3f} "
                  f"{lnmodels.currency()}，"
                  f"全译完约 {_avg_cost * len(eps):.2f}")


def cmd_list(args) -> None:
    if not os.path.isdir(NOVELS_DIR):
        print("还没有作品。")
        return
    for slug in sorted(os.listdir(NOVELS_DIR)):
        meta = load_json(os.path.join(NOVELS_DIR, slug, "meta.json"), None)
        if not meta:
            continue
        eps = len(meta.get("episodes") or [])
        done = (meta.get("progress") or {}).get("translated_through", 0)
        print(f"  {slug:32s} {done:4d}/{eps:<4d}  {meta.get('title','')[:40]}")


# ------------------------------------------------------------------ CLI

_READ_ONLY_COMMANDS = {"lessons", "list", "residue", "status", "terms"}


def _command_writes(args) -> bool:
    if args.cmd in _READ_ONLY_COMMANDS:
        return False
    if args.cmd == "stale":
        return bool(args.retranslate)
    if args.cmd == "names":
        return bool(args.apply)
    if args.cmd == "polish":
        return bool(args.write)
    if args.cmd == "next":
        return not bool(args.dry_run)
    return True


def main() -> None:
    p = argparse.ArgumentParser(description="按需增量翻译日文轻小说（带故事记忆）")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="新建作品（抓目录）")
    i.add_argument("url", help="kakuyomu 作品 URL")
    i.add_argument("--slug", help="自定义短名")
    i.add_argument("--force", action="store_true")
    i.set_defaults(fn=cmd_init)

    im = sub.add_parser("import", help="导入本地 EPUB / TXT（建书，不花 token）")
    im.add_argument("path", help="本地 .epub 或 .txt 文件")
    im.add_argument("--title", help="覆盖书名（默认取 EPUB 元数据/文件名）")
    im.add_argument("--author", help="覆盖作者")
    im.add_argument("--slug", help="自定义短名")
    im.set_defaults(fn=cmd_import)

    st = sub.add_parser("stale", help="列出用旧术语表翻过的章节（默认只报告）")
    st.add_argument("slug")
    st.add_argument("--term", help="只看原文包含这个词的章节")
    st.add_argument("--retranslate", action="store_true",
                    help="真的重翻（花钱；默认最多 3 章）")
    st.add_argument("--limit", type=int, default=3, help="本次最多重翻几章")
    st.add_argument("--model", default=TRANSLATE_MODEL)
    st.set_defaults(fn=cmd_stale)

    tm = sub.add_parser("terms", help="按片假名频次找候选术语（0 token）")
    tm.add_argument("slug")
    tm.add_argument("--top", type=int, default=40)
    tm.add_argument("--count", type=int, default=3, help="至少出现几次")
    tm.add_argument("--min", type=int, default=2, help="词至少几个假名")
    tm.add_argument("--json", action="store_true")
    tm.set_defaults(fn=cmd_terms)

    n = sub.add_parser("next", help="按需翻译接下来的 N 章（核心命令）")
    n.add_argument("slug")
    n.add_argument("count", nargs="?", type=int, default=3)
    n.add_argument("--from-chapter", type=int, help="从第几章开始（默认接着上次）")
    n.add_argument("--force", action="store_true", help="忽略已有译文重译")
    n.add_argument("--summary", action="store_true", help="译完顺便生成梗概")
    n.add_argument("--dry-run", action="store_true", help="只分段和估算，不调用 API")
    n.add_argument("--allow-missing", action="store_true", help="行号缺失不重试")
    n.add_argument("--model", default=TRANSLATE_MODEL)
    n.add_argument("--temperature", type=float, default=0.3)
    n.set_defaults(fn=cmd_next)

    f = sub.add_parser("fetch", help="只抓原文，不翻译")
    f.add_argument("slug")
    f.add_argument("count", nargs="?", type=int, default=5)
    f.set_defaults(fn=cmd_fetch)

    s = sub.add_parser("summary",
                       help="为已译章节生成梗概（喂故事记忆 + 阅读页「前情」）")
    s.add_argument("slug")
    s.add_argument("--from-chapter", type=int, default=1)
    s.add_argument("--count", type=int, default=10)
    s.add_argument("--force", action="store_true")
    s.add_argument("--model", default=AUX_MODEL)
    s.set_defaults(fn=cmd_summary)

    rv = sub.add_parser("review", help="校对已译章节（默认只报告，不花 token）")
    rv.add_argument("slug")
    rv.add_argument("--chapter", type=int, help="只校对第 N 章")
    rv.add_argument("--from-chapter", type=int, default=None)
    rv.add_argument("--count", type=int, default=1)
    rv.add_argument("--all", action="store_true", help="校对全部已译章节")
    rv.add_argument("--llm", action="store_true", help="启用 AI 校对（消耗 token）")
    rv.add_argument("--fix", action="store_true",
                    help="自动修可验证的术语旧译名（不花 token）")
    rv.add_argument("--fix-ai", action="store_true",
                    help="让 AI 修订阻断项（隐含 --llm；会备份原译文）")
    rv.add_argument("--no-learn", action="store_true",
                    help="不把本次发现沉淀为本书经验")
    rv.add_argument("--fail-on-blocker", action="store_true")
    rv.add_argument("--model", default=REVIEW_MODEL)
    rv.add_argument("--temperature", type=float, default=0.2)
    rv.set_defaults(fn=cmd_review)

    l = sub.add_parser("learn", help="记录术语/人物/风格纠正（永久生效）")
    l.add_argument("slug")
    l.add_argument("--term", nargs="*", help="日文=中文，可多个")
    l.add_argument("--character", nargs="*",
                   help="名字=描述|voice:语气|lexicon:词汇|syntax:句法|volume:本卷|aliases:别名1,别名2")
    l.add_argument("--style", help="全篇风格要求")
    l.add_argument("--narrator", help="第一人称叙述者的滤镜/语气")
    l.add_argument("--honorifics", help="称谓处理规则")
    l.add_argument("--medium", choices=["web", "ebook", "paper"],
                   help="发布媒介：网络连载/电子书/纸质书")
    l.add_argument("--guide", help="载入一份额外的翻译准则文本文件")
    l.add_argument("--note", help="其它特别注意")
    l.add_argument("--lesson", nargs="*", help="追加一条本书翻译经验")
    l.set_defaults(fn=cmd_learn)

    les = sub.add_parser("lessons", help="查看本书沉淀的翻译经验")
    les.add_argument("slug")
    les.add_argument("--limit", type=int, default=20)
    les.set_defaults(fn=cmd_lessons)

    tt = sub.add_parser("titles", help="批量把日文章节名翻成中文")
    tt.add_argument("slug")
    tt.add_argument("--model", default=AUX_MODEL)
    tt.add_argument("--no-book", action="store_true", help="不翻译书名")
    tt.set_defaults(fn=cmd_titles)

    fx = sub.add_parser("fix", help="修改已译章节的译名并同步术语表（不花 token）")
    fx.add_argument("slug")
    fx.add_argument("--rename", nargs="*", help="旧译名=新译名，可多个")
    fx.set_defaults(fn=cmd_fix)

    nm = sub.add_parser("names", help="找「同一个日文名被译成多种写法」（不花 token）")
    nm.add_argument("slug")
    nm.add_argument("--apply", action="store_true",
                    help="把主流译法写进术语表（只影响之后新翻的章节）")
    nm.add_argument("--sample", type=int, default=35, help="抽多少段给模型（默认 35）")
    nm.add_argument("--model", default=AUX_MODEL)
    nm.set_defaults(fn=cmd_names)

    pl = sub.add_parser("polish", help="润色已译章节（消除翻译腔；默认干跑）")
    pl.add_argument("slug")
    pl.add_argument("--chapter", type=int, help="只润色第 N 章")
    pl.add_argument("--all", action="store_true", help="润色全部已译章节")
    pl.add_argument("--write", action="store_true", help="真的落盘（自动备份）")
    pl.add_argument("--budget", type=int, default=40000, help="本轮 token 上限")
    pl.add_argument("--model", default=AUX_MODEL)
    pl.add_argument("--temperature", type=float, default=0.4)
    pl.add_argument("--samples", type=int, default=3, help="打印几个前后对比")
    pl.set_defaults(fn=cmd_polish)

    rs = sub.add_parser("residue", help="看每章残留的假名数（未译干净的日文词）")
    rs.add_argument("slug")
    rs.add_argument("--limit", type=int, default=20, help="超过多少算告警（默认 20）")
    rs.add_argument("--top", type=int, default=20, help="最多列多少章")
    rs.add_argument("--context", action="store_true",
                    help="把每一处残留连同上下文（前后各 20 字）打出来")
    rs.set_defaults(fn=cmd_residue)

    st = sub.add_parser("status", help="看进度与故事记忆")
    st.add_argument("slug")
    st.set_defaults(fn=cmd_status)

    ls = sub.add_parser("list", help="列出所有作品")
    ls.set_defaults(fn=cmd_list)

    args = p.parse_args()
    if not _command_writes(args):
        args.fn(args)
        return
    try:
        runtime_lock = lndata.acquire_lock(LAYOUT)
    except lndata.DataRootError as ex:
        print(f"错误：{ex}；请先停止正在运行的书架服务", file=sys.stderr)
        raise SystemExit(2)
    try:
        import lnjobs
        try:
            lnjobs.STORE.assert_writable()
        except lnjobs.RecoveryRequired as ex:
            die(str(ex))
        args.fn(args)
    finally:
        runtime_lock.__exit__(None, None, None)


if __name__ == "__main__":
    main()
