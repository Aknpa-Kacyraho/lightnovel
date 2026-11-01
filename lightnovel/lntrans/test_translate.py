#!/usr/bin/env python3
"""翻译健壮性测试（学自 auto-novel 的两项校验 + 二分降级）。

不调用真 LLM：把 call_llm 打桩，喂各种"坏输出"，
验证校验能发现问题、二分能救回来、失败时不会静默塞原文。

为什么必须测：这类逻辑平时跑得好好的，只有在模型偶发抽风时
（少输出一段、把日文抄回来）才暴露 —— 不测就是盲区。
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


ARGS = argparse.Namespace(model="stub", temperature=0.0, allow_missing=False)
META = {"glossary": {}, "characters": {}, "summaries": {}, "style": {},
        "title": "t", "episodes": []}


class Stub:
    """按预设脚本依次返回；记录每次请求用的段落数。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, system, prompt, model, temperature, retries=3,
                 role=None):
        # 从 prompt 里数出给了几段（以 #编号: 开头）
        import re
        ids = re.findall(r"^#(\d+):", prompt, re.M)
        self.calls.append(len(ids))
        out = self.script.pop(0) if self.script else ""
        if callable(out):
            out = out(len(ids))
        return out, {"total_tokens": 7}


def run(script, paras, start=0, depth=0):
    stub = Stub(script)
    orig = lt.call_llm
    lt.call_llm = stub
    try:
        stats = {"tok": 0, "calls": 0}
        out, used = lt.robust_translate_paras(META, paras, start, "sys",
                                              ARGS, "", stats, depth)
        return out, stub, stats
    finally:
        lt.call_llm = orig


print("=" * 66)
print("0. 轻小说翻译准则 / 角色卡注入")
print("=" * 66)
RULES_META = {
    "glossary": {"魔法": "魔力"},
    "characters": {
        "アリス": {
            "desc": "女主角",
            "voice": "傲娇，紧张时句子变短",
            "address": "叫主角「笨蛋」",
            "lexicon": "不用四字词",
            "syntax": "短句多，爱省略",
            "volume": "第一卷",
            "aliases": ["アリスちゃん"],
        }
    },
    "summaries": {},
    "style": {"medium": "web", "narrator": "第一人称吐槽滤镜",
              "guide": "术语只增不改"},
    "title": "t",
    "episodes": [],
}
_sysp = lt.build_system_prompt(RULES_META)
for _key in ("轻小说", "短句", "角色", "吐槽", "术语表", "段落",
             "漏译", "敬语", "拟声"):
    check(f"系统 prompt 含「{_key}」", _key in _sysp)
check("web 媒介用短注、不跳转", "半行以内" in _sysp)
check("本书补充准则会注入", "术语只增不改" in _sysp)
check("叙述者滤镜会注入", "第一人称吐槽滤镜" in _sysp)
for _med, _needle in (("paper", "脚注"), ("ebook", "章末注")):
    _p = lt.build_system_prompt({"style": {"medium": _med}})
    check(f"{_med} 媒介加注策略", _needle in _p)
_prompt, _used = lt.build_chunk_prompt(
    RULES_META, ["アリスちゃんは魔法を使った。"], 0, "")
check("术语按需注入", "魔法 => 魔力" in _prompt)
check("角色别名能命中角色卡", "アリス：" in _prompt)
check("角色声音字段完整注入",
      all(x in _prompt for x in ("傲娇", "称呼：", "词汇习惯：", "句法习惯：",
                                 "本卷时间点：")))
check("本段术语统计正确", _used == ["魔法"], str(_used))

print("=" * 66)
print("A. 正常情况：一次成功")
print("=" * 66)
paras = ["これは一つ目。", "これは二つ目。"]
out, stub, st = run(["#1:这是第一段。\n#2:这是第二段。"], paras)
check("输出正确", out == ["这是第一段。", "这是第二段。"], str(out))
check("只请求 1 次", len(stub.calls) == 1, f"{len(stub.calls)} 次")

print()
print("=" * 66)
print("B. 校验①：段落数不齐 → 重试 3 次 → 二分降级")
print("=" * 66)


class SizeStub:
    """按**请求段数**决定成败的桩：n >= fail_at 永远失败，否则成功。

    为什么这样设计：二分降级的核心就是"段数变小后更容易成功"。
    用段数当条件，既确定又能证明二分真的起了作用
    （之前用"第几次调用"当条件，二分后计数会错乱，断言不可靠）。
    """

    def __init__(self, fail_at):
        self.fail_at = fail_at
        self.calls = []

    def __call__(self, system, prompt, model, temperature, retries=3,
                 role=None):
        import re
        # 必须从 prompt 里读**实际的编号**：二分后右半段的编号是 #3/#4 而不是 #1/#2，
        # 桩如果硬写 #1 起，会永远对不上号（我自己踩过这个测试陷阱）。
        nums = [int(x) for x in re.findall(r"^#(\d+):", prompt, re.M)]
        n = len(nums)
        self.calls.append(n)
        if not nums:
            return "", {"total_tokens": 7}
        if n >= self.fail_at:
            nums = nums[:-1]                 # 少输出一段 → 编号缺失
        body = "\n".join(f"#{i}:第{i}段。" for i in nums)
        return body, {"total_tokens": 7}


paras4 = ["一。", "二。", "三。", "四。"]
stub = SizeStub(fail_at=4)          # 整段(4)永远失败；二分后(<=2)成功
orig = lt.call_llm
lt.call_llm = stub
try:
    stats = {"tok": 0, "calls": 0}
    out, _ = lt.robust_translate_paras(META, paras4, 0, "sys", ARGS, "", stats)
finally:
    lt.call_llm = orig

check("二分后每半段都成功，拼回 4 段",
      out == ["第1段。", "第2段。", "第3段。", "第4段。"], str(out))
check("先按整段重试 3 次（4,4,4）", stub.calls[:3] == [4, 4, 4], str(stub.calls))
check("随后二分 → 请求段数变小（2,2）",
      stub.calls[3:5] == [2, 2], str(stub.calls))
check("总请求数受控（<= 8）", len(stub.calls) <= 8, f"{len(stub.calls)} 次")

print()
print("=" * 66)
print("C. 校验②：把日文原样抄回来 → 判定失败并重试")
print("=" * 66)
paras = ["これは日本語です。", "これも日本語です。"]
out, stub, st = run([
    "#1:これは日本語です。\n#2:これも日本語です。",   # 行数对但没翻 → 应被识破
    "#1:这是中文。\n#2:这也是中文。",
], paras)
check("抄回原文被识破并重试", len(stub.calls) == 2, f"{len(stub.calls)} 次")
check("第二次拿到正确译文", out == ["这是中文。", "这也是中文。"], str(out))

print()
print("=" * 66)
print("D. 一直失败：保留原文并明确告知（不静默插入坏译文）")
print("=" * 66)
paras = ["これは失敗する。"]        # 单段，无法二分
out, stub, st = run(["#9:乱七八糟"], paras, depth=5)
check("单段失败时保留原文", out == paras, str(out))
check("失败也返回了可用的列表长度", len(out) == len(paras))

print()
print("=" * 66)
print("E. 单段成功不应触发二分")
print("=" * 66)
out, stub, st = run(["#1:只有一段。"], ["一つ。"])
check("单段一次成功", out == ["只有一段。"] and len(stub.calls) == 1, str(out))

print()
print("=" * 66)
print("F. detect_chinese：中性字符不算中文（防日文数字/符号蒙混）")
print("=" * 66)
# 回归：数字 / 空格 / # | 是中英日共用的中性字符，早先被算进"中文证据"，
# 会让一整段全是数字/符号的日文（含日期、编号）冒充中文。
check("纯数字/符号/空格不算中文",
      not lt.detect_chinese("1234 #| 5678  90 2025-10-16"))
check("正常中文译文仍判为中文", lt.detect_chinese("这是正常的中文译文。"))
check("日文原文不判为中文", not lt.detect_chinese("これは日本語の原文です。"))
# 回归：假名是中文里绝不会出现的字符。汉字多、假名少的日文曾被误判成中文
# （"汉字占比 > 0.75" 这一条短路过一切）。
check("汉字多、假名少的日文不判为中文", not lt.detect_chinese("彼女は無表情で立っていた。"))
check("少量假名也判为日文", not lt.detect_chinese("日本語の原文"))
# 回归（用户报「翻译卡住了」的根因）：模型偶尔会把某个专有名词留成假名
# （例：「祀ろわぬ教会」）。旧规则 `jp >= 3` 直接把整段好译文判成日文 →
# 3 次重试 + 全段二分 → 一章 19 次请求 / 3.8 万 token 白花，界面上就是"卡住"。
# 判据改成看假名**比例**：零星几个是没译的词，成规模的才是整段没翻。
check("零星假名（未译的专有名词）不判为日文",
      lt.detect_chinese("那家伙也是祀ろわぬ教会的成员？他站在舞台中央，"
                        "用演员般夸张的动作张开双臂，底下没有一个人理他。"))
check("整段假名仍判为日文",
      not lt.detect_chinese("ちょび髭に連れられて薄暗い階段を降りた先には、"
                            "広い空間が広がっていた。"))
check("成比例假名（半翻半留）仍判为日文",
      not lt.detect_chinese("那家伙也是祀ろわぬ教会の成员？彼は舞台の上で両腕を広げた。"))
check("chinese_share 能分出主次",
      lt.chinese_share("那家伙也是祀ろわぬ教会的成员，站在舞台中央张开双臂。") > 0.8)

print()
print("=" * 66)
print("F3. 零星日文不触发重试风暴（用户报「卡住」的成本问题）")
print("=" * 66)
# 长段：假名占比极小，一次就通过（真实线上那章就是这种，951 字里 3 个假名）
_LONG = ("天花板上吊着的枝形吊灯的光莫名发黄，把满是灰尘的空气照得过分清楚。"
         "整面墙铺着深红地毯，还有那根白白雕了一堆花纹、品味糟糕透顶的柱子。"
         "简直就像个小箱子里的古典音乐会舞台。说不定这家伙也是祀ろわぬ教会的成员？")
_out_jp, _stub_jp, _ = run([lambda n: f"#1: {_LONG}"] * 3, ["「あ」"])
check("长段里零星假名 → 重试一次后收下（不做 3 轮重试 + 全段二分）",
      bool(_out_jp) and _LONG[:8] in _out_jp[0] and len(_stub_jp.calls) == 2,
      f"calls={_stub_jp.calls} out={str(_out_jp)[:40]}")

# 短段：一句话里就夹着假名名，比例上仍判"像日文"，但重试到末次应**收下**
# （以中文为主），不要继续二分 —— 那里花钱最快、收益最低。
_SHORT = "那家伙也是祀ろわぬ教会的成员。"
_out_s, _stub_s, _ = run([lambda n: f"#1: {_SHORT}"] * 3, ["「あ」"])
check("短段夹假名：末次以中文为主就收下（不二分烧钱）",
      bool(_out_s) and _SHORT[:6] in (_out_s[0] or ""), f"out={str(_out_s)[:40]}")
check("短段夹假名：最多 MAX_TRY 次，不再二分",
      len(_stub_s.calls) <= 3, f"calls={_stub_s.calls}")

print()
print("=" * 66)
print("F5. 翻译质量兜底：假名残留 / 英文漂移（用户报的三个问题里两个）")
print("=" * 66)
# 1) 固定短语的确定性清洗（不花 token）
check("ございました 直接换成「非常感谢」",
      lt.clean_residual("谢谢你救了我……ございました。") == "谢谢你救了我……非常感谢。")
check("引号内刻意引用日文不算残留",
      lt.kana_outside_quotes("用日语来说就是「贈り物」") == 0)
check("引号外残留要能数出来", lt.kana_outside_quotes("他说ございました。") == 6)

# 2) 引号外还有假名 → 重试一次（给了明确指令），第二次干净就收
# 注意顺序：常见客套话**先被确定性词表清洗掉**，所以这类根本不会触发重试。
_stub_kana = Stub(["#1: 谢谢你救了我……ございました。"])
_stub_kana2 = Stub(["#1: 他まっすぐ走った。", "#1: 他笔直地跑了。"])
_s_k = {"tok": 0, "calls": 0}
_orig_k = lt.call_llm
lt.call_llm = _stub_kana
try:
    _out_k, _ = lt.robust_translate_paras(META, ["「助けてくれてありがとう」"], 0, "sys",
                                          ARGS, "", _s_k)
finally:
    lt.call_llm = _orig_k
check("词表里的客套话：清洗掉、不花重试",
      _out_k and "ございました" not in _out_k[0] and len(_stub_kana.calls) == 1,
      f"calls={_stub_kana.calls} out={str(_out_k)[:40]}")

# 词表之外的残留假名 → 才走"重试一次"
_orig_k2 = lt.call_llm
lt.call_llm = _stub_kana2
try:
    _s_k2 = {"tok": 0, "calls": 0}
    _out_k2, _ = lt.robust_translate_paras(META, ["「まっすぐ走った」"], 0, "sys",
                                           ARGS, "", _s_k2)
finally:
    lt.call_llm = _orig_k2
check("词表外的假名：重试一次并拿到干净译文",
      _out_k2 and "まっすぐ" not in _out_k2[0] and len(_stub_kana2.calls) == 2,
      f"calls={_stub_kana2.calls} out={str(_out_k2)[:40]}")

# 3) 英文漂移：原文没有的成句英文才重试；品牌名不重试
check("英文漂移识别（原文没有的成句英文）",
      lt.english_drift("他打开了 further more the door", "彼はドアを開けた") ==
      ["further more the door"])
check("品牌名/原文有的英文不算漂移",
      lt.english_drift("他打开 Discord 看了 Shiro Live", "DiscordでShiro Liveを見た") == [])
_stub_eng = Stub(["#1: 他打开了 furthermore the door。", "#1: 他打开了门。"])
_s_e = {"tok": 0, "calls": 0}
_orig_e = lt.call_llm
lt.call_llm = _stub_eng
try:
    _out_e, _ = lt.robust_translate_paras(META, ["「ドアを開けた」"], 0, "sys", ARGS, "", _s_e)
finally:
    lt.call_llm = _orig_e
check("英文漂移：重试一次（不做无限二分）",
      _out_e and "furthermore" not in _out_e[0] and len(_stub_eng.calls) == 2,
      f"calls={_stub_eng.calls} out={str(_out_e)[:40]}")

# 4) 术语锁定会注入 prompt（人名一致性的机制保障）
_meta_t = {"glossary": {"ローラ": "萝拉"}, "characters": {}, "summaries": {},
           "style": {}, "title": "t", "episodes": []}
_prompt_t, _used_t = lt.build_chunk_prompt(_meta_t, ["ローラが走る。"], 0, "")
check("术语表里的名字会注入到该段 prompt", "ローラ" in _prompt_t and "萝拉" in _prompt_t,
      f"used={_used_t}")

print()
print("=" * 66)
print("F4. 三维守门员：次数 / 深度 / 本章 token 预算")
print("=" * 66)
# 病根不是"判定不准"，而是"小误判 → 大代价"的放大链：否决 → 重试 → 二分 →
# 两半再二分，没有 token 上限。这里锁住第三维（预算），前两维见 MAX_SEG_CALLS / depth。
_b = {"tok": 0, "limit": 0, "degraded": 0}
_s = {"tok": 0, "calls": 0}
_out_b, _ = lt.robust_translate_paras(META, ["「一つ」"], 0, "sys", ARGS, "", _s, budget=_b)
check("预算为 0：一次请求都不发（守门在最前面）", _s["calls"] == 0, f"calls={_s['calls']}")
check("预算为 0：退回原文并标失败（不冒充已译）",
      _out_b == ["「一つ」"] and _s.get("failed"), str(_out_b))

# 花完预算后**不再放大**：第一版虽被判定"不太像中文"（短句夹假名），
# 但以中文为主 → 收下 + 标未译全 + 记一笔降级，而不是继续重试/二分。
_SHORT2 = "那家伙也是祀ろわぬ教会的成员。"
# 用固定回复的桩把它跑到预算耗尽（**先装桩再调**，否则会打真接口）
_stub_b2 = Stub([lambda n: f"#1: {_SHORT2}"] * 3)
_orig_b2 = lt.call_llm
lt.call_llm = _stub_b2
try:
    _s3 = {"tok": 0, "calls": 0}
    _b3 = {"tok": 0, "limit": 5, "degraded": 0}
    _out_b3, _ = lt.robust_translate_paras(META, ["「あ」"], 0, "sys", ARGS, "", _s3,
                                           budget=_b3)
finally:
    lt.call_llm = _orig_b2
check("预算耗尽：不再重试（只发了 1 次请求）", _s3["calls"] == 1, f"calls={_s3['calls']}")
check("预算耗尽：以中文为主就收下（不是把整章打回原文）",
      bool(_out_b3) and "祀ろわぬ" in _out_b3[0], str(_out_b3)[:40])
check("预算耗尽：标记未译全（partial），并记降级次数",
      _s3.get("partial") == 1 and _b3.get("degraded") == 1,
      f"partial={_s3.get('partial')} degraded={_b3.get('degraded')}")

print()
print("=" * 66)
print("F6. 润色（polish）：改写可以，改坏不行")
print("=" * 66)
_META_P = {"glossary": {"ローラ": "萝拉", "三徳包丁": "三德刀"}, "characters": {},
           "summaries": {}, "style": {}, "title": "t", "episodes": []}
_sysp, _prompt = lt._polish_prompt(_META_P, ["萝拉拿起了三德刀。"])
check("润色 prompt 带术语硬约束", "萝拉" in _prompt and "三德刀" in _prompt)
check("润色 prompt 禁止改人名/不增删信息",
      "一个字都不许改" in _prompt and "不增删信息" in _prompt)
check("润色 prompt 要求真的改写且保持引号体系",
      "必须真的改写" in _prompt and "引号体系" in _prompt)
check("解析容忍 #>1<: 这种走样格式",
      lt._parse_polish("#>1<: 甲\n#>2<: 乙", 2) == ["甲", "乙"])
check("解析兼容全角冒号与缺号",
      lt._parse_polish("#1：甲\n#3: 丙", 3) == ["甲", "", "丙"])

_old = "我在这栋建筑前，一边向身为房东的老头出示钥匙，一边这样开了口。"
check("正常润色：接受", lt._polish_ok(_old, "我站在楼前，把钥匙给房东老头看，开了口。", _META_P) == "")
check("原样抄回：拒绝", lt._polish_ok(_old, _old, _META_P) != "")
check("改成英文：拒绝", lt._polish_ok(_old, "I stood before the door.", _META_P) != "")
check("对白数变了：拒绝",
      lt._polish_ok("「甲」「乙」", "「甲乙」", _META_P) != "")
check("术语丢了：拒绝",
      lt._polish_ok("萝拉拿起了三德刀。", "少女拿起了厨刀。", _META_P) != "")
check("长度离谱（删一半）：拒绝",
      lt._polish_ok("这句话很长很长很长很长很长很长很长。", "很短。", _META_P) != "")
check("多出日文：拒绝",
      lt._polish_ok("他走了。", "他走了ございました。", _META_P) != "")

print()
print("=" * 66)
print("F2. parse_chunk_reply：无编号续行不丢、重复编号不覆盖")
print("=" * 66)
_o, _missing = lt.parse_chunk_reply("#1:第一句\n继续补充。\n#2:第二段。", ["a", "b"], 0)
check("无编号续行接到当前段（不截断译文）",
      _o == ["第一句 继续补充。", "第二段。"] and not _missing, str(_o))
_o2, _m2 = lt.parse_chunk_reply("#1:甲\n#1:乙", ["a"], 0)
check("重复编号内容并入而非被覆盖", _o2 == ["甲 乙"], str(_o2))
_o3, _m3 = lt.parse_chunk_reply("#1:重复\n#1:重复", ["a"], 0)
check("重复编号但内容相同 → 不重复拼接", _o3 == ["重复"], str(_o3))

print()
print("=" * 66)
print("F3. --allow-missing：编号缺失时接受（缺失处暂留原文），不重试")
print("=" * 66)
_am = argparse.Namespace(model="stub", temperature=0.0, allow_missing=True)
_stub_am = Stub(["#1:只有第一段。"])          # 缺 #2
_orig_llm = lt.call_llm
lt.call_llm = _stub_am
_st_am = {"tok": 0, "calls": 0}
try:
    _out_am, _ = lt.robust_translate_paras(META, ["一つ。", "二つ。"], 0, "sys",
                                           _am, "", _st_am)
finally:
    lt.call_llm = _orig_llm
check("--allow-missing 缺号时只调一次（不重试）且缺失处暂留原文",
      len(_stub_am.calls) == 1 and _out_am == ["只有第一段。", "二つ。"], str(_out_am))
check("--allow-missing 置 stats['partial']（写出但不冒充译全）、不置 failed",
      _st_am.get("partial") == 1 and not _st_am.get("failed"), str(_st_am))

# 失败必须置 stats["failed"]，供 translate_chapter 判断"不算已译、不落盘"
_fo, _fs, _fst = run(["#1:日本語のまま。"] * 4, ["一つだけ。"])
check("robust 失败时置 stats['failed']（供上层不落盘/不推进）",
      _fst.get("failed", 0) >= 1 and _fo == ["一つだけ。"], f"stats={_fst}")

print()
print("=" * 66)
print("G. 单段调用上限（宽松安全帽）：毒段不再烧满 93 次")
print("=" * 66)
# 回归：递归上限是 depth<4 × MAX_TRY=3 → 单段最坏 3×(1+2+4+8+16)=93 次。
# 加一个宽松上限（> 最深可恢复成本 61）掐掉"纯毒段"的尾部重试，且不误伤能成的段。
paras16 = [f"原文第{i}段。" for i in range(1, 17)]
stub = SizeStub(fail_at=1)          # 任何段数都少输出 → 永远失败 → 递归到底
orig = lt.call_llm
lt.call_llm = stub
try:
    stats = {"tok": 0, "calls": 0}
    out, _ = lt.robust_translate_paras(META, paras16, 0, "sys", ARGS, "", stats)
finally:
    lt.call_llm = orig

check("上限高于最深可恢复成本 61（不误伤能成的段）", lt.MAX_SEG_CALLS > 61,
      f"MAX_SEG_CALLS={lt.MAX_SEG_CALLS}")
check("毒段调用数被截断在 64（而非最坏 93）", stats["calls"] == lt.MAX_SEG_CALLS,
      f"{stats['calls']} 次")
check("截断后仍保留原文（不塞坏译文）", out == paras16, str(out[:2]))

print()
print("=" * 66)
print("G. 不可翻段落（分隔线/纯符号）必须原样穿透，不许拖垮整章")
print("=" * 66)
# 真实事故：第 31 章末尾一条 `――――――` 被送给模型，模型照抄回来，
# 「必须是中文」的校验把它判成"抄回原文" → 重试 3 次 → 整章不落盘。
check("分隔线没有可翻文字", not lt.has_translatable("――――――――――"))
check("纯数字/纯符号也没有", not lt.has_translatable("123 456 ！！！ ◆"))
check("假名算可翻", lt.has_translatable("これは日本語です。"))
check("汉字算可翻（中日同形也要过一遍）", lt.has_translatable("魔法少女"))

out, stub, st = run([], ["――――――――――", "◆◆◆", "１２３"])
check("整段都是装饰线：一次模型都不调", stub.calls == [] and st["calls"] == 0)
check("整段都是装饰线：原样返回", out == ["――――――――――", "◆◆◆", "１２３"], str(out))

out, stub, st = run([
    "#1:――――――――――\n#2:这是日语。",
], ["――――――――――", "これは日本語です。"])
check("混合段：装饰线照原文、正文照译", out == ["――――――――――", "这是日语。"], str(out))
check("混合段一次成功（不因为装饰线被抄回而重试）", len(stub.calls) == 1, str(stub.calls))
check("装饰线不计入「未译全」",
      not st.get("incomplete_paragraphs") and not st.get("failed"),
      str(st.get("incomplete_paragraphs")))

print()
print("=" * 66)
print("H. 解析器：编号块之外的模型附言不许混进正文")
print("=" * 66)
# 真实风险：模型在最后一段后面附一句"（以上）"或"说明：…"，被当成续行拼进正文，
# 读者看到的小说最后一句就是模型的废话；而且段数/编号校验全过，很难发现。
_o, _m = lt.parse_chunk_reply("#1:甲\n#2:乙\n\n多余的说明文字", ["a", "b"], 0)
check("空行后的附言被丢掉", _o == ["甲", "乙"], str(_o))
_o, _ = lt.parse_chunk_reply("#1:甲\n#2:乙\n多余的说明文字", ["a", "b"], 0)
check("紧贴段尾的附言也被丢掉", _o == ["甲", "乙"], str(_o))
_o, _ = lt.parse_chunk_reply("#1:「甲」\n「乙」", ["a"], 0)
check("折行的对白仍然保留（不能误删正文）", "「乙」" in _o[0], str(_o))
_o, _ = lt.parse_chunk_reply("#1:甲\n\n「乙」", ["a"], 0)
check("空行后的对白行保留（有的模型这么排版）", "「乙」" in _o[0], str(_o))
check("整段英文成句也算「可翻」（会被译成中文）",
      lt.has_translatable("I will never forget that night."))
check("两个英文词的专名/缩写不算可翻（不送模型）",
      not lt.has_translatable("Lyrical Lily"))
check("纯 URL 不算可翻", not lt.has_translatable("https://example.com/works/1"))

print()
print("=" * 66)
print("I. 单段请求：模型不带编号 / 只漏几段时不许硬判失败")
print("=" * 66)
# 真实事故（2026-10-22 手机主库）：某章有一句「何を言っているんだこいつは……」，
# 二分到 1 段后模型只回一句译文（或把 prompt 尾部的说明抄回来）→ 解析不到编号 →
# 判「编号缺失」→ 重试到整章 token 预算耗尽 → 该章永远不落盘，整本卡在 48/54。
_p, _ = lt.build_chunk_prompt(
    {"title": "t", "glossary": {}, "characters": {}}, ["a"], 22, "")
check("单段请求不再要求编号", "不要编号" in _p and "同样编号" not in _p, _p[-120:])
_o, _m = lt.parse_chunk_reply(
    "#23:那家伙在说什么啊……\n\n翻译时先判断每句是谁说的、对谁说；保持该角色的词汇和句法习惯。\n"
    "请输出同样段数、同样编号的简体中文译文，每段一行。",
    ["何を言っているんだこいつは......"], 22)
check("单段回复里的 prompt 回声被过滤掉",
      _o == ["那家伙在说什么啊……"] and not _m, (_o, _m))
_o, _m = lt.parse_chunk_reply("那家伙在说什么啊……\n\n说明：以上。",
                             ["何を言っているんだこいつは......"], 22)
check("单段纯文本回复也能收下（不判缺失）",
      _o == ["那家伙在说什么啊……"] and not _m, (_o, _m))
_o, _m = lt.parse_chunk_reply("#1:甲\n#3:丙", ["a", "b", "c"], 0)
check("多段仍然按编号判缺失（#2 少了一行）", _o == ["甲", "", "丙"] and _m == [2],
      (_o, _m))

print()
print("=" * 66)
print("J. 模型复读：同一句/同一段连续出现两次时去重")
print("=" * 66)
_dup = ("第一句是足够长的重复内容。第一句是足够长的重复内容。"
        "第二句也是足够长的内容。第二句也是足够长的内容。")
_clean = lt._dedupe_repeated_output(_dup, "原文只有一句，不含重复。")
check("★ 章末每句翻两次会收成一次", _clean == "第一句是足够长的重复内容。第二句也是足够长的内容。",
      _clean)
_dup2 = ("前面一句很长的话。后面一句更长的话。"
         "前面一句很长的话。后面一句更长的话。")
_clean2 = lt._dedupe_repeated_output(_dup2, "原文不重复。")
check("★ 整块 A B A B 只保留一份", _clean2 == "前面一句很长的话。后面一句更长的话。",
      _clean2)
_src_rep = "角色在复读同一句话。角色在复读同一句话。"
check("原文自己就复读时不动（忠于原文）",
      lt._dedupe_repeated_output(_src_rep, _src_rep) == _src_rep)
check("短语气词连续「？」/「！」不误删",
      lt._dedupe_repeated_output("？。？。", "原文。") == "？。？。")
_para = "这是一个足够长的重复段落，应该只留一份。"
check("相邻重复长段落只留一份",
      lt._dedupe_repeated_output(_para + "\n\n" + _para, "原文。").strip() == _para)

print()
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("✅ 翻译健壮性测试全部通过")
