# AGENTS.md

Guidance for AI coding agents working in this directory. Full picture: `README.md`. This is the operator dashboard for [Triage Bot](../README.md) — a Next.js 16 (App Router) app consuming the FastAPI operator API's read-side endpoints in `../api/`. Standalone npm project, not part of the root Python `uv`/`pyproject.toml` tooling.

## The one architectural rule that matters most here

Server Components fetch the FastAPI backend directly, server-to-server — the bearer token (`TRIAGE_API_BEARER_TOKEN`) never reaches the browser. Client Components never call FastAPI directly; they go through same-origin Next.js Route Handlers under `src/app/api/runs/**`, which proxy to FastAPI server-side, because the backend has no CORS support and uses a single static bearer token. Adding a new client-side data need means adding a Route Handler, not reaching for the bearer token in client code.

## Commands

```bash
npm run dev         # local dev server, http://localhost:3000
npm run lint         # eslint
npm run typecheck    # tsc --noEmit
npm test              # vitest run
npm run gen:types     # regenerate src/lib/api/schema.d.ts from the FastAPI app's /openapi.json (run the API locally first)
```

`src/lib/api/schema.d.ts` is generated from the backend's OpenAPI schema — never hand-edit it; run `gen:types` again after any change to `api/schemas/` on the backend.

## Reference index

| Need | Read |
|---|---|
| App architecture, commands, configuration | `README.md` |
| Full API contract this app depends on | `../docs/agent/architecture-conventions.md` |
| Overall Triage Bot architecture/vision | `../docs/summary.md` |
| Root engineering standards & safety protocols | `../AGENTS.md` |

<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->
