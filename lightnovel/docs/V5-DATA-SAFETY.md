# v5 data safety

Version `5.0.0-alpha.5` adds form-based LAN login with random sessions,
same-origin write checks, Host validation, security headers and rate limits on
top of durable translation-task recovery and unified model configuration.
It does not yet claim to be a hardened public-internet service.

## Directory contract

When `LNTRANS_HOME` is set, the application uses one data home:

```text
/data/
  .lntrans-state.json
  .lntrans.lock
  backups/
  generations/
    gen-YYYYMMDD-HHMMSS-xxxx/
      novels/
      data/
        jobs/
          quarantine/
      profile/
  staging/
```

Application code is separate and may be mounted read-only. The old v4 layout is
still supported when `LNTRANS_HOME` is unset.

`.lntrans-state.json` is the only active-generation pointer. Migration copies
and verifies a complete generation before atomically changing that pointer.
Rollback changes the pointer back; it does not rename individual data folders.

## Migration

Dry-run first:

```bash
python lntrans/lnmigrate.py migrate \
  --home /data \
  --source-root ./lntrans \
  --source-profile ./lnfinder
```

Apply after checking free space and file counts:

```bash
python lntrans/lnmigrate.py migrate \
  --home /data \
  --source-root ./lntrans \
  --source-profile ./lnfinder \
  --write
```

Old data is copied, never deleted or moved. Failed staging trees are retained
for diagnosis but are unreachable by the active pointer. Back up the data home
with the existing `lnbackup.py` workflow before each migration.

## Single-instance ownership

`lnserve.py` takes a non-blocking OS advisory lock for its entire lifetime.
Linux uses `fcntl.flock`; Windows uses `msvcrt.locking` plus a path-derived
kernel mutex so Store Python/application-isolation contexts cannot bypass the
ownership rule. The lock is released by the operating system on process death.
The lock marker is diagnostic only and must never be used to decide whether a
process is alive.

Use local ext4/btrfs storage or a container-local volume. Network filesystems
may not implement advisory locks consistently and are not supported for the
active data home.

## CLI write boundary

The same data-root lock is acquired by:

- `lnserve.py`;
- mutating `lntrans.py` commands (`init`, `next` without dry-run, `fetch`,
  `summary`, `review`, `learn`, `titles`, `fix`, `names --apply` and
  `polish --write`);
- `lnbackup.py export`;
- `lnbackup.py restore --write`.

Read-only commands such as `status`, `list`, `lessons`, `residue`, `verify`,
`info`, dry-run migration and dry-run restore do not take the exclusive lock.

The maintenance scripts and finder profile writers are not yet migrated to the
same process lock. Stop the bookshelf service before running mutation commands
in `align_quotes.py`, `repair_dialogue.py`, `repair_chrome.py`, or finder
commands that write profiles or reports.

The web backup endpoint runs while the server owns the data-root lock, but a
backup taken during active translation is not promised to be a transactional
point-in-time snapshot. Stop translation or the service when that guarantee is
required.

## Chapter sidecars

Every v5 chapter write creates `chapters/NNNN.meta.json`. It records:

- source SHA-256 and exact translated-content SHA-256;
- model provider/id, prompt version and translation-configuration hash;
- token usage, estimated cost and incomplete paragraph numbers;
- `complete` or `partial`.

The writer installs the sidecar before atomically replacing the text. A crash
between those operations leaves an explicit hash mismatch. Readers then treat
the chapter as unavailable and may retranslate it; they never mistake mixed
versions for completed content.

A `partial` chapter remains readable, but its chapter number stays in the
completion queue. Resuming work retries only the uncached/missing paragraphs
and does not re-buy paragraphs already present in the segment cache.

Legacy v4 chapters without a sidecar remain readable. Deterministic edits
(term replacement, review fixes, quote/dialogue repairs) refresh the sidecar's
content and configuration hashes.

## Durable jobs and recovery

Each translation task has one JSON file under `data/jobs/`. It records a stable
job id, idempotency key, requested and actual chapter ranges, model
configuration, usage/cost, completed chapters, remaining chapters, partial
chapters, error and one of eight states.

At service startup, leftover `queued` or `running` records become
`interrupted`. The in-memory queue is not replayed. The reader displays how many
chapters completed and remain; paid work resumes only after the user clicks
the confirmation action or sends `resume: true`.

Completed chapters are facts taken from the text + valid sidecar. Recovery
recomputes the missing set, so already usable chapters are skipped even if the
process was killed during a model request or after several restarts.

## Task-log corruption

If any task record is malformed, the service enters restricted recovery mode:

- bookshelf, chapter reads, reading progress and bookshelf updates continue;
- backup download remains available;
- translation start/stop and other job-state writes return HTTP 503;
- unreadable jobs are isolated from normal reads instead of freezing unrelated POSTs;
- `/api/recovery` and the page banner identify the bad job file.

Inspect without changing data:

```bash
python lntrans/lnjobs.py list
python lntrans/lnjobs.py verify
```

The repair operation is a reversible move into `data/jobs/quarantine/`:

```bash
python lntrans/lnjobs.py quarantine <job-id>
python lntrans/lnjobs.py quarantine <job-id> --write
```

The service never silently deletes a corrupt log and never resumes writes just
because the bad file disappeared from the active scan.

## Version gate

If a data home has a `schema_version` newer than the running application, the
application refuses to start. It must never guess how to downgrade or rewrite
newer data.

