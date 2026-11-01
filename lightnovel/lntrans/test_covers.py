#!/usr/bin/env python3
"""回归：封面抓取只许 http/https，且不许指向本机/内网。

背景：`og:image` 是从源站页面里读出来的字符串，等价于"远端可控的输入"。
旧实现直接 `urlopen(img_url)` —— 构造一条 `og:image: file:///etc/passwd`
就能让服务读本地文件（再把内容当图片落盘）。现在校验抽成纯函数
`safe_img_url`，本测试不联网、不打源站，只断言判据本身。

行为写死在断言里（别让下一轮"顺手简化"悄悄改掉）：
  - `file://` / `data:` / `javascript:` → 拒绝
  - 相对路径按 page_url 补全（`/img/a.jpg`、`//cdn/x.jpg`）
  - 不限制与 page_url 同 host（源站封面常在 CDN），但本机/内网 → 拒绝

失败必须反馈到退出码：run_selftests.py 只看 returncode（外加扫 ❌）。
"""

from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []
total = [0]


def check(name, cond, extra=""):
    total[0] += 1
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


_s = importlib.util.spec_from_file_location("lncovers", os.path.join(HERE, "lncovers.py"))
lc = importlib.util.module_from_spec(_s)
_s.loader.exec_module(lc)

PAGE = "https://kakuyomu.jp/works/1"
s = lc.safe_img_url

check("file:// 被拒绝", s(PAGE, "file:///etc/passwd") is None)
check("data: 被拒绝", s(PAGE, "data:image/png;base64,iVBORw0KGgo=") is None)
check("javascript: 被拒绝", s(PAGE, "javascript:alert(1)") is None)
check("空串被拒绝", s(PAGE, "") is None)
check("相对路径按 page_url 补全",
      s(PAGE, "/img/a.jpg") == "https://kakuyomu.jp/img/a.jpg",
      repr(s(PAGE, "/img/a.jpg")))
check("协议相对按 page_url 补全",
      s(PAGE, "//cdn.example.com/x.jpg") == "https://cdn.example.com/x.jpg",
      repr(s(PAGE, "//cdn.example.com/x.jpg")))
check("绝对 https 原样放行",
      s(PAGE, "https://kakuyomu.jp/img/a.jpg") == "https://kakuyomu.jp/img/a.jpg")
check("绝对 http 放行",
      s(PAGE, "http://cdn.example.com/x.jpg") == "http://cdn.example.com/x.jpg")
check("不限制与 page_url 同 host（CDN 封面能抓）",
      s(PAGE, "https://images.kakuyomu.jp/x.jpg") == "https://images.kakuyomu.jp/x.jpg")
check("127.0.0.1 被拒绝", s(PAGE, "http://127.0.0.1/x.jpg") is None)
check("localhost 被拒绝", s(PAGE, "http://localhost/x.jpg") is None)
check("192.168.x 被拒绝", s(PAGE, "http://192.168.1.5/x.jpg") is None)
check("169.254.x 被拒绝", s(PAGE, "http://169.254.169.254/x.jpg") is None)
check("172.16.x 被拒绝", s(PAGE, "http://172.16.0.9/x.jpg") is None)
check("172.32.x 放行（不是私网段）",
      s(PAGE, "http://172.32.0.9/x.jpg") == "http://172.32.0.9/x.jpg")
check("坏输入不抛异常（只返回 None）", s(PAGE, "http://[::1") is None)

if fails:
    print(f"\n失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print(f"\n全部 {total[0]} 项断言通过")
