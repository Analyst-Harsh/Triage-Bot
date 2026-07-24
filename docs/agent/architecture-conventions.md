# Architecture & module conventions — full detail

The detailed state-schema architecture and the module layout / testing / typing conventions that `AGENTS.md` points to. For the pipeline/vision level (why two entry points, the five-step pipeline, what makes it "production"), see `docs/summary.md` — this doc is one level more concrete: it's about how the code implementing that vision is organized.

## Architecture: state schema (`graph/state.py`, `graph/schemas/`)

The data contract every graph node reads and writes, and what the Postgres checkpointer persists between steps:

- Top-level `TriageState` is a `TypedDict` (LangGraph-native, checkpointer-friendly). Every nested slot (`IssuePayload`, `PlannerOutput`, `ResearchFindings`, `DraftOutput`, `RiskAssessment`, `EpisodicMemoryHit`, `RunMeta`) is a Pydantic `BaseModel` for real validation. Nodes construct/validate the Pydantic model, then write it into the TypedDict slot on their partial-update return.
- `TriageState` has **no top-level `messages` key**. Tool-calling nodes (the Researcher, and any future node built the same way, e.g. a Drafter code-fix loop) are `AgentSubgraph`s (`graph/nodes/agent_subgraph.py`), each with its own **private** `messages` channel on its own `AgentLoopState` — absent from `TriageState`, so it starts empty every run and never propagates to the parent. This superseded an earlier design (top-level `messages` shared across nodes for "free" tracing): once the Researcher became a genuine nested `StateGraph`, that subgraph's own checkpoint namespace and OTel/Langfuse traces already carry the full trajectory, so sharing a top-level channel only bought cross-node scoping ambiguity and an ever-growing log re-serialized into every later checkpoint, for no added observability. Nodes still hand off typed contracts only (`PlannerOutput` → `ResearchFindings`, never raw message history); `ResearchFindings.tool_calls: list[ToolCallRecord]` is the typed, programmatically-derived distillation of a trajectory that downstream nodes actually consume.
- Draft actions (`graph/schemas/actions.py`) are a Pydantic discriminated union on `action_type` (`CommentAction` / `LabelAction` / `CloseAction` / `CodeFixAction`) rather than one loosely-typed dict, so an incomplete or mismatched action fails validation instead of silently producing a half-filled action. This design also functions as a prompt-injection mitigation — see `docs/agent/security.md`.
- Guardrail counters (`iteration_count`, `tool_calls_made`, `estimated_cost_usd`, `max_iterations`, `max_cost_usd`) live in `RunMeta`, since LangGraph's built-in `recursion_limit` caps graph steps but not $ spend.
- `episodic_context: list[EpisodicMemoryHit]` holds only the current run's retrieved matches — the actual episodic memory store (Postgres/pgvector) is future work, not part of this schema.
- Both entry points (webhook and replay) construct state identically via `graph.state.create_initial_state()` — don't duplicate init logic between them.

## Module layout convention

One Pydantic model (or tightly related pair, e.g. `RunError`/`RunMeta`) per file under `graph/schemas/`, all re-exported from `graph/schemas/__init__.py`. Follow this pattern for any new schema additions rather than growing an existing file or importing from the submodule directly.

## Testing convention

`tests/graph/` mirrors the `graph/` layout. Every schema has a construction test and a JSON round-trip test (`model_dump_json` → `model_validate_json`). The discriminated union additionally has dispatch and rejection tests. `tests/graph/test_state.py` round-trips full `TriageState` instances through LangGraph's own `langgraph.checkpoint.serde.jsonplus.JsonPlusSerializer` (`dumps_typed`/`loads_typed`) — this is the check that actually matters, since it proves state survives what the Postgres checkpointer will do to it in production, not just that individual models validate. Any new state field should get this same round-trip coverage, not just a unit test of the field in isolation.

## Typing convention

`pyright` runs in `strict` mode across the **whole project** (`include = ["."]`, not an allowlist of specific paths — new code under `api/`/`tools/` gets checked automatically without touching config) (Pydantic v2's native `dataclass_transform` support means no plugin is needed, unlike mypy). `reportMissingTypeStubs` is disabled in `[tool.pyright]` — that check is about third-party library stub completeness (e.g. `langgraph`'s submodules have inconsistent `py.typed` coverage), not our own code's type coverage, so it's not worth failing strict mode over. Every function needs a return type annotation (including `-> None` for tests), and helper functions that accept arbitrary override kwargs (the `make_*(**overrides: Any) -> Model` pattern used throughout `tests/graph/schemas/`) type them as `**overrides: Any` with an explicit `dict[str, Any]` for the defaults — don't leave `**kwargs` unannotated.

## Adding a new top-level source directory

If you start putting code in a currently-empty directory (`api/`, `tools/`), nothing needs to change in `[tool.pyright]` or `[tool.ruff]` — both already scan the whole project by default and only exclude `.venv`/`__pycache__`/dot-directories.
