from datetime import UTC, datetime
from typing import Any

from graph.schemas import Evidence, ResearchFindings, ResearchSummary, ToolCallRecord


def make_evidence(**overrides: Any) -> Evidence:
    defaults: dict[str, Any] = {
        "source_type": "github",
        "reference": "https://github.com/octo/repo/pull/7",
        "snippet": "Fixed by adding a null check.",
        "relevance": 0.9,
        "sha": "abc123",
    }
    defaults.update(overrides)
    return Evidence(**defaults)


def make_tool_call_record(**overrides: Any) -> ToolCallRecord:
    defaults: dict[str, Any] = {
        "tool_name": "search_code",
        "arguments": {"query": "NoneType"},
        "status": "success",
    }
    defaults.update(overrides)
    return ToolCallRecord(**defaults)


def make_research_summary(**overrides: Any) -> ResearchSummary:
    defaults: dict[str, Any] = {
        "summary": "The bug is caused by a missing null check.",
        "evidence": [make_evidence()],
        "focus_addressed": ["search codebase for NoneType"],
        "gaps": ["Could not confirm on the latest release."],
        "confidence": 0.8,
    }
    defaults.update(overrides)
    return ResearchSummary(**defaults)


def make_findings(**overrides: Any) -> ResearchFindings:
    defaults: dict[str, Any] = {
        "summary": "The bug is caused by a missing null check.",
        "evidence": [make_evidence()],
        "focus_addressed": ["search codebase for NoneType"],
        "gaps": [],
        "confidence": 0.8,
        "tool_calls": [make_tool_call_record()],
        "tools_used": ["github"],
        "researched_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ResearchFindings(**defaults)


def test_evidence_construction() -> None:
    evidence = make_evidence()
    assert evidence.source_type == "github"
    assert evidence.sha == "abc123"


def test_evidence_json_round_trip() -> None:
    evidence = make_evidence()
    restored = Evidence.model_validate_json(evidence.model_dump_json())
    assert restored == evidence


def test_evidence_sha_defaults_to_none_for_web_sources() -> None:
    evidence = make_evidence(source_type="web", sha=None)
    assert evidence.sha is None


def test_tool_call_record_construction() -> None:
    record = make_tool_call_record()
    assert record.tool_name == "search_code"
    assert record.status == "success"


def test_tool_call_record_json_round_trip() -> None:
    record = make_tool_call_record()
    restored = ToolCallRecord.model_validate_json(record.model_dump_json())
    assert restored == record


def test_research_summary_construction() -> None:
    summary = make_research_summary()
    assert summary.evidence[0].source_type == "github"


def test_research_summary_json_round_trip() -> None:
    summary = make_research_summary()
    restored = ResearchSummary.model_validate_json(summary.model_dump_json())
    assert restored == summary


def test_findings_construction() -> None:
    findings = make_findings()
    assert findings.evidence[0].source_type == "github"
    assert findings.tools_used == ["github"]


def test_findings_json_round_trip() -> None:
    findings = make_findings()
    restored = ResearchFindings.model_validate_json(findings.model_dump_json())
    assert restored == findings
