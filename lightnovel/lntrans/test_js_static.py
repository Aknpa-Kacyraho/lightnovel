#!/usr/bin/env python3
"""护栏：前端脚本已从 Python 字符串搬到 `static/*.js`（另有 CSS），且仍是合法 JS。

P1（内嵌 JS 外置）为什么要这个测试：
  内嵌 JS 曾以 Python 三引号字符串存在 —— 编辑时改错一个引号，整个 `lnserve.py`
  都可能解析不过 / 或把一段脚本悄悄截断（"一个引号废整页"）。搬到真实 `.js`
  文件后，编辑器/高亮/`node --check` 能直接作用其上。这个测试守住"别再塞回去"：
  1. `static/` 下五个文件都在、非空；
  2. 模块全局 ACTION_JS/LIB_JS/DISLIKE_JS/READER_JS/DETAIL_JS 确实**读自文件**
     （内容逐字节相等）—— 防止有人又把大段 JS 写回 .py；
  3. 每个文件过 `node --check`（证明是合法 JS）。node 不在时**判失败**：
     test_click 本来就硬依赖 node（缺了会抛异常），这里若只告警就又是一条
     假绿通道；在目标机装 node 即可（Linux/Android/Termux 同理）。

失败必须反馈到退出码：run_selftests.py 只看 returncode（外加扫 ❌）。
"""

from __future__ import annotations

import importlib.util
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


# 导入 lnserve（会读 static/*.js）。不连网络、不开服务。
_s = importlib.util.spec_from_file_location("lnserve", os.path.join(HERE, "lnserve.py"))
mod = importlib.util.module_from_spec(_s)
sys.argv = ["lnserve"]
_s.loader.exec_module(mod)

STATIC = os.path.join(HERE, "static")
PAIRS = [("ACTION_JS", "action.js"), ("LIB_JS", "lib.js"),
         ("DISLIKE_JS", "dislike.js"), ("READER_JS", "reader.js"),
         ("DETAIL_JS", "detail.js"), ("REVIEW_JS", "review.js"),
         ("QUEUE_JS", "queue.js"), ("META_JS", "meta.js"),
         ("LNUI_PREVIEW_JS", "lnui-preview.js"),
         ("LNUI_SETTINGS_JS", "lnui-settings.js")]

for var, fname in PAIRS:
    p = os.path.join(STATIC, fname)
    exists = os.path.exists(p)
    body = ""
    if exists:
        with open(p, encoding="utf-8") as f:
            body = f.read()
    check(f"static/{fname} 存在且非空", exists and len(body.strip()) > 0,
          f"{len(body)} 字符")
    check(f"{var} 读自 static/{fname}（逐字节一致）", getattr(mod, var) == body)

# CSS 也外置了（lnserve 的 `CSS = lr.CSS + _read_static("app.css")`）。
# 它比 JS 更"硬"：文件缺失时服务**根本起不来**（模块级读取），所以必须有护栏，
# 而且不能只看"文件在"—— 还要确认模块常量真的是 `lr.CSS + 文件全文`。
_css_p = os.path.join(STATIC, "app.css")
_css_body = ""
if os.path.exists(_css_p):
    # newline="" 与 `_read_static()` 一致：默认的通用换行会把 CRLF 折成 LF，
    # 于是"逐字节一致"在混入 CRLF 时假红（反过来也会掩盖真正的差异）。
    with open(_css_p, encoding="utf-8", newline="") as f:
        _css_body = f.read()
check("static/app.css 存在且非空（缺了服务起不来）",
      os.path.exists(_css_p) and len(_css_body.strip()) > 0, f"{len(_css_body)} 字符")
check("CSS == lnrender.CSS + static/app.css 全文",
      getattr(mod, "CSS") == (mod.lr.CSS + _css_body) and len(mod.CSS) > len(mod.lr.CSS),
      f"CSS {len(getattr(mod, 'CSS', ''))} 字符 / 基础 {len(mod.lr.CSS)}")

# ---- 状态栏单一写入入口（架构约束，不是事后断言） ---------------------------
# 病根复盘：这个 bug 修过两次都复发（先是 tick/poll 各写一套文案，后来 v4.5 又把
# 服务端整句 message 塞进同一个槽）。两次都只是"把文案改成一致"，因为**谁都能
# 拿到那个 DOM 元素**。现在元素被关进 reader.js 的 TB 闭包里，外部只拿到函数：
# 新功能想写状态，物理上只能走这几个入口，不可能再出现第二个写入方。
_rd = open(os.path.join(STATIC, "reader.js"), encoding="utf-8").read()
check("reader.js 只在一处取 tb-status（元素不进全局作用域）",
      _rd.count("getElementById('tb-status')") == 1)
check("没有 tbStatus / tbProg 这类模块级引用残留",
      "tbStatus" not in _rd and "tbProg" not in _rd and "tbFill" not in _rd)
check("TB 闭包对外只暴露写入口（取元素在闭包内）",
      "const TB = (function()" in _rd
      and all(k in _rd for k in ("setStop", "setStatus", "setSeg",
                                 "transStatus", "setProgress")))
# 扫**所有**静态脚本（不是写死一份名单）：以后新增 review2.js 之类也自动纳入。
# 只有 reader.js 的 TB 闭包可以碰这几个 id。
for _p in sorted(glob.glob(os.path.join(STATIC, "*.js"))):
    _f = os.path.basename(_p)
    if _f == "reader.js":
        continue
    _s = open(_p, encoding="utf-8").read()
    check(f"{_f} 不直接碰状态栏（要显示状态只能调 TB 的函数）",
          "tb-status" not in _s and "tb-prog" not in _s and "tb-seg" not in _s)

# ---- 术语/人名悬浮：正文标注在 lnrender，点击行为在 reader.js ----------
# 这两半必须都在：只有标注没有 JS = 点了没反应（"按钮骗人"的同一类 bug）；
# 只有 JS 没有标注 = 永远没有可点的东西。另外 #gtip 只许 reader.js 创建。
check("reader.js 实现了术语悬浮（点 .gloss 弹出 #gtip）",
      "closest('.gloss')" in _rd and "gtip" in _rd)
for _p in sorted(glob.glob(os.path.join(STATIC, "*.js"))):
    _f = os.path.basename(_p)
    if _f == "reader.js":
        continue
    check(f"{_f} 不自己造 #gtip（气泡只有一个实现）",
          "gtip" not in open(_p, encoding="utf-8").read())

node = shutil.which("node")
if node:
    for _var, fname in PAIRS:
        r = subprocess.run([node, "--check", os.path.join(STATIC, fname)],
                           capture_output=True, encoding="utf-8", errors="replace")
        tail = (r.stderr or "").strip().splitlines()
        check(f"node --check static/{fname}", r.returncode == 0,
              tail[-1] if (r.returncode and tail) else "")
else:
    # 不静默跳过：node 缺失 = 五段前端脚本没人验语法，这与 test_click
    # （缺 node 直接抛异常）必须同一策略。
    check("node 可用（前端脚本语法检查依赖它，缺了不算通过）", False,
          "未找到 node —— 装 node 再跑")

print()
_all = not fails
print("回归结果：", "全部通过 ✅" if _all else f"仍有失败 ❌ {fails}")
if not _all:
    sys.exit(1)
