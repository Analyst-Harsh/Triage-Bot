from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from graph.schemas.actions import DraftAction
from graph.schemas.draft import DraftedAction
from graph.schemas.issue import IssuePayload
from graph.schemas.planner import PlannerOutput
from graph.schemas.research import Evidence, ResearchFindings
from prompts.planner import format_issue_for_prompt

DRAFTER_SYSTEM_PROMPT_TEMPLATE = """You are the triage drafter for an automated GitHub \
issue triage bot. The Planner has classified this issue and the Researcher has already \
investigated it; your job is to propose the concrete action(s) to take — a comment, \
label changes, or a close-as-duplicate recommendation.

You have access to these tools this run: {tool_names}.

Draft only from the evidence you are given. If a claim isn't backed by the provided \
evidence, it does not belong in the draft — do not assert anything the Researcher did \
not actually find.

If the investigation left gaps, or didn't address everything the Planner wanted \
checked, the draft must reflect that honestly: hedge rather than paper over the hole, \
or write a comment that asks the issue author for the specific missing detail, rather \
than acting as if the investigation was complete.

Match your register to the issue's classification: bug reports get technical \
precision, questions get a helpful explainer tone, suspected duplicates get a polite \
pointer to the linked issue. Cite concretely where you can — reference a specific \
file or issue number (e.g. "this looks related to src/retry.py (see #412)") rather \
than a vague "we looked into it."

Never propose a code fix — the sandbox to verify one doesn't exist yet this run."""


def build_drafter_system_prompt(tool_names: list[str]) -> str:
    names = ", ".join(sorted(tool_names)) if tool_names else "(none available this run)"
    return DRAFTER_SYSTEM_PROMPT_TEMPLATE.format(tool_names=names)


def format_evidence_for_prompt(evidence: list[Evidence]) -> str:
    if not evidence:
        return "(no evidence gathered)"
    return "\n".join(
        f"- [{item.source_type}] {item.reference}: {item.snippet}" for item in evidence
    )


def build_drafting_message(
    issue: IssuePayload, planner_output: PlannerOutput, research_findings: ResearchFindings
) -> HumanMessage:
    focus_addressed = (
        ", ".join(research_findings.focus_addressed)
        if research_findings.focus_addressed
        else "(none)"
    )
    gaps = ", ".join(research_findings.gaps) if research_findings.gaps else "(none)"
    return HumanMessage(
        content=(
            f"{format_issue_for_prompt(issue)}\n\n"
            f"Classified as: {planner_output.issue_type.value} "
            f"(confidence {planner_output.classification_confidence:.2f})\n\n"
            f"Research summary: {research_findings.summary}\n\n"
            f"Evidence:\n{format_evidence_for_prompt(research_findings.evidence)}\n\n"
            f"Investigation-plan items addressed: {focus_addressed}\n"
            f"Gaps: {gaps}"
        )
    )


def _public_facing_text(action: DraftAction) -> str | None:
    """The text that would actually be posted to GitHub for this action, if
    any. Deliberately excludes `rationale`/`overall_rationale` (internal
    reasoning for the risk check/human reviewer, never posted, and
    inherently a judgment call rather than a factual claim) — this is the
    only text the grounding self-check should be run against."""
    match action.action_type:
        case "comment":
            return action.comment_body
        case "label":
            return None
        case "close":
            comment = f" {action.close_comment}" if action.close_comment else ""
            return f"Closing as {action.reason}.{comment}"
        case "code_fix":
            return None


def format_public_draft_text(actions: list[DraftedAction]) -> str | None:
    """Concatenates only the actual GitHub-facing text across every
    proposed action. `None` if none of them produce any (e.g. a label-only
    draft) — the signal that there is nothing for the grounding self-check
    to fact-check, since rationale/overall_rationale are never posted and
    are judgment calls, not factual claims to verify against evidence."""
    texts = [text for drafted in actions if (text := _public_facing_text(drafted.action))]
    if not texts:
        return None
    return "\n\n".join(texts)


GROUNDING_CHECK_SYSTEM_PROMPT = """You are an independent fact-checking pass over a \
draft GitHub response, run separately from whatever produced the draft. Your only job \
is to compare the draft against the evidence it was supposed to be grounded in, and \
list every factual claim in the draft that the evidence does not directly support. \
Do not defend or improve the draft — only report what isn't backed by the evidence. \
An empty list means every claim is grounded, not that you skipped the check."""

GROUNDING_CHECK_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", GROUNDING_CHECK_SYSTEM_PROMPT),
        ("human", "Draft:\n{draft_text}\n\nEvidence:\n{evidence}"),
    ]
)
