from datetime import UTC, datetime

from graph.schemas import IssueType, PlannerOutput


def make_planner_output(**overrides) -> PlannerOutput:
    defaults = dict(
        issue_type=IssueType.BUG,
        classification_confidence=0.87,
        investigation_plan=["search codebase for related error", "check open duplicates"],
        reasoning="Stack trace matches a known exception type.",
        classified_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return PlannerOutput(**defaults)


def test_construction():
    output = make_planner_output()
    assert output.issue_type is IssueType.BUG
    assert len(output.investigation_plan) == 2


def test_json_round_trip():
    output = make_planner_output()
    restored = PlannerOutput.model_validate_json(output.model_dump_json())
    assert restored == output
