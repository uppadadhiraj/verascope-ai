"""All enums shared across models, schemas and agents.

Centralized so the Planner/Debugger/Validation status vocab (section 21, 23,
37 of the spec) stays consistent everywhere it's referenced.
"""
from __future__ import annotations

import enum


class RepositoryStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLONING = "CLONING"
    SCANNING = "SCANNING"
    PARSING = "PARSING"
    EMBEDDING = "EMBEDDING"
    SUMMARIZING = "SUMMARIZING"
    READY = "READY"
    FAILED = "FAILED"


class RepositorySourceType(str, enum.Enum):
    GITHUB = "GITHUB"
    ZIP = "ZIP"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class StepStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class TaskType(str, enum.Enum):
    CHAT = "CHAT"
    DEBUG = "DEBUG"
    FEATURE = "FEATURE"
    SECURITY_SCAN = "SECURITY_SCAN"
    GENERAL = "GENERAL"


class EvidenceStatus(str, enum.Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    HYPOTHESIZED = "HYPOTHESIZED"
    VERIFIED = "VERIFIED"
    INSUFFICIENT = "INSUFFICIENT"


class AgentRunStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentName(str, enum.Enum):
    ORCHESTRATOR = "orchestrator"
    PLANNER = "planner"
    REPOSITORY = "repository"
    DEBUGGER = "debugger"
    SECURITY = "security"
    TEST = "test"
    FIX = "fix"
    REVIEW = "review"
    VALIDATION = "validation"


class RelationshipType(str, enum.Enum):
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"
    USES = "USES"
    DEPENDS_ON = "DEPENDS_ON"
    EXPOSES = "EXPOSES"
    READS_FROM = "READS_FROM"
    WRITES_TO = "WRITES_TO"


class FindingSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class ChangeType(str, enum.Enum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"


class ChangeLifecycleState(str, enum.Enum):
    """Distinguishes PROPOSED / APPLIED / TESTED / VALIDATED (section 37) --
    these must never be conflated."""

    PROPOSED = "PROPOSED"
    APPLIED = "APPLIED"
    TESTED = "TESTED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"


class TestRunStatus(str, enum.Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class ApprovalType(str, enum.Enum):
    CODE_CHANGE = "CODE_CHANGE"
    GIT_OPERATION = "GIT_OPERATION"
    PR_CREATION = "PR_CREATION"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


class PullRequestStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    BRANCH_CREATED = "BRANCH_CREATED"
    COMMITTED = "COMMITTED"
    PUSHED = "PUSHED"
    PR_CREATED = "PR_CREATED"
    FAILED = "FAILED"
