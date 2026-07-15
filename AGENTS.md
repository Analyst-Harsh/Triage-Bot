# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.

## Engineering standards (default — applies without being asked)

This is a production-grade repository, not a prototype or demo. Every change defaults to production-grade engineering, regardless of how the request is phrased — "production grade" does not need to be said in a prompt for it to apply here.

- **Design patterns over raw/ad-hoc code.** When an established pattern fits, use it instead of hand-rolling something bespoke. This codebase already commits to specific patterns — follow them rather than introducing a competing style:
  - Discriminated unions for polymorphic data (`graph/schemas/actions.py`'s `DraftAction`), not loosely-typed dicts with optional fields for every variant.
  - A typed contract at every boundary (Pydantic models in/out of graph nodes, the `TriageState` TypedDict as the single source of truth for graph state) — see **Architecture** below.
  - Factory functions for non-trivial construction (`create_initial_state()`) instead of duplicating init logic at each call site.
  - One model/responsibility per file, re-exported from a package `__init__.py` (see **Module layout convention** below) — not one large file accumulating unrelated classes.
- **Validate at boundaries, trust internals.** Pydantic models validate anything crossing a node, API, or serialization boundary. Don't re-validate the same data deeper in business logic once it's already a validated model.
- **Type-complete by default.** Every function gets a real return type annotation; strict `pyright` passing is the bar, not an aspiration. Avoid `Any` as a shortcut — it's acceptable only where genuinely unavoidable (e.g. heterogeneous test-fixture kwargs, see **Typing convention**), and only with the same explicit, deliberate annotation used there.
- **Tests are part of the definition of done**, not a follow-up task. New schemas/models get the same coverage shape as existing ones (construction + JSON round-trip at minimum; full checkpoint-serde round-trip for anything touching `TriageState` — see **Testing convention**).
- **Lint, format, and type-check clean before considering work finished.** These are enforced by git hooks (see `lefthook.yml` below), but don't treat the hook as the first line of defense — run `ruff check .` / `ruff format --check .` / `pyright` yourself and fix what they find as part of doing the work, not as a separate cleanup pass.
- **No silent shortcuts.** No "TODO: fix later," no swallowed exceptions, no disabled lint/type rules to make something pass — if a rule genuinely shouldn't apply, say why inline (see the `S101`/`tests/**` and `reportMissingTypeStubs` precedents below) rather than blanket-disabling it.
- **When there's more than one way to build something, pick the one a senior engineer shipping this to production would pick** — not the one that's fastest to type out. If that's a nontrivial judgment call, it's worth a sentence of reasoning in the code (a comment) or the commit, not just a silent choice.

## Project overview

Triage Bot is a LangGraph-based agent that triages GitHub issues. Full architecture and vision live in `docs/summary.md` (read it before making cross-cutting design decisions) — treat it as the source of truth for the intended pipeline and stack, not this file.

In one line: two entry points (a live GitHub webhook and a replay pipeline of backfilled OSS issues) feed the same LangGraph pipeline — Planner → Researcher → Drafter → Risk check → Auto-post/Approval queue — with every outcome logged to episodic memory, checkpointed via Postgres, and traced via OpenTelemetry + Langfuse.

Current state: the project is early. The state schema (`graph/schemas/`, `graph/state.py`) is implemented and tested. The graph nodes themselves, the FastAPI webhook/replay entry points (`api/`), and agent tools (`tools/`) are not yet built — those directories currently exist but are empty.

## Commands

This project uses `uv` for dependency management (Python 3.14, see `.python-version`).

```bash
uv sync                    # install/update dependencies
uv run python main.py      # run the app entrypoint
uv run pytest              # run the full test suite (tests/ is the default testpath)
uv run pytest -v           # verbose
uv run pytest tests/graph/test_state.py::test_checkpoint_serde_round_trip_on_initial_state  # run a single test
uv run ruff format .        # format the whole project
uv run ruff format --check . # check formatting without changing files (what pre-push runs)
uv run ruff check .         # lint (see rule set below)
uv run ruff check . --fix   # lint and auto-fix what's safely fixable
uv run pyright              # type check (strict mode, whole-project — see [tool.pyright] in pyproject.toml)
uv run lefthook install     # one-time: activate the git hooks (must be run manually per clone, uv doesn't do this automatically)
uv run lefthook run pre-commit  # run the pre-commit hook set manually against staged files
uv run lefthook run pre-push     # run the pre-push hook set manually against the whole project
```

Any new code should pass `ruff format --check .`, `ruff check .`, and `pyright` cleanly — all three are configured in `pyproject.toml` (`[tool.ruff]`/`[tool.ruff.lint]`/`[tool.ruff.format]`, `[tool.pyright]`) and currently pass on the full codebase.

**Ruff lint rule set**: beyond flake8-equivalent (`E`/`W`/`F`) plus `I`/`UP`/`B`/`C4`, also enabled: `N` (naming), `S` (bandit security — relevant since this bot processes untrusted issue text and will execute sandboxed code fixes), `SIM` (simplify), `RUF` (ruff-specific), `PT` (pytest style), `DTZ` (no naive datetimes — matches the `datetime.now(UTC)` convention already used everywhere), `ASYNC` (for when FastAPI handlers land), `ARG` (unused arguments), `PERF`, `TID` (tidy imports). `S101` (assert) is ignored under `tests/**` via `per-file-ignores` since assert is idiomatic pytest, not a security concern there.

**Git hooks (`lefthook.yml`)**: `pre-commit` runs `ruff format` → `ruff check --fix` → `pyright`, scoped to staged files only, auto-fixing and re-staging what it can (`stage_fixed: true`) — kept fast and low-friction for every commit. `pre-push` re-runs format/lint/type-check across the **whole project** in check-only mode (no auto-fix — a push shouldn't silently rewrite files) plus the full `pytest` suite — this is the safety net that catches anything a staged-files-only pre-commit could miss (e.g. a change that breaks type-checking in a file you didn't touch).

## Architecture

**State schema (`graph/state.py`, `graph/schemas/`)** — the data contract every future graph node reads and writes, and what the Postgres checkpointer persists between steps:

- Top-level `TriageState` is a `TypedDict` (LangGraph-native, checkpointer-friendly). Every nested slot (`IssuePayload`, `PlannerOutput`, `ResearchFindings`, `DraftOutput`, `RiskAssessment`, `EpisodicMemoryHit`, `RunMeta`) is a Pydantic `BaseModel` for real validation. Nodes construct/validate the Pydantic model, then write it into the TypedDict slot on their partial-update return.
- `messages: Annotated[list[BaseMessage], add_messages]` lives at top-level state (not hidden in a subgraph) so the Researcher's tool-calling loop (codebase/DocMind/web/MCP search) gets free step-by-step tracing — this is what trajectory evals need.
- Draft actions (`graph/schemas/actions.py`) are a Pydantic discriminated union on `action_type` (`CommentAction` / `LabelAction` / `CloseAction` / `CodeFixAction`) rather than one loosely-typed dict, so an incomplete or mismatched action fails validation instead of silently producing a half-filled action.
- Guardrail counters (`iteration_count`, `tool_calls_made`, `estimated_cost_usd`, `max_iterations`, `max_cost_usd`) live in `RunMeta`, since LangGraph's built-in `recursion_limit` caps graph steps but not $ spend.
- `episodic_context: list[EpisodicMemoryHit]` holds only the current run's retrieved matches — the actual episodic memory store (Postgres/pgvector) is future work, not part of this schema.
- Both future entry points (webhook and replay) should construct state identically via `graph.state.create_initial_state()` — don't duplicate init logic between them.

**Module layout convention**: one Pydantic model (or tightly related pair, e.g. `RunError`/`RunMeta`) per file under `graph/schemas/`, all re-exported from `graph/schemas/__init__.py`. Follow this pattern for any new schema additions rather than growing an existing file or importing from the submodule directly.

**Testing convention** (`tests/graph/`, mirrors `graph/` layout): every schema has a construction test and a JSON round-trip test (`model_dump_json` → `model_validate_json`). The discriminated union additionally has dispatch and rejection tests. `tests/graph/test_state.py` round-trips full `TriageState` instances through LangGraph's own `langgraph.checkpoint.serde.jsonplus.JsonPlusSerializer` (`dumps_typed`/`loads_typed`) — this is the check that actually matters, since it proves state survives what the Postgres checkpointer will do to it in production, not just that individual models validate. Any new state field should get this same round-trip coverage, not just a unit test of the field in isolation.

**Typing convention**: `pyright` runs in `strict` mode across the **whole project** (`include = ["."]`, not an allowlist of specific paths — new code under `api/`/`tools/` gets checked automatically without touching config) (Pydantic v2's native `dataclass_transform` support means no plugin is needed, unlike mypy). `reportMissingTypeStubs` is disabled in `[tool.pyright]` — that check is about third-party library stub completeness (e.g. `langgraph`'s submodules have inconsistent `py.typed` coverage), not our own code's type coverage, so it's not worth failing strict mode over. Every function needs a return type annotation (including `-> None` for tests), and helper functions that accept arbitrary override kwargs (the `make_*(**overrides: Any) -> Model` pattern used throughout `tests/graph/schemas/`) type them as `**overrides: Any` with an explicit `dict[str, Any]` for the defaults — don't leave `**kwargs` unannotated.

**If you add a new top-level source directory** (e.g. start putting code in `api/` or `tools/`), nothing needs to change in `[tool.pyright]` or `[tool.ruff]` — both already scan the whole project by default and only exclude `.venv`/`__pycache__`/dot-directories.
