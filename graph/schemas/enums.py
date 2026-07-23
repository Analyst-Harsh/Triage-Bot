from enum import StrEnum


class IssueSource(StrEnum):
    WEBHOOK = "webhook"
    REPLAY = "replay"


class IssueType(StrEnum):
    BUG = "bug"
    FEATURE_REQUEST = "feature_request"
    QUESTION = "question"
    DOCUMENTATION = "documentation"
    DUPLICATE = "duplicate"
    NEEDS_MORE_INFO = "needs_more_info"
    SPAM_OR_ABUSE = "spam_or_abuse"
    OTHER = "other"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionType(StrEnum):
    COMMENT = "comment"
    LABEL = "label"
    CLOSE = "close"
    CODE_FIX = "code_fix"


class RunStatus(StrEnum):
    RECEIVED = "received"
    PLANNING = "planning"
    RESEARCHING = "researching"
    DRAFTING = "drafting"
    RISK_CHECK = "risk_check"
    AUTO_POSTED = "auto_posted"
    PENDING_APPROVAL = "pending_approval"
    APPROVED_AND_POSTED = "approved_and_posted"
    REJECTED = "rejected"
    FAILED = "failed"


class PostOutcome(StrEnum):
    POSTED = "posted"
    FAILED = "failed"
    QUEUED = "queued"
