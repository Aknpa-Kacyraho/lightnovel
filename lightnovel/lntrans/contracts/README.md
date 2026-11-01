# v5 data contracts

These schemas describe durable facts.  Phase 2 implements the file-based task
archive and chapter-sidecar writer while keeping the records versioned.

## Job record

One JSON object represents one durable translation task.  The task log may be
JSON Lines, one object per file, or another append-only store later, but every
object must validate against `job-v1.schema.json`.

The task log answers **why work stopped**.  It does not define whether a
chapter is readable.

## Chapter sidecar

`chapters/NNNN.meta.json` describes the final content written to
`chapters/NNNN.txt`. It answers **what this chapter is**:

* the source hash it was translated from;
* the hash of the exact translated text written to disk;
* the exact model and prompt configuration used;
* actual usage and configured cost;
* paragraphs that remain incomplete.

The text/content hash pair is required.  The writer installs the sidecar before
atomically replacing the text; a crash between those operations leaves a
visible hash mismatch, so stale content is never reported as complete.

`status` is `complete` or `partial`. A complete chapter must have an empty
`incomplete_paragraphs` list; a partial chapter must list at least one missing
paragraph. Both remain readable when the source hash matches.

`translation_config_hash` includes source, provider, model, prompt, glossary,
character and style revisions.  A different hash means "available, but can be
retranslated with the current configuration"; it does not invalidate readable
content.

## Recovery rules

Recovery code:

1. Read the current target chapter range.
2. Treat the chapter file + valid sidecar as the content source of truth.
3. Recompute remaining work from source hashes, content availability and
   current budget.
4. Never replay a historical event stream as the only way to decide what is
   translated.
5. Turn leftover `queued`/`running` jobs into `interrupted` at startup.
6. Require explicit user confirmation before resuming paid work.
7. Enter read-only recovery mode if any task log is malformed.

