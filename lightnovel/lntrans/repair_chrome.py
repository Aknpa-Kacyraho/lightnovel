#!/usr/bin/env python3
"""清掉已落盘章节里的**网站页脚残留**（站点改版留下的历史脏数据）。

背景：抓正文的 fallback 原来是「从 widget-episodeBody 起切 200KB 再正则抓 <p>」，
把页脚的注册引导（新規ユーザー登録 / 今はしない）、安卓字体提示、
応援コメント 区全当正文抓了进来；LLM 又老老实实把它们翻成中文 ——
于是**每一章末尾**都能读到「点击滚动 / 部分Android设备上字体设置不会生效」。
抓取逻辑已经修好（只取 episodeBody 那一个 div），但**已经落盘的章节不会自己变好**。

做法（保守，不猜）：
  1. 重新抓一次干净原文（免费，不花 token）；
  2. 干净原文与旧原文按"段"求**共同前缀** K；
  3. 旧文件第 K 段之后当残留删掉；译文**同索引一起删**
     （渲染是 zh[i] ↔ jp[i] 按段对齐，只删一边会让中日文错位）；
  4. 对不上的（段数不等、前缀太短、译文末段看着也脏）**跳过并报告** ——
     宁可留着几行页脚，也不能删掉正文。

用法：
  python3 repair_chrome.py                      # 干跑，只报告
  python3 repair_chrome.py --apply              # 真改（改写前先备份到系统临时目录）
  python3 repair_chrome.py --slug <slug> --apply
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 加载子模块时会把 sys.argv 改成假值（那些模块自己也用 argv），
# 不还原的话**本脚本自己的参数会被忽略**（踩过：--apply 没生效，白跑一遍）
_REAL_ARGV = list(sys.argv)

_spec = importlib.util.spec_from_file_location("lntrans", os.path.join(HERE, "lntrans.py"))
lt = importlib.util.module_from_spec(_spec)
sys.argv = ["lntrans"]
_spec.loader.exec_module(lt)

_spec2 = importlib.util.spec_from_file_location("lnrender", os.path.join(HERE, "lnrender.py"))
lr = importlib.util.module_from_spec(_spec2)
sys.argv = ["lnrender"]
_spec2.loader.exec_module(lr)

# 中文译文里不该出现的"网站文案"痕迹（用来判断译文侧是否也需要人工看一眼）
DIRTY_ZH = ("点击滚动", "字体设置", "注册", "登录", "应援", "评论", "通知",
            "关注", "免费", "安卓")


def common_prefix(a: list[str], b: list[str]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


# 页脚区**必然**包含的锚点（kakuyomu 阅读器的评论/设置面板）。
# 找到它就能一刀切，不用逐条猜"小/中/大"这种也可能是正文的词。
ANCHOR_JP = ("応援コメント", "タップでスクロール", "一部のAndroid端末では",
             "新規ユーザー登録", "アカウントをお持ちの方", "応援したユーザー",
             "さんがに応援しました", "閲覧履歴", "表示設定")
ANCHOR_ZH = ("应援评论", "点击滚动", "部分安卓设备", "新用户注册", "用户注册",
             "应援的用户", "进行了应援", "还没有应援", "浏览历史", "显示设置",
             "小说未读章节数", "追踪关注用户")


def junk_start(seq: list[str], anchors: tuple[str, ...]) -> int | None:
    for i, x in enumerate(seq):
        if any(a in x for a in anchors):
            return i
    return None


def repair_chapter(slug: str, idx: int, meta: dict, apply: bool) -> str:
    """返回 "skip:…" / "clean" / "trim …"。"""
    ndir = os.path.join(lt.novel_dir(slug))
    rp = os.path.join(ndir, "raw", f"{idx:04d}.txt")
    zp = os.path.join(ndir, "chapters", f"{idx:04d}.txt")
    if not os.path.exists(rp):
        return "skip:没有原文"
    old_raw = open(rp, encoding="utf-8").read()
    eps = meta.get("episodes") or []
    if idx >= len(eps):
        return "skip:没有这一话的 id"
        clean = lt.fetch_episode_text(meta["source_id"], eps[idx]["id"],
                                      meta.get("source") or "kakuyomu")
    time.sleep(0.6)
    P, C = lr.jp_paragraphs(old_raw), lr.jp_paragraphs(clean)
    # 文件都以换行结尾，解析出来会多一个空段；不归一化的话
    # 每次跑都会说"还得删 1 段"（内容其实已经干净了）—— 归一化后才幂等。
    for seq in (P, C):
        while seq and seq[-1] == "":
            seq.pop()
    if P == C:
        return "clean"
    cp = common_prefix(P, C)
    if cp < max(3, int(len(C) * 0.6)):
        return f"skip:共同前缀太短（{cp}/{len(C)}）"
    # 原文侧：以**干净抓取**为准，但要能对得上（否则说明抓取本身变了）
    keep_jp = len(C)
    if cp == len(C) - 1 and P and P[cp].startswith(C[cp]):
        keep_jp = cp + 1          # 旧文件把"末段正文 + 页脚行"并成了一段
    elif cp != len(C):
        return f"skip:与干净原文对不上（cp={cp}/{len(C)}）"
    jj = junk_start(P, ANCHOR_JP)
    if jj is None or abs(jj - keep_jp) > 3:
        return f"skip:原文找不到页脚锚点（keep={keep_jp} anchor={jj}）"

    has_zh = os.path.exists(zp) and os.path.getsize(zp) > 0
    Z = lr.zh_paragraphs(open(zp, encoding="utf-8").read()) if has_zh else []
    while Z and Z[-1] == "":
        Z.pop()
    keep_z = len(Z)
    if has_zh:
        # 译文侧要切到哪一段？
        #  · zh 与 jp 段数相等（d=0）→ 直接按原文边界切：翻译是逐段对应的，
        #    这一步是严格的，不需要猜（大多数情况走这条）；
        #  · 段数差 d（翻译时合并过几段）→ 单独找译文的页脚锚点，并用
        #    "干净原文长度 - d"交叉验证，对不上就不动它。
        d = len(P) - len(Z)
        if d < 0 or d > 3:
            return f"skip:中日段数差得太多（zh={len(Z)} jp={len(P)}）"
        if d == 0:
            keep_z = keep_jp
        else:
            zj = junk_start(Z, ANCHOR_ZH)
            if zj is None or abs(zj - (keep_jp - d)) > 3:
                return (f"skip:段数差 {d} 且译文页脚对不上"
                        f"（anchor={zj} 期望≈{keep_jp - d}）")
            keep_z = zj
        if keep_z < 1:
            return "skip:译文内容段数为 0"
        if any(w in Z[keep_z - 1] for w in DIRTY_ZH):
            return "skip:译文末段混着网站文案，需人工看"
    if not apply:
        return (f"trim 原文 {len(P)} → {keep_jp} 段"
                + (f"，译文 {len(Z)} → {keep_z} 段" if has_zh else ""))
    # —— 真改 ——
    with open(rp, "w", encoding="utf-8") as f:
        f.write("\n".join(C) + "\n")
    if has_zh:
        with open(zp, "w", encoding="utf-8") as f:
            f.write("\n".join(Z[:keep_z]) + "\n")
        lt.refresh_chapter_meta(slug, idx, meta, update_glossary=False)
    return (f"trim 原文 {len(P)} → {keep_jp} 段"
            + (f"，译文 {len(Z)} → {keep_z} 段" if has_zh else ""))


def main() -> int:
    sys.argv = _REAL_ARGV
    ap = argparse.ArgumentParser(description="清掉章节里的网站页脚残留")
    ap.add_argument("--apply", action="store_true", help="真改（默认干跑）")
    ap.add_argument("--slug", default="", help="只处理这一本")
    args = ap.parse_args()

    root = getattr(lt, "NOVELS_DIR", None) or os.path.join(HERE, "novels")
    # 干净环境（刚部署、还没译过书）直接跑维护脚本不该 traceback：
    # os.listdir 在不存在的目录上会抛 FileNotFoundError。
    if not os.path.isdir(root):
        print(f"没有作品目录：{root}")
        print("（正常状态：还没翻译过任何书，或 LNTRANS_DATA_ROOT 指向了空目录。）")
        return 0
    slugs = ([args.slug] if args.slug
             else sorted(d for d in os.listdir(root)
                         if os.path.isdir(os.path.join(root, d))
                         and not d.startswith(".")))
    backup = os.path.join(tempfile.gettempdir(),
                          "lntrans-chrome-backup-" + time.strftime("%Y%m%d-%H%M%S"))
    total = {"clean": 0, "trim": 0, "skip": 0}
    for slug in slugs:
        mp = os.path.join(root, slug, "meta.json")
        if not os.path.exists(mp):
            continue
        meta = json.load(open(mp, encoding="utf-8"))
        # ⚠ 备份必须在**改写之前**：repair_chapter 会就地覆盖 raw/chapters，
        # 事后备份等于备份了改后的内容，回滚不了（踩过：备份目录是脏数据）。
        if args.apply:
            for sub in ("raw", "chapters"):
                src = os.path.join(root, slug, sub)
                if os.path.isdir(src):
                    shutil.copytree(src, os.path.join(backup, slug, sub),
                                    dirs_exist_ok=True)
        rows = []
        for i in range(len(meta.get("episodes") or [])):
            try:
                res = repair_chapter(slug, i, meta, args.apply)
            except (Exception, SystemExit) as e:  # noqa: BLE001
                # SystemExit 也要接住：lt.die() 是 sys.exit(1)，不接的话
                # 单话抓取失败就会中断整脚本（而此时已改的章节还没备份）。
                res = f"skip:{type(e).__name__}: {e}"
            if res == "clean":
                total["clean"] += 1
                continue
            if res.startswith("skip"):
                total["skip"] += 1
            else:
                total["trim"] += 1
            rows.append(f"    #{i+1} {res}")
        if rows:
            print(f"  {slug}（{len(meta.get('episodes') or [])} 话）")
            print("\n".join(rows))
    print(f"\n干净 {total['clean']} 话 · 清掉页脚 {total['trim']} 话 · 跳过 {total['skip']} 话")
    if args.apply:
        print(f"备份：{backup}")
    elif total["trim"]:
        print("（干跑。确认后再加 --apply）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
