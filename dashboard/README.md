# Triage Bot — Operator Dashboard

Next.js 15/16 (App Router) operator dashboard for [Triage Bot](../README.md), consuming the FastAPI operator API in `../api/`. Standalone npm project — no monorepo tooling ties it to the rest of the repo, same convention as `../github_page/`.

Overview page (stat cards, filterable runs table) and a per-run detail page (pipeline output, diff viewer, embedded Langfuse trace summary, approve/reject). See `docs/agent/architecture-conventions.md` at the repo root for the full API contract this app is built against.

## Architecture

Server Components fetch the FastAPI backend directly (server-to-server, bearer token never reaches the browser). Client Components go through same-origin Next.js Route Handlers, which proxy to FastAPI server-side — the backend has no CORS support and a single static bearer token, so the browser never talks to it directly.

## Commands

```bash
npm install
npm run dev         # local dev server, http://localhost:3000
npm run build        # production build
npm run lint          # eslint
npm run typecheck     # tsc --noEmit
npm test               # vitest run
npm run gen:types      # regenerate src/lib/api/schema.d.ts from the FastAPI app's /openapi.json (run the API locally first)
```

## Configuration

Server-only env vars, `.env.local` (never committed, never `NEXT_PUBLIC_*`):

```
TRIAGE_API_BASE_URL=http://127.0.0.1:8000
TRIAGE_API_BEARER_TOKEN=<matches the API's API_BEARER_TOKEN setting>
```
