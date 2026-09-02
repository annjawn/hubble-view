# Developing Hubble

This guide covers local development, testing, architecture, packaging, and provider integrations. Product information belongs in the [README](README.md).

## Architecture

Hubble is a desktop application with two local processes:

- `frontend/` contains the Electron shell and React/Vite renderer.
- `backend/` contains the FastAPI service, provider adapters, analytics, and SQLite persistence layer.

Electron starts the backend on an available loopback port and passes the operating system's application-data directory through `HARNESS_METRICS_DATA_DIR`. Packaged builds include a standalone PyInstaller backend executable; end users do not need Python or `uv` installed.

```text
Provider-owned local data
          │
          ▼
Provider adapters → scanner → Hubble SQLite database
                                  │
                                  ▼
                         FastAPI analytics API
                                  │
                                  ▼
                         Electron + React UI
```

## Repository layout

```text
assets/                         Shared project and README artwork
backend/
  src/harness_metrics/
    api/                        HTTP routes
    providers/                  Harness-specific adapters
    services/                   Scanning and analytics
    config.py                   Runtime settings and data paths
    database.py                 SQLite schema and persistence
    main.py                     FastAPI application
    service.py                  Packaged service entry point
  tests/                        Backend tests and parser fixtures
frontend/
  electron/                     App lifecycle, windows, tray, sidecar
  icons/                        macOS and Windows application icons
  scripts/                      Packaging helpers
  src/                          React components, views, hooks, and API client
```

## Prerequisites

- Node.js with npm
- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/)
- macOS for producing a DMG and `.icns`
- Windows for producing and validating an NSIS installer

## Initial setup

Install the backend environment:

```bash
cd backend
uv sync --group dev
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

## Run the desktop app

From `frontend/`:

```bash
npm run dev
```

This starts Vite and Electron together. In development, Electron invokes the backend through `uv`, waits for its health endpoint, and then reveals the main window. To use a nonstandard `uv` executable, set `HUBBLE_UV_PATH` before starting Electron.

For renderer-only work, use two terminals from `frontend/`:

```bash
npm run backend:dev
```

```bash
npm run dev:renderer
```

The manual development service listens at `http://127.0.0.1:8765`.

## Data and diagnostics

Hubble stores its database and service logs in Electron's platform-specific user-data directory:

- macOS: `~/Library/Application Support/Hubble/`
- Windows: `%APPDATA%\Hubble\`

The packaged service writes diagnostics to `logs/service.log`. Do not commit user databases, harness logs, generated backend bundles, or installer output.

## Verification

Run the backend suite:

```bash
cd backend
uv run --group dev python -m pytest
```

Run frontend checks:

```bash
cd frontend
npm run typecheck
npm test
npm run build
```

For a change that touches provider parsing, add a minimal synthetic fixture to `backend/tests/test_parsers.py`. Tests must not depend on a developer's real harness data or home directory.

## Adding or changing a provider

1. Implement `ProviderAdapter` under `backend/src/harness_metrics/providers/`.
2. Discover only the provider's documented or well-understood local data locations.
3. Normalize records into Hubble usage events with stable source identifiers so rescans remain idempotent.
4. Register the adapter in `provider_registry()`.
5. Add parser tests covering tokens, sessions, timestamps, models, projects, and any provider-specific fields.
6. Add the provider mark under `frontend/src/assets/harnesses/` and wire it through `ProviderMark`, provider colors, dashboard, providers, and tray views.

Adapters must tolerate missing, incomplete, changing, and concurrently written source data. Never copy provider credentials or secrets into Hubble's database.

## Packaging

The packaging step first freezes the FastAPI service with PyInstaller, then builds the renderer and Electron processes, and finally creates the platform installer.

Build macOS:

```bash
cd frontend
npm run dist:mac
```

Build Windows:

```bash
cd frontend
npm run dist:win
```

Artifacts are written under `frontend/release/`. Packaged applications execute the bundled backend directly and must be tested on a machine that does not have the development environment on its `PATH`.

Public macOS distribution requires an Apple Developer ID Application certificate and notarization. Windows distribution should likewise be code-signed before release.

## Pull requests

- Keep changes focused and preserve unrelated work in the tree.
- Include tests for parser and analytics behavior.
- Verify both the empty state and populated state for UI changes.
- Avoid committing generated `dist`, `release`, `.backend-build`, or `backend-dist` content.
- Explain new filesystem locations or data assumptions in the pull request.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
