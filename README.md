# Triage Bot

[![CI](https://github.com/Analyst-Harsh/Triage-Bot/actions/workflows/bi_frost.yml/badge.svg)](https://github.com/Analyst-Harsh/Triage-Bot/actions/workflows/bi_frost.yml)
[![Coverage](https://raw.githubusercontent.com/Analyst-Harsh/Triage-Bot/python-coverage-comment-action-data/badge.svg)](https://github.com/Analyst-Harsh/Triage-Bot/tree/python-coverage-comment-action-data)

A LangGraph-based agent that triages GitHub issues. A live webhook and a replay pipeline of backfilled OSS issues both feed the same pipeline — **Planner → Researcher → Drafter → Risk check → Auto-post/Approval queue** — with every outcome logged to episodic memory, checkpointed via Postgres, and traced via OpenTelemetry + Langfuse.

The project is early-stage: the state schema (`graph/schemas/`, `graph/state.py`) is implemented and tested; the graph nodes, FastAPI webhook/replay entry points (`api/`), and agent tools (`tools/`) are still being built.

## Quickstart

Requires the `git` CLI on `PATH` (used at runtime by `utils/diff_applier.py`'s `DiffApplier` to apply an approved code-fix diff when opening a pull request — not just a dev/CI tool here), in addition to `uv`.

```bash
uv sync                        # install dependencies (Python 3.14, see .python-version)
cp -n .env.example .env        # -n: won't clobber an existing .env — then fill in the values you need
uv run lefthook install        # one-time: activate pre-commit/pre-push git hooks
uv run pytest                  # run the test suite
uv run python main.py          # run the replay pipeline against the demo issue
```

`main.py` is resume-safe: if a run pauses for approval (a MEDIUM/HIGH-risk drafted action), it prompts interactively at the terminal for each queued action and posts whatever's approved. Re-running `uv run python main.py` while a prior run on the same issue is still paused resumes that pending approval instead of starting a duplicate run.

### Episodic memory (optional)

Set `EPISODIC_MEMORY_DATABASE_URL` in `.env` to enable it; leave unset and every node degrades to a no-op automatically. `docker compose up -d` starts a local Postgres + pgvector instance matching the DSN in `.env.example`, plus an [Adminer](https://www.adminer.org/) GUI at [localhost:8080](http://localhost:8080) to browse the `episodes` table (System: PostgreSQL, Server: `episodic-memory-db`, credentials: `triage_bot`/`triage_bot`/`triage_bot`).

```bash
docker compose up -d           # starts local pgvector-enabled Postgres + Adminer GUI
```

## Documentation

| | |
|---|---|
| **Architecture, pipeline, product vision** | [`docs/summary.md`](docs/summary.md) |
| **Engineering standards & agent operating rules** | [`AGENTS.md`](AGENTS.md) |
| **Security threat model & secrets handling** | [`docs/agent/security.md`](docs/agent/security.md) |
| **Design-pattern rationale** | [`docs/agent/engineering-standards.md`](docs/agent/engineering-standards.md) |
| **State schema & module conventions** | [`docs/agent/architecture-conventions.md`](docs/agent/architecture-conventions.md) |
| **Reporting a vulnerability** | [`SECURITY.md`](SECURITY.md) |

## Stack

LangGraph, MCP, E2B, PyGithub, Tavily, Pydantic, FastAPI, OpenTelemetry + Langfuse, Postgres.
