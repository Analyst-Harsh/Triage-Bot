from enum import StrEnum


class NodeName(StrEnum):
    """Canonical graph node identifiers. Used as `add_node()` keys,
    `TriageNode.name` values, and `route_after_auto_post()`'s routing
    targets (see `graph/builder.py`), so a node's name is a single symbol
    shared everywhere it's referenced instead of a string literal repeated
    at each call site."""

    PLANNER = "planner"
    SPAM_CLOSE = "spam_close"
    RESEARCHER = "researcher"
    DRAFTER = "drafter"
    RISK_CHECK = "risk_check"
    AUTO_POST = "auto_post"
    APPROVAL_QUEUE = "approval_queue"
