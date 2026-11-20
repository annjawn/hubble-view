---
paths:
  - "frontend/**/*.{ts,tsx,mjs}"
---

# Frontend TypeScript style

- Strict TypeScript with `noUnusedLocals` and `noUnusedParameters`. No `any`; narrow `unknown` at IPC and network boundaries.
- Dependencies are pinned to caret ranges in `package.json`. Do not use `latest`; change a version deliberately and commit the lockfile with it.
- Two-space indent, single quotes, no semicolons, matching the existing files.
- Function components with named exports. One view per file in `src/views/`, shared pieces in `src/components/<area>/`.
- Styling is Tailwind utility classes plus the few component classes in `src/index.css` (`panel`, `drag-region`). Provider colors come from `src/lib/providerColors.ts`; do not hard-code them in components.
- Formatting helpers live in `src/lib/format.ts`. Dates from the API are ISO strings; day keys (`YYYY-MM-DD`) are already in the machine's local time zone, so do not shift them again.

## Data access

- Every HTTP call goes through `src/lib/api.ts`, which adds the base URL and the launch token. Do not call `fetch` from components.
- Show a dollar figure only through `estimate()` in `src/lib/format.ts`, and say next to it that it is an API list-price estimate.
- Every response type is declared in `src/types/api.ts` and mirrors the backend field names exactly, in snake_case.
- Server state lives in React Query hooks in `src/hooks/useMetrics.ts`. Give each hook a stable `queryKey` that includes its parameters, and choose a `refetchInterval` deliberately: each sessions or events request triggers a backend scan.
- Render transcript, tool, and config content as text. Never use `dangerouslySetInnerHTML` for data that came from a harness.

## Electron

- Keep `contextIsolation: true` and `nodeIntegration: false` on every window. The renderer reaches the main process only through the `desktop` bridge in `electron/preload.ts`.
- Adding an IPC channel means three edits: the handler in `electron/main.ts`, the bridge in `electron/preload.ts`, and the type in `src/types/electron.d.ts`.
- Treat IPC arguments as untrusted. Validate type and scope in the handler before touching the filesystem or `shell`.
- Guard optional desktop features with `window.desktop?.`, because the renderer also runs in a plain browser during `npm run dev:renderer`.
- The main process is the only place that spawns the backend. Pass configuration to it through `HARNESS_METRICS_*` environment variables.
