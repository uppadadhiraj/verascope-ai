"""Import every model so Base.metadata is fully populated for Alembic
autogenerate and for `Base.metadata.create_all` in tests."""
from app.models.agent_run import AgentRun, ToolCall
from app.models.approval import Approval
from app.models.code_change import CodeChange
from app.models.conversation import Conversation
from app.models.dependency import RepositoryDependency
from app.models.file import RepositoryFile
from app.models.finding import Finding
from app.models.message import Message
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.symbol import RepositorySymbol
from app.models.task import Task, TaskStep
from app.models.test_run import TestRun
from app.models.user import User

__all__ = [
    "AgentRun",
    "ToolCall",
    "Approval",
    "CodeChange",
    "Conversation",
    "RepositoryDependency",
    "RepositoryFile",
    "Finding",
    "Message",
    "PullRequest",
    "Repository",
    "RepositorySymbol",
    "Task",
    "TaskStep",
    "TestRun",
    "User",
]
