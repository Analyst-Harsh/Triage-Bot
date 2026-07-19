from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, JsonValue

ResearchToolName = Literal["docmind", "github", "web"]


class Evidence(BaseModel):
    """One citation backing a research finding. `sha` is populated whenever
    the source naturally carries a git blob/commit SHA (GitHub commits/PRs,
    DocMind's codebase index) — that's the "SHA-stamped" traceability
    guarantee: a citation still points at the exact code/commit even if the
    file changes later. `None` for web results, or when a tool result
    doesn't expose one."""

    source_type: ResearchToolName
    reference: str = Field(description="Where this came from, e.g. a file path, PR/issue URL.")
    snippet: str = Field(description="The relevant excerpt, verbatim from the source.")
    relevance: float = Field(ge=0.0, le=1.0)
    sha: str | None = Field(
        default=None, description="Git blob/commit SHA, copied verbatim from the tool output."
    )


class ToolCallRecord(BaseModel):
    """One tool invocation actually made during the research loop. Derived
    programmatically from the trajectory's `AIMessage.tool_calls` /
    `ToolMessage` pairs — never asked of the model, since self-reported
    bookkeeping is a hallucination risk the model has no reason to get
    exactly right."""

    tool_name: str
    arguments: dict[str, JsonValue]
    status: Literal["success", "error"]


class ResearchSummary(BaseModel):
    """The LLM-facing contract: what the Researcher asks the model to
    produce after the tool-calling loop ends. Field `description=`s double
    as the model's instructions, same as `PlannerClassification`."""

    summary: str = Field(description="What was found, in plain language.")
    evidence: list[Evidence] = Field(
        default=[],
        description=(
            "Citations backing the summary. Copy `sha` values verbatim from "
            "tool outputs when present; omit if the source has none."
        ),
    )
    focus_addressed: list[str] = Field(
        default=[],
        description="Which items from the investigation plan were actually covered.",
    )
    gaps: list[str] = Field(
        default=[],
        description=(
            "Investigation-plan items that could not be addressed, and why "
            "(e.g. a tool was unavailable, results were inconclusive)."
        ),
    )
    confidence: float = Field(ge=0.0, le=1.0)


class ResearchFindings(BaseModel):
    """Persisted research output. `tool_calls`/`tools_used`/`researched_at`
    are system-derived (see `ToolCallRecord`) rather than LLM-authored — the
    same two-stage split `PlannerOutput` uses over `PlannerClassification`.

    `tools_used` is the actual tool *function* names invoked (e.g.
    `"search_code"`, `"list_commits"`) — not `ResearchToolName`: a single MCP
    server exposes many differently-named tools, so there's no clean
    many-to-one mapping down to "docmind"/"github"/"web". `Evidence.
    source_type` is the field that carries that higher-level categorization,
    as a judgment call the model itself makes per citation."""

    summary: str
    evidence: list[Evidence] = []
    focus_addressed: list[str] = []
    gaps: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    tool_calls: list[ToolCallRecord] = []
    tools_used: list[str] = []
    researched_at: datetime
