# Triage Bot

[![CI](https://github.com/Analyst-Harsh/Triage-Bot/actions/workflows/bi_frost.yml/badge.svg)](https://github.com/Analyst-Harsh/Triage-Bot/actions/workflows/bi_frost.yml)
[![Coverage](https://raw.githubusercontent.com/Analyst-Harsh/Triage-Bot/python-coverage-comment-action-data/badge.svg)](https://github.com/Analyst-Harsh/Triage-Bot/tree/python-coverage-comment-action-data)

A LangGraph-based agent that triages GitHub issues. A live webhook and a replay pipeline of backfilled OSS issues both feed the same pipeline — **Planner → Researcher → Drafter → Risk check → Auto-post/Approval queue** — with every outcome logged to episodic memory, checkpointed via Postgres, and traced via OpenTelemetry + Langfuse.

The project is early-stage: the state schema (`graph/schemas/`, `graph/state.py`) is implemented and tested; the graph nodes, FastAPI webhook/replay entry points (`api/`), and agent tools (`tools/`) are still being built.

## Quickstart

```bash
uv sync                        # install dependencies (Python 3.14, see .python-version)
cp -n .env.example .env        # -n: won't clobber an existing .env — then fill in the values you need
uv run lefthook install        # one-time: activate pre-commit/pre-push git hooks
uv run pytest                  # run the test suite
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
