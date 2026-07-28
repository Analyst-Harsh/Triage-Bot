from typing import Annotated, Literal

from pydantic import Field

from graph.schemas.base import StrictBaseModel


class SandboxResult(StrictBaseModel):
    passed: bool
    logs: str
    test_command: str
    duration_seconds: float


class CommentAction(StrictBaseModel):
    action_type: Literal["comment"] = "comment"
    comment_body: str


class LabelAction(StrictBaseModel):
    action_type: Literal["label"] = "label"
    labels_to_add: list[str] = Field(default_factory=list[str])
    labels_to_remove: list[str] = Field(default_factory=list[str])


class CloseAction(StrictBaseModel):
    action_type: Literal["close"] = "close"
    reason: str
    close_comment: str | None = None


class CodeFixAction(StrictBaseModel):
    action_type: Literal["code_fix"] = "code_fix"
    diff: str
    target_files: list[str]
    sandbox_result: SandboxResult
    base_commit_sha: str  # real GitHub SHA the tarball was fetched at
    base_ref: str  # the branch/SHA originally requested


class CodeFixIntent(StrictBaseModel):
    """Signals intent to attempt a code fix. Carries no diff, target_files,
    or sandbox_result fields — those are always filled in from the
    sandbox's own recorded result, never by you. Do not try to supply them.

    `extra="forbid"` (inherited from `StrictBaseModel`) closes the gap where
    Pydantic would otherwise silently drop unknown fields: a model emitting
    a full CodeFixAction-shaped payload (diff/target_files/sandbox_result/...)
    alongside action_type="code_fix" would validate successfully with those
    fields quietly discarded, rather than being rejected outright.
    finalize() builds the real CodeFixAction from the sandbox's own recorded
    SandboxAttempts, never from anything the model supplies here."""

    action_type: Literal["code_fix"] = "code_fix"


DraftAction = Annotated[
    CommentAction | LabelAction | CloseAction | CodeFixAction,
    Field(discriminator="action_type"),
]

DraftIntent = Annotated[
    CommentAction | LabelAction | CloseAction | CodeFixIntent,
    Field(discriminator="action_type"),
]
"""Everything the Drafter LLM may propose. Replaces NonCodeDraftAction."""
