from enum import StrEnum


class NodeName(StrEnum):
    """Canonical graph node identifiers. Used as `add_node()` keys,
    `TriageNode.name` values, and `route_by_risk()`'s routing targets, so a
    node's name is a single symbol shared everywhere it's referenced instead
    of a string literal repeated at each call site."""

    PLANNER = "planner"
    RESEARCHER = "researcher"
    DRAFTER = "drafter"
    RISK_CHECK = "risk_check"
    AUTO_POST = "auto_post"
    APPROVAL_QUEUE = "approval_queue"
