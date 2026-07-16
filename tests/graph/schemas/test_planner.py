from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from graph.schemas import IssueType, PlannerClassification, PlannerOutput


def make_planner_output(**overrides: Any) -> PlannerOutput:
    defaults: dict[str, Any] = {
        "issue_type": IssueType.BUG,
        "classification_confidence": 0.87,
        "investigation_plan": ["search codebase for related error", "check open duplicates"],
        "reasoning": "Stack trace matches a known exception type.",
        "classified_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return PlannerOutput(**defaults)


def make_planner_classification(**overrides: Any) -> PlannerClassification:
    defaults: dict[str, Any] = {
        "issue_type": IssueType.BUG,
        "classification_confidence": 0.87,
        "investigation_plan": ["search codebase for related error", "check open duplicates"],
        "reasoning": "Stack trace matches a known exception type.",
    }
    defaults.update(overrides)
    return PlannerClassification(**defaults)


def test_construction() -> None:
    output = make_planner_output()
    assert output.issue_type is IssueType.BUG
    assert len(output.investigation_plan) == 2


def test_json_round_trip() -> None:
    output = make_planner_output()
    restored = PlannerOutput.model_validate_json(output.model_dump_json())
    assert restored == output


def test_classification_construction() -> None:
    classification = make_planner_classification()
    assert classification.issue_type is IssueType.BUG
    assert len(classification.investigation_plan) == 2


def test_classification_json_round_trip() -> None:
    classification = make_planner_classification()
    restored = PlannerClassification.model_validate_json(classification.model_dump_json())
    assert restored == classification


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_classification_confidence_out_of_bounds_rejected(confidence: float) -> None:
    with pytest.raises(ValidationError):
        make_planner_classification(classification_confidence=confidence)


@pytest.mark.parametrize("confidence", [0.0, 1.0])
def test_classification_confidence_boundary_values_accepted(confidence: float) -> None:
    classification = make_planner_classification(classification_confidence=confidence)
    assert classification.classification_confidence == confidence
