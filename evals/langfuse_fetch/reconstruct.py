import json
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import JsonValue

from evals.schemas import ReconstructedRun, ReconstructedTrajectory
from graph.nodes.node_names import NodeName
from graph.nodes.trajectory import derive_tool_call_records, resolve_dangling_tool_calls
from graph.schemas import (
    DraftOutput,
    IssuePayload,
    PlannerOutput,
    PostResults,
    ResearchFindings,
    RiskAssessment,
    RunMeta,
    RunStatus,
)

# Confirmed against a real trace (see docs/agent/evals.md): the auto-instrumented
# top-level graph invocation is a CHAIN named "LangGraph" whose parent is the
# root SPAN this repo's own `observability.tracing.root_span` creates, named
# "triage_run". Its `output` is the complete final `TriageState` dict for one
# full `main()` invocation.
_ROOT_SPAN_NAME = "triage_run"
_TOP_LEVEL_CHAIN_NAME = "LangGraph"

_MESSAGE_CLASSES: dict[str, type[BaseMessage]] = {
    "human": HumanMessage,
    "ai": AIMessage,
    "tool": ToolMessage,
    "system": SystemMessage,
}


def _as_observation_dict(observation: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(observation, dict):
        raise ValueError(f"expected an observation dict, got {type(observation)}")
    return observation


def _parse_json_field(value: JsonValue) -> Any:
    """`input`/`output` are always raw JSON-encoded strings on this SDK
    version (confirmed -- see `raw_fetch.fetch_all_observations`); `None`
    when the observation has no such field (e.g. a SPAN, which this repo's
    own `node_span` never attaches input/output to)."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"expected a JSON-encoded string, got {type(value)}")
    return json.loads(value)


def _start_time(observation: dict[str, JsonValue]) -> str:
    # "startTime" is in the API's "core" field group, always present --
    # confirmed via ObservationV2's required (non-Optional) start_time field.
    return cast(str, observation["startTime"])


def _latest_by_start_time(observations: list[dict[str, JsonValue]]) -> dict[str, JsonValue]:
    return max(observations, key=_start_time)


def _find_top_level_langgraph_chain(
    observations: list[dict[str, JsonValue]],
) -> dict[str, JsonValue]:
    """The single `CHAIN` observation named 'LangGraph' whose parent is the
    root `triage_run` SPAN. A trace can hold more than one of these --
    thread_id/trace_id are deterministic per-issue, so every historical
    `main()` invocation against the same issue lands in the same trace --
    always picks the latest by `startTime`, i.e. the most recent time this
    issue was actually run (an initial run, or its most recent resume)."""
    by_id = {cast(str, obs["id"]): obs for obs in observations}
    candidates: list[dict[str, JsonValue]] = []
    for obs in observations:
        if obs.get("type") != "CHAIN" or obs.get("name") != _TOP_LEVEL_CHAIN_NAME:
            continue
        parent_id = obs.get("parentObservationId")
        parent = by_id.get(parent_id) if isinstance(parent_id, str) else None
        if parent is not None and parent.get("name") == _ROOT_SPAN_NAME:
            candidates.append(obs)
    if not candidates:
        raise ValueError(
            "no top-level 'LangGraph' CHAIN observation found under a 'triage_run' "
            "root span in this trace -- this run may not have had Langfuse tracing "
            "configured, or ingestion hasn't caught up yet"
        )
    return _latest_by_start_time(candidates)


def build_run(observations: list[JsonValue]) -> ReconstructedRun:
    """Reconstructs the final-state view of the most recent run attempt in
    `observations` (one trace_id's full raw fetch). Every field validates
    directly against the real `graph.schemas` objects -- the winning
    top-level chain's `output` already *is* the complete final `TriageState`
    dict, confirmed empirically against a real trace."""
    obs_dicts = [_as_observation_dict(obs) for obs in observations]
    top_level = _find_top_level_langgraph_chain(obs_dicts)
    state = _parse_json_field(top_level["output"])
    return ReconstructedRun(
        issue=IssuePayload.model_validate(state["issue"]),
        planner_output=(
            PlannerOutput.model_validate(state["planner_output"])
            if state.get("planner_output") is not None
            else None
        ),
        research_findings=(
            ResearchFindings.model_validate(state["research_findings"])
            if state.get("research_findings") is not None
            else None
        ),
        draft=(
            DraftOutput.model_validate(state["draft"]) if state.get("draft") is not None else None
        ),
        risk_assessment=(
            RiskAssessment.model_validate(state["risk_assessment"])
            if state.get("risk_assessment") is not None
            else None
        ),
        post_results=(
            PostResults.model_validate(state["post_results"])
            if state.get("post_results") is not None
            else None
        ),
        run_meta=RunMeta.model_validate(state["run_meta"]),
        status=RunStatus(state["status"]),
    )


def message_from_dict(message: dict[str, Any]) -> BaseMessage:
    """Each message dict is a flat `model_dump()` of a real
    `langchain_core.messages` object (confirmed against a real trace) --
    reconstruction is a simple `type`-keyed dispatch back to the matching
    class, not a hand-rolled field-shape adapter."""
    message_type = message.get("type")
    if not isinstance(message_type, str):
        raise ValueError(f"message missing a string 'type' field: {message!r}")
    message_class = _MESSAGE_CLASSES.get(message_type)
    if message_class is None:
        raise ValueError(f"unrecognized message type {message_type!r}")
    return message_class.model_validate(message)


def build_trajectory(
    observations: list[JsonValue], *, node_name: NodeName
) -> ReconstructedTrajectory:
    """Reconstructs the raw tool-calling trajectory for one `AgentSubgraph`
    node (Researcher or Drafter) from the latest same-named CHAIN
    observation anywhere in `observations` -- deliberately NOT scoped to the
    winning top-level 'LangGraph' chain `build_run` picks. Confirmed against
    a real trace with an interrupt/resume: the *latest* top-level chain is
    often the resume invocation (ApprovalQueue onward), which never re-runs
    Researcher/Drafter at all -- those nodes only ran under the earlier,
    *initial* invocation of the same overall run. Scoping strictly to the
    winning top-level chain's id would then find nothing, even though the
    trajectory is right there, one top-level chain earlier in the same
    trace. Picking the latest same-named node CHAIN across the whole trace
    correctly follows a resume back to where the node actually ran.

    Reuses this repo's own `graph.nodes.trajectory.resolve_dangling_tool_calls`/
    `derive_tool_call_records` on the reconstructed messages rather than
    reimplementing tool-call extraction."""
    obs_dicts = [_as_observation_dict(obs) for obs in observations]
    candidates = [
        obs
        for obs in obs_dicts
        if obs.get("type") == "CHAIN" and obs.get("name") == node_name.value
    ]
    if not candidates:
        raise ValueError(
            f"no {node_name.value!r} CHAIN observation found anywhere in this "
            "trace -- this node may not have run for this issue (e.g. a "
            "spam-rejected run never reaches Researcher/Drafter)"
        )
    node_chain = _latest_by_start_time(candidates)
    state = _parse_json_field(node_chain["output"])
    raw_messages = cast(list[dict[str, Any]], state["messages"])
    messages = resolve_dangling_tool_calls([message_from_dict(m) for m in raw_messages])
    tool_call_records = derive_tool_call_records(messages)
    return ReconstructedTrajectory(
        node_name=node_name,
        messages=[m.model_dump(mode="json") for m in messages],
        tool_call_records=tool_call_records,
    )
