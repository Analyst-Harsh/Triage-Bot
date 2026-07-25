from datetime import UTC, datetime

from graph.schemas import (
    DIFF_PREVIEW_MAX_BYTES,
    ActionType,
    ApprovalRequest,
    CloseAction,
    CodeFixAction,
    CommentAction,
    DraftOutput,
    IssuePayload,
    LabelAction,
    QueuedActionSummary,
    RiskAssessment,
    RunMeta,
)


class ApprovalRequestBuilder:
    """Builds the `interrupt()` payload (`ApprovalRequest`) `ApprovalQueueNode`
    surfaces for human review -- one `QueuedActionSummary` per queued
    (non-LOW-risk) drafted action. Groups the per-action summarization and
    diff-truncation logic that would otherwise be a handful of loose module
    functions passing a shared byte cap around by hand.
    """

    def __init__(self, *, diff_preview_max_bytes: int = DIFF_PREVIEW_MAX_BYTES) -> None:
        self._diff_preview_max_bytes = diff_preview_max_bytes

    def build(
        self,
        issue: IssuePayload,
        draft: DraftOutput,
        risk_assessment: RiskAssessment,
        run_meta: RunMeta,
        queued_indices: list[int],
    ) -> ApprovalRequest:
        """Builds the request for exactly the queued indices -- the caller
        (`ApprovalQueueNode`) is responsible for identifying which
        positions in `draft.actions` are actually `PostOutcome.QUEUED`."""
        if not queued_indices:
            raise ValueError("ApprovalRequestBuilder.build requires at least one queued index")

        summaries: list[QueuedActionSummary] = []
        for index in queued_indices:
            drafted = draft.actions[index]
            assessment = risk_assessment.action_assessments[index]
            (
                summary,
                target_files,
                sandbox_passed,
                sandbox_test_command,
                diff_preview,
                truncated,
            ) = self._summarize_action(drafted.action)
            summaries.append(
                QueuedActionSummary(
                    index=index,
                    action_type=ActionType(drafted.action.action_type),
                    summary=summary,
                    rationale=drafted.rationale,
                    risk_level=assessment.level,
                    risk_reasoning=assessment.reasoning,
                    risk_factors=assessment.risk_factors,
                    target_files=target_files,
                    sandbox_passed=sandbox_passed,
                    sandbox_test_command=sandbox_test_command,
                    diff_preview=diff_preview,
                    diff_truncated=truncated,
                )
            )

        return ApprovalRequest(
            run_id=run_meta.run_id,
            repo_full_name=issue.repo_full_name,
            issue_number=issue.issue_number,
            issue_url=issue.url,
            actions=summaries,
            requested_at=datetime.now(UTC),
        )

    def _summarize_action(
        self, action: CommentAction | LabelAction | CloseAction | CodeFixAction
    ) -> tuple[str, list[str], bool | None, str | None, str | None, bool]:
        """Returns `(summary, target_files, sandbox_passed,
        sandbox_test_command, diff_preview, diff_truncated)` -- the
        code-fix-only fields are `None`/`[]`/`False` for every other
        action type."""
        match action:
            case CommentAction():
                body = action.comment_body.strip()
                summary = body if len(body) <= 200 else f"{body[:200]}…"
                return summary, [], None, None, None, False
            case LabelAction():
                parts = [f"+{label}" for label in action.labels_to_add]
                parts += [f"-{label}" for label in action.labels_to_remove]
                summary = ", ".join(parts) if parts else "No label changes"
                return summary, [], None, None, None, False
            case CloseAction():
                return f"Close issue: {action.reason}", [], None, None, None, False
            case CodeFixAction():
                count = len(action.target_files)
                summary = f"Code fix touching {count} file{'' if count == 1 else 's'}"
                diff_preview, diff_truncated = self._truncate_diff(action.diff)
                return (
                    summary,
                    action.target_files,
                    action.sandbox_result.passed,
                    action.sandbox_result.test_command,
                    diff_preview,
                    diff_truncated,
                )

    def _truncate_diff(self, diff: str) -> tuple[str, bool]:
        encoded = diff.encode("utf-8")
        if len(encoded) <= self._diff_preview_max_bytes:
            return diff, False

        truncated_bytes = encoded[: self._diff_preview_max_bytes]
        # A preview only -- the full diff is always retained in state -- so
        # silently dropping a partial multi-byte char at the cut boundary is
        # an acceptable tradeoff for keeping this a plain byte-length cap.
        truncated_text = truncated_bytes.decode("utf-8", errors="ignore")
        marker = (
            f"\n… [diff truncated: showing {len(truncated_bytes)} of {len(encoded)} "
            "bytes; full diff retained in run state]"
        )
        return truncated_text + marker, True
