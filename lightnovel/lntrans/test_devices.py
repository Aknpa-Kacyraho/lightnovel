#!/usr/bin/env python3
"""回归：长期设备凭据（「记住这台电脑」）。

边界：
  * 文件里只有 SHA-256，没有明文凭据；Cookie 里也不是主口令；
  * 过期失效；用一次自动续期；最多 32 台，旧的先淘汰；
  * 损坏的文件不静默删除（另存 .bak 再重建）；
  * 撤销后立即失效；重建缓存（模拟进程重启）后仍认。
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


_s = importlib.util.spec_from_file_location(
    "lndevices", os.path.join(HERE, "lndevices.py"))
dev = importlib.util.module_from_spec(_s)
_s.loader.exec_module(dev)

tmp = tempfile.mkdtemp(prefix="ln-devices-")
try:
    path = os.path.join(tmp, "data", "devices.json")

    print("=" * 66)
    print("A. 发凭据 / 验凭据 / 文件里没有明文")
    print("=" * 66)
    secret, rec = dev.issue(path, label="Windows Chrome/126", ttl=30 * 86400)
    check("发出来的凭据是随机长串", len(secret) >= 32 and secret != "token")
    check("记录里只有摘要与公开字段",
          set(rec) == {"id", "digest", "label", "created", "last_seen", "expires"})
    raw = open(path, encoding="utf-8").read()
    check("文件里没有明文凭据", secret not in raw and "secret" not in raw)
    if os.name == "posix":
        check("文件权限不是所有人可读",
              (os.stat(path).st_mode & 0o077) == 0, oct(os.stat(path).st_mode))
    else:
        # Windows 没有 POSIX mode 位，st_mode 恒不满足 0o077 == 0；
        # 这不是业务回归。明文凭据检查已在上一项完成，这里只跳过权限位。
        print("  ⏭️  非 POSIX 平台没有权限位，跳过 mode 检查（明文检查已通过）")
    check("正确凭据通过", dev.verify(path, secret) is not None)
    check("错误凭据被拒", dev.verify(path, "wrong-" + secret) is None)
    check("空凭据被拒", dev.verify(path, "") is None and dev.verify(path, None) is None)

    print("=" * 66)
    print("B. 重启（丢缓存重读磁盘）后仍认")
    print("=" * 66)
    dev.reset_cache()
    check("模拟重启后凭据仍有效", dev.verify(path, secret) is not None)

    print("=" * 66)
    print("C. 过期 / 续期 / 上限 / 损坏")
    print("=" * 66)
    now = time.time()
    s_exp, _ = dev.issue(path, label="old", ttl=60, now=now - 120)
    check("过期凭据失效", dev.verify(path, s_exp, now=now) is None)

    s_slide, _ = dev.issue(path, label="slide", ttl=100 * 86400, now=now - 90 * 86400)
    before = {d["id"]: d for d in dev.describe(path)}.get(
        next(d["id"] for d in dev.describe(path) if d["label"] == "slide"))
    dev.verify(path, s_slide, ttl=100 * 86400, now=now)
    after = {d["id"]: d for d in dev.describe(path)}.get(before["id"])
    check("用到一半时自动续期",
          after is not None and after["expires"] > before["expires"],
          f"{before['expires']:.0f}→{(after or {}).get('expires', 0):.0f}")
    check("续期后仍然只认原凭据", dev.verify(path, s_slide) is not None)

    for i in range(dev.MAX_DEVICES + 3):
        dev.issue(path, label=f"extra-{i}", now=now + i)
    devices = dev.describe(path)
    check(f"最多记住 {dev.MAX_DEVICES} 台", len(devices) == dev.MAX_DEVICES,
          f"得到 {len(devices)}")
    check("淘汰的是最久没用的那台",
          all(d["label"] != "extra-0" for d in devices)
          and any(d["label"] == f"extra-{dev.MAX_DEVICES + 2}" for d in devices))

    bad = os.path.join(tmp, "data", "broken.json")
    os.makedirs(os.path.dirname(bad), exist_ok=True)
    with open(bad, "w", encoding="utf-8") as f:
        f.write("{not json")
    dev.reset_cache()
    check("损坏文件按空表处理（不抛异常）", dev.describe(bad) == [])
    check("损坏文件被另存备份而不是删掉",
          any(n.startswith("broken.json.bak-") for n in os.listdir(os.path.dirname(bad))))
    s_new, _ = dev.issue(bad, label="after-corrupt")
    check("损坏后仍能重新记住设备", dev.verify(bad, s_new) is not None)

    print("=" * 66)
    print("D. 撤销")
    print("=" * 66)
    s_rev, _ = dev.issue(path, label="revoke-me")
    check("撤销成功", dev.revoke(path, s_rev) is True)
    check("撤销后立即失效", dev.verify(path, s_rev) is None)
    check("撤销不存在的凭据返回 False", dev.revoke(path, "no-such-secret") is False)
    n = len(dev.describe(path))
    check("全部忘掉", dev.revoke_all(path) == n and dev.describe(path) == [])

    print("=" * 66)
    print("E. 公开字段不含秘密")
    print("=" * 66)
    s_pub, _ = dev.issue(path, label="pub")
    pub = dev.describe(path)
    check("describe 只给 id/标签/时间",
          pub and set(pub[0]) == {"id", "label", "created", "last_seen", "expires"}
          and s_pub not in json.dumps(pub))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
_all = not fails
print("回归结果：", "全部通过 ✅" if _all else f"仍有失败 ❌ {fails}")
if not _all:
    sys.exit(1)
