from typing import Any

from graph.schemas import ResearchFindings, ResearchSource


def make_findings(**overrides: Any) -> ResearchFindings:
    defaults: dict[str, Any] = {
        "summary": "The bug is caused by a missing null check.",
        "sources": [
            ResearchSource(
                source_type="codebase",
                reference="src/handlers/foo.py:42",
                snippet="if value is None: ...",
                relevance=0.9,
            )
        ],
        "code_references": ["src/handlers/foo.py"],
        "confidence": 0.8,
        "open_questions": ["Is this reproducible on the latest release?"],
    }
    defaults.update(overrides)
    return ResearchFindings(**defaults)


def test_construction() -> None:
    findings = make_findings()
    assert findings.sources[0].source_type == "codebase"


def test_json_round_trip() -> None:
    findings = make_findings()
    restored = ResearchFindings.model_validate_json(findings.model_dump_json())
    assert restored == findings
