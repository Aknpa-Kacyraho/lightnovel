# Contributing

## Ground rules

- Never commit runtime books, translations, reading state, profiles, feedback,
  API keys, logs, generated databases, or data-root migrations.
- Do not make the application write into its code directory.
- Do not add a dependency without documenting why the standard library is not
  sufficient and updating the license notices.
- Preserve legacy v4 read support until a documented major migration removes it.

## Required checks

Run all self-tests:

```bash
cd lntrans
python run_selftests.py
```

For data-layer changes, also run:

```bash
python test_contracts.py
python test_data_safety.py
```

Changes to migrations or data-root locks must include a failure test that kills
the process at the relevant step. A successful happy-path migration alone is
not sufficient.

Any new command that writes the data root must acquire the same `lndata`
exclusive lock. Do not add a mutating maintenance path outside that lock
without documenting it as an explicit limitation.

## Commits and licenses

By submitting a contribution, you agree that it may be distributed under the
GNU Affero General Public License v3.0 or later in `LICENSE`. Add attribution to
`NOTICE` when incorporating third-party code or assets. Do not copy upstream
code without recording its license and source.

