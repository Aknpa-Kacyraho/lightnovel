#!/usr/bin/env python3
"""Initialize, migrate, inspect, or roll back a v5 data home.

All mutating operations require ``--write``.  Migration copies and verifies the
old data before atomically switching ``active_generation``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lndata  # noqa: E402


def _print(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lnmigrate")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ini = sub.add_parser("init", help="初始化一个空数据根")
    ini.add_argument("--home", required=True)
    ini.add_argument("--write", action="store_true", help="真正写盘（默认干跑）")

    mig = sub.add_parser("migrate", help="把 v4 数据迁移到代际目录")
    mig.add_argument("--home", required=True)
    mig.add_argument("--source-root", required=True,
                     help="旧 lntrans 目录（包含 novels/ 与 data/）")
    mig.add_argument("--source-profile",
                     help="旧画像数据目录（默认 source-root 同级的 lnfinder/）")
    mig.add_argument("--write", action="store_true", help="真正写盘（默认干跑）")

    rb = sub.add_parser("rollback", help="原子切回上一代")
    rb.add_argument("--home", required=True)
    rb.add_argument("--write", action="store_true", help="真正写盘（默认干跑）")

    st = sub.add_parser("status", help="查看数据根版本与 active generation")
    st.add_argument("--home", required=True)

    a = ap.parse_args(argv)
    try:
        if a.cmd == "init":
            _print(lndata.initialize_home(a.home, write=a.write))
            if not a.write:
                print("（干跑不写盘；确认后加 --write）")
            return 0

        if a.cmd == "migrate":
            _print(lndata.migrate_legacy(
                a.home, a.source_root, a.source_profile, write=a.write))
            if not a.write:
                print("（干跑不写盘；确认后加 --write）")
            return 0

        if a.cmd == "rollback":
            _print(lndata.rollback(a.home, write=a.write))
            if not a.write:
                print("（干跑不写盘；确认后加 --write）")
            return 0

        if a.cmd == "status":
            _print(lndata.status(a.home))
            return 0
    except lndata.DataRootError as ex:
        print(f"错误：{ex}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
