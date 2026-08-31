# Hubble

Hubble is an offline-first desktop dashboard for monitoring local Claude Code and Codex usage. The Electron and React frontend runs alongside a local FastAPI service, which scans provider-owned logs, normalizes usage events, and stores aggregate-ready records in SQLite.

## Repository layout

```text
backend/                       Python API and metrics pipeline
  src/harness_metrics/         API, providers, storage, and services
  tests/                       Backend test suite

frontend/                      Electron desktop app and React UI
  electron/                    Desktop lifecycle, tray, and sidecar startup
  src/                         Components, hooks, API client, and views
```

## Requirements

- Node.js and npm
- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
cd backend
uv sync

cd ../frontend
npm install
```

## Development

Start the desktop app from `frontend/`:

```bash
cd frontend
npm run dev
```

Electron starts the FastAPI backend automatically on `127.0.0.1:8765`. For browser-only UI development, use two terminals from `frontend/`:

```bash
npm run backend:dev
npm run dev:renderer
```

## Verification

```bash
cd backend
uv run pytest

cd ../frontend
npm run typecheck
npm run test
npm run build
```

## Extending providers

Implement `ProviderAdapter` under `backend/src/harness_metrics/providers/`, then register the adapter in `provider_registry()`.

## Privacy

All normalized data remains in the operating system's application-data directory. Credentials are not copied into the application database. The current adapters report metrics available in local logs, including tokens, cache tokens, sessions, projects, models, tool calls, duration, and reported cost.
