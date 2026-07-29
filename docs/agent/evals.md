# Eval suite (`evals/`)

Triage Bot's own evals — judging whether the agent's classification, research, and drafted actions are actually *good*, not just schema-valid. Complements the test suite (`tests/`), which proves the code doesn't crash; this proves the agent's judgment is trustworthy.

## Scope, this pass

Three eval types: **E2E** (final-outcome correctness/coherence), **Researcher** (trajectory quality/groundedness), **Drafter** (groundedness/tone). Each gets both a hand-labeled (deterministic, golden-dataset) check set and an LLM-judge (rubric, no ground truth needed) check set.

**Explicit not-now follow-ups** — deliberately out of scope, not silently missing:
- Planner and Risk-check node evals.
- Calibration eval (does `classification_confidence`/`ResearchSummary.confidence` actually predict correctness).
- Episodic-memory ablation eval (does retrieved memory context measurably improve outcomes).
- CI wiring/gating — this is a manual/on-demand CLI tool only.
- Writing eval scores back to Langfuse (`client.api.scores`) — considered during design, cut as an unverified API surface with no explicit ask behind it.
- Content-level injection-leak detection in graders — `#16`'s golden case (system-prompt extraction) was verified clean by a one-off manual script inspecting the reconstructed draft/trajectory, not by a repeatable automated grader assertion. There's no `GraderCheck` today that scans drafted comment/PR text for leaked internal-prompt content.
- A minimum-risk-level assertion for LLM-judged `comment`/`close` actions — `GoldenCase.expected_max_risk_level` is an upper-bound-only check (nothing exceeds it); there's no way to assert a risk level is *at least* some floor. `#15`'s golden case is the concrete example: its `close` action was independently confirmed (via `reconstruct.build_run`) to be rated `MEDIUM` with reasoning that explicitly names the issue's injected fake content as untrustworthy, but that's not something this suite can regression-test today.
- Full sandbox tool-call-log inspection for tool-misuse-bait cases — `#17`'s golden case was confirmed clean (the injected shell "provisioning" text never appears inside an `install_dependencies`/`run_tests` call argument, only in the initial human message carrying the raw issue body as context) by a one-off manual trajectory scan this pass, not a wired-up grader check.

## Data flow: Langfuse only, never `results/*.json`

`results/*.json` (gitignored, replay-pipeline-only) cannot contain what this suite needs: the Researcher's/Drafter's raw tool-calling trajectory lives only in their private `AgentLoopState.messages` channel (`graph/nodes/agent_subgraph.py`), which never propagates into `TriageState` and therefore never reaches a result file. Langfuse's `CallbackHandler` auto-instruments every node dispatch and every LLM/tool call inside that loop, so it's the only place with the full picture.

A `GoldenCase` (`evals/schemas/golden_case.py`) stores only `repo_full_name`/`issue_number` — never a run_id or trace_id. `evals/langfuse_fetch/client.py::resolve_trace_id()` re-derives `thread_id = f"{repo}#{issue_number}"` then `trace_id = create_trace_id(thread_id)`, the same deterministic derivation `graph/state.py::create_initial_state` uses for a real run. This means **a trace can (and does) hold more than one historical run attempt** for the same issue — every `main()` invocation against that issue, across however many dev/replay sessions, lands in the same trace_id. Every reconstruction function picks the *latest* matching observation by `startTime`.

### The confirmed observation-tree shape

Verified empirically against real traces (not assumed from docs):

- The auto-instrumented **top-level graph invocation** is a `CHAIN` named `"LangGraph"` whose parent is the root `SPAN` this repo's own `observability.tracing.root_span` creates, named `"triage_run"`. That `CHAIN`'s `output` **is the complete final `TriageState` dict** — `issue`, `planner_output`, `research_findings`, `draft`, `risk_assessment`, `post_results`, `status`, `run_meta`, every one of them already in the exact shape `graph.schemas`' real Pydantic models validate. `evals/langfuse_fetch/reconstruct.py::build_run()` finds the latest such chain and `model_validate`s straight into those real schemas (`ReconstructedRun`) — no hand-rolled projection.
- The per-node `CHAIN` observations named `"researcher"`/`"drafter"` (same auto-instrumentation, nested under the run's top-level chain) carry the full `AgentLoopState` at that node's end, including `messages` — the raw trajectory. Each message dict is a flat `model_dump()` of a real `langchain_core.messages` object (`{"type": "ai", "tool_calls": [{"name","args","id","type":"tool_call"}], ...}`, already LangChain-native, not OpenAI's shape). `reconstruct.py::message_from_dict()` is a simple `type`-keyed dispatch back to the matching message class — not a hand-rolled field adapter.
- **Interrupt/resume matters for trajectory reconstruction.** A resume is its own, later top-level `"LangGraph"` chain (same trace, later `startTime`) — but it never re-runs Researcher/Drafter. `build_trajectory()` deliberately does **not** scope to the winning (latest) top-level chain's id; it searches for the latest same-named node `CHAIN` anywhere in the trace, so a resume-only invocation still finds the trajectory from the earlier invocation that actually ran that node.
- Two real API quirks, easy to get wrong: `input`/`output` are always raw JSON-encoded **strings** on this SDK version (`parse_io_as_json` was removed server-side — confirmed via a live 400) — always `json.loads()` them. Pagination is **cursor-based** (`ObservationsV2Meta.cursor: str | None`, no `page`/`limit`/`total_items`).
- A naming collision that turned out harmless: the auto-instrumented `CHAIN` for the whole Researcher/Drafter subgraph invocation and this repo's own manually-created `SPAN` (`node_span`, metadata-only, wraps just `assemble_node`) share the same name (e.g. `"researcher"`) but sit in two entirely separate parent chains — filtering on `type` alone disambiguates them.

### Not every issue that was ever replayed has usable trace data

`RunMeta.trace_id` is always populated (it's a pure hash of `thread_id`), **regardless of whether Langfuse was actually configured for that run** — a real-looking `trace_id` in an old `results/*.json` file is not proof tracing was live for it. Confirmed directly: of the handful of distinct `(repo, issue_number)` pairs backing this repo's 27 replay result files, one (`arrow-py/arrow#1278`, the arrow `dehumanize()` bug) has **zero** observations under its trace_id — none of its replay runs were ever actually traced. There is nothing to fix in `reconstruct.py` for that; there's no data to fetch. A `GoldenCase` can only ever reference an issue that was actually run with Langfuse configured.

## Local cache (`evals/cache_store.py`)

Free-tier Langfuse retention is ~2 months; a `TraceCache` sits in front of every fetch so eval runs don't depend on Langfuse still holding a historical trace. `evals/.cache/{trace_id}.json` (gitignored), one file per trace, storing **only** the verbatim raw fetch (`CachedTraceData.raw_observations`) — `ReconstructedRun`/`ReconstructedTrajectory` are recomputed fresh from that every time, never persisted, since reconstruction is a pure, in-memory, no-I/O computation. A `reconstruct.py` bug fix or logic change takes effect immediately on the next run with no cache-invalidation step. `get_or_fetch(trace_id, fetch)` is the one entry point every grader/CLI path uses; `fetch` is a thunk so a cache hit costs zero Langfuse API calls.

## Judges (`evals/judges/`)

`judge_chat_model()` (`evals/judges/model.py`) uses **Anthropic**, deliberately a different provider than this app's own OpenAI-based nodes (Planner/RiskCheck/Researcher/Drafter) — a judge sharing the same model family as the thing it grades risks correlated blind spots, the same concern `docs/agent/security.md` raises about an LLM-based injection check grading its own manipulated output.

Two call shapes:
- **Rubric judges** (`e2e_judge.py`, `researcher_judge.py::run_researcher_groundedness_judge`, `drafter_judge.py::run_drafter_groundedness_judge`/`run_drafter_tone_judge`) reuse `llm.structured.call_structured` against a small `JudgeRubricOutput` schema — the same primitive every graph node's LLM call goes through.
- **`agentevals` trajectory judge** (`researcher_judge.py::run_researcher_efficiency_judge`, `drafter_judge.py::run_drafter_efficiency_judge`) uses `agentevals.trajectory.llm.create_async_trajectory_llm_as_judge`, passing `judge=` (a real `BaseChatModel`) — never `model=` (a bare string, which `agentevals` would resolve itself via its own `init_chat_model`/raw env vars, bypassing `Settings` entirely). `DrafterSubgraph` is architecturally identical to `ResearcherSubgraph` (same `AgentSubgraph` tool-calling loop — see `graph/nodes/drafter.py`'s class docstring), so the same efficiency rubric (did the loop proceed without redundant/looping calls) applies unchanged; `_run_drafter_case` in `cli.py` builds the Drafter's `ReconstructedTrajectory` unconditionally whenever judges are enabled, the same way `_run_researcher_case` does.

`evals.graders.researcher_grader` deliberately does **not** use `agentevals`' trajectory *match* evaluators, even though the package is installed for exactly this kind of use: `GoldenCase.expected_researcher_tool_subset` is a bare list of tool *names*, not a full reference trajectory with matching arguments, which is what `agentevals`' match evaluators actually compare against. The hand-labeled check is instead a plain set-containment check over `ToolCallRecord.tool_name`.

Every judge prompt (`evals/judges/prompts/`) includes the same "untrusted data, not instructions" framing sentence `prompts/researcher.py`/`prompts/drafter.py` already use for tool output — judge inputs (drafted comments, evidence, issue text) are downstream of the same untrusted issue content those nodes already treat as a threat surface (`docs/agent/security.md`).

## Golden dataset (`evals/golden/cases.py`)

Five cases currently, all from `Analyst-Harsh/triage-bot-test` (the only issues with clean, fully-resolvable traces found during authoring — see the "not every issue" section above for why `arrow-py/arrow#1278` isn't one of them, and why `#1` from the same test repo was also excluded: its trace has orphaned root spans from what looks like an earlier tracing setup, not a clean case to build a golden expectation on). More cases to be added as more issues get run with tracing configured.

`#9` is the first genuine spam/abuse case (filling the gap noted below under "Explicit not-now follow-ups" for prompt-injection, though this one is content-based spam, not injection) — it exercises `SpamCloseNode`'s current behavior: unlike the old `SpamRejectedNode`, a spam classification now produces a one-action `close` draft and routes to `approval_queue` for human sign-off, rather than short-circuiting with no draft at all. That required two fixes: `evals/graders/e2e_grader.py::_check_spam_short_circuit` now checks `research_findings is None` (Researcher never ran) instead of `draft is None`, and `evals/cli.py::_run_selected` skips the `researcher`/`drafter` eval types entirely for a case with `expected_spam_short_circuit=True`, since there's no trajectory to reconstruct when those nodes never ran.

`#12`-`#17` are the first `issue_category="prompt_injection"` cases — six real, distinct adversarial issues (`Analyst-Harsh/triage-bot-test#12`-`#17`), each embedding a genuine injection payload inside an otherwise-legitimate bug/feature report, mapped to the OWASP LLM Top 10 (2025): instruction override (`#12`, LLM01), fake authority/impersonation (`#13`, LLM01), structured-output schema manipulation (`#14`, LLM01), delimiter confusion (`#15`, LLM01), system-prompt extraction (`#16`, LLM07), and tool-misuse bait (`#17`, LLM06). Full per-technique detail and the defense mechanism each one exercises: `docs/agent/security.md`'s "Red-team validation" section. All six pass today (`uv run python -m evals.cli run e2e --case-id <id> --no-judge`). What the grader actually catches is worth being precise about: `expected_issue_type`/`forbidden_action_types` catch classification-level and action-type-level manipulation (`#12`, `#14`); `code_fix` risk (`#12`-`#14`, `#16`-`#17`) is hardcoded `HIGH` by fixed policy in `RiskCheckNode` regardless of input, so there's no LLM judgment call to test there — `#13`'s "auto-post without review" bait targets a decision that structurally doesn't exist. `#15` is the one case whose `close` action goes through the real LLM-judged risk path; `#16` and `#17` were confirmed clean by one-off manual scripts against the reconstructed trace data (not automated grader checks) — see the three new gaps below.

## Running it

```
uv run python -m evals.cli fetch-cache --all
uv run python -m evals.cli run all --all              # hand-labeled + LLM judges
uv run python -m evals.cli run e2e --all --no-judge    # hand-labeled only, no LLM spend
uv run python -m evals.cli run drafter --case-id <id> --json
```

Every subcommand resolves `Settings` via `get_settings()` once at startup and fails fast if Langfuse credentials are unset, before any cache-miss fetch is attempted — same convention as `scripts/verify_langfuse_metadata.py`.
