#!/usr/bin/env python3
"""Per-role endpoints, local-first routing and automatic fallback."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="lnroutes-test-")
ROOT = os.path.join(TMP, "root")
PROFILE = os.path.join(TMP, "profile")
os.makedirs(os.path.join(ROOT, "novels"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
os.makedirs(PROFILE, exist_ok=True)
os.environ["LNTRANS_DATA_ROOT"] = ROOT
os.environ["LNTRANS_LNFINDER"] = PROFILE
os.environ.pop("LNTRANS_HOME", None)

hits = {"local": 0, "cloud": 0}


def make_stub(label: str):
    class Stub(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            hits[label] += 1
            n = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(n)
            body = json.dumps({
                "choices": [{"message": {"content": "#1:中文"}}],
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
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"


local_srv, local_base = make_stub("local")
cloud_srv, cloud_base = make_stub("cloud")

os.environ["LNTRANS_LLM_BASE_URL"] = local_base
os.environ["LNTRANS_LLM_BASE_URL_REVIEW"] = cloud_base
os.environ["LNTRANS_LLM_PROVIDER_REVIEW"] = "deepseek"
os.environ["LNTRANS_LLM_API_KEY"] = "local-key"
os.environ["LNTRANS_LLM_API_KEY_REVIEW"] = "review-key"
os.environ["LNTRANS_LLM_FALLBACK"] = "1"
os.environ["LNTRANS_LLM_FALLBACK_BASE_URL"] = cloud_base
os.environ["LNTRANS_LLM_FALLBACK_MODEL"] = "deepseek-flash"
os.environ["LNTRANS_LLM_FALLBACK_API_KEY"] = "fallback-key"
os.environ["LNTRANS_CRED"] = os.path.join(TMP, "no-cred.yaml")
os.environ.pop("DEEPSEEK_API_KEY", None)
os.environ.pop("DSHA_DEEPSEEK_OFFICIAL_API_KEY", None)
os.environ["LNTRANS_MODEL_TRANSLATE"] = "sakura-local"
os.environ["LNTRANS_MODEL_AUXILIARY"] = "sakura-local"
os.environ["LNTRANS_MODEL_REVIEW"] = "deepseek-flash"
os.environ["LNTRANS_PRICE_INPUT_CNY_PER_M"] = "0"
os.environ["LNTRANS_PRICE_OUTPUT_CNY_PER_M"] = "0"
os.environ["LNTRANS_DEEPSEEK_PRICE_INPUT_CNY_PER_M"] = "1"
os.environ["LNTRANS_DEEPSEEK_PRICE_OUTPUT_CNY_PER_M"] = "2"
os.environ["LNTRANS_DAILY_BUDGET_CNY"] = "0"
os.environ["LNTRANS_JOB_BUDGET_CNY"] = "0"

sys.path.insert(0, HERE)
import lnmodels  # noqa: E402
import lntrans as lt  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


print("=" * 66)
print("1. 角色路由")
print("=" * 66)
tr = lnmodels.routes_for("translate")
rev = lnmodels.routes_for("review")
check("翻译：主本地 + 备 DeepSeek", len(tr) == 2
      and tr[0].provider == "local" and not tr[0].fallback
      and tr[1].provider == "deepseek" and tr[1].fallback)
check("校对：只有 DeepSeek，不回落",
      len(rev) == 1 and rev[0].provider == "deepseek"
      and rev[0].base_url == cloud_base and rev[0].model == "deepseek-flash")
check("校对 key 用角色自己的",
      lnmodels.api_key("review") == "review-key")
check("公开配置区分角色 provider",
      lnmodels.public_config()["roles"]["translate"]["provider"] == "local"
      and lnmodels.public_config()["roles"]["review"]["provider"] == "deepseek")

print("=" * 66)
print("2. 各走各的端点")
print("=" * 66)
lt.call_llm("s", "u", "sakura-local", 0.1, role="translate")
check("翻译打到本地", hits["local"] == 1 and hits["cloud"] == 0)
lt.call_llm("s", "u", "deepseek-flash", 0.1, role="review")
check("校对打到云端", hits["local"] == 1 and hits["cloud"] == 1)

print("=" * 66)
print("3. 本地连不上 -> 自动切；再调用不反复撞本地")
print("=" * 66)
local_srv.shutdown()
local_srv.server_close()
before_local = hits["local"]
before_cloud = hits["cloud"]
reply, usage = lt.call_llm("s", "u", "sakura-local", 0.1, role="translate")
check("本地失败后由云端完成", reply == "#1:中文" and usage["total_tokens"] == 15)
check("云端收到一次兜底", hits["cloud"] == before_cloud + 1)
check("熔断已打开", not lnmodels.primary_available("translate"))
lt.call_llm("s", "u", "sakura-local", 0.1, role="translate")
check("熔断期内不再撞本地", hits["local"] == before_local)
check("第二次仍走云端", hits["cloud"] == before_cloud + 2)

print("=" * 66)
print("4. 成本按实际 provider")
print("=" * 66)
check("本地按配置 0 元",
      lnmodels.estimate_cost(1000, 1000, "translate",
                             provider_name="local")["amount"] == 0.0)
check("兜底按 DeepSeek 价",
      lnmodels.estimate_cost(1_000_000, 1_000_000, "translate",
                             provider_name="deepseek")["amount"] == 3.0)
ledger = os.path.join(ROOT, "data", "llm-usage.jsonl")
with open(ledger, encoding="utf-8") as f:
    rows = [json.loads(x) for x in f if x.strip()]
check("账本记录实际 provider",
      [r["provider"] for r in rows]
      == ["local", "deepseek", "deepseek", "deepseek"],
      str([r["provider"] for r in rows]))
check("兜底费用 > 0", float(rows[-1]["cost"]["amount"]) > 0)

print("=" * 66)
print("5. 边车可以记混合 provider")
print("=" * 66)
raw = os.path.join(ROOT, "novels", "__route_test__")
os.makedirs(os.path.join(raw, "chapters"), exist_ok=True)
with open(os.path.join(raw, "meta.json"), "w", encoding="utf-8") as f:
    json.dump({"episodes": [{"title": "t"}], "glossary": {}}, f)
with open(os.path.join(raw, "chapters", "0001.raw.txt"), "w",
          encoding="utf-8") as f:
    f.write("こんにちは\n")
lt.NOVELS_DIR = os.path.join(ROOT, "novels")
args = type("A", (), {"model": "sakura-local"})()
rec = lt.chapter_meta_record(
    "__route_test__", 0, {"glossary": {}, "characters": {}, "style": {}},
    args, text="你好", raw_sha=lt._sha256_text("こんにちは\n"),
    tokens_in=10, tokens_out=5, incomplete_paragraphs=[],
    provider_name="local+deepseek", model_id="sakura-local+deepseek-flash",
    cost={"amount": 0.0001, "currency": "CNY", "estimated": True})
check("边车记 actual provider/model/cost",
      rec["model_provider"] == "local+deepseek"
      and rec["model_id"] == "sakura-local+deepseek-flash"
      and rec["cost"]["amount"] == 0.0001)

cloud_srv.shutdown()
cloud_srv.server_close()

print("=" * 66)
if fails:
    print(f"失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("全部通过")
