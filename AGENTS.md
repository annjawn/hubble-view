# Hubble — agent guide

Hubble is a local-first desktop dashboard for coding-agent activity. It reads the data that Claude Code, Codex, Cursor, Kiro, OpenCode, and Antigravity already keep on this machine, normalizes it into its own SQLite database, and shows it in an Electron app. Product copy lives in `README.md`; contributor setup lives in `DEVELOPING.md`.

## Layout

| Path | What it is |
| --- | --- |
| `backend/` | Python 3.11+ FastAPI service (`harness_metrics`). Owns `pyproject.toml`, `uv.lock`, `.venv`, tests. |
| `backend/src/harness_metrics/providers/` | One `ProviderAdapter` per harness (usage events) plus `*_trace.py` parsers (session timelines). |
| `backend/src/harness_metrics/services/` | `scanner.py` (import loop), `analytics.py` (queries), `artifacts.py` (config/skills viewer with redaction). |
| `backend/src/harness_metrics/database.py` | SQLite schema and one-shot migrations keyed in `app_settings`. |
| `frontend/electron/` | Main process: windows, tray, spawns the backend sidecar, IPC. |
| `frontend/src/` | React renderer. API types in `src/types/api.ts`, transport in `src/lib/api.ts`, queries in `src/hooks/`. |
| `frontend/scripts/` | PyInstaller and macOS packaging helpers. |
| `backlog/` | Local planning notes for proposed features (git-ignored, so present only on the author's machine). Read the relevant file before starting one. |

Keep the repository root limited to documentation, repository configuration, and the two application directories.

## Commands

Run Python and `uv` from `backend/`; run npm, Vite, TypeScript, and Electron from `frontend/`.

```bash
cd backend && uv sync --group dev             # install
cd backend && uv run --group dev python -m pytest
cd backend && uv run ruff check .             # lint (import order, pyflakes, likely bugs)
cd frontend && npm install
cd frontend && npm run dev                    # Electron + Vite + backend via uv
cd frontend && npm run typecheck && npm test && npm run build
```

Backend change: run pytest and ruff. Frontend change: run typecheck, test, and build. A change that crosses the HTTP or IPC boundary: run both. `.github/workflows/ci.yml` runs the same checks on every push and pull request. The frontend has no ESLint: typescript-eslint does not support the TypeScript 7 this repo uses, so `tsc` with `noUnusedLocals` and `noUnusedParameters` is the static gate.

## How data flows

1. `UsageScanner.scan()` asks each adapter to `discover()` source files and re-parses any whose size or mtime changed (`scanned_files`). An adapter that implements `scan_source` resumes from saved state instead of re-reading the source: Claude from a byte offset, OpenCode from a `time_updated` watermark. Polling endpoints call `scan(max_age=...)` so they reuse a recent scan.
2. Adapters yield `UsageEvent`s; trace parsers yield timeline dicts. Both are upserted by a deterministic `id`, so a rescan must produce the same ids for the same source record.
3. `AnalyticsService` aggregates for the API. Days are bucketed in the machine's local time zone (`date(occurred_at, 'localtime')`) because the renderer keys its grids by local day.
4. Transcript text is indexed for search in the FTS5 table `trace_search`, kept in step by triggers on `trace_events`. The `trace_retention_days` setting prunes transcript text only; `usage_events` is never pruned.
5. Cost figures are estimates computed at read time from `pricing.py` and returned as `estimated_cost_usd`. `cost_usd` holds only what a provider itself reported. Update the table, its version, and its sources together.
6. Electron starts the service on a free loopback port with `HARNESS_METRICS_DATA_DIR` and a per-launch `HARNESS_METRICS_API_TOKEN`. The renderer gets both over IPC and sends the token as `X-Hubble-Token`. `/api/health` answers before the first import ends and reports `initial_scan_complete`.

## Rules that are easy to break

- **Local only.** Never copy provider credentials into the database, and never send usage or transcript data off the machine without an explicit product requirement. Anything shown from a config file goes through `_redact` in `services/artifacts.py`.
- **Source data is hostile.** Harness files are undocumented, change between versions, and are written while Hubble reads them. Parse JSONL with `read_jsonl` (skips partial and corrupt lines), type-check every field before use, and never let one file abort a scan.
- **Do not guess a harness format.** Check the vendor's documentation first; where none exists, inspect the shape of real local data (keys and types, not content) and say in a comment what you observed. See `.claude/rules/external-docs.md`.
- **Token buckets do not overlap.** `input_tokens`, `cache_read_tokens`, `cache_write_tokens`, and `output_tokens` are disjoint. Codex reports cached input inside `input_tokens`, so it is subtracted. One response must be counted once: Claude repeats a `requestId` across lines, and Codex writes both `token_count` and `token_usage_record`.
- **Changing an event id or a parser's meaning needs a migration** in `Database.initialize()` that clears the affected `scanned_files` rows (and stale `usage_events` rows if ids changed). Prefer a targeted delete: Hubble's history is meant to outlive the source logs.
- **Contracts are typed twice.** A response-shape change touches `api/routes.py` or `services/analytics.py`, `frontend/src/types/api.ts`, and usually a test in `backend/tests/test_api.py`.
- **Adding a provider** follows the checklist in `DEVELOPING.md` ("Adding or changing a provider"): adapter, registry, synthetic-fixture tests, provider mark, colors, and views.
- **Tests never read a developer's real home directory.** Build synthetic fixtures under `tmp_path`.

## Packaging and local delivery

`npm run dist:mac` (from `frontend/`) freezes the backend with PyInstaller, builds the app, ad-hoc signs it, and writes `release/mac-arm64/Hubble.app` and a DMG. Do not commit `dist`, `dist-electron`, `release`, `backend-dist`, or `.backend-build`.

After completing any application code or UI change on macOS, build, install, and open the app without waiting to be asked. Packaging and reinstalling are part of finishing the change.

1. From `frontend/`, run `npm run dist:mac`. It must end with the bundle reported as "valid on disk".
2. Back up the database before a build that changes the schema or adds a migration: `sqlite3 "file:$HOME/Library/Application Support/Hubble/metrics.db?mode=ro" ".backup '<same folder>/metrics.backup-<timestamp>.db'"`.
3. Quit Hubble (`osascript -e 'tell application "Hubble" to quit'`) and confirm no `Hubble` or `hubble-service` process remains.
4. Replace `/Applications/Hubble.app` cleanly, never as an overlay: move the old bundle to the Trash, then `cp -R release/mac-arm64/Hubble.app /Applications/Hubble.app`. Overlaying with `ditto` leaves stale sealed resources and invalidates the signature. Check the copy with `codesign --verify --deep --strict`.
5. Launch with `env -u ELECTRON_RUN_AS_NODE -u ELECTRON_NO_ATTACH_CONSOLE open /Applications/Hubble.app`. Shells started by VS Code and other Electron-based editors export `ELECTRON_RUN_AS_NODE=1`, and `open` passes it on; with it set, Hubble starts as plain Node and exits at once without a window or a log line.
6. Verify the installed app: the process list shows `/Applications/Hubble.app/Contents/Resources/backend/hubble-service`, and `~/Library/Application Support/Hubble/logs/service.log` shows `Application startup complete` followed by `GET /api/overview ... 200`, with no `401`, `500`, `Skipping`, or `Traceback` lines.

Report the outcome of each step. If a step fails, stop and say so; do not leave `/Applications` without a working Hubble — restore the previous bundle from the Trash.

## Working with subagents

Project subagents live in `.claude/agents/` and run on Opus 5.5 at medium effort: `hubble-coder` (implementation), `hubble-researcher` (documentation and format research), and `hubble-reviewer` (independent review of a diff). Coding conventions are in `.claude/rules/`.

## Commits

Conventional prefixes as in `git log` (`feat:`, `fix:`, `docs:`, `chore:`). Commit messages describe the change only, with no assistant or tool attribution. Cite the documentation URL and section when a change depends on external behavior.
