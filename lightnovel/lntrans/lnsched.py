#!/usr/bin/env python3
"""lnsched —— 翻译调度：从"读到哪翻到哪"改成"在读就一直翻 + 可排队的翻译列表"。

## 为什么要换调度

旧模型是「自动翻译开关 + 读到位置之后再翻 N 章」。它有两个结构性问题：

1. **跟不上阅读**。N 章（默认 3）是硬上限，读者连读 5 章就必然断粮，
   于是每章都要停下来等 30~45 秒 —— 用户原话："翻译跟不上我阅读的速度"。
   把 N 调大只是把断点推远，问题是"上限"这个设计本身：**没人读的时候上限
   不该消耗预算，有人在读的时候上限不该拦住他**。
2. **没有"提前翻"的入口**。想先攒几本再读，只能一本本打开、点翻译、等它跑。

新模型（本模块）只回答一个问题：**下一章该翻哪本书**。

* 正在读的书：`last_read_at` 在 `idle_minutes` 内 → 持续翻它的下一章，
  不设"读到 + N"上限，直到全部译完或读者离开超过 `idle_minutes`。
* 翻译列表：显式加入的书按顺序翻，不受"在读"限制（提前攒书）。
* 全局每日 token 预算 + 全局暂停：无人在读时也不会无限烧钱。

## 边界

本模块**不碰**章节文件、不调模型、不写 books 状态。它只维护一个调度状态文件
（`data/sched.json`），把"谁、为什么、排第几"讲清楚；真正的翻译由调用方注入的
函数执行（`job_active` / `next_missing` / `start_job`）。这样调度逻辑可以用纯
单元测试覆盖，不会因为"翻译本身很重"而只能靠手工验证 —— 上一版把策略写进
worker 里，改一次要重新跑一遍真模型，最后谁都不敢动。
"""

from __future__ import annotations

import json
import os
import time
from typing import NamedTuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("LNTRANS_DATA_ROOT") or HERE
DATA = os.path.join(ROOT, "data")
STATE_PATH = os.path.join(DATA, "sched.json")

SCHEMA = 1
DEFAULT_BUDGET = 300_000     # token/天：约 60~90 章，够连读一整晚
DEFAULT_IDLE_MIN = 30        # 读完最后一下之后再翻多久算"还在读"
MAX_BATCH = 2                # 一轮最多排几章：短批更好插队，也更容易停


class Action(NamedTuple):
    """调度器给出的一个决定：翻这本书的下一批。"""
    slug: str
    reason: str          # reading | queue | resume
    count: int


class Scheduler:
    def __init__(self, path: str = STATE_PATH, *, now=None):
        self.path = path
        self._now = now or time.time
        self.state = self._load()

    def reload(self) -> None:
        self.state = self._load()

    # ---------------------------------------------------------------- 状态
    def _default(self) -> dict:
        return {
            "version": SCHEMA,
            "paused": False,
            "daily_budget": DEFAULT_BUDGET,
            "idle_minutes": DEFAULT_IDLE_MIN,
            "day": self._day(),
            "used_today": 0,
            "books": {},     # slug -> {queued_at, order, paused, last_read_at, done_at}
        }

    def _day(self) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(self._now()))

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            st = self._default()
        base = self._default()
        if not isinstance(st, dict):
            st = {}
        for k, v in base.items():
            st.setdefault(k, v)
        if not isinstance(st.get("books"), dict):
            st["books"] = {}
        return st

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def _book(self, slug: str) -> dict:
        return self.state["books"].setdefault(slug, {})

    def _roll_day(self) -> None:
        today = self._day()
        if self.state.get("day") != today:
            self.state["day"] = today
            self.state["used_today"] = 0

    # ---------------------------------------------------------------- 用户动作
    def note_read(self, slug: str, persist: bool = True) -> None:
        """读者在动这本书（打开 / 翻页 / 轮询）。每读一次就续一次命。

        `persist=False` 只更新内存：阅读页每 2.5 秒轮询一次，每次都 fsync
        等于拿手机闪存当草稿纸（而且完全没必要，进程重启最多丢 30 秒）。
        """
        b = self._book(slug)
        b["last_read_at"] = self._now()
        b.pop("done_at", None)
        if persist:
            self.save()

    def enqueue(self, slug: str) -> None:
        b = self._book(slug)
        if not b.get("queued_at"):
            orders = [x.get("order", 0) for x in self.state["books"].values()]
            b["queued_at"] = self._now()
            b["order"] = (max(orders) + 1) if orders else 1
        b.pop("done_at", None)
        self.save()

    def forget(self, slug: str) -> None:
        """把这本书从翻译列表里彻底移出（在读标记、队列、暂停全清）。

        只 dequeue 是不够的：一本"在读"的书行还在（reason=reading），
        按钮点了像没反应（用户报过「移除队列没用」）。想彻底不翻它，
        必须连 last_read_at 一起清掉，下次打开阅读页才会重新算"在读"。
        """
        self.state["books"].pop(slug, None)
        self.save()

    def dequeue(self, slug: str) -> None:
        b = self._book(slug)
        b.pop("queued_at", None)
        b.pop("order", None)
        self.save()

    def set_paused(self, slug: str, paused: bool) -> None:
        self._book(slug)["paused"] = bool(paused)
        self.save()

    def pause_all(self, paused: bool) -> None:
        self.state["paused"] = bool(paused)
        self.save()

    def set_budget(self, tokens: int) -> None:
        self.state["daily_budget"] = max(0, int(tokens))
        self.save()

    def set_idle(self, minutes: int) -> None:
        self.state["idle_minutes"] = max(1, min(24 * 60, int(minutes)))
        self.save()

    def add_usage(self, tokens: int, cost: float | None = None) -> None:
        """记一天翻了多少。

        `cost` 为章节实际费用：本地模型是 0 元，**不计入 token 预算** ——
        预算只约束云端花费，不能因为本地免费翻译就把额度耗光。
        `cost=None`（旧调用/测试）保持原行为。
        """
        if cost is not None:
            try:
                if float(cost) <= 0:
                    return
            except (TypeError, ValueError):
                return
        self._roll_day()
        self.state["used_today"] = int(self.state.get("used_today") or 0) + max(0, int(tokens))
        self.save()

    # ---------------------------------------------------------------- 判断
    def is_paused(self, slug: str) -> bool:
        """这本书是否被用户「停止/暂停」（硬停之一）。"""
        b = self.state["books"].get(slug) or {}
        return bool(b.get("paused"))

    def is_reading(self, slug: str) -> bool:
        b = self.state["books"].get(slug) or {}
        at = float(b.get("last_read_at") or 0)
        if not at:
            return False
        return (self._now() - at) <= float(self.state.get("idle_minutes") or DEFAULT_IDLE_MIN) * 60

    def budget_left(self) -> int:
        self._roll_day()
        return int(self.state.get("daily_budget") or 0) - int(self.state.get("used_today") or 0)

    def over_budget(self) -> bool:
        """今天花超了预算（只是提醒，**不阻止**在读的书继续翻）。

        早期版本把预算当硬闸：用满就停。实际使用里它就是"读到一半卡住"的
        另一个来源 —— 用户为了继续读，只能在翻译列表里反复加预算。
        私用阅读器的正确语义是：预算是**刹车灯**，不是**刹车**；
        真正的硬停只有「全局暂停」和「暂停本书」。
        """
        b = int(self.state.get("daily_budget") or 0)
        return b > 0 and self.budget_left() <= 0

    def blocked_globally(self) -> bool:
        # 只由「全局暂停」决定。预算见 over_budget()（仅用于界面提示）。
        return bool(self.state.get("paused"))

    def candidates(self) -> list[tuple[str, str, dict]]:
        """按优先级列出候选：(slug, 原因, 书的调度状态)。

        顺序：正在读的（越近越先）→ 翻译列表（按 order）→ 其它都不翻。
        `done_at` 的书跳过；暂停的书跳过（但它仍留在列表里给用户看）。
        """
        books = self.state["books"]
        reading, queued = [], []
        for slug, b in books.items():
            if b.get("paused") or b.get("done_at"):
                continue
            if self.is_reading(slug):
                reading.append((float(b.get("last_read_at") or 0), slug))
            if b.get("queued_at"):
                queued.append((int(b.get("order") or 0), float(b.get("queued_at") or 0), slug))
        reading.sort(reverse=True)
        queued.sort()
        out = [(s, "reading", books[s]) for _, s in reading]
        seen = {s for _, s in reading}
        out += [(s, "queue", books[s]) for *_, s in queued if s not in seen]
        return out

    def pick(self, next_missing) -> Action | None:
        """挑下一本要翻的书。`next_missing(slug) -> list[int]` 由调用方注入。

        只返回"这本书还有没翻的章"的候选；全书译完的会在调度状态里记 done_at，
        不再每 2 秒扫一遍它的目录（那是本项目的性能反模式）。
        """
        if self.blocked_globally():
            return None
        for slug, reason, b in self.candidates():
            try:
                missing = next_missing(slug)
            except Exception:  # noqa: BLE001 - 单本读盘失败不该饿死整条队列
                continue
            if not missing:
                b["done_at"] = self._now()
                b.pop("queued_at", None)
                self.save()
                continue
            return Action(slug=slug, reason=reason,
                          count=max(1, min(MAX_BATCH, len(missing))))
        return None

    # ---------------------------------------------------------------- 给界面看
    def view(self, have_count, total_of) -> dict:
        """翻译列表页的数据。`have_count(slug)` / `total_of(slug)` 由调用方注入。"""
        rows = []
        for slug, reason, b in self.candidates():
            have, total = have_count(slug), total_of(slug)
            # 已全部译完的书不再占"正在翻译"的位置：它没有下一章可翻，
            # 列出来只会让人以为"卡住了"（pick 下次扫到它会把 done_at 打上）。
            if total and have >= total:
                continue
            rows.append({
                "slug": slug,
                "reason": reason,
                "reading": self.is_reading(slug),
                "queued": bool(b.get("queued_at")),
                "order": b.get("order"),
                "paused": bool(b.get("paused")),
                "have": have,
                "total": total,
            })
        paused_rows = [{"slug": s, "reason": "paused", "paused": True,
                        "have": have_count(s), "total": total_of(s)}
                       for s, b in self.state["books"].items() if b.get("paused")]
        self._roll_day()
        return {
            "paused": bool(self.state.get("paused")),
            "budget": int(self.state.get("daily_budget") or 0),
            "used_today": int(self.state.get("used_today") or 0),
            "budget_left": self.budget_left(),
            "idle_minutes": int(self.state.get("idle_minutes") or DEFAULT_IDLE_MIN),
            "rows": rows,
            "paused_rows": paused_rows,
        }
