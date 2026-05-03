"""
Agent components — декомпозиция монолитного AIAgent на независимые модули.

Каждый компонент отвечает за одну область ответственности и может быть
протестирован изолированно.
"""

from .budget_tracker import BudgetTracker
from .session_manager import SessionManager
from .credential_resolver import CredentialResolver
from .tool_dispatcher import ToolDispatcher, ToolCall, ToolResult
from .message_builder import MessageBuilder

__all__ = [
    "BudgetTracker",
    "SessionManager",
    "CredentialResolver",
    "ToolDispatcher",
    "ToolCall",
    "ToolResult",
    "MessageBuilder",
]
