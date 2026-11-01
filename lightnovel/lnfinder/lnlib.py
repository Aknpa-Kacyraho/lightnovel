"""lnlib —— 轻小说发现工具的共用库。

只用 Python 标准库，避免依赖问题。
数据来源（上游源站，全部可公开访问）：
  * Kakuyomu   https://kakuyomu.jp/  → 页面内嵌 Apollo JSON（排行榜 / 标签 / 搜索）
  * 成为小说家吧 https://api.syosetu.com/novelapi/api/ → 官方 JSON API（日文站点，部分网络不可达）
"""

from __future__ import annotations

import gzip
import html
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_CACHE: dict[str, tuple[float, bytes, str]] = {}
CACHE_TTL = 300.0


def fetch(url: str, *, headers: dict | None = None, timeout: int = 25, use_cache: bool = True) -> str:
    """取回 URL 文本。带内存缓存与 gzip 处理。失败抛 FetchError。"""
    now = time.time()
    if use_cache and url in _CACHE:
        ts, body, enc = _CACHE[url]
        if now - ts < CACHE_TTL:
            return body.decode(enc, "replace")

    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"})
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            enc = resp.headers.get("Content-Encoding", "")
            if enc == "gzip":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            elif enc == "deflate":
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            ctype = resp.headers.get("Content-Type", "")
            charset = "utf-8"
            m = re.search(r"charset=([\w-]+)", ctype)
            if m:
                charset = m.group(1)
            _CACHE[url] = (now, raw, charset)
            return raw.decode(charset, "replace")
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code} for {url}") from e
    except Exception as e:  # noqa: BLE001
        raise FetchError(f"{type(e).__name__}: {e} for {url}") from e


class FetchError(RuntimeError):
    pass


# ---------------------------------------------------------------- Kakuyomu

KAKUYOMU = "https://kakuyomu.jp"
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)

GENRE_JP = {
    "FANTASY": "奇幻",
    "ACTION": "动作",
    "SF": "科幻",
    "LOVE_STORY": "恋爱",
    "ROMANCE": "浪漫",
    "DRAMA": "戏剧",
    "HORROR": "恐怖",
    "MYSTERY": "悬疑",
    "NONFICTION": "纪实",
    "HISTORY": "历史",
    "CRITICISM": "评论",
    "OTHERS": "其他",
    "MAHO": "魔法少女",
    "FAN_FICTION": "二次创作",
}

SERIAL_JP = {"COMPLETED": "完结", "RUNNING": "连载中", "SUSPENDED": "休载"}


def kakuyomu_page(path: str) -> dict:
    """请求 kakuyomu 页面并返回其中的 Apollo 状态与查询键。"""
    url = path if path.startswith("http") else KAKUYOMU + path
    text = fetch(url)
    m = _NEXT_DATA_RE.search(text)
    if not m:
        raise FetchError(f"页面内没有 __NEXT_DATA__：{url}")
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        # 归一成 FetchError：调用方（kakuyomu_works 等）只捕 FetchError，
        # 裸 JSONDecodeError 会穿透到上层当未知异常，等于没兜住。
        raise FetchError(f"__NEXT_DATA__ 不是合法 JSON：{url}") from e
    page_props = data.get("props", {}).get("pageProps", {})
    apollo = page_props.get("__APOLLO_STATE__") or {}
    return {"url": url, "apollo": apollo, "page_props": page_props, "html": text}


def kakuyomu_works(path: str) -> list[dict]:
    """从任意 kakuyomu 页面抽出 Work 实体列表（带标签、连载状态、字数等）。"""
    page = kakuyomu_page(path)
    out = []
    for key, val in page["apollo"].items():
        if key.startswith("Work:") and isinstance(val, dict) and val.get("title"):
            out.append(normalize_work(val, page["apollo"]))
    return out


def normalize_work(w: dict, apollo: dict) -> dict:
    author = w.get("author") or {}
    author_name = None
    if isinstance(author, dict) and "__ref" in author:
        acc = apollo.get(author["__ref"]) or {}
        author_name = acc.get("activityName") or acc.get("name") or acc.get("screenName")
    elif isinstance(author, dict):
        author_name = author.get("activityName") or author.get("name")
    wid = str(w.get("id", ""))
    return {
        "source": "kakuyomu",
        "id": wid,
        "url": f"{KAKUYOMU}/works/{wid}",
        "title": w.get("title") or "",
        "catchphrase": w.get("catchphrase") or "",
        "genre": w.get("genre") or "",
        "genre_jp": GENRE_JP.get(w.get("genre") or "", w.get("genre") or ""),
        "tags": [t.strip() for t in (w.get("tagLabels") or []) if t and t.strip()],
        "author": author_name,
        "serial_status": SERIAL_JP.get(w.get("serialStatus") or "", w.get("serialStatus") or ""),
        "episodes": w.get("publicEpisodeCount") or 0,
        "characters": w.get("totalCharacterCount") or 0,
        "review_points": w.get("totalReviewPoint") or 0,
        "published_at": (w.get("publishedAt") or "")[:10],
        "last_episode_at": (w.get("lastEpisodePublishedAt") or "")[:10],
        "has_publication": bool(w.get("hasPublication")),
    }


# 流派 code（Apollo 里的 UPPER）↔ 站点 slug（/search?genre_name= 与 /rankings/{slug}/）。
# 站点只有这 12 个流派有榜/检索页；MAHO、FAN_FICTION 之流无对应页，故不入表。
GENRE_SLUG = {
    "FANTASY": "fantasy", "ACTION": "action", "SF": "sf",
    "LOVE_STORY": "love_story", "ROMANCE": "romance", "DRAMA": "drama",
    "HORROR": "horror", "MYSTERY": "mystery", "NONFICTION": "nonfiction",
    "HISTORY": "history", "CRITICISM": "criticism", "OTHERS": "others",
}
RANKING_RANGES = ("daily", "weekly", "monthly", "yearly", "entire")
RANKING_VARIATIONS = ("all", "long", "short")


def kakuyomu_ranking(genre: str = "all", range_: str = "weekly",
                     variation: str = "all") -> list[dict]:
    """真榜单页 /rankings/{genre}/{range}?work_variation={variation}。

    genre 收 UPPER code（FANTASY）/ slug（fantasy）/ "all"；一页约 110 本。
    首页 Apollo 那套 rankedWorks 只回 3 本，做发现太薄 —— 这个才是主入口。
    """
    slug = GENRE_SLUG.get(genre, genre)
    if range_ not in RANKING_RANGES:
        raise ValueError(f"未知榜单区间：{range_}（可选 {RANKING_RANGES}）")
    if variation not in RANKING_VARIATIONS:
        raise ValueError(f"未知榜单变体：{variation}（可选 {RANKING_VARIATIONS}）")
    return kakuyomu_works(f"/rankings/{slug}/{range_}?work_variation={variation}")


def kakuyomu_rankings() -> dict:
    """周榜（真榜单页，~110 本）+ 首页随机推荐 / 近 30 天新章 / 推荐关键词。"""
    page = kakuyomu_page("/")
    apollo = page["apollo"]
    root = apollo.get("ROOT_QUERY", {})
    res = {"weekly": [], "recommended": [], "fresh": [], "keywords": []}

    def refs(key_contains: str) -> list[dict]:
        for k, v in root.items():
            if key_contains in k:
                nodes = v.get("nodes") if isinstance(v, dict) else v
                works = []
                for item in nodes or []:
                    ref = item.get("__ref") if isinstance(item, dict) else None
                    if ref and ref in apollo:
                        works.append(normalize_work(apollo[ref], apollo))
                return works
        return []

    res["recommended"] = refs("recommendedWorksInRandomOrder")
    res["fresh"] = refs("kakuyomuNextWorksInRandomOrder")
    res["keywords"] = next(
        (v for k, v in root.items() if "recommendedKeywords" in k), []
    )
    # 周榜优先用真榜单页；拿不到再退回首页那 3 本，别让整条发现链挂掉
    try:
        res["weekly"] = kakuyomu_ranking("all", "weekly")
    except FetchError:
        res["weekly"] = refs("rankedWorks")
    return res


def kakuyomu_search(query: str, pages: int = 1, *,
                    genre: str | None = None,
                    order: str | None = None) -> list[dict]:
    """/search 检索：q（关键词）、genre_name（流派 slug）、order（如 weekly_ranking）、page。"""
    parts = []
    if query:
        parts.append("q=" + urllib.parse.quote(query))
    if genre:
        parts.append("genre_name=" + GENRE_SLUG.get(genre, genre))
    if order:
        parts.append("order=" + order)
    base = "/search" + ("?" + "&".join(parts) if parts else "")
    seen, out = set(), []
    for p in range(1, pages + 1):
        sep = "&" if "?" in base else "?"
        path = base if p == 1 else f"{base}{sep}page={p}"
        try:
            works = kakuyomu_works(path)
        except FetchError:
            if not out:
                raise        # 一页都没搜到：如实上抛，别假装"没有这本书"
            break            # 已拿到结果：保留，停止翻页
        for w in works:
            if w["id"] not in seen:
                seen.add(w["id"])
                out.append(w)
    return out


# ---------------------------------------------------------------- 成为小说家吧
# 一般向 ncode.syosetu.com / R18 novel18.syosetu.com 共用同一套页面模板。
# 反爬很轻但**要求完整浏览器头**：少 Accept / Sec-Fetch-* 就 403（实测），
# R18 还要 over18=yes（否则年龄确认页）。API 在 api.syosetu.com/novelapi|novel18api。
SYOSETU_API = "https://api.syosetu.com/novelapi/api/"
SYOSETU_R18_API = "https://api.syosetu.com/novel18api/api/"
SYOSETU = "https://ncode.syosetu.com"
SYOSETU_R18 = "https://novel18.syosetu.com"
SYOSETU_DOMAINS = {"syosetu": SYOSETU, "novel18": SYOSETU_R18}
_R18_COOKIE = "over18=yes"

_SYOSETU_HEADERS = {
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://syosetu.com/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-site",
    "Upgrade-Insecure-Requests": "1",
}


def syosetu_headers(r18: bool = False, *, api: bool = False) -> dict:
    h = dict(_SYOSETU_HEADERS)
    if api:
        h["Accept"] = "application/json,text/html,*/*;q=0.8"
        h.pop("Sec-Fetch-Dest", None)
        h.pop("Sec-Fetch-Mode", None)
        h.pop("Sec-Fetch-Site", None)
        h.pop("Upgrade-Insecure-Requests", None)
    if r18:
        h["Cookie"] = _R18_COOKIE
        h["Referer"] = "https://novel18.syosetu.com/"
    return h


def syosetu_source(url_or_code: str) -> tuple[str, str] | None:
    """识别 syosetu 链接或裸 ncode，返回 (source, ncode)。

    source ∈ {"syosetu", "novel18"}；ncode 统一大写（本地 source_id 用它）。
    只认 URL/裸码，不解析正文。
    """
    s = (url_or_code or "").strip()
    m = re.match(r"https?://(ncode|novel18)\.syosetu\.com/([nN][0-9A-Za-z]+)/?", s)
    if m:
        return ("novel18" if m.group(1) == "novel18" else "syosetu",
                m.group(2).upper())
    m = re.fullmatch(r"([nN][0-9A-Za-z]{5,})", s)
    if m:
        return ("syosetu", m.group(1).upper())
    return None


def syosetu_api(r18: bool = False, **params) -> list[dict]:
    """官方 JSON API。order=weekly|monthly|new|hyoka|favnovelcnt|reviewcnt；
    genre=101.. (101 异世界转生 / 102 异世界 / 201 SF / 301 恋爱 ...)；lim≤500。
    """
    params.setdefault("out", "json")
    params.setdefault("lim", 50)
    params.setdefault("of", "t-n-w-s-k-g-l-e-nu-ga-ka-nt-gf-gl")
    source = "novel18" if r18 else "syosetu"
    base = SYOSETU_R18_API if r18 else SYOSETU_API
    text = fetch(f"{base}?{urllib.parse.urlencode(params)}",
                 headers=syosetu_headers(r18, api=True))
    data = json.loads(text)
    rows = data[1:] if isinstance(data, list) else []
    out = []
    for r in rows:
        ncode = str(r.get("ncode") or "")
        if not ncode:
            continue
        out.append({
            "source": source,
            "id": ncode.upper(),
            "url": f"{SYOSETU_DOMAINS[source]}/{ncode.lower()}/",
            "title": r.get("title") or "",
            "catchphrase": "",
            "genre": str(r.get("genre") or ""),
            "genre_jp": "",
            "tags": [k for k in (r.get("keyword") or "").split() if k]
                    + (["R18"] if r18 else []),
            "author": r.get("writer") or "",
            "serial_status": "完结" if r.get("end") == 1 else "连载中",
            "episodes": r.get("general_all_no") or 0,
            "characters": r.get("length") or 0,
            "review_points": r.get("global_point") or 0,
            "fav_count": r.get("fav_novel_cnt") or 0,
            "published_at": (r.get("general_firstup") or "")[:10],
            "last_episode_at": (r.get("general_lastup") or "")[:10],
            "has_publication": False,
            "r18": r18,
        })
    return out


def syosetu_rankings(r18: bool = False, limit: int = 60) -> list[dict]:
    """周榜 + 新作，按 ncode 去重（API 无分页，lim 一次拿够）。"""
    seen, out = set(), []
    for order in ("weekly", "new"):
        try:
            rows = syosetu_api(r18=r18, order=order, lim=limit)
        except (FetchError, ValueError):
            continue
        for w in rows:
            if w["id"] in seen:
                continue
            seen.add(w["id"])
            out.append(w)
    return out


def syosetu_search(word: str, *, r18: bool = False, limit: int = 60) -> list[dict]:
    word = (word or "").strip()
    if not word:
        return []
    return syosetu_api(r18=r18, word=word, lim=limit)


def _html_text(s: str, *, keep_breaks: bool = False) -> str:
    """去标签取文本；ruby 的注音（rt/rp）丢掉，别把假名混进正文。"""
    s = re.sub(r"<rt[^>]*>.*?</rt>", "", s or "", flags=re.S)
    s = re.sub(r"<rp[^>]*>.*?</rp>", "", s, flags=re.S)
    if keep_breaks:
        s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[ \t\u3000]+", " ", html.unescape(s)).strip()


_EP_RE = (r'<a[^>]*href="/%s/(\d+)/"[^>]*class="p-eplist__subtitle"[^>]*>(.*?)</a>')
_CH_RE = r'<div class="p-eplist__chapter-title"[^>]*>(.*?)</div>'


def syosetu_parse_work(html_text: str, ncode: str,
                       source: str = "syosetu") -> dict:
    """从作品页 HTML 抽标题/作者/简介/目录（纯函数，测试不联网）。"""
    ncode_u = ncode.upper()
    title = _html_text(_first(html_text,
                              r'<h1 class="p-novel__title[^"]*"[^>]*>(.*?)</h1>')
                       or "")
    author = _html_text(_first(html_text,
                               r'<div class="p-novel__author"[^>]*>(.*?)</div>')
                        or "")
    author = re.sub(r"^作者[：:]\s*", "", author)
    synopsis = _html_text(_first(
        html_text, r'<div[^>]*class="p-novel__summary"[^>]*>(.*?)</div>') or "",
        keep_breaks=True)
    synopsis = re.sub(r"\n{3,}", "\n\n", synopsis)
    toc: list[dict] = []
    cur: dict | None = None
    pat = re.compile(_CH_RE + "|" + (_EP_RE % re.escape(ncode.lower())), re.S)
    for m in pat.finditer(html_text):
        if m.group(1) is not None:
            cur = {"title": _html_text(m.group(1)), "episodes": []}
            toc.append(cur)
            continue
        eid, etitle = m.group(2), _html_text(m.group(3))
        if cur is None:
            cur = {"title": "", "episodes": []}
            toc.append(cur)
        if any(e["id"] == eid for e in cur["episodes"]):
            continue
        cur["episodes"].append({"id": eid, "title": etitle, "at": "",
                                "publishedAt": ""})
    if not toc:
        # 兼容 class 顺序变化：退回只按链接抓，标题留空
        for m in re.finditer(r'<a[^>]*href="/%s/(\d+)/"[^>]*>(.*?)</a>'
                             % re.escape(ncode.lower()), html_text, re.S):
            eid = m.group(1)
            if not any(e["id"] == eid for g in toc for e in g["episodes"]):
                toc.append({"title": "", "episodes": [
                    {"id": eid, "title": _html_text(m.group(2)), "at": "",
                     "publishedAt": ""}]})
    if not toc and "p-novel__body" in html_text:
        # 短篇：作品页直接是正文，没有 p-eplist/话链接。当成第 1 话。
        toc = [{"title": "", "episodes": [
            {"id": "1", "title": title, "at": "", "publishedAt": ""}]}]
    episodes = [e for g in toc for e in g["episodes"]]
    return {
        "source": source,
        "source_id": ncode_u,
        "url": f"{SYOSETU_DOMAINS[source]}/{ncode.lower()}/",
        "title": title,
        "author": author,
        "synopsis": synopsis,
        "toc": toc,
        "episodes": episodes,
        "episode_count": len(episodes),
        "r18": source == "novel18",
    }


def syosetu_work(ncode_or_url: str, r18: bool | None = None) -> dict:
    """抓作品页（含分页目录）并解析。r18 不给就按域名判断。"""
    parsed = syosetu_source(ncode_or_url)
    if not parsed:
        raise FetchError(f"不是 syosetu 作品链接：{ncode_or_url}")
    source, ncode = parsed
    if r18 is not None:
        source = "novel18" if r18 else "syosetu"
    url = f"{SYOSETU_DOMAINS[source]}/{ncode.lower()}/"
    first = fetch(url, headers=syosetu_headers(source == "novel18"))
    pages = 1
    for m in re.finditer(r'href="[^"]*[?&]p=(\d+)"', first):
        pages = max(pages, int(m.group(1)))
    html_all = first
    for pno in range(2, min(pages, 200) + 1):
        try:
            html_all += fetch(f"{url}?p={pno}",
                             headers=syosetu_headers(source == "novel18"))
        except FetchError:
            break
    return syosetu_parse_work(html_all, ncode, source)


def syosetu_parse_episode(html_text: str) -> str:
    """从章节页 HTML 取正文，一段一行（空段落保留为空行）。

    注意 `p-novel__body` 里通常有三块 `p-novel__text`：--preface（前書き）、
    无修饰的正文、--afterword（後書き）。**只要正文**，前后记不是小说内容。
    """
    i = html_text.find('class="p-novel__body"')
    chunk = html_text[i:] if i >= 0 else html_text
    inner = None
    for m in re.finditer(
            r'<div class="([^"]*p-novel__text[^"]*)"[^>]*>(.*?)</div>', chunk, re.S):
        cls = m.group(1)
        if "--preface" in cls or "--afterword" in cls:
            continue
        inner = m.group(2)
        break
    if inner is None:
        raise FetchError("章节页没有正文 p-novel__text（结构变了或被拦）")
    lines = []
    for pm in re.finditer(r"<p[^>]*>(.*?)</p>", inner, re.S):
        lines.append(_html_text(pm.group(1), keep_breaks=True))
    return "\n".join(lines).strip()


def syosetu_episode_text(ncode: str, eid: str, r18: bool = False) -> str:
    base = f"{SYOSETU_DOMAINS['novel18' if r18 else 'syosetu']}/{ncode.lower()}"
    try:
        return syosetu_parse_episode(
            fetch(f"{base}/{int(eid)}/", headers=syosetu_headers(r18)))
    except FetchError:
        if str(eid) != "1":
            raise
        # 短篇（作品页直接是正文）没有 /1/，回退到作品页。
        return syosetu_parse_episode(
            fetch(f"{base}/", headers=syosetu_headers(r18)))


# ---------------------------------------------------------------- Novelup
# ⚠ 实验性，**未接线**（全仓无任何调用方）。保留只为记录反推来的端点/选择器，勿当可用源接入。
# 搁置原因：全站挂 AWS WAF（+CloudFront）。冷 stdlib → 202 挑战页；真浏览器过验证后落
# aws-waf-token（~4 天）内少量请求可 200；但**连续自动化抓取**（=发现 + 翻一本 100+ 章）
# 会触发 IP 级升级：403/405 → CAPTCHA，之后纯 stdlib 永久打不通（连人都得去浏览器点）。
# 这与"按钮名字就是承诺 / 数字不能骗人"直接冲突 —— 翻译翻到一半源站变 CAPTCHA 是坏体验。
# 唯一出路是给源池"加一家"，但代价是每 4 天手动过验证 + 随时可能中断，故不做。
# 真页面实测（2026-10）：搜索/作品/目录/正文选择器已坐实（见下各函数）。

NOVELUP = "https://novelup.plus"
_WAF_MARKERS = ("gokuprops", "aws-waf", "awswaf", "challenge-container")
_WAF_TOKEN_ERR = "Novelup 需 aws-waf-token，请重新获取"


def waf_token() -> str:
    """Novelup 的 aws-waf-token：环境变量 LNTRANS_WAF_TOKEN 优先，
    其次 lntrans/data/settings.json 的 novelup_waf_token（该文件被导出脚本排除，不进包）。"""
    tok = (os.environ.get("LNTRANS_WAF_TOKEN") or "").strip()
    if tok:
        return tok
    root = os.environ.get("LNTRANS_DATA_ROOT")
    if not root:
        return ""
    try:
        with open(os.path.join(root, "data", "settings.json"), encoding="utf-8") as f:
            return (json.load(f).get("novelup_waf_token") or "").strip()
    except (OSError, ValueError):
        return ""


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "")


def _first(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text, re.S)
    return m.group(1) if m else None


def _num(txt: str) -> int:
    m = re.match(r"\s*([\d.]+)\s*([KkMm]?)", txt or "")
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2).upper()
    if unit == "K":
        val *= 1000
    elif unit == "M":
        val *= 1_000_000
    return int(val)


def _novelup_get(url: str) -> str:
    """Novelup 全站挂在 AWS WAF 后面：不带 aws-waf-token 会被回 202 挑战页；
    机器流量打多了会被升级成 403/405（人机验证）——即便 token 还在。
    对缺 token / 挑战页 / 被升级统一抛 FetchError，绝不把挑战页当正文。"""
    tok = waf_token()
    if not tok:
        raise FetchError(_WAF_TOKEN_ERR)
    try:
        text = fetch(url, headers={"Cookie": f"aws-waf-token={tok}"}, use_cache=False)
    except FetchError as e:
        if any(code in str(e) for code in ("HTTP 403", "HTTP 405", "HTTP 429")):
            raise FetchError(_WAF_TOKEN_ERR) from e
        raise
    if any(mark in text[:8000].lower() for mark in _WAF_MARKERS):
        raise FetchError(_WAF_TOKEN_ERR)
    return text


def novelup_search(query: str, pages: int = 1) -> list[dict]:
    seen, out = set(), []
    q = urllib.parse.quote(query)
    for p in range(1, pages + 1):
        url = f"{NOVELUP}/search?q={q}&search[tag]=1&sort=1&p={p}"
        try:
            text = _novelup_get(url)
        except FetchError:
            if not out:
                raise        # 一页都没搜到：如实上抛，别假装"没有这本书"
            break            # 已拿到结果：保留分页结果，停止翻页
        for chunk in re.split(r'<div class="sumally', text)[1:]:
            m = re.search(
                r'class="story_name"><a[^>]*href="([^"]*/story/(\d+))"[^>]*>(.*?)</a>',
                chunk, re.S,
            )
            if not m:
                continue
            href, sid, title = m.group(1), m.group(2), _strip_tags(m.group(3))
            if sid in seen:
                continue
            seen.add(sid)
            likes = _first(chunk, r'class="count_good">.*?<span>([^<]+)</span>')
            points = _first(chunk, r'class="story_point">.*?<span>([^<]+)</span>')
            out.append({
                "source": "novelup",
                "id": sid,
                "url": href,
                "title": unescape(title).strip(),
                "catchphrase": unescape(
                    _strip_tags(_first(chunk, r'class="story_comment">(.*?)</p>') or "")
                ).strip(),
                "genre": "",
                "genre_jp": "",
                "tags": [],
                "author": unescape(
                    _first(chunk, r'class="story_author_name"><a[^>]*>([^<]+)</a>') or ""
                ).strip(),
                "serial_status": "",
                "episodes": 0,
                "characters": 0,
                "review_points": _num(likes or points or ""),
                "published_at": "",
                "last_episode_at": "",
                "has_publication": False,
            })
    return out


def novelup_work(sid: str) -> dict:
    text = _novelup_get(f"{NOVELUP}/story/{sid}")
    title = _strip_tags(_first(text, r"<h1[^>]*>(.*?)</h1>") or "")
    desc = _first(text, r'<meta name="description" content="([^"]*)"')
    author = _first(text, r'class="story_author_name"><a[^>]*>([^<]+)</a>')
    if not author:
        author = _first(text, r'/user/\d+/profile"[^>]*>([^<]+)</a>')
    return {
        "source": "novelup",
        "id": str(sid),
        "url": f"{NOVELUP}/story/{sid}",
        "title": unescape(title).strip(),
        "catchphrase": unescape(desc or "").strip(),
        "genre": "",
        "genre_jp": "",
        "tags": [],
        "author": unescape(author or "").strip(),
        "serial_status": "",
        "episodes": 0,
        "characters": 0,
        "review_points": 0,
        "published_at": "",
        "last_episode_at": "",
        "has_publication": False,
    }


def novelup_toc(sid: str, pages: int = 1) -> list[dict]:
    """目录：/story/{id} 与 /story/{id}?p={page}（长作品 200 话/页）。

    只在 .episodeListItem 里取链接 —— 页面上的「最新話を読む」等工具按钮
    href 也形如 /story/{id}/{cid}，整页扫会把它误当第 1 章。
    """
    eps, seen = [], set()
    link = re.compile(r'/story/%s/(\d+)"[^>]*>(.*?)</a>' % re.escape(str(sid)), re.S)
    for p in range(1, pages + 1):
        url = f"{NOVELUP}/story/{sid}" + ("" if p == 1 else f"?p={p}")
        try:
            text = _novelup_get(url)
        except FetchError:
            if not eps:
                raise
            break
        for item in re.split(r'class="episodeListItem', text)[1:]:
            m = link.search(item)
            if not m:
                continue
            cid, title = m.group(1), m.group(2)
            if cid in seen:
                continue
            seen.add(cid)
            eps.append({
                "id": cid,
                "title": unescape(_strip_tags(title)).strip(),
                "url": f"{NOVELUP}/story/{sid}/{cid}",
            })
    return eps


def novelup_episode_text(sid: str, cid: str) -> str:
    """正文在章节页 p#episode_content 里（不是目录页 /story/{id}）。"""
    text = _novelup_get(f"{NOVELUP}/story/{sid}/{cid}")
    m = re.search(r'<p[^>]*id="episode_content"[^>]*>(.*?)</p>', text, re.S)
    if not m:
        m = re.search(r'id="episode_content"[^>]*>(.*?)</(?:p|div)>', text, re.S)
    if not m:
        raise FetchError(f"Novelup 章节页没找到正文 episode_content：{sid}/{cid}")
    body = re.sub(r"<br\s*/?>", "\n", m.group(1))
    return unescape(_strip_tags(body)).strip()


# ---------------------------------------------------------------- 展示

def fmt_int(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0"
    if n >= 10000:
        return f"{n/10000:.1f}万"
    return str(n)


def short(text: str, width: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    out, w = [], 0
    for ch in text:
        cw = 2 if ord(ch) > 0x2E80 else 1
        if w + cw > width:
            break
        out.append(ch)
        w += cw
    return "".join(out) + ("…" if w >= width else "")


def unescape(s: str) -> str:
    return html.unescape(s or "")
