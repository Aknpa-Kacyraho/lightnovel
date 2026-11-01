#!/usr/bin/env python3
"""OpenAI-compatible model roles, local no-key mode, cost ledger and budgets."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="lnmodels-test-")
ROOT = os.path.join(TMP, "root")
PROFILE = os.path.join(TMP, "profile")
os.makedirs(os.path.join(ROOT, "novels"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
os.makedirs(PROFILE, exist_ok=True)
os.environ["LNTRANS_DATA_ROOT"] = ROOT
os.environ["LNTRANS_LNFINDER"] = PROFILE
os.environ.pop("LNTRANS_HOME", None)

seen_headers = []


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        seen_headers.append(dict(self.headers))
        body = json.dumps({
            "choices": [{"message": {"content": "#1:中文译文。"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                      "total_tokens": 15},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"

os.environ["LNTRANS_LLM_BASE_URL"] = base
os.environ.pop("LNTRANS_LLM_BASE", None)
os.environ.pop("LNTRANS_LLM_API_KEY", None)
os.environ.pop("DEEPSEEK_API_KEY", None)
os.environ.pop("DSHA_DEEPSEEK_OFFICIAL_API_KEY", None)
os.environ["LNTRANS_CRED"] = os.path.join(TMP, "does-not-exist.yaml")
os.environ["LNTRANS_MODEL_TRANSLATE"] = "translate-model"
os.environ["LNTRANS_MODEL_AUXILIARY"] = "cheap-model"
os.environ["LNTRANS_MODEL_REVIEW"] = "review-model"
os.environ["LNTRANS_TRANSLATE_PRICE_INPUT_CNY_PER_M"] = "3"
os.environ["LNTRANS_TRANSLATE_PRICE_OUTPUT_CNY_PER_M"] = "9"
os.environ["LNTRANS_DAILY_BUDGET_CNY"] = "0"
os.environ["LNTRANS_JOB_BUDGET_CNY"] = "1.5"

sys.path.insert(0, HERE)
import lnmodels  # noqa: E402
import lntrans as lt  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


print("=" * 66)
print("1. 端点、角色模型与本地免密钥")
print("=" * 66)
check("新版端点变量生效", lnmodels.base_url() == base)
check("两个旧变量仍兼容", (
    os.environ.pop("LNTRANS_LLM_BASE_URL", None) is not None
    and (os.environ.__setitem__(
        "LNTRANS_LLM_BASE", "http://127.0.0.1:9999/legacy")) is None
    and lnmodels.base_url() == "http://127.0.0.1:9999/legacy"
))
os.environ["LNTRANS_LLM_BASE_URL"] = base
os.environ.pop("LNTRANS_LLM_BASE", None)
check("翻译/辅助/校对模型分别配置",
      lnmodels.model_for("translate") == "translate-model"
      and lnmodels.model_for("auxiliary") == "cheap-model"
      and lnmodels.model_for("review") == "review-model")
check("本地 OpenAI-compatible 无 key 也可用",
      lnmodels.is_local() and lnmodels.public_config()["ok"])

secret = "sk-" + "x" * 32
os.environ["LNTRANS_LLM_API_KEY"] = secret
pub = json.dumps(lnmodels.public_config(), ensure_ascii=False)
check("公开配置只报告 key 已配置，不回传密钥",
      '"key_configured": true' in pub.lower() and secret not in pub)
os.environ.pop("LNTRANS_LLM_API_KEY")
os.environ["LNTRANS_LLM_API_KEY"] = ""
os.environ["DEEPSEEK_API_KEY"] = "legacy-key"
check("新版空 key 不会遮蔽旧变量", lnmodels.api_key() == "legacy-key")
os.environ.pop("LNTRANS_LLM_API_KEY")
os.environ.pop("DEEPSEEK_API_KEY")

print("=" * 66)
print("2. 真实本地调用：无 Authorization、记录 usage 与费用")
print("=" * 66)
reply, usage = lt.call_llm("system", "#1:原文", "translate-model", 0.1)
check("本地端点调用成功", reply == "#1:中文译文。" and usage["total_tokens"] == 15)
_h = seen_headers[-1] if seen_headers else {}
check("本地端点未发送 Authorization", "Authorization" not in _h)
_ledger = os.path.join(ROOT, "data", "llm-usage.jsonl")
with open(_ledger, encoding="utf-8") as f:
    rows = [json.loads(x) for x in f if x.strip()]
check("账本只记录角色、模型、token 与费用",
      len(rows) == 1 and rows[0]["role"] == "translate"
      and rows[0]["usage"] == {"input": 10, "output": 5}
      and "system" not in json.dumps(rows[0])
      and "#1:原文" not in json.dumps(rows[0]))
check("费用按配置价格计算",
      abs(float(rows[0]["cost"]["amount"]) - 0.000075) < 1e-9,
      str(rows[0]["cost"]))
check("今日花费与账本一致",
      abs(lnmodels.public_config()["spent_today"] - 0.000075) < 1e-9)

print("=" * 66)
print("3. 日预算在请求前阻断，不会重复付费")
print("=" * 66)
os.environ["LNTRANS_DAILY_BUDGET_CNY"] = "0.00001"
before_calls = len(seen_headers)
blocked = False
try:
    lt.call_llm("system", "#1:原文", "translate-model", 0.1)
except lnmodels.BudgetExceeded:
    blocked = True
check("超出日预算时请求前阻断", blocked and len(seen_headers) == before_calls)
check("任务预算可单独配置", lnmodels.job_budget() == 1.5)

print("=" * 66)
print("4. 角色模型映射到成本账本")
print("=" * 66)
os.environ["LNTRANS_DAILY_BUDGET_CNY"] = "0"
_aux, _ = lt.call_llm("system", "短标题", "cheap-model", 0.2)
with open(_ledger, encoding="utf-8") as f:
    rows2 = [json.loads(x) for x in f if x.strip()]
check("辅助模型记为 auxiliary",
      rows2[-1]["role"] == "auxiliary"
      and rows2[-1]["model"] == "cheap-model")

# 三个角色使用同一个模型时，不能再靠 model 名反推角色；调用方必须显式
# 传 role，否则书名/校对都会误记成翻译费用。
_same, _ = lt.call_llm(
    "system", "书名", "deepseek-chat", 0.2, role="auxiliary")
with open(_ledger, encoding="utf-8") as f:
    rows3 = [json.loads(x) for x in f if x.strip()]
check("同模型时显式角色仍记为 auxiliary",
      rows3[-1]["role"] == "auxiliary"
      and rows3[-1]["source"] == "auxiliary")

print("=" * 66)
print("5. 冷启动账本与 CJK token 估算")
print("=" * 66)
lnmodels._SPENT.clear()
_role_before, _ = lt.call_llm(
    "system", "冷启动", "translate-model", 0.1, role="translate")
with open(_ledger, encoding="utf-8") as f:
    ledger_total = round(sum(
        float((json.loads(x).get("cost") or {}).get("amount", 0) or 0)
        for x in f if x.strip()
    ), 8)
check("新进程首条记录不会把今日花费重置为单次金额",
      abs(lnmodels.public_config()["spent_today"] - ledger_total) < 1e-8,
      f'{lnmodels.public_config()["spent_today"]} != {ledger_total}')
check("17 个日文字符至少估为 17 token",
      lnmodels.estimate_tokens("あ" * 17) >= 17,
      str(lnmodels.estimate_tokens("あ" * 17)))
check("中英混合不会低估 CJK 部分",
      lnmodels.estimate_tokens("中文十七字" + "abcd") >= 5)

srv.shutdown()
srv.server_close()
print()
if fails:
    print(f"失败 {len(fails)} 项：{fails}")
    print(f"保留现场：{TMP}")
    sys.exit(1)
shutil.rmtree(TMP, ignore_errors=True)
print("模型角色、本地无密钥、成本账本与预算全部通过")
