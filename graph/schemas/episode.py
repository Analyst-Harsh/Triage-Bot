from datetime import datetime
from uuid import UUID

from graph.schemas.base import StrictBaseModel
from graph.schemas.draft import DraftedAction
from graph.schemas.enums import IssueType, RiskLevel, RunStatus
from graph.schemas.post_result import PostResults


class Episode(StrictBaseModel):
    """Persisted episodic-memory record -- what `EpisodicMemoryStore.save_episode`
    writes (as `AsyncPostgresStore.aput`'s JSON `value`) and `find_similar`
    reads back. Never enters `TriageState`/the checkpointer; it's a
    store-layer record, not graph state.

    `run_id` doubles as the store's item key (`str(run_id)`), so a
    re-executed node (e.g. after an at-least-once resume) upserts the same
    row rather than writing a duplicate episode for the same run.
    """

    run_id: UUID
    repo_full_name: str
    issue_number: int
    issue_summary: str
    issue_type: IssueType
    issue_text: str
    """The `title\\n\\nbody` text `EpisodicMemoryStore.save_episode` tells
    `AsyncPostgresStore` to embed (`index=["issue_text"]`) -- distinct from
    `issue_summary` (title only), which is what shows up in a retrieved
    `EpisodicMemoryHit`'s display text."""
    actions_taken: list[DraftedAction]
    risk_levels: list[RiskLevel]
    post_results: PostResults | None = None
    outcome: RunStatus
    created_at: datetime
