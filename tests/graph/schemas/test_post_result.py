from datetime import UTC, datetime
from typing import Any

from graph.schemas import ActionPostResult, PostOutcome, PostResults


def make_action_post_result(**overrides: Any) -> ActionPostResult:
    defaults: dict[str, Any] = {
        "outcome": PostOutcome.POSTED,
        "detail": "https://github.com/octo/repo/issues/42#issuecomment-1",
    }
    defaults.update(overrides)
    return ActionPostResult(**defaults)


def make_post_results(**overrides: Any) -> PostResults:
    defaults: dict[str, Any] = {
        "action_results": [make_action_post_result()],
        "evaluated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PostResults(**defaults)


def test_action_post_result_construction() -> None:
    result = make_action_post_result()
    assert result.outcome is PostOutcome.POSTED
    assert result.detail == "https://github.com/octo/repo/issues/42#issuecomment-1"


def test_action_post_result_detail_defaults_to_none() -> None:
    result = make_action_post_result(outcome=PostOutcome.QUEUED, detail=None)
    assert result.detail is None


def test_action_post_result_json_round_trip() -> None:
    result = make_action_post_result()
    restored = ActionPostResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_post_results_construction() -> None:
    results = make_post_results()
    assert len(results.action_results) == 1
    assert results.action_results[0].outcome is PostOutcome.POSTED


def test_post_results_json_round_trip() -> None:
    results = make_post_results()
    restored = PostResults.model_validate_json(results.model_dump_json())
    assert restored == results


def test_post_results_with_multiple_action_results() -> None:
    results = make_post_results(
        action_results=[
            make_action_post_result(outcome=PostOutcome.POSTED, detail="url"),
            make_action_post_result(outcome=PostOutcome.QUEUED, detail=None),
            make_action_post_result(outcome=PostOutcome.FAILED, detail="boom"),
        ]
    )
    assert [r.outcome for r in results.action_results] == [
        PostOutcome.POSTED,
        PostOutcome.QUEUED,
        PostOutcome.FAILED,
    ]
