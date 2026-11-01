# Lightnovel Shelf

**v5.0.0-alpha.14 — whole-chapter translation and remembered LAN devices**

A local-first Japanese light-novel translator and personal bookshelf. It keeps
translations, terminology, character memory, reading progress and taste data on
your own machine.

This version is an alpha. The v5 data-root migration, generation switching,
single-instance ownership, durable job logs, interrupt recovery, model roles and
cost controls are implemented and fault-tested, but container deployment and
the reading-data layer are not complete yet.

## Run the existing local setup

```bash
cd lntrans
python run_selftests.py
python lnserve.py --port 8099
```

Open <http://127.0.0.1:8099/>.

Python 3.10+ is required. Translation needs an OpenAI-compatible endpoint; a
local engine works without a key on a loopback address. Role routing, block
limits and fallback are described below and in `.env.example`.

## v5 data home

For long-term use, migrate from the legacy `lntrans/novels`, `lntrans/data` and
`lnfinder` layout into one data home:

```bash
python lntrans/lnmigrate.py migrate \
  --home /data \
  --source-root lntrans \
  --source-profile lnfinder

python lntrans/lnmigrate.py migrate \
  --home /data \
  --source-root lntrans \
  --source-profile lnfinder \
  --write

LNTRANS_HOME=/data python lntrans/lnserve.py --port 8099
```

The first command is a dry run. Migration copies and verifies data before
atomically changing the active generation. Old data is not deleted. A second
server using the same home is rejected by an OS-level lock.

Translation jobs are stored under `data/jobs/`. A process restart changes
`queued`/`running` work to `interrupted`; readers see the completed and
remaining chapter lists and must explicitly confirm a resume. Completed
chapters are identified from their text plus `chapters/NNNN.meta.json`, not by
replaying an event log. A source/content hash mismatch makes that chapter
unavailable instead of treating it as complete.

Inspect or validate the job archive:

```bash
python lntrans/lnjobs.py list
python lntrans/lnjobs.py verify
```

If a job record is corrupt, the service starts in restricted recovery mode.
Reading, progress, bookshelf changes and backup remain available. The job-writing
translation endpoints are rejected with HTTP 503. The UI and `/api/recovery`
identify the bad file.
Quarantine it only after inspecting it:

```bash
python lntrans/lnjobs.py quarantine <job-id>
python lntrans/lnjobs.py quarantine <job-id> --write
```

Mutating translation commands and `lnbackup export` / `restore --write` use the
same lock, so stop the server before running them. Read-only commands remain
available while the service is running. See the data-safety document for the
maintenance-script boundary and backup snapshot limitation.

See [docs/V5-DATA-SAFETY.md](docs/V5-DATA-SAFETY.md) for the directory contract,
migration failure behavior and locked phase-2 task/chapter sidecar contracts.

## Model configuration

The endpoint accepts any OpenAI-compatible Chat Completions service. Configure
separate translation, auxiliary and review models, prices and optional
per-day/per-task budgets through environment variables:

```bash
# translate/auxiliary stay local; review goes to DeepSeek; local failures fall back
LNTRANS_LLM_BASE_URL=http://127.0.0.1:50087/v1/chat/completions \
LNTRANS_LLM_API_KEY=... \
LNTRANS_MODEL_TRANSLATE=/path/to/model.gguf \
LNTRANS_MODEL_AUXILIARY=/path/to/model.gguf \
LNTRANS_LLM_BASE_URL_REVIEW=https://api.deepseek.com/chat/completions \
LNTRANS_MODEL_REVIEW=deepseek-flash \
LNTRANS_LLM_FALLBACK=1 \
LNTRANS_LLM_FALLBACK_BASE_URL=https://api.deepseek.com/chat/completions \
LNTRANS_LLM_FALLBACK_MODEL=deepseek-flash \
python lntrans/lnserve.py --port 8099
```

The per-role endpoint/key variables (`..._TRANSLATE`, `..._AUXILIARY`,
`..._REVIEW`) override the global endpoint; review has no fallback, while
translation/auxiliary try the local endpoint first and switch to DeepSeek after
a connection/auth/5xx/timeout failure (120-second circuit breaker). Local
loopback endpoints do not require a key. The old
`LNTRANS_LLM_BASE` / `DEEPSEEK_API_KEY` names remain supported. See
[docs/MODEL-CONFIG.md](docs/MODEL-CONFIG.md) and `.env.example`.

## Chapter-block translation

A paragraph translated alone loses the scene around it, so translation is
chapter-scoped. A chapter is sent as one block and split only at paragraph
boundaries when it exceeds the model's limit; the tail of the previous block is
kept as system context and results are cached per block.

`LNTRANS_TRANSLATE_MODE` picks the prompt contract: `batch` (numbered `#N`
chunks, for general chat models) or `sakura` (the model's own
`将下面的日文文本翻译成中文：...` template, for sentence-level JP→ZH engines).
Both use the same whole-chapter flow, and the template follows the provider that
actually runs (a fallback to the cloud switches back to the general template).

Block limits are measured, not guessed:

| Setting | Default | Evidence |
| --- | --- | --- |
| `LNTRANS_CHAPTER_CHARS` (local) | 2160 | Sakura holds ~2400 chars; 3941→22/28 dialogue pairs, 3189→16/20, 2389→10/10, 1550→18/18 |
| `LNTRANS_DEEPSEEK_CHAPTER_CHARS` (cloud) | 6000 | 7393-char block: 60/60 dialogue pairs, ratio 0.79, no truncation |
| `LNTRANS_DEEPSEEK_MAX_TOKENS` | 32000 | reasoning counts as completion; smaller budgets truncate or empty the answer |

A local model that still drops dialogue lines is retried at a smaller block and
can be escalated to the fallback provider for that chapter; a block that keeps
failing stays in the source language and the chapter is marked incomplete.

Every real call appends token and cost data to `data/llm-usage.jsonl` without
storing prompts, translations or credentials. The reader shows the configured
models, today's spend and whether a key is configured.

## Verify

```bash
cd lntrans
python run_selftests.py
```

The suite is isolated from real data and currently contains 35 tests. CI also
builds a CI-only image with a read-only application layer and a single writable
`/data` volume.

## Security

- Do not expose the service directly to the public Internet.
- LAN mode uses a form login; the access token is never put in the URL.
- Browser sessions are random, expiring HttpOnly cookies, not the master token.
- A successful LAN login also remembers the browser with a long-lived random
  device secret (only its SHA-256 is stored, under `data/devices.json`), so a
  service restart does not ask for the token again; "exit this device" revokes
  it. `LNTRANS_DEVICE_DAYS` sets the lifetime (180 days, renewed on use).
- Cross-site writes, unexpected Host headers and repeated login/translation
  starts are rejected or rate-limited.
- Set `LNTRANS_TOKEN_FILE` for a fixed token kept outside the data root, and use
  `LNTRANS_ALLOWED_HOSTS` for an intentional Tailscale or reverse-proxy hostname.
- Do not commit `.env`, API keys, translations, reading state or profiles.
- Prefer local ext4/btrfs storage or a container-local volume. Advisory locks on
  network filesystems are not considered reliable.

See [SECURITY.md](SECURITY.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

