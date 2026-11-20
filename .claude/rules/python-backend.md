---
paths:
  - "backend/**/*.py"
---

# Backend Python style

- Target Python 3.11. Use built-in generics and unions (`list[str]`, `str | None`). Annotate every function signature.
- Imports: standard library, third party, then local, separated by blank lines. Inside `providers/` use relative imports; elsewhere import from `harness_metrics`.
- Lines run up to 120 characters. Double quotes. Four-space indent. `uv run ruff check .` must pass; it enforces import order, pyflakes, and likely-bug rules. No formatter is configured, so match the file you are in.
- Private module helpers start with an underscore. Adapters are classes with `id` and `name` class attributes; parsers are module-level functions.
- Comments explain why a rule exists or what a source format does. Do not restate the code.

## Parsing source data

- Read JSONL through `read_jsonl` in `providers/jsonl.py`. It skips blank, partial, and corrupt lines and yields only objects with their original line numbers. For append-only files, `read_jsonl_from` resumes at a byte offset and assigns the same line numbers.
- Implement `scan_source` on an adapter only when a source can be resumed without context from earlier records. Whatever it returns as state must be enough to continue, and a full `parse` must still produce the same event ids.
- Check the type of every value before using it: `value.get("x") if isinstance(value, dict) else {}`. A record that is a list, or a field that is null, must not raise.
- Open another tool's SQLite database read-only (`sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=...)`), close it, and catch `sqlite3.Error`.
- A parser returns nothing for a source it cannot read. It never raises for bad data.
- Build event ids from stable source identity (request id, message id, row id), falling back to path and line number. The same record must hash to the same id on every scan.
- Timestamps are stored as ISO 8601 strings with an offset. Never store `str(None)`; fall back to the file's mtime.

## Database and API

- All SQL takes parameters. Never format values into a statement.
- Schema changes go in `SCHEMA` with `IF NOT EXISTS`; behavior changes that need a re-import get a one-shot migration keyed in `app_settings`, following the existing blocks in `Database.initialize()`.
- Route handlers stay thin: validate, call a service, return. Aggregation belongs in `services/`.
- Keep routes synchronous (`def`) unless they await something; FastAPI runs them in a thread pool, and they block on SQLite.

## Tests

- pytest, one behavior per test, named `test_<what_it_guarantees>`.
- Fixtures are synthetic and built under `tmp_path`. Pass `adapters=[...]` and a temp `Settings` to `create_app`; never touch the real home directory or database.
- Every parser or analytics fix comes with a test that fails without it.
