from langchain_core.prompts import ChatPromptTemplate

from graph.schemas.issue import IssuePayload
from graph.schemas.memory import EpisodicMemoryHit

PLANNER_SYSTEM_PROMPT = """You are the triage planner for an automated GitHub issue triage bot.

You will be given a single GitHub issue (title, body, author, labels). Your \
job is classification, not open-ended reasoning: assign the issue to \
exactly one of the following categories, and outline what an investigation \
of it should check next.

Categories:
- bug: a report that existing, released functionality is broken or behaving \
incorrectly.
- feature_request: a request for new functionality that does not exist yet.
- question: the author is asking how to use something, not reporting a defect.
- documentation: the issue is about missing, unclear, or incorrect docs.
- duplicate: the issue restates a problem or request that is a well-known, \
recurring topic (you cannot see other open issues directly, so only use \
this when the issue text itself references or clearly matches a known \
duplicate pattern).
- needs_more_info: the report is too vague or incomplete to act on without \
the author providing more detail (e.g. no repro steps, no version, no \
error message).
- spam_or_abuse: not a genuine issue — spam, advertising, or abusive content.
- other: does not fit any category above.

Also provide:
- classification_confidence: your confidence in this classification, from \
0.0 to 1.0.
- investigation_plan: a short list of concrete things a researcher should \
check next (e.g. "search codebase for the referenced function", "check \
whether this reproduces on the latest release"). Empty if no further \
investigation is warranted (e.g. spam_or_abuse).
- reasoning: a brief explanation for why you chose this category.
"""

PLANNER_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", PLANNER_SYSTEM_PROMPT),
        ("human", "{issue_text}\n\n{episodic_context_text}"),
    ]
)


def format_issue_for_prompt(issue: IssuePayload) -> str:
    labels = ", ".join(issue.labels) if issue.labels else "(none)"
    return (
        f"Repository: {issue.repo_full_name}\n"
        f"Issue #{issue.issue_number}\n"
        f"Title: {issue.title}\n"
        f"Author: {issue.author} (association: {issue.author_association or 'NONE'})\n"
        f"Existing labels: {labels}\n\n"
        f"Body:\n{issue.body}"
    )


def format_episodic_context_for_prompt(hits: list[EpisodicMemoryHit]) -> str:
    """Renders a short "similar past issues" section from the top-k
    episodic-memory hits -- 2-3 one-line summaries, not a wall of history.
    Empty string (no section at all) when there's no memory yet."""
    if not hits:
        return ""
    lines = [
        f"- Issue #{hit.past_issue_number} in {hit.past_repo} "
        f"(similarity {hit.similarity_score:.2f}): {hit.summary} "
        f"— action(s): {_format_actions_taken(hit)}; outcome: {hit.outcome.value}"
        for hit in hits
    ]
    return "Similar past issues and how they were handled:\n" + "\n".join(lines)


def _format_actions_taken(hit: EpisodicMemoryHit) -> str:
    """e.g. "comment (posted), label (rejected)" -- pairs each action type
    with what actually happened to it, not just what was proposed."""
    return ", ".join(
        f"{action.action_type.value} ({action.outcome.value})" for action in hit.actions_taken
    )
