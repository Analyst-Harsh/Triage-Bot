# Triage Bot — Operator Dashboard

Next.js 16 (App Router) operator dashboard for [Triage Bot](../README.md), consuming the FastAPI operator API in `../api/`. Standalone npm project — no monorepo tooling ties it to the rest of the repo, same convention as `../github_page/`.

Two views: an overview page for triaging the whole queue at a glance, and a per-run detail page for triaging one issue's pipeline output. See `../docs/agent/architecture-conventions.md` for the full API contract this app is built against.

## Contents

- [Overview page](#overview-page)
- [Run detail page](#run-detail-page)
- [Architecture](#architecture)
- [Commands](#commands)
- [Testing](#testing)
- [Configuration](#configuration)

## Overview page

The default `/dashboard` route — a Server Component that prefetches the runs list, a period-scoped summary, and an all-time health summary, then hydrates a client tree so the first paint already has real data, no loading flash.

| Piece | What it shows |
|---|---|
| **Stat cards** | Animated counts (auto-posted, queued, approved, rejected, failed) for the selected time period |
| **Status distribution bar** | Proportional breakdown of run outcomes at a glance |
| **System health panel** | All-time health summary in the sidebar, independent of the period filter |
| **Runs table** | Filterable (status, repo, source, period) and paginated, with status/risk badges; filters live in the URL so a filtered view is a shareable link |

## Run detail page

`/dashboard/runs/[owner]/[repo]/[issueNumber]` — a Server Component fetches the run's full detail (404s become Next.js `notFound()`), and a client component keeps it live via polling. The pipeline's output is rendered as a sequence of sections mirroring the graph itself:

- **Approval panel** — shown only when the run is paused on `pending_approval`; approve or reject each queued action individually, with per-action notes.
- **Planner / Research / Draft sections** — the classification, investigation findings, and drafted response, with an embedded **diff viewer** for any proposed code fix.
- **Risk and post-results** — risk level and reasoning per action, side by side with what actually happened when it posted (or didn't).
- **Episodic memory section** — the past-run "memory" hits the Planner used for context on this issue.
- **Trace summary panel** — an embedded Langfuse trace summary (duration/cost per observation), shown when the run has a `trace_id`.

Retry and resume actions are proxied through Next.js Route Handlers rather than calling FastAPI from the browser.

## Architecture

Server Components fetch the FastAPI backend directly (server-to-server, bearer token never reaches the browser). Client Components go through same-origin Next.js Route Handlers, which proxy to FastAPI server-side — the backend has no CORS support and a single static bearer token, so the browser never talks to it directly. All request/response types come from a generated OpenAPI schema (`src/lib/api/schema.d.ts`), consumed through a thin `TriageApiClient` wrapper and an `openapi-fetch`-based query/hooks layer built on TanStack Query.

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

## Testing

Vitest + Testing Library, co-located with the code under test (`*.test.ts(x)` next to the module it covers) rather than a parallel `tests/` tree — nearly every module under `src/lib/` and the higher-risk components (e.g. the approval panel) have one. `npm test` runs the full suite.

## Configuration

Server-only env vars, `.env.local` (never committed, never `NEXT_PUBLIC_*`):

```
TRIAGE_API_BASE_URL=http://127.0.0.1:8000
TRIAGE_API_BEARER_TOKEN=<matches the API's API_BEARER_TOKEN setting>
```
