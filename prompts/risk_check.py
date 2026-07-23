from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate

from graph.schemas.draft import DraftOutput
from graph.schemas.research import ResearchFindings
from prompts.drafter import public_facing_text

RISK_CHECK_SYSTEM_PROMPT = """You are the risk-judgment pass for an automated GitHub \
issue triage bot. Some drafted actions have already been resolved by fixed policy before \
reaching you -- label changes are always low-risk, and code fixes always require human \
review regardless of how the fix looks. Your job is only to judge the remaining actions: \
comments and issue closes.

For each action shown to you, decide:
- low: a routine, low-stakes comment or close -- factual, appropriately hedged, nothing \
an author could reasonably be upset by if it turned out wrong.
- medium: a substantive comment (makes a strong or consequential claim) or a close that \
isn't obviously uncontroversial.
- high: a comment making an assertive claim on thin or no evidence, a tone that could \
read as dismissive, or a close whose grounds are genuinely ambiguous.

Judge only the text that would actually be posted to GitHub -- never the internal \
rationale, which is not public-facing and not what you're being asked to grade. Give a \
reasoning and, when not low, the specific risk_factors driving that level (e.g. \
"unsupported claim", "assertive tone", "irreversible close"). You must return exactly \
one judgment for every action_index shown to you, in any order.
"""

RISK_CHECK_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", RISK_CHECK_SYSTEM_PROMPT),
        (
            "human",
            "Actions to judge:\n{actions_text}\n\n"
            "Overall rationale for this draft: {overall_rationale}\n"
            "Unsupported claims flagged by the independent grounding check: "
            "{unsupported_claims}\n"
            "Research confidence: {confidence}",
        ),
    ]
)


def format_judged_actions_for_prompt(draft: DraftOutput, judged_indices: list[int]) -> str:
    lines: list[str] = []
    for index in judged_indices:
        text = public_facing_text(draft.actions[index].action)
        lines.append(f"[action_index={index}] {text}")
    return "\n\n".join(lines)


def build_risk_judgment_messages(
    draft: DraftOutput,
    research_findings: ResearchFindings | None,
    judged_indices: list[int],
) -> list[BaseMessage]:
    unsupported_claims = (
        ", ".join(draft.unsupported_claims) if draft.unsupported_claims else "(none)"
    )
    confidence = (
        f"{research_findings.confidence:.2f}" if research_findings else "(no research findings)"
    )
    return RISK_CHECK_PROMPT.format_messages(
        actions_text=format_judged_actions_for_prompt(draft, judged_indices),
        overall_rationale=draft.overall_rationale,
        unsupported_claims=unsupported_claims,
        confidence=confidence,
    )
