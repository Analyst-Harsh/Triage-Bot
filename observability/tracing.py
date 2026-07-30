"""Langfuse tracing: the OpenTelemetry + Langfuse half of observability/'s
cross-cutting systems (see docs/summary.md's "Observability" section) --
`logging_config.py` already covers structured logs; this module covers the
trace/span side, degrading to a no-op when unconfigured, the same contract
`utils/episodic_memory_store.py`'s `NullEpisodicMemoryStore` uses.

A single `langfuse.langchain.CallbackHandler`, passed into the top-level
`graph.ainvoke()` call in `main.py`, is what produces the entire nested span
tree for free: LangGraph propagates that config's callbacks into every node,
every nested subgraph (the Researcher's/Drafter's own compiled
`StateGraph`s), and every LLM/tool call inside them via LangChain's own
contextvar-based config propagation -- no per-node code is required for that
structural nesting. What this module adds on top:

- `root_span`: one root span for `main()`'s whole run, bound to a
  deterministic trace ID (`create_trace_id`, seeded from `thread_id`) so the
  initial `ainvoke()` and a later interrupt/resume share one trace even
  though they're two separate calls.
- `node_span`: creates a span for one node's body (`TriageNode.__call__`,
  `AgentSubgraph.assemble_node`) so it can enrich its own span with this
  repo's own cost/token accounting, namespaced `authoritative_*` wherever
  it's attached -- deliberately distinct from Langfuse's own per-generation
  cost estimate (derived from Langfuse's own model price table, not this
  repo's litellm-based, prompt-cache-aware `llm/pricing.py::estimate_cost_usd`,
  which is what `RunMeta`'s guardrail actually enforces against -- see
  `docs/agent/architecture-conventions.md`).

  This creates its own span rather than enriching whatever span the
  `CallbackHandler` already auto-created for the same node dispatch, even
  though that seems redundant at first (a first cut of this tried exactly
  that "ambient current span" approach via `Langfuse.update_current_span`,
  and it silently attached metadata to the *wrong* span every time --
  confirmed empirically, not just in theory: LangChain's async callback
  dispatch (`langchain_core/callbacks/manager.py::ahandle_event`) fires each
  handler's `on_chain_start` via `asyncio.gather`, so the Langfuse handler's
  `context.attach()` -- the call that makes its new span "current" -- runs
  inside an isolated `asyncio.create_task`. Per Python's `contextvars`
  semantics, a mutation made inside a spawned task's context never
  propagates back to the caller once that task completes, so by the time
  `RunnableCallable.ainvoke()` (`langgraph/_internal/_runnable.py`) resumes
  and actually calls our node body, "current" still points at whatever was
  ambient *before* the callback dispatch ran -- the parent span, not the
  just-created per-node one. Holding a span object directly, created and
  updated within our own single coroutine, sidesteps this entirely: nothing
  about it depends on inheriting context across that task boundary).

Never pass a `SecretStr` object (or its resolved value) into a span/trace
attribute -- only into the `Langfuse` client constructor itself (see
`docs/agent/security.md`).
"""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager

from langfuse import Langfuse, LangfuseSpan, get_client, propagate_attributes
from langfuse.langchain import CallbackHandler
from langfuse.types import TraceContext

from config.settings import Settings

_configured = False


def ensure_langfuse_client(settings: Settings) -> None:
    """Idempotent, process-wide setup -- mirrors `logging_config.configure_logging()`'s
    `_configured` guard. Constructs the one `Langfuse` client this process
    uses (retrievable anywhere afterward via `langfuse.get_client()`, which
    resolves to it automatically since it's the only client instantiated)
    if both `settings.langfuse_public_key`/`langfuse_secret_key` are set;
    otherwise does nothing; every other function in this module then stays a
    no-op, exactly like the unset-`database_url` case degrades to
    `NullEpisodicMemoryStore`.
    """
    global _configured
    if _configured:
        return
    if settings.langfuse_public_key is None or settings.langfuse_secret_key is None:
        return
    Langfuse(
        public_key=settings.langfuse_public_key.get_secret_value(),
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_host,
    )
    _configured = True


def create_trace_id(seed: str) -> str:
    """Deterministic 32-hex-char trace ID derived from `seed` (pure hashing --
    no client/network involved, safe to call even when tracing isn't
    configured). Called with `thread_id` (repo#issue_number, already
    deterministic) so `RunMeta.trace_id` is always populated the same way for
    a given thread, ready for a future out-of-process resume to continue the
    same trace by re-deriving the identical ID from the same seed."""
    return Langfuse.create_trace_id(seed=seed)


def build_callback_handler(trace_id: str | None = None) -> CallbackHandler | None:
    """The one `CallbackHandler` instance `main.py` passes into every
    `graph.ainvoke()` call for a run -- `None` when tracing isn't configured,
    so callers pass `callbacks=[handler] if handler else []`.

    `trace_id` defaults to `None` -- the handler is constructed with no
    `trace_context`, which every current caller relies on: the handler's own
    `_take_root_trace_context` always honors an explicit `trace_context` over
    whatever's ambiently open in OTel context, which (verified against the
    installed SDK) produced a second, sibling root-level span in the same
    trace when both `root_span` and this handler were given the same
    `trace_id` explicitly -- two independent root observations tagged with
    the same trace ID, neither referencing the other as parent. With no
    `trace_context`, this handler's own root chain span instead falls
    through to normal ambient nesting and attaches under whatever
    `root_span` already opened, which is always already active by the time
    `graph.ainvoke()` fires its first callback, since `root_span` wraps that
    call -- this is `main.py`'s path today.

    Pass an explicit `trace_id` only when there is no ambient `root_span`
    open to nest under -- e.g. a future FastAPI resume-only handler that
    recovers `trace_id` from a checkpointed `RunMeta` and fires a single
    `ainvoke(Command(resume=...))` with nothing wrapping it. There, ambient
    context has nothing to offer, so binding via `trace_context` explicitly
    is the only way to keep the resume in the same trace as the original
    run -- the exact case this parameter exists for, not yet exercised by
    any caller in this codebase.
    """
    if not _configured:
        return None
    trace_context: TraceContext | None = {"trace_id": trace_id} if trace_id is not None else None
    return CallbackHandler(trace_context=trace_context)


@asynccontextmanager
async def root_span(
    *, name: str, trace_id: str, session_id: str, metadata: Mapping[str, object]
) -> AsyncGenerator[None]:
    """Wraps `main()`'s whole run in one Langfuse span bound to `trace_id`,
    with `session_id`/`metadata` attached at the trace level -- everything
    nested inside (both `graph.ainvoke()` calls, across the interrupt/resume
    boundary, plus the issue fetch and result-file write around them) shares
    this one trace. `session_id=thread_id` also groups the initial run and
    its resume together in Langfuse's own UI.

    An `@asynccontextmanager` wrapper around the SDK's own context manager,
    which is sync-only (`start_as_current_observation` returns an
    `_AgnosticContextManager` supporting `__enter__`/`__exit__` only, not the
    async dunder methods) -- a plain `with` block nests fine inside an async
    generator function, since nothing in the SDK's enter/exit does blocking
    I/O.

    A no-op `nullcontext`-equivalent when tracing isn't configured.
    """
    if not _configured:
        yield
        return
    client = get_client()
    with (
        client.start_as_current_observation(
            name=name, as_type="span", trace_context={"trace_id": trace_id}
        ),
        propagate_attributes(session_id=session_id, metadata=dict(metadata)),
    ):
        try:
            yield
        finally:
            # Buffered client-side, same as any OTel exporter -- main.py is a
            # short-lived script, so an explicit flush here (rather than
            # waiting for the background flush interval) is what guarantees
            # spans actually reach Langfuse before the process exits.
            client.flush()


@asynccontextmanager
async def node_span(name: str) -> AsyncGenerator[LangfuseSpan | None]:
    """Wraps one graph node's body in its own span, named `name` (`self.name`
    at each of this function's two call sites -- `TriageNode.__call__`,
    `AgentSubgraph.assemble_node` -- since the span name is only known
    per-instance, not at class-definition time, which is also why this is a
    plain wrapped function rather than Langfuse's own `@observe()` decorator).

    Yields the span itself so the caller can `span.update(metadata=...)`
    with its own already-computed numbers before the block exits -- see this
    module's docstring for why this creates its own span rather than
    enriching the `CallbackHandler`'s auto-created one for the same node
    dispatch. Yields `None` when tracing isn't configured -- callers must
    guard on that before calling `.update()`.
    """
    if not _configured:
        yield None
        return
    with get_client().start_as_current_observation(name=name, as_type="span") as span:
        yield span
