# Model configuration

Lightnovel uses an OpenAI-compatible Chat Completions endpoint. Existing
`LNTRANS_LLM_BASE` and `DEEPSEEK_API_KEY` installations keep working.

Copy `.env.example` to your private environment configuration. Do not commit
the resulting file.

## Endpoint and key

```text
LNTRANS_LLM_BASE_URL=https://api.deepseek.com/chat/completions
LNTRANS_LLM_API_KEY=...
```

`LNTRANS_LLM_BASE` remains a compatibility alias for the URL. A local loopback
endpoint (`127.0.0.1`, `localhost`, `::1`) may run without a key. If a key is
present it is still sent, allowing local gateways that enforce authentication.

Each role can use its own endpoint and key. Unset values inherit the global
endpoint above:

```text
LNTRANS_LLM_BASE_URL_TRANSLATE=...
LNTRANS_LLM_API_KEY_TRANSLATE=...
LNTRANS_LLM_BASE_URL_AUXILIARY=...
LNTRANS_LLM_API_KEY_AUXILIARY=...
LNTRANS_LLM_BASE_URL_REVIEW=...
LNTRANS_LLM_API_KEY_REVIEW=...
```

Key lookup is role-aware. A DeepSeek host reads `DEEPSEEK_API_KEY` (or the
credential file) rather than the local `LNTRANS_LLM_API_KEY`, so a local engine
key is never sent to the cloud.

The required compatibility surface is:

- `POST` Chat Completions JSON;
- `choices[0].message.content`;
- optional `usage.prompt_tokens` and `usage.completion_tokens`.

When usage is absent, Lightnovel labels the token count as estimated. Streaming
is not required.

## Task roles

```text
LNTRANS_MODEL_TRANSLATE=deepseek-flash
LNTRANS_MODEL_AUXILIARY=deepseek-flash
LNTRANS_MODEL_REVIEW=deepseek-flash
```

The roles cover:

| Role | Work |
| --- | --- |
| `translate` | chapter translation and dialogue repair |
| `auxiliary` | book/chapter titles, synopsis, summaries, names and polish |
| `review` | AI review and AI-assisted fixes |

`LNTRANS_MODEL` remains a common fallback. CLI `--model` still overrides the
configured model for that invocation.

## Local + cloud routing and automatic fallback

A practical setup: translation and auxiliary work run on a local GGUF engine,
review runs on DeepSeek, and translation/auxiliary fall back to DeepSeek when the
local engine is unreachable.

```text
LNTRANS_LLM_BASE_URL=http://127.0.0.1:50087/v1/chat/completions
LNTRANS_LLM_API_KEY=<local-engine key>
LNTRANS_MODEL_TRANSLATE=/path/to/model.gguf
LNTRANS_MODEL_AUXILIARY=/path/to/model.gguf

LNTRANS_LLM_BASE_URL_REVIEW=https://api.deepseek.com/chat/completions
LNTRANS_MODEL_REVIEW=deepseek-flash

LNTRANS_LLM_FALLBACK=1
LNTRANS_LLM_FALLBACK_BASE_URL=https://api.deepseek.com/chat/completions
LNTRANS_LLM_FALLBACK_MODEL=deepseek-flash
```

- Fallback applies only to `translate` and `auxiliary`; `review` uses its own
  endpoint and has no fallback.
- It triggers on connection errors, timeouts, 401/403/404/429 and 5xx after the
  normal retries. A 400/422 (bad prompt/request) is reported and **not** switched
  automatically.
- After a local failure the local route is skipped for 120 seconds, so a dead
  engine does not cost one timeout per chunk. The next call after the cooldown
  probes it again; a success clears the breaker.
- The fallback key is `LNTRANS_LLM_FALLBACK_API_KEY` when set, otherwise the
  DeepSeek key from `DEEPSEEK_API_KEY` or the credential file.
- Chapter sidecars record the provider/model that actually ran. A chapter that
  used both is recorded as `local+deepseek` with a combined model id.

## Prices and budgets

Prices are currency units per million tokens:

```text
LNTRANS_PRICE_INPUT_CNY_PER_M=2
LNTRANS_PRICE_OUTPUT_CNY_PER_M=8
LNTRANS_DAILY_BUDGET_CNY=0
LNTRANS_JOB_BUDGET_CNY=0
```

Role-specific price overrides use prefixes such as
`LNTRANS_TRANSLATE_PRICE_INPUT_CNY_PER_M` and
`LNTRANS_REVIEW_PRICE_OUTPUT_CNY_PER_M`. A value of `0` for either budget means
"no limit".

Local inference can be recorded as free by setting the normal price variables to
`0`. DeepSeek fallback/review use their own price variables so setting local
prices to zero does not make cloud calls look free:

```text
LNTRANS_PRICE_INPUT_CNY_PER_M=0
LNTRANS_PRICE_OUTPUT_CNY_PER_M=0
LNTRANS_DEEPSEEK_PRICE_INPUT_CNY_PER_M=2
LNTRANS_DEEPSEEK_PRICE_OUTPUT_CNY_PER_M=8
```

The budget is advisory, not a brake. Exceeding it does not stop a book that is
being read; the reader and `/queue` show `used X (over budget)` and a book that
is not being read simply waits. The only hard stops are the global pause and the
per-book pause, and a budget of `0` means unlimited.

## Chapter-block translation

Translation is chapter-scoped, not paragraph-by-paragraph: a paragraph fed alone
loses the context of the scene, and sentence-level models have their own prompt
contract. `LNTRANS_TRANSLATE_MODE` selects the path:

| Value | Prompt | Use for |
| --- | --- | --- |
| `batch` (default) | `#N` numbered chunks, one reply block per chunk | general chat models |
| `sakura` | the model's own `将下面的日文文本翻译成中文：...` template, one block in, translation only out | Sakura and similar JP→ZH sentence models |

Both modes send a whole chapter (splitting only at paragraph boundaries when it
is longer than the block limit) and keep the tail of the previous block as
system context. Results are cached per block, so a retry only re-sends the block
that failed.

Block size is per provider, measured rather than guessed:

```text
LNTRANS_CHAPTER_CHARS=2160            # local engines; Sakura holds ~2400 chars
LNTRANS_DEEPSEEK_CHAPTER_CHARS=6000   # cloud; 7393 chars tested complete
LNTRANS_DEEPSEEK_MAX_TOKENS=32000     # reasoning tokens share this budget
```

A small local model that drops dialogue lines even at 2160 characters triggers
the dialogue guard, is retried at a smaller block, and can be escalated to the
fallback provider for that chapter. A failed block stays in the source language,
the chapter is still written and marked incomplete in the sidecar.

Reasoning models count thoughts as completion tokens. `max_tokens` that is too
small returns truncated or empty content, and the retry loop pays for the same
thinking again; DeepSeek therefore defaults to 32000 while local engines keep
their configured value.

Before a request the translator probes the primary endpoint with a 5 second TCP
connect (one retry). A dead local engine is detected in seconds and the fallback
circuit opens immediately instead of waiting for the generation timeout.


## Local cost ledger

Usage is appended to `data/llm-usage.jsonl`. Each line records only:

- timestamp and task role;
- provider and model id;
- input/output tokens and estimated cost;
- coarse source label.

It never records prompts, source text, translations, API keys or request
headers. `/api/modelcfg` exposes models, sanitized endpoint, prices, budget and
today's total to the local UI. It exposes only whether a key is configured,
never the key itself.
