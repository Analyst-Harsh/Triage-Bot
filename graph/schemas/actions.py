from typing import Annotated, Literal

from pydantic import BaseModel, Field


class SandboxResult(BaseModel):
    passed: bool
    logs: str
    test_command: str
    duration_seconds: float


class CommentAction(BaseModel):
    action_type: Literal["comment"] = "comment"
    comment_body: str


class LabelAction(BaseModel):
    action_type: Literal["label"] = "label"
    labels_to_add: list[str] = []
    labels_to_remove: list[str] = []


class CloseAction(BaseModel):
    action_type: Literal["close"] = "close"
    reason: str
    close_comment: str | None = None


class CodeFixAction(BaseModel):
    action_type: Literal["code_fix"] = "code_fix"
    diff: str
    target_files: list[str]
    sandbox_result: SandboxResult


DraftAction = Annotated[
    CommentAction | LabelAction | CloseAction | CodeFixAction,
    Field(discriminator="action_type"),
]
