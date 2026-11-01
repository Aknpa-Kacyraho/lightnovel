"""去掉模型复读：译文里整段/整句连续重复时，删掉多出来的一份。

只处理足够长的句子/段落；「？」「！」或短对白可能真的是角色在复读，
不能误删。原文自己就有同样重复时完全不动（忠于原著）。
"""

from __future__ import annotations

import re

_SENT_SPAN_RE = re.compile(
    r'[^\n。！？!?]+[。！？!?]+[」』”"]?|[^\n。！？!?]+$')


def _sentence_units(text: str) -> list[tuple[int, int, str]]:
    out = []
    for m in _SENT_SPAN_RE.finditer(text):
        key = m.group(0).strip()
        if key:
            out.append((m.start(), m.end(), key))
    return out


def _drop_spans(text: str, units: list[tuple[int, int, str]],
                drop: set[int]) -> str:
    if not drop:
        return text
    parts, last = [], 0
    for i, (a, b, _k) in enumerate(units):
        if i in drop:
            parts.append(text[last:a])
            last = b
    parts.append(text[last:])
    return "".join(parts)


def dedupe_sentence_line(line: str) -> str:
    """去掉同一段里连续复读的句子。

    只处理**长句**或**成组的 A A / A B A B**：短语气词可能真是结巴/追问。
    """
    units = _sentence_units(line)
    keys = [u[2] for u in units]
    n = len(keys)
    if n < 2:
        return line
    drop: set[int] = set()
    # 整块复读：A B C A B C（2~4 句一块）
    i = 0
    while i < n:
        hit = False
        for size in (4, 3, 2):
            if i + 2 * size <= n and keys[i:i + size] == keys[i + size:i + 2 * size]:
                chars = sum(len(k) for k in keys[i:i + size])
                if chars >= 16:
                    drop.update(range(i + size, i + 2 * size))
                    i += 2 * size
                    hit = True
                    break
        if not hit:
            i += 1
    # 逐句复读：A A B B C C（至少两组，或单句够长）
    i = 0
    while i + 1 < n:
        if keys[i] == keys[i + 1] and len(keys[i]) >= 4:
            group = [i]
            j = i + 2
            while j + 1 < n and keys[j] == keys[j + 1] and len(keys[j]) >= 4:
                group.append(j)
                j += 2
            pair_chars = sum(len(keys[k]) for k in group) * 2
            if len(group) >= 2 or pair_chars >= 60:
                drop.update(k + 1 for k in group)
            i = j
        else:
            i += 1
    return _drop_spans(line, units, drop)


def dedupe_paragraph_lines(text: str) -> str:
    """去掉相邻的重复长段落（中间隔空行也算）。短句对白不动。"""
    out, prev = [], ""
    for line in text.split("\n"):
        key = line.strip()
        if key and key == prev and len(key) >= 20:
            continue
        out.append(line)
        if key:
            prev = key
    return "\n".join(out)


def dedupe_repeated_output(text: str, source: str = "") -> str:
    """修模型复读；原文自己重复时原样返回。"""
    if not text:
        return text
    if source:
        if dedupe_paragraph_lines(source) != source:
            return text
        if any(dedupe_sentence_line(x) != x for x in source.split("\n")):
            return text
    cleaned = dedupe_paragraph_lines(text)
    cleaned = "\n".join(dedupe_sentence_line(x) for x in cleaned.split("\n"))
    return cleaned
