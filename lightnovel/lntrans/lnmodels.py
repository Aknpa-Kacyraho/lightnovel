#!/usr/bin/env python3
"""OpenAI-compatible model configuration, cost estimates and local budget ledger.

No prompt or translation text is written to the ledger.  It records only role,
model, token counts and cost so the UI can explain spending without exposing
credentials or story content.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lndata  # noqa: E402

LAYOUT = lndata.resolve_layout()
ROOT = LAYOUT.data_root
DATA = os.path.join(ROOT, "data")
LEDGER = os.path.join(DATA, "llm-usage.jsonl")
ROLES = ("translate", "auxiliary", "review")

_LEDGER_LOCK = threading.RLock()
_SPENT: dict[str, float] = {}
_SPENT_SIG: dict[str, tuple[int, int]] = {}


class BudgetExceeded(RuntimeError):
    pass


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value
    return default


def _float_env(*names: str, default: float) -> float:
    raw = _env(*names, default=str(default))
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return default


def _int_env(*names: str, default: int) -> int:
    raw = _env(*names, default=str(default))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return default


def _role_upper(role: str | None) -> str:
    role = role if role in ROLES else "translate"
    return role.upper() if role else ""


def base_url(role: str | None = None) -> str:
    suffix = f"_{_role_upper(role)}" if role else ""
    return _env(
        f"LNTRANS_LLM_BASE_URL{suffix}", f"LNTRANS_LLM_BASE{suffix}",
        "LNTRANS_LLM_BASE_URL", "LNTRANS_LLM_BASE",
        default="https://api.deepseek.com/chat/completions",
    ).strip()


def _provider_from_host(host: str) -> str:
    host = (host or "").lower()
    if "deepseek" in host:
        return "deepseek"
    if host in ("127.0.0.1", "localhost", "::1"):
        return "local"
    return "openai-compatible"


def provider(role: str | None = None) -> str:
    suffix = f"_{_role_upper(role)}" if role else ""
    return _env(
        f"LNTRANS_LLM_PROVIDER{suffix}", "LNTRANS_LLM_PROVIDER",
        default=_provider_from_host(
            urllib.parse.urlparse(base_url(role)).hostname or ""),
    ).strip() or "openai-compatible"


def is_local(role: str | None = None) -> bool:
    host = (urllib.parse.urlparse(base_url(role)).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def model_for(role: str) -> str:
    role = role if role in ROLES else "translate"
    upper = role.upper()
    return _env(
        f"LNTRANS_MODEL_{upper}", "LNTRANS_MODEL",
        default="deepseek-flash",
    ).strip() or "deepseek-flash"


def role_for_model(model: str) -> str:
    hits = [role for role in ROLES if model_for(role) == model]
    return hits[0] if hits else "translate"


def max_output_tokens() -> int:
    return _int_env("LNTRANS_LLM_MAX_OUTPUT_TOKENS",
                    "LNTRANS_LLM_MAX_TOKENS", default=8000)


def timeout_seconds() -> int:
    return _int_env("LNTRANS_LLM_TIMEOUT", default=180)


def request_retries() -> int:
    return _int_env("LNTRANS_LLM_RETRIES", default=3)


def _cred_path() -> str:
    return os.path.expanduser(_env(
        "LNTRANS_CRED", default="~/.dsh/.credentials.yaml"))


def _cred_value(names: tuple[str, ...]) -> str:
    path = _cred_path()
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return ""
    for name in names:
        match = re.search(rf"{name}:\s*(\S+)", text)
        if match:
            return match.group(1).strip("\"'")
    return ""


def deepseek_key() -> str:
    direct = _env(
        "DEEPSEEK_API_KEY", "DSHA_DEEPSEEK_OFFICIAL_API_KEY",
    ).strip()
    if direct:
        return direct
    return _cred_value(("DEEPSEEK_API_KEY", "DSHA_DEEPSEEK_OFFICIAL_API_KEY"))


def api_key(role: str | None = None) -> str:
    if role is None:
        direct = _env(
            "LNTRANS_LLM_API_KEY", "DEEPSEEK_API_KEY",
            "DSHA_DEEPSEEK_OFFICIAL_API_KEY",
        ).strip()
        if direct:
            return direct
        return _cred_value(("LNTRANS_LLM_API_KEY", "DEEPSEEK_API_KEY",
                            "DSHA_DEEPSEEK_OFFICIAL_API_KEY"))
    suffix = f"_{_role_upper(role)}"
    direct = _env(f"LNTRANS_LLM_API_KEY{suffix}").strip()
    if direct:
        return direct
    if provider(role) == "deepseek" or "deepseek" in (
            urllib.parse.urlparse(base_url(role)).hostname or "").lower():
        return deepseek_key()
    if is_local(role):
        return _env("LNTRANS_LLM_API_KEY").strip()
    return _env(
        "LNTRANS_LLM_API_KEY", "DEEPSEEK_API_KEY",
        "DSHA_DEEPSEEK_OFFICIAL_API_KEY",
    ).strip() or deepseek_key()


def auth_headers(role: str | None = None) -> dict[str, str]:
    key = api_key(role)
    return {"Authorization": f"Bearer {key}"} if key else {}


def _truthy(name: str) -> bool:
    return _env(name, default="").strip().lower() in ("1", "true", "yes", "on")


def fallback_base_url() -> str:
    return _env(
        "LNTRANS_LLM_FALLBACK_BASE_URL", "LNTRANS_LLM_FALLBACK_BASE",
        default="https://api.deepseek.com/chat/completions",
    ).strip()


def fallback_model() -> str:
    return _env("LNTRANS_LLM_FALLBACK_MODEL",
                default="deepseek-flash").strip() or "deepseek-flash"


def fallback_api_key() -> str:
    return _env("LNTRANS_LLM_FALLBACK_API_KEY").strip() or deepseek_key()


def fallback_enabled() -> bool:
    return _truthy("LNTRANS_LLM_FALLBACK") and bool(fallback_base_url()) \
        and bool(fallback_api_key())


@dataclass(frozen=True)
class Route:
    role: str
    base_url: str
    api_key: str
    model: str
    provider: str
    fallback: bool = False

    @property
    def local(self) -> bool:
        host = (urllib.parse.urlparse(self.base_url).hostname or "").lower()
        return host in ("127.0.0.1", "localhost", "::1")


_PRIMARY_FAILED_UNTIL: dict[str, float] = {}
_PRIMARY_FAILED_LOCK = threading.Lock()


def primary_available(role: str) -> bool:
    with _PRIMARY_FAILED_LOCK:
        return time.time() >= _PRIMARY_FAILED_UNTIL.get(role, 0.0)


def mark_primary_failed(role: str, seconds: float = 120.0) -> None:
    with _PRIMARY_FAILED_LOCK:
        _PRIMARY_FAILED_UNTIL[role] = time.time() + max(1.0, float(seconds))


def clear_primary_failed(role: str) -> None:
    with _PRIMARY_FAILED_LOCK:
        _PRIMARY_FAILED_UNTIL.pop(role, None)


def probe(route: Route, timeout: float = 2.0) -> bool:
    """快速 TCP 探测主端点是否在（2 秒）。

    为什么需要：PC 关机/断网时 TCP 连接会**卡到 socket 超时**（我们给生成留的
    是 10 分钟），这段时间界面看着就是"卡住"，兜底要等到超时才生效。
    这里先花 2 秒摸一下端口：连不上就直接判主端点失败、立刻走兜底。
    """
    u = urllib.parse.urlparse(route.base_url)
    host = u.hostname
    if not host:
        return False
    port = u.port or (443 if u.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def routes_for(role: str, model: str | None = None) -> list[Route]:
    role = role if role in ROLES else "translate"
    primary = Route(
        role=role,
        base_url=base_url(role),
        api_key=api_key(role),
        model=(model or model_for(role)),
        provider=provider(role),
    )
    routes = [primary]
    if role in ("translate", "auxiliary") and fallback_enabled():
        fb = Route(
            role=role,
            base_url=fallback_base_url(),
            api_key=fallback_api_key(),
            model=fallback_model(),
            provider="deepseek",
            fallback=True,
        )
        if (fb.base_url, fb.model) != (primary.base_url, primary.model):
            routes.append(fb)
    if not primary_available(role) and len(routes) > 1:
        return routes[1:]
    return routes


def _price(role: str, direction: str, fallback: float) -> float:
    upper = (role if role in ROLES else "translate").upper()
    direction = direction.upper()
    return _float_env(
        f"LNTRANS_{upper}_PRICE_{direction}_CNY_PER_M",
        f"LNTRANS_PRICE_{direction}_CNY_PER_M",
        default=fallback,
    )


def _deepseek_price(direction: str, fallback: float) -> float:
    direction = direction.upper()
    return _float_env(
        f"LNTRANS_DEEPSEEK_PRICE_{direction}_CNY_PER_M",
        default=fallback,
    )


def estimate_cost(tokens_in: int, tokens_out: int,
                  role: str = "translate",
                  provider_name: str | None = None) -> dict:
    if provider_name in ("deepseek", "mixed"):
        price_in = _deepseek_price("INPUT", 2.0)
        price_out = _deepseek_price("OUTPUT", 8.0)
    else:
        price_in = _price(role, "INPUT", 2.0)
        price_out = _price(role, "OUTPUT", 8.0)
    amount = (
        max(0, int(tokens_in)) * price_in
        + max(0, int(tokens_out)) * price_out
    ) / 1_000_000
    return {
        "amount": round(amount, 8),
        "currency": currency(),
        "estimated": True,
    }


def estimate_tokens(text: str) -> int:
    """Conservative provider-neutral estimate used only when usage is absent.

    CJK text is commonly close to one token per character; counting it as
    half understated both cost and chapter budgets by roughly 2x.  Latin text
    keeps the usual ~4 characters/token approximation.
    """
    value = text or ""
    cjk = len(re.findall(
        r"[\u2e80-\u9fff\u3040-\u30ff\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]",
        value,
    ))
    other = max(0, len(value) - cjk)
    return max(1, cjk + (other + 3) // 4)


def daily_budget() -> float:
    return _float_env("LNTRANS_DAILY_BUDGET_CNY", default=0.0)


def currency() -> str:
    return _env("LNTRANS_COST_CURRENCY", default="CNY")


def job_budget() -> float:
    return _float_env("LNTRANS_JOB_BUDGET_CNY", default=0.0)


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _ledger_signature() -> tuple[int, int]:
    try:
        st = os.stat(LEDGER)
        return (st.st_size, st.st_mtime_ns)
    except OSError:
        return (0, 0)


def _load_spent(day: str | None = None, *, refresh: bool = False) -> float:
    day = day or _today()
    with _LEDGER_LOCK:
        signature = _ledger_signature()
        if not refresh and day in _SPENT and _SPENT_SIG.get(day) == signature:
            return _SPENT[day]
        total = 0.0
        if os.path.isfile(LEDGER):
            try:
                with open(LEDGER, encoding="utf-8") as f:
                    for line in f:
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if str(rec.get("at", ""))[:10] != day:
                            continue
                        value = (rec.get("cost") or {}).get("amount", 0)
                        if isinstance(value, (int, float)):
                            total += float(value)
            except OSError:
                pass
        _SPENT[day] = round(total, 8)
        _SPENT_SIG[day] = signature
        return _SPENT[day]


def ensure_budget() -> None:
    limit = daily_budget()
    if limit <= 0:
        return
    spent = _load_spent()
    if spent >= limit:
        raise BudgetExceeded(
            f"今日模型预算已用完：{spent:.4f} / {limit:.4f} "
            f"{currency()}")


def record_usage(*, role: str, model: str, usage: dict,
                 cost: dict | None = None, source: str = "llm",
                 provider_name: str | None = None) -> dict:
    tokens_in = int(usage.get("prompt_tokens",
                              usage.get("input_tokens", 0)) or 0)
    tokens_out = int(usage.get("completion_tokens",
                               usage.get("output_tokens", 0)) or 0)
    total = int(usage.get("total_tokens", 0) or 0)
    if tokens_in == 0 and tokens_out == 0 and total > 0:
        tokens_out = total
    provider_name = provider_name or provider()
    cost = dict(cost or estimate_cost(
        tokens_in, tokens_out, role, provider_name=provider_name))
    stamp = datetime.now().astimezone()
    rec = {
        "schema_version": 1,
        "at": stamp.isoformat(timespec="seconds"),
        "role": role if role in ROLES else "translate",
        "provider": provider_name,
        "model": model,
        "usage": {"input": tokens_in, "output": tokens_out},
        "cost": cost,
        "source": source,
    }
    with _LEDGER_LOCK:
        os.makedirs(DATA, exist_ok=True)
        day = stamp.date().isoformat()
        before = _ledger_signature()
        with open(LEDGER, "a", encoding="utf-8", newline="") as f:
            f.write(json.dumps(rec, ensure_ascii=False,
                               separators=(",", ":")) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        # 每次模型调用后都重读整个账本会让「一天几千次调用」变成
        # O(调用数²) 行解析。账本只由本进程追加（数据根锁保证单实例）：
        # 追加前签名与上次读取一致，就说明没有别的写者，直接增量记账；
        # 否则（启动后第一次读、或外部进程写过）保守地重读一遍。
        if day in _SPENT and _SPENT_SIG.get(day) == before:
            amount = float((rec.get("cost") or {}).get("amount", 0) or 0)
            _SPENT[day] = round(_SPENT.get(day, 0.0) + amount, 8)
            _SPENT_SIG[day] = _ledger_signature()
        else:
            _load_spent(day, refresh=True)
    return rec


def _safe_base_url(role: str | None = None) -> str:
    parsed = urllib.parse.urlsplit(base_url(role))
    host = parsed.hostname or ""
    if parsed.port:
        host += f":{parsed.port}"
    return urllib.parse.urlunsplit((
        parsed.scheme, host, parsed.path, "", ""))


def _role_price(role: str, direction: str) -> float:
    if provider(role) == "deepseek":
        return _deepseek_price(direction, 2.0 if direction == "INPUT" else 8.0)
    return _price(role, direction, 2.0 if direction == "INPUT" else 8.0)


def public_config() -> dict:
    roles = {}
    for role in ROLES:
        routes = routes_for(role)
        fallback = next((r for r in routes if r.fallback), None)
        if fallback is None and role in ("translate", "auxiliary") \
                and fallback_enabled():
            fallback = Route(role=role, base_url=fallback_base_url(),
                             api_key=fallback_api_key(),
                             model=fallback_model(), provider="deepseek",
                             fallback=True)
        roles[role] = {
            "model": model_for(role),
            "provider": provider(role),
            "base_url": _safe_base_url(role),
            "key_configured": bool(api_key(role)),
            "local": is_local(role),
            "price_input_per_m": _role_price(role, "INPUT"),
            "price_output_per_m": _role_price(role, "OUTPUT"),
            "fallback": bool(fallback),
            "fallback_provider": fallback.provider if fallback else "",
            "fallback_model": fallback.model if fallback else "",
            "fallback_price_input_per_m": (
                _deepseek_price("INPUT", 2.0) if fallback else 0.0),
            "fallback_price_output_per_m": (
                _deepseek_price("OUTPUT", 8.0) if fallback else 0.0),
        }
    return {
        "provider": provider(),
        "base_url": _safe_base_url(),
        "key_configured": bool(api_key()),
        "local": is_local(),
        "roles": roles,
        "fallback": bool(fallback_enabled()),
        "fallback_model": fallback_model() if fallback_enabled() else "",
        "max_output_tokens": max_output_tokens(),
        "daily_budget": daily_budget(),
        "job_budget": job_budget(),
        "spent_today": _load_spent(),
        "currency": currency(),
        "ok": bool(is_local() or api_key()),
        "error": ("" if is_local() or api_key()
                  else "远程模型未配置 API key"),
    }
