# Repository guidance

## Structure

- `backend/` is the Python 3.11+ FastAPI service and owns its `pyproject.toml`, `uv.lock`, virtual environment, source, and tests.
- `frontend/` is the Electron, React, TypeScript, and Vite application and owns its npm configuration, dependencies, desktop process, renderer source, and build output.
- Keep the repository root limited to cross-project documentation, repository configuration, and the two application directories.

## Working conventions

- Run Python and `uv` commands from `backend/`.
- Run npm, Vite, TypeScript, and Electron commands from `frontend/`.
- Keep frontend-to-backend contracts typed in `frontend/src/types/` and API transport code in `frontend/src/lib/`.
- Add provider integrations behind `ProviderAdapter` in `backend/src/harness_metrics/providers/`.
- Preserve the local-only privacy model: do not copy provider credentials into the application database or send usage data to external services without an explicit product requirement.

## Verification

For backend changes, run:

```bash
cd backend
uv run pytest
```

For frontend changes, run:

```bash
cd frontend
npm run typecheck
npm run test
npm run build
```

When a change crosses the API boundary, verify both projects.
