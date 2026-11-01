#!/usr/bin/env python3
"""引号忠实度测试：引号必须**跟着原文**，不许按任何偏好统一。

用户原话（两轮）：
  1.「为什么翻译对话有时候是“”有时候是「」」——原文是「」，是我们的输出在漂。
  2.「不要强制用「」，我说过忠于原著。我不希望我自己的意志影响翻译。信达雅，先是信。」

所以正确行为不是"选一种字形统一"，而是**原文用哪种就哪种**：
  - 原文「」→ 译文「」；原文“”→ 译文“”；原文没有引号 → 不增不减；
  - 结构不一致（引号数量/开闭角色不同）→ 整段不动，机械层不碰译者的句子处理。

附带守住另一个更严重的问题：**多行对白只译第一行**（漏译）。
实测某部作品有 152 段如此，而段数/编号/中文校验全过 —— 只能靠引号对数兜。

不调 LLM，零 token。
"""

from __future__ import annotations

import argparse
import importlib.util
import sys

sys.path.insert(0, ".")
_s = importlib.util.spec_from_file_location("lt", "lntrans.py")
lt = importlib.util.module_from_spec(_s)
sys.argv = ["x"]
_s.loader.exec_module(lt)

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


align = lt.align_quotes_with_source

# --- 1. 跟着原文走（两个方向都要测，只测一个方向等于没测出"偏好"） -------------
check("原文「」译文“”→ 改成「」", align("“呼……”", "「呼……」") == "「呼……」")
check("原文“”译文「」→ 改成“”", align("「呼……」", "“呼……”") == "“呼……”")
check("原文『』译文「」→ 改成『』", align("「他说「嗯」」", "「他说『嗯』」") == "「他说『嗯』」")
check("原文嵌套「」→ 照原文", align("「a『b』」", "「a「b」」") == "「a「b」」")
check("原文无引号 → 不删除", align("译文加了「引号」", "原文没有引号") == "译文加了「引号」")
check("译文无引号 → 不添加", align("译文没有引号", "原文有「引号」") == "译文没有引号")
check("空串", align("", "「a」") == "" and align("「a」", "") == "「a」")

# --- 2. 结构不一致时整段不动（机械层不许改译者的句子处理） --------------------
check("引号数量不同 → 不动", align("「合并了一句」", "「一句」「另一句」") == "「合并了一句」")
check("开闭角色不同 → 不动", align("「a」b」", "「a」「b」") == "「a」b」")
check("多段对白只译一段 → 不动", align("「甲」", "「甲」「乙」「丙」") == "「甲」")

# --- 3. 健壮性 ---------------------------------------------------------------
check("幂等", all(align(align(z, s), s) == align(z, s)
                  for z, s in [("“a”", "「a」"), ("「a」", "“a”"), ("『x』", "「x」")]))
_strip = lambda s: "".join(c for c in s if c not in "「」『』“”‘’")
check("只改引号字形，别的字符不动",
      _strip(align("“你好”ABC123。", "「你好」")) == _strip("“你好”ABC123。"))

# --- 4. 漏译检测（多行对白只译首行） ------------------------------------------
miss = lt._missing_dialogue
check("3 处对白只译 1 处 → 标出", miss(["「A」\n「B」\n「C」"], ["「甲」"]) == [0])
check("1 对 1 → 不标", miss(["「x」"], ["「乙」"]) == [])
check("2 对 2 → 不标", miss(["「a」「b」"], ["「c」「d」"]) == [])
check("无引号段不参与", miss(["叙述一句"], ["叙述一句"]) == [])
check("多段时只标坏的那段",
      miss(["「a」", "「b」\n「c」"], ["「x」", "「y」"]) == [1])

# --- 5. prompt 必须写清"跟原文"，且不许写死一种字形 ---------------------------
sysp = lt.build_system_prompt({"glossary": {}, "characters": {}, "summaries": {},
                              "style": {}, "title": "t", "episodes": []})
check("prompt 要求引号跟着原文", "引号跟着原文" in sysp)
check("prompt 明令不许替换引号体系", "不要为了统一而替换引号体系" in sysp)
check("prompt 不许写死「」或“”", "引号一律用" not in sysp)
check("prompt 强调多行对白逐行译", "每一行都要译出来" in sysp)

# --- 6. 端到端：桩 LLM 故意写错字形，出来必须跟原文 ---------------------------
class Stub:
    """按脚本返回；记录每次请求的段数。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, system, prompt, model, temperature, retries=3,
                 role=None):
        import re
        ids = re.findall(r"^#(\d+):", prompt, re.M)
        self.calls.append(len(ids))
        out = self.script.pop(0) if self.script else ""
        return out, {"total_tokens": 7}


def run(script, paras):
    stub = Stub(script)
    orig = lt.call_llm
    lt.call_llm = stub
    try:
        stats = {"tok": 0, "calls": 0}
        out, used = lt.robust_translate_paras(
            {"glossary": {}, "characters": {}, "summaries": {}, "style": {},
             "title": "t", "episodes": []},
            paras, 0, "sys",
            argparse.Namespace(model="stub", temperature=0.0, allow_missing=False),
            "", stats)
        return out, stub, stats
    finally:
        lt.call_llm = orig


_out, _stub, _ = run(["#1: “甲”\n#2: “乙”"], ["「あ」", "「い」"])
check("端到端：弯引号被对齐成原文的「」", _out == ["「甲」", "「乙」"], str(_out))

_out2, _, _ = run(["#1: 「甲」"], ["“あ”"])
check("端到端：原文“”就保留“”", _out2 == ["“甲”"], str(_out2))

_out3, _stub3, _ = run(["#1: 「只有第一句」", "#1: 「三句都译了：一」「二」「三」"],
                       ["「一」\n「二」\n「三」"])
check("端到端：漏译对白会重试", len(_stub3.calls) >= 2, str(_stub3.calls))
check("端到端：重试后拿到的译文被接受", "三句都译了" in (_out3[0] if _out3 else ""), str(_out3))

# --- 6b. 残留口径：只有"真残留"才算（否则指标永远假红） ----------------------
# 踩过：把颜文字 `(つд⊂)`、装饰性浊点 `啊゛～`、喊叫的 `ーーー` 都算成"没译干净的假名"，
# 全库永远是红的 —— 一个永远红的指标等于没有指标。
check("颜文字里的假名不算残留", lt.kana_outside_quotes("(つд⊂)揉揉眼 ( ﾟдﾟ )瞪大眼！！") == 0)
check("长一点的颜文字/拟声括号也算",
      lt.kana_outside_quotes("（……妈゛妈゛……！太帅了，我已经不行了……！）") == 0)
check("装饰性浊点/长音符不算", lt.kana_outside_quotes("啊゛～，幼女前辈") == 0
      and lt.kana_outside_quotes("啊啊～～～～～！太尊了ー！！！") == 0)
check("真残留照样数出来", lt.kana_outside_quotes("还嘎——ん。") == 1)
check("外来语里的假名照数", lt.kana_outside_quotes("他说ケーキ很好吃") == 2)

# --- 7. 残留指标（允许"夹零星日文"就必须可计量） ------------------------------
check("count_kana 数平假名与片假名",
      lt.count_kana("那家伙也是祀ろわぬ教会的成员。") == 3
      and lt.count_kana("纯中文，没有假名。") == 0
      and lt.count_kana("カタカナとひらがな") == 9)

import inspect
_src = inspect.getsource(lt._translate_chapter_impl)
check("缓存命中路径也做对齐", "align_quotes_with_source" in _src)

print()
if fails:
    print(f"❌ test_quotes: {len(fails)} 项失败: {fails}")
    sys.exit(1)
print("✅ test_quotes 全部通过")
