#!/usr/bin/env python3
"""按作品隔离的译文校对。

设计边界（对应“校对流水线”的最小可用落地）：

* 规则校对不调用模型、不花 token：段落对齐、漏译、日文残留、术语锁定、
  数字/标点/节奏、情绪逐字反义。
* AI 校对只在调用方显式要求时运行；它只报告问题，不重写译文。
* 所有报告、观察池、经验、修订记录都写在 ``novels/<slug>/qa/`` 下，
  文件名带 work_id，绝不读写其它作品。
* ``--fix`` 只自动修“术语旧译名”这种可字符串验证的冲突；译文改写必须
  经 AI 修订并逐段校验，失败就回退。

这个模块不直接 import lntrans，避免循环导入；需要存储/LLM 时延迟取。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time


KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
SEVERITIES = ("blocker", "suggestion", "observation")
SEV_LABEL = {"blocker": "阻断", "suggestion": "建议", "observation": "观察"}
TYPE_LABEL = {
    "para_count": "段落数",
    "omission": "漏译",
    "japanese": "日文残留",
    "term_missing": "术语缺失",
    "term_old": "旧译名",
    "term": "术语",
    "number": "数字",
    "emotion": "情绪反义",
    "rhythm": "段落节奏",
    "style": "翻译腔",
    "voice": "角色语气",
    "reference": "指代",
    "mistranslation": "疑似错译",
    "llm_format": "AI 输出格式",
    "other": "其它",
}
LLM_TYPES = {"omission", "mistranslation", "reference", "voice", "rhythm",
             "style", "term", "other"}
LLM_SEVERITY = {"blocker", "suggestion", "observation"}


def _lt():
    import lntrans  # noqa: PLC0415  （延迟导入，避免 lntrans <-> lnreview 循环）
    return lntrans


def qa_dir(slug: str) -> str:
    return os.path.join(_lt().novel_dir(slug), "qa")


def report_paths(slug: str, chapter: int) -> tuple[str, str]:
    d = qa_dir(slug)
    stem = f"review-{chapter:04d}"
    return os.path.join(d, stem + ".json"), os.path.join(d, stem + ".md")


def assert_work(meta: dict, slug: str) -> None:
    """硬校验：这本书的 meta 不能拿着另一本书的 slug/内容来用。"""
    if not isinstance(meta, dict):
        raise ValueError("作品记忆不是对象")
    work_id = str(meta.get("work_id") or meta.get("slug") or "")
    if work_id and work_id != str(slug):
        raise ValueError(
            f"作品隔离失败：请求 {slug}，记忆属于 {work_id}（拒绝跨书校对/翻译）")
    if meta.get("slug") and str(meta["slug"]) != str(slug):
        raise ValueError(
            f"作品隔离失败：请求 {slug}，meta.slug={meta['slug']}")


def ensure_work_id(meta: dict, slug: str) -> None:
    """旧数据没有 work_id 时补上；有冲突时直接拒绝。"""
    assert_work(meta, slug)
    meta.setdefault("work_id", str(slug))
    meta.setdefault("slug", str(slug))


def _trunc(s: str, n: int = 180) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n] + "…"


def _issue(para: int, typ: str, severity: str, *, jp: str = "", zh: str = "",
           evidence: str = "", suggestion: str = "", **extra) -> dict:
    out = {
        "para": max(0, int(para)),       # 0 = 整章，1-based = 具体段
        "type": typ,
        "severity": severity if severity in SEVERITIES else "observation",
        "quote_jp": _trunc(jp),
        "quote_zh": _trunc(zh),
        "evidence": _trunc(evidence, 300),
        "suggestion": _trunc(suggestion, 300),
    }
    out.update(extra)
    return out


def _term_history(meta: dict) -> dict[str, list[str]]:
    """日文术语 -> 历史上用过的旧中文译名（只用于发现回退，不注入 prompt）。"""
    out: dict[str, list[str]] = {}
    rows = list(meta.get("glossary_history") or [])
    # 兼容旧数据：早期版本只把变更写进 history.jsonl，没有 glossary_history。
    if not rows:
        slug = str(meta.get("work_id") or meta.get("slug") or "")
        if slug:
            hp = os.path.join(_lt().novel_dir(slug), "history.jsonl")
            try:
                with open(hp, encoding="utf-8") as f:
                    for line in f:
                        try:
                            ev = json.loads(line)
                        except ValueError:
                            continue
                        for key in ("term_changes", "glossary_changes"):
                            for ch in ev.get(key) or []:
                                if isinstance(ch, dict):
                                    rows.append(ch)
            except OSError:
                pass
    for ch in rows:
        if not isinstance(ch, dict):
            continue
        jp, old = str(ch.get("jp") or ""), str(ch.get("old") or "")
        new = str(ch.get("new") or "")
        if jp and old and old != new:
            out.setdefault(jp, [])
            if old not in out[jp]:
                out[jp].append(old)
    return out


def _numbers(s: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?%?", s or "")


def rule_check(raw: str, zh: str, meta: dict) -> list[dict]:
    """确定性的硬检查。返回的问题全部带原文/译文片段依据。"""
    lt = _lt()
    rp = lt.split_paragraphs((raw or "").split("\n"))
    zp = lt.split_paragraphs((zh or "").split("\n"))
    issues: list[dict] = []

    if len(rp) != len(zp):
        issues.append(_issue(
            0, "para_count", "blocker",
            jp=f"原文 {len(rp)} 段", zh=f"译文 {len(zp)} 段",
            evidence=f"段落数不一致（原文 {len(rp)}，译文 {len(zp)}）",
            suggestion="先恢复与原文一致的段落数，再逐段校对。",
            raw_count=len(rp), zh_count=len(zp)))

    glossary = meta.get("glossary") or {}
    hist = _term_history(meta)
    n = min(len(rp), len(zp))
    for i in range(n):
        a, b = rp[i], zp[i]
        if not a.strip() and not b.strip():
            continue
        para = i + 1
        if a.strip() and not b.strip():
            issues.append(_issue(
                para, "omission", "blocker", jp=a,
                evidence="原文这一段非空，译文对应段为空。",
                suggestion="补译这一段，并保持与前后段的衔接。"))
            continue
        if not a.strip():
            if b.strip():
                issues.append(_issue(
                    para, "omission", "suggestion", zh=b,
                    evidence="原文是空行，译文却新增了内容。",
                    suggestion="确认是不是把上下文说明写进了正文；应删除或并回正确段落。"))
            continue

        # 日文残留：假名是中文里不会自然出现的字符。保留一个假名可能是专名，
        # 三个以上或占比明显就按阻断处理。
        kana = KANA.findall(b)
        ratio = len(kana) / max(len(b), 1)
        if len(kana) >= 3 or (len(kana) >= 2 and ratio >= 0.04):
            issues.append(_issue(
                para, "japanese", "blocker", jp=a, zh=b,
                evidence=f"译文含 {len(kana)} 个假名（占比 {ratio:.1%}）。",
                suggestion="把残留的日文译成中文；专有名词按术语表统一。"))

        # 术语锁定：原文出现术语，译文必须用锁定译名。
        for jp, zh_term in glossary.items():
            jp, zh_term = str(jp or ""), str(zh_term or "")
            if not jp or not zh_term or jp not in a:
                continue
            if zh_term not in b:
                issues.append(_issue(
                    para, "term_missing", "blocker", jp=a, zh=b,
                    evidence=f"术语「{jp}」在本书锁定为「{zh_term}」，本段未出现该译名。",
                    suggestion=f"按术语表使用「{zh_term}」。",
                    term=jp, term_zh=zh_term))
            for old in hist.get(jp, []):
                if old and old != zh_term and old in b:
                    issues.append(_issue(
                        para, "term_old", "blocker", jp=a, zh=b,
                        evidence=f"术语「{jp}」的旧译名「{old}」仍在使用；本书已锁定「{zh_term}」。",
                        suggestion=f"把「{old}」改为「{zh_term}」。",
                        term=jp, term_zh=zh_term, old=old))

        # 数字：中文可能写成汉字，所以这里只报“原文有阿拉伯数字、译文全没有/明显不同”。
        rn, zn = _numbers(a), _numbers(b)
        if rn and rn != zn:
            issues.append(_issue(
                para, "number", "suggestion", jp=a, zh=b,
                evidence=f"原文数字 {rn[:6]}，译文数字 {zn[:6]}。",
                suggestion="核对数字是否漏译、误译或单位变化。"))

        # 原文明确的冷静/克制 → 译文暴怒/摔打：只报候选，不自动改。
        calm = re.search(r"平静|冷静|冷淡|克制|落ち着|静か|平然", a)
        angry = re.search(r"暴怒|怒吼|吼叫|摔|大怒|咆哮|怒不可遏", b)
        if calm and angry:
            issues.append(_issue(
                para, "emotion", "suggestion", jp=a, zh=b,
                evidence=f"原文有「{calm.group(0)}」，译文有「{angry.group(0)}」。",
                suggestion="核对是否把克制写成了爆发；保持原文情绪强度。"))

        # 翻译腔：只做低置信度观察，不自动改写。
        for pat, why in (
            (r"对于.{0,14}(能够|此事|莅临|感激不尽)", "日式长敬语可能未拆短"),
            (r"的的|了了|进行了一次", "疑似翻译腔/病句"),
            (r"被.{0,10}所", "被动句可能过重"),
        ):
            if re.search(pat, b):
                issues.append(_issue(
                    para, "style", "observation", jp=a, zh=b,
                    evidence=f"命中模式「{pat}」（{why}）。",
                    suggestion="冷读一遍，改成自然中文；保留角色正式度。"))
                break

    # 段落节奏：原文的空行是节奏的一部分，译文不能整章合并。
    raw_breaks = len(re.findall(r"\n\s*\n", raw or ""))
    zh_breaks = len(re.findall(r"\n\s*\n", zh or ""))
    if abs(raw_breaks - zh_breaks) >= 3:
        issues.append(_issue(
            0, "rhythm", "suggestion",
            jp=f"{raw_breaks} 个空行间隔", zh=f"{zh_breaks} 个空行间隔",
            evidence="译文的空行/分段间隔与原文差异较大。",
            suggestion="恢复原文的短段和换行节奏，不要把碎句合并成大段。"))

    return _dedup(issues)


def _dedup(issues: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in issues:
        key = (it.get("para"), it.get("type"), it.get("quote_zh"),
               it.get("term"), it.get("old"))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _character_context(meta: dict, raw: str, zh: str) -> str:
    lt = _lt()
    bits = []
    for name, info in (meta.get("characters") or {}).items():
        names = lt._character_names(name, info)  # noqa: SLF001
        if any(n and (n in raw or n in zh) for n in names):
            bits.append(lt._character_card(name, info))  # noqa: SLF001
    return "\n".join(bits)


def _terms_context(meta: dict, raw: str) -> str:
    hit = []
    for jp, zh in (meta.get("glossary") or {}).items():
        if jp and jp in raw:
            hit.append(f"{jp} => {zh}")
    return "\n".join(sorted(hit))


def _lessons_context(meta: dict, limit: int = 8) -> str:
    out = []
    raw = meta.get("lessons") or []
    if not isinstance(raw, list):
        raw = []
    for x in raw[-limit:]:
        t = x.get("text") if isinstance(x, dict) else str(x)
        if t:
            out.append("- " + _trunc(t, 240))
    return "\n".join(out)


def _windows(raw_paras: list[str], zh_paras: list[str],
             max_chars: int = 7000) -> list[tuple[int, int]]:
    """按字符数切窗口；窗口内原文/译文段号始终对齐。"""
    out, start, size = [], 0, 0
    for i in range(len(raw_paras)):
        add = len(raw_paras[i]) + len(zh_paras[i] if i < len(zh_paras) else "") + 12
        if i > start and size + add > max_chars:
            out.append((start, i))
            start, size = i, 0
        size += add
    if start < len(raw_paras):
        out.append((start, len(raw_paras)))
    return out


def build_llm_prompt(slug: str, meta: dict, raw_paras: list[str],
                     zh_paras: list[str], start: int, end: int) -> str:
    lt = _lt()
    raw = "\n".join(raw_paras)
    zh = "\n".join(zh_paras)
    chars = _character_context(meta, raw, zh)
    terms = _terms_context(meta, raw)
    lessons = _lessons_context(meta)
    title = meta.get("title") or ""
    lines = [
        "你是校对，不是译者。只校对下面这一部作品，不要使用其它作品的信息。",
        f"【作品隔离】work_id={slug}；书名={title}；本章=第{start + 1}-{end}段",
        "只报告问题，不改写整段；没有原文依据的猜测降为 observation。",
        "逐项输出问题：段号、类型、等级、原文片段、译文片段、依据、建议方向。",
        "等级：blocker=术语/指代/时空/漏译等硬冲突；suggestion=语气、称呼、",
        "轻微节奏漂移；observation=风格/翻译腔等需要人判断的问题。",
        "",
        "【角色卡（只属于本书）】",
        chars or "（未提供）",
        "",
        "【术语表（只属于本书，锁定译名）】",
        terms or "（本窗口未命中术语）",
    ]
    if lessons:
        lines += ["", "【本书经验（只适用于本书）】", lessons]
    summaries = meta.get("summaries") or {}
    if isinstance(summaries, dict) and summaries:
        try:
            keys = sorted((k for k in summaries if str(k).isdigit()),
                          key=lambda x: int(x))[-2:]
        except ValueError:
            keys = []
        if keys:
            lines += ["", "【前情梗概（只用于检查跨章一致性）】"]
            for k in keys:
                lines.append(f"第{k}话：{_trunc(summaries[k], 240)}")
    lines += [
        "",
        "【原文】",
        "\n".join(f"#{start + i + 1}:{raw_paras[i]}" for i in range(start, end)),
        "",
        "【译文】",
        "\n".join(f"#{start + i + 1}:{zh_paras[i] if i < len(zh_paras) else ''}"
                  for i in range(start, end)),
        "",
        "只输出 JSON 数组，不要 Markdown、不要解释。每项格式：",
        '{"para":1,"type":"term|omission|mistranslation|reference|voice|rhythm|style|other",'
        '"severity":"blocker|suggestion|observation","quote_jp":"…","quote_zh":"…",'
        '"evidence":"…","suggestion":"…"}',
        "para 用 1-based 段号；整章问题用 0。没有问题输出 []。",
    ]
    return "\n".join(lines)


def _extract_json(text: str):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    a, b = text.find("["), text.rfind("]")
    if a >= 0 and b > a:
        try:
            return json.loads(text[a:b + 1])
        except (ValueError, TypeError):
            pass
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        try:
            obj = json.loads(text[a:b + 1])
            if isinstance(obj, dict):
                for k in ("issues", "problems", "results"):
                    if isinstance(obj.get(k), list):
                        return obj[k]
        except (ValueError, TypeError):
            pass
    return None


def _norm_llm_issue(x, start: int, end: int) -> dict | None:
    if not isinstance(x, dict):
        return None
    try:
        para = int(x.get("para") or 0)
    except (TypeError, ValueError):
        para = 0
    if para and not (start + 1 <= para <= end):
        para = 0
    typ = str(x.get("type") or "other").strip()
    if typ not in LLM_TYPES:
        typ = "other"
    sev = str(x.get("severity") or "observation").strip()
    if sev not in LLM_SEVERITY:
        sev = "observation"
    evidence = str(x.get("evidence") or "").strip()
    # 文档的硬规则：没有原文依据的“疑似”不能升级为阻断。
    if sev == "blocker" and not evidence:
        sev = "observation"
    return _issue(
        para, typ, sev,
        jp=str(x.get("quote_jp") or ""),
        zh=str(x.get("quote_zh") or ""),
        evidence=evidence,
        suggestion=str(x.get("suggestion") or x.get("fix_direction") or ""),
        source="llm")


def llm_check(slug: str, meta: dict, raw_paras: list[str],
              zh_paras: list[str], *, model: str, temperature: float,
              quiet: bool = False) -> tuple[list[dict], int]:
    """分段校对；每章最多若干窗口，避免超长章节爆上下文。"""
    lt = _lt()
    issues: list[dict] = []
    tokens = 0
    for start, end in _windows(raw_paras, zh_paras):
        prompt = build_llm_prompt(slug, meta, raw_paras, zh_paras, start, end)
        if not quiet:
            print(f"    AI 校对第 {start + 1}-{end} 段…", end="", flush=True)
        try:
            reply, usage = lt.call_llm(
                "你是严谨的轻小说译文校对。只报告有原文依据的问题，"
                "不重译，不总结剧情，不引用其它作品。",
                prompt, model, temperature, role="review")
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001
            issues.append(_issue(
                0, "other", "observation",
                evidence=f"AI 校对请求失败：{type(e).__name__}: {e}",
                suggestion="稍后重试，或先看规则检查结果。", source="llm"))
            continue
        tokens += int((usage or {}).get("total_tokens") or 0)
        data = _extract_json(reply)
        if not isinstance(data, list):
            issues.append(_issue(
                0, "llm_format", "observation",
                evidence="AI 没有返回可解析的 JSON 数组。",
                suggestion="重试；若持续出现，检查模型是否被其它提示词干扰。",
                source="llm", raw_reply=_trunc(reply, 500)))
            if not quiet:
                print(" 格式异常", flush=True)
            continue
        got = 0
        for x in data:
            it = _norm_llm_issue(x, start, end)
            if it:
                issues.append(it)
                got += 1
        if not quiet:
            print(f" {got} 项", flush=True)
    return _dedup(issues), tokens


def derive_lessons(issues: list[dict], meta: dict) -> list[str]:
    """把可验证的问题压成短经验。只写本书，重复内容不重复追加。"""
    out = []
    glossary = meta.get("glossary") or {}
    for it in issues:
        typ = it.get("type")
        sev = it.get("severity")
        if sev == "observation":
            continue
        if typ in ("term_missing", "term_old"):
            jp, zh = it.get("term"), it.get("term_zh")
            old = it.get("old")
            if jp and zh:
                if old:
                    out.append(f"术语「{jp}」统一译作「{zh}」，不要回退到「{old}」。")
                else:
                    out.append(f"术语「{jp}」统一译作「{zh}」，出现原文时不要漏掉。")
        elif typ in ("omission", "japanese"):
            out.append("翻译后逐段核对：不漏段、不把日文原文留在译文里。")
        elif typ == "para_count":
            out.append("输出前核对段落数：译文段数必须与原文一致，空行也要保留。")
        elif typ in ("voice", "reference"):
            sug = it.get("suggestion") or ""
            if sug:
                out.append(f"角色声音：{_trunc(sug, 180)}")
        elif typ == "term":
            sug = it.get("suggestion") or ""
            if sug:
                out.append(f"术语：{_trunc(sug, 180)}")
        elif typ == "emotion":
            out.append("情绪强度按原文：不要把“平静/冷淡/克制”译成暴怒或摔打。")
        elif typ == "number":
            out.append("数字、百分比、金额和等级按原文逐项核对，不要漏掉或改单位。")
        elif typ == "rhythm":
            out.append("保留原文的短段、空行和换行节奏，不要把碎句合并成大段。")
        elif typ == "style":
            out.append("冷读时拆掉日式长敬语和翻译腔；正式度靠词汇与句式，不靠堆“您/请”。")
    return out


def add_lessons(slug: str, meta: dict | None, texts: list[str], *,
                chapter: int = 0, source: str = "review") -> list[str]:
    """追加经验到 meta（供下一章 prompt 注入）和 qa/lessons.json。"""
    if not texts:
        return []
    lt = _lt()
    with lt.novel_lock(slug):
        fresh = lt.load_meta(slug)
        ensure_work_id(fresh, slug)
        lessons = fresh.setdefault("lessons", [])
        if not isinstance(lessons, list):
            lessons = []
            fresh["lessons"] = lessons
        existing = {str(x.get("text") if isinstance(x, dict) else x).strip()
                    for x in lessons}
        added = []
        for text in texts:
            text = " ".join(str(text or "").split())
            if not text or len(text) < 4 or text in existing:
                continue
            item = {
                "text": text[:300],
                "chapter": int(chapter or 0),
                "source": source,
                "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            lessons.append(item)
            existing.add(text)
            added.append(text)
        # 只保留最近 50 条，避免 meta 无限膨胀；经验是“只增不改”，
        # 但过老的条目可以从注入窗口淘汰，原文仍可从 qa/lessons.json 追溯。
        if len(lessons) > 50:
            fresh["lessons"] = lessons[-50:]
        if added:
            lt.save_meta(slug, fresh)
            d = qa_dir(slug)
            os.makedirs(d, exist_ok=True)
            lt.save_json(os.path.join(d, "lessons.json"),
                         fresh.get("lessons") or [])
            _write_lessons_md(slug, fresh)
        if meta is not None:
            meta["lessons"] = list(fresh.get("lessons") or [])
        return added


def _write_lessons_md(slug: str, meta: dict) -> None:
    lines = [f"# 翻译经验 · {meta.get('title') or slug}", "",
             "只适用于本书；后续翻译会把这些条目注入角色上下文。", ""]
    for i, x in enumerate(meta.get("lessons") or [], 1):
        if isinstance(x, dict):
            lines.append(f"{i}. {x.get('text','')}  "
                         f"<small>第{x.get('chapter') or '?'}章 · {x.get('source','')}</small>")
        else:
            lines.append(f"{i}. {x}")
    _lt().save_text(os.path.join(qa_dir(slug), "lessons.md"), "\n".join(lines) + "\n")


def _write_markdown(slug: str, report: dict) -> str:
    lines = [
        f"# 校对报告 · 第 {report['chapter']} 章",
        "",
        f"- 作品：{report.get('work_id')}",
        f"- 时间：{report.get('at')}",
        f"- 模式：{report.get('mode')}",
        f"- 段落：原文 {report.get('raw_count')} / 译文 {report.get('zh_count')}",
        f"- 问题：阻断 {report['counts']['blocker']} · "
        f"建议 {report['counts']['suggestion']} · 观察 {report['counts']['observation']}",
    ]
    if report.get("escalate"):
        lines.append("- ⚠ 观察池已触发人工复核阈值")
    lines.append("")
    if not report.get("issues"):
        lines.append("未发现明显问题。")
    for it in report.get("issues") or []:
        lines.append(
            f"## 第 {it.get('para') or '全章'} 段 · "
            f"{TYPE_LABEL.get(it.get('type'), it.get('type'))} · "
            f"{SEV_LABEL.get(it.get('severity'), it.get('severity'))}")
        if it.get("quote_jp"):
            lines.append(f"- 原文：{it['quote_jp']}")
        if it.get("quote_zh"):
            lines.append(f"- 译文：{it['quote_zh']}")
        if it.get("evidence"):
            lines.append(f"- 依据：{it['evidence']}")
        if it.get("suggestion"):
            lines.append(f"- 建议：{it['suggestion']}")
        lines.append("")
    text = "\n".join(lines)
    _lt().save_text(report_paths(slug, report["chapter"])[1], text)
    return text


def _append_observations(slug: str, report: dict) -> int:
    """观察池按作品分文件；返回本书当前观察级条目数。"""
    d = qa_dir(slug)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "observations.jsonl")
    existing = 0
    seen = set()
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    existing += 1
                    try:
                        x = json.loads(line)
                    except ValueError:
                        continue
                    seen.add((x.get("chapter"), x.get("type"),
                              x.get("para"), x.get("evidence")))
        except OSError:
            existing = 0
    add = []
    for it in report.get("issues") or []:
        if it.get("severity") in ("suggestion", "observation"):
            key = (report["chapter"], it.get("type"), it.get("para"),
                   it.get("evidence"))
            if key in seen:
                continue
            seen.add(key)
            add.append({
                "work_id": slug, "chapter": report["chapter"],
                "at": report["at"], "type": it.get("type"),
                "severity": it.get("severity"), "para": it.get("para"),
                "evidence": it.get("evidence"),
            })
    if add:
        with open(p, "a", encoding="utf-8") as f:
            for x in add:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
    return existing + len(add)


def _review_chapter_impl(slug: str, idx: int, meta: dict | None = None, *,
                         use_llm: bool = False, model: str | None = None,
                         temperature: float = 0.2, fix: bool = False,
                         learn: bool = True, quiet: bool = False) -> dict:
    """校对第 idx 章（0-based）。只读译文；fix=True 才写回。"""
    lt = _lt()
    model = model or lt.REVIEW_MODEL
    raw_p = lt.chapter_path(slug, idx, "raw")
    zh_p = lt.chapter_path(slug, idx, "zh")
    with lt.novel_lock(slug):
        # Always refresh here.  Callers may have loaded meta before waiting for
        # a translation job; reusing that snapshot would overwrite newer
        # progress later in this function.
        meta = lt.load_meta(slug)
        ensure_work_id(meta, slug)
        if not os.path.exists(raw_p):
            raise FileNotFoundError(f"第 {idx + 1} 章没有原文：{raw_p}")
        if not os.path.exists(zh_p) or os.path.getsize(zh_p) <= 0:
            raise FileNotFoundError(f"第 {idx + 1} 章还没有译文：{zh_p}")
        raw = open(raw_p, encoding="utf-8").read()
        zh = open(zh_p, encoding="utf-8").read()
    raw_sha = lt._sha256_file(raw_p)
    zh_file_sha = lt._sha256_file(zh_p)
    zh_text_sha = hashlib.sha256(zh.encode("utf-8")).hexdigest()
    raw_paras = lt.split_paragraphs(raw.split("\n"))
    zh_paras = lt.split_paragraphs(zh.split("\n"))

    if not quiet:
        print(f"  校对第 {idx + 1} 章：规则检查…", flush=True)
    issues = rule_check(raw, zh, meta)
    tokens = 0
    if use_llm:
        got, tokens = llm_check(slug, meta, raw_paras, zh_paras,
                                model=model, temperature=temperature, quiet=quiet)
        issues = _dedup(issues + got)

    counts = {s: sum(1 for x in issues if x.get("severity") == s)
              for s in SEVERITIES}
    report = {
        "work_id": slug,
        "chapter": idx + 1,
        "title": (meta.get("episodes") or [{}])[idx].get("title", "")
        if idx < len(meta.get("episodes") or []) else "",
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "rules+ai" if use_llm else "rules",
        "model": model if use_llm else "",
        "tokens": tokens,
        "raw_count": len(raw_paras),
        "zh_count": len(zh_paras),
        "counts": counts,
        "issues": issues,
        "escalate": False,
    }
    with lt.novel_lock(slug):
        current_raw_sha = hashlib.sha256(
            open(raw_p, "rb").read()).hexdigest()
        current_zh_sha = hashlib.sha256(
            open(zh_p, "rb").read()).hexdigest()
    stale_snapshot = (current_raw_sha != raw_sha
                      or current_zh_sha != zh_file_sha)
    if stale_snapshot:
        report["stale_snapshot"] = True
        report["stale_reason"] = "校对期间原文或译文已变化，未写入观察池、经验或修订。"

    # 观察池阈值按作品算；达到 20 条就提示人工复核（文档里的阈值落地，
    # 先选一个保守值，避免每条轻微观察都打断阅读）。
    if not stale_snapshot:
        with lt.novel_lock(slug):
            obs_n = _append_observations(slug, report)
        report["observations_total"] = obs_n
        report["escalate"] = obs_n >= 20
        if report["escalate"]:
            with open(os.path.join(qa_dir(slug), "escalations.jsonl"),
                      "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "work_id": slug, "at": report["at"],
                    "chapter": idx + 1, "observations_total": obs_n,
                    "reason": "观察池达到阈值，建议人工复核",
                }, ensure_ascii=False) + "\n")

    if learn and not stale_snapshot:
        lessons = derive_lessons(issues, meta)
        added = add_lessons(slug, meta, lessons, chapter=idx + 1,
                            source="review")
        report["lessons_added"] = added

    if fix and not stale_snapshot:
        report["fix"] = apply_fixes(slug, idx, meta, report, use_llm=use_llm,
                                    model=model, temperature=temperature,
                                    expected_sha256=zh_text_sha)
        # 修订后重新跑一次规则检查，报告以修订后的文本为准。
        with lt.novel_lock(slug):
            fresh = lt.load_meta(slug)
            zh2 = open(zh_p, encoding="utf-8").read()
        issues2 = rule_check(raw, zh2, fresh)
        report["after"] = {
            "counts": {s: sum(1 for x in issues2 if x.get("severity") == s)
                       for s in SEVERITIES},
            "issues": issues2,
        }
        report["issues_before"] = report["issues"]
        report["issues"] = issues2
        report["counts"] = report["after"]["counts"]
        with lt.novel_lock(slug):
            fresh = lt.load_meta(slug)
            prog = fresh.setdefault("progress", {})
            inc = list(prog.get("incomplete") or [])
            if any(x.get("severity") == "blocker" for x in issues2):
                if idx + 1 not in inc:
                    inc.append(idx + 1)
            else:
                inc = [c for c in inc if c != idx + 1]
            prog["incomplete"] = inc
            lt.save_meta(slug, fresh)
    elif fix:
        report["fix"] = {
            "changed": False, "stale": True,
            "note": "校对期间原文或译文已变化，已放弃自动修订。",
        }

    lt.save_json(report_paths(slug, idx + 1)[0], report)
    _write_markdown(slug, report)
    return report


def review_chapter(slug: str, idx: int, meta: dict | None = None, *,
                   use_llm: bool = False, model: str | None = None,
                   temperature: float = 0.2, fix: bool = False,
                   learn: bool = True, quiet: bool = False) -> dict:
    """公共入口：只对短 I/O 和写回转持书锁，LLM 阶段必须放锁外。"""
    lt = _lt()
    model = model or lt.REVIEW_MODEL
    return _review_chapter_impl(
        slug, idx, meta, use_llm=use_llm, model=model,
        temperature=temperature, fix=fix, learn=learn, quiet=quiet)


def _backup_chapter(slug: str, idx: int) -> str:
    lt = _lt()
    src = lt.chapter_path(slug, idx, "zh")
    base = src + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    p, n = base, 1
    while os.path.exists(p):
        n += 1
        p = f"{base}-{n}"
    with open(src, encoding="utf-8") as f:
        text = f.read()
    lt.save_text(p, text)
    return p


def apply_fixes(slug: str, idx: int, meta: dict, report: dict, *,
                use_llm: bool = False, model: str | None = None,
                temperature: float = 0.2,
                expected_sha256: str | None = None) -> dict:
    """只修可验证的阻断项。

    第一层：术语旧译名替换（字符串可验证，不花 token）。
    第二层：用户显式开启 AI 校对时，才让模型只改被标记的段落，并校验
    段落数、中文、术语；任何一项不通过就回退。
    """
    lt = _lt()
    model = model or lt.REVIEW_MODEL
    zh_p = lt.chapter_path(slug, idx, "zh")
    with lt.novel_lock(slug):
        text = open(zh_p, encoding="utf-8").read()
    start_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if expected_sha256 and start_sha != expected_sha256:
        return {"changed": False, "stale": True,
                "note": "译文在校对开始后已经变化，已放弃覆盖。"}
    original = text
    actions = []
    pairs: list[tuple[str, str, str]] = []
    for it in report.get("issues") or []:
        if it.get("severity") != "blocker" or it.get("type") != "term_old":
            continue
        old, new = it.get("old"), it.get("term_zh")
        if old and new and old != new:
            pairs.append((old, new, it.get("term") or ""))
    for old, new, term in pairs:
        cnt = text.count(old)
        if cnt:
            text = text.replace(old, new)
            actions.append({"old": old, "new": new, "count": cnt,
                            "reason": f"术语「{term}」锁定为「{new}」",
                            "by": "rule"})

    # AI 修订只针对仍存在的阻断项，且只接收问题段，不把整章交给模型。
    if use_llm:
        blockers = [x for x in report.get("issues") or []
                    if x.get("severity") == "blocker"
                    and x.get("type") in ("omission", "japanese", "mistranslation",
                                          "reference", "voice", "term_missing")
                    and int(x.get("para") or 0) > 0]
        paras = lt.split_paragraphs(text.split("\n"))
        raw_paras = lt.split_paragraphs(
            open(lt.chapter_path(slug, idx, "raw"), encoding="utf-8")
            .read().split("\n"))
        todo = []
        for it in blockers:
            n = int(it["para"]) - 1
            if 0 <= n < len(paras) and n < len(raw_paras):
                todo.append((n, raw_paras[n], paras[n], it))
        if todo:
            prompt = _revision_prompt(slug, meta, todo)
            try:
                reply, usage = lt.call_llm(
                    "你是修订者，只改给出的段落，不重译其它段落，不改剧情。",
                    prompt, model, temperature, role="review")
                report["fix_tokens"] = int((usage or {}).get("total_tokens") or 0)
                data = _extract_json(reply)
                if isinstance(data, dict):
                    data = data.get("revisions") or data.get("items")
                if isinstance(data, list):
                    for x in data:
                        if not isinstance(x, dict):
                            continue
                        try:
                            n = int(x.get("para") or 0) - 1
                        except (TypeError, ValueError):
                            continue
                        after = str(x.get("after") or "").strip()
                        if not (0 <= n < len(paras)) or not after:
                            continue
                        before = paras[n]
                        if len(after) > max(200, len(before) * 3):
                            continue
                        if KANA.findall(after):
                            continue
                        if not lt.detect_chinese(after):
                            continue
                        bad_term = False
                        for _jp, _zh in (meta.get("glossary") or {}).items():
                            if str(_jp or "") and str(_jp) in raw_paras[n] \
                                    and str(_zh or "") and str(_zh) not in after:
                                bad_term = True
                                break
                        if bad_term:
                            continue
                        paras[n] = after
                        actions.append({"para": n + 1, "old": _trunc(before),
                                        "new": _trunc(after),
                                        "reason": "AI 修订阻断项",
                                        "by": "llm"})
            except (Exception, SystemExit) as e:  # noqa: BLE001
                report.setdefault("fix_errors", []).append(
                    f"{type(e).__name__}: {e}")
        text = "\n".join(paras)

    if text == original:
        return {"changed": False, "actions": actions,
                "note": "没有可自动修复的阻断项；报告仍保留原样。"}
    with lt.novel_lock(slug):
        current = open(zh_p, encoding="utf-8").read()
        if hashlib.sha256(current.encode("utf-8")).hexdigest() != start_sha:
            return {"changed": False, "stale": True,
                    "actions": actions,
                    "note": "译文在模型修订期间发生变化，已放弃覆盖。"}
        fresh = lt.load_meta(slug)
        backup = _backup_chapter(slug, idx)
        lt.save_text(zh_p, text)
        lt.refresh_chapter_meta(slug, idx, fresh)
        lt.rebuild_novel_md(slug, fresh, force=True)
        lt.save_json(os.path.join(qa_dir(slug), f"fix-{idx + 1:04d}.json"), {
            "work_id": slug, "chapter": idx + 1,
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "backup": backup, "actions": actions,
        })
    return {"changed": True, "actions": actions, "backup": backup}


def _revision_prompt(slug: str, meta: dict,
                     todo: list[tuple[int, str, str, dict]]) -> str:
    lines = [
        "你只修订下面这些被校对标记的段落。属于同一部作品，",
        f"work_id={slug}，书名={meta.get('title') or ''}。",
        "不要改其它段落，不要解释，不要增删剧情。只输出 JSON 数组：",
        '[{"para":段号,"before":"改前","after":"改后","evidence":"依据"}]',
        "",
        "角色卡：",
        _character_context(meta, "\n".join(x[1] for x in todo), "") or "（无）",
        "",
        "术语表：",
        _terms_context(meta, "\n".join(x[1] for x in todo)) or "（无）",
        "",
    ]
    for n, raw, zh, it in todo:
        lines += [
            f"【第{n + 1}段】问题：{it.get('type')} / {it.get('evidence')}",
            f"原文：{raw}",
            f"当前译文：{zh}",
            "只改这一段；改后必须仍是中文，并保留原意与段落长度量级。",
            "",
        ]
    return "\n".join(lines)


def latest_report(slug: str, chapter: int) -> dict | None:
    p = report_paths(slug, chapter)[0]
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None

