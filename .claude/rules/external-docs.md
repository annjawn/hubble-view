# Check the documentation before relying on tool behavior

Hubble depends on tools whose behavior this repository does not control: six coding harnesses' on-disk formats, FastAPI, Pydantic, SQLite, Electron, electron-builder, electron-vite, PyInstaller, uv, React Query, and Recharts. A guess about any of them costs a release, and a wrong guess about a harness format silently corrupts a user's history.

Before writing code that depends on external behavior:

1. Read the official documentation for the exact surface you will use, at the version pinned in `backend/uv.lock` or `frontend/package-lock.json`. `frontend/package.json` pins many packages to `latest`, so the lockfile is the source of truth for what is installed.
2. Cross-check against the source when it is available: the library under `backend/.venv` or `frontend/node_modules`, or the tool's repository.
3. For harness log formats, which are mostly undocumented, inspect real local files and record their structure: record types, key names, value types. Do not copy message content into code, tests, comments, or reports.
4. If the documentation and the data leave the question open, stop and ask. Do not fill the gap with what similar tools usually do.

When you write the code:

- Preserve names exactly as the source spells them (`cache_read_input_tokens`, `cached_input_tokens`, `requestId`, `callID`). Where a remote name maps to a Hubble field, say so in a comment.
- Next to any parsing rule that rests on observation rather than documentation, leave a comment that says what was observed, for example "Codex writes each response's usage as both `token_count` and `token_usage_record`".
- Cite the URL and section in the commit message, and in a code comment when the behavior is surprising.

Documentation worth starting from:

- Claude Code sessions and memory: https://code.claude.com/docs/en/sessions and https://code.claude.com/docs/en/memory
- SQLite date functions and WAL: https://www.sqlite.org/lang_datefunc.html and https://www.sqlite.org/wal.html
- Electron security checklist: https://www.electronjs.org/docs/latest/tutorial/security
- FastAPI: https://fastapi.tiangolo.com/ — uv: https://docs.astral.sh/uv/ — PyInstaller: https://pyinstaller.org/
