import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from graph.schemas import ApprovalRequest, QueuedActionSummary, RiskLevel


def make_queued_action_summary(**overrides: Any) -> QueuedActionSummary:
    defaults: dict[str, Any] = {
        "index": 0,
        "action_type": "comment",
        "summary": "Could you share a reproduction?",
        "rationale": "Not enough information to act yet.",
        "risk_level": RiskLevel.MEDIUM,
        "risk_reasoning": "Makes a claim not fully backed by evidence.",
        "risk_factors": ["assertive tone"],
    }
    defaults.update(overrides)
    return QueuedActionSummary(**defaults)


def make_approval_request(**overrides: Any) -> ApprovalRequest:
    defaults: dict[str, Any] = {
        "run_id": uuid4(),
        "repo_full_name": "octo/repo",
        "issue_number": 42,
        "issue_url": "https://github.com/octo/repo/issues/42",
        "actions": [make_queued_action_summary()],
        "requested_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ApprovalRequest(**defaults)


def test_queued_action_summary_construction() -> None:
    summary = make_queued_action_summary()
    assert summary.index == 0
    assert summary.risk_level is RiskLevel.MEDIUM
    assert summary.target_files == []
    assert summary.diff_preview is None


def test_queued_action_summary_json_round_trip() -> None:
    summary = make_queued_action_summary()
    restored = QueuedActionSummary.model_validate_json(summary.model_dump_json())
    assert restored == summary


def test_approval_request_construction() -> None:
    request = make_approval_request()
    assert len(request.actions) == 1
    assert request.issue_number == 42


def test_approval_request_json_round_trip() -> None:
    request = make_approval_request()
    restored = ApprovalRequest.model_validate_json(request.model_dump_json())
    assert restored == request


def test_approval_request_payload_is_json_serializable() -> None:
    """The `interrupt()` payload must survive `model_dump(mode="json")` ->
    `json.dumps` -- the exact path LangGraph's serde takes."""
    request = make_approval_request()
    serialized = json.dumps(request.model_dump(mode="json"))
    assert json.loads(serialized)["issue_number"] == 42
