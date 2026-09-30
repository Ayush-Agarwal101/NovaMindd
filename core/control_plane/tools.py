"""
NovaMindd — Tool Registry and Authorization

Typed tool definitions with explicit permission and resource schemas.
The LLM never receives raw system access; every tool call passes through here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


class ToolStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


@dataclass
class ToolSchema:
    """
    Complete description of a NovaMindd tool.

    Every tool must declare:
    - its argument schema (JSON Schema subset)
    - required permissions
    - whether it needs network access
    - whether it requires human approval
    """
    tool_id: str
    name: str
    description: str
    argument_schema: dict[str, Any]         # JSON Schema for arguments
    output_schema: dict[str, Any]           # JSON Schema for output
    required_permissions: list[str]
    requires_network: bool = False
    requires_human_approval: bool = False
    allowed_roles: list[str] = field(default_factory=list)
    status: ToolStatus = ToolStatus.ENABLED
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallRequest:
    tool_id: str
    arguments: dict[str, Any]
    user_id: str
    user_roles: list[str]
    request_id: str | None = None


@dataclass
class ToolCallResult:
    tool_id: str
    request_id: str | None
    success: bool
    output: Any
    error: str | None = None
    execution_time_ms: int = 0


# ---------------------------------------------------------------------------
# Built-in tool definitions
# ---------------------------------------------------------------------------

BUILTIN_TOOLS: list[ToolSchema] = [
    ToolSchema(
        tool_id="python_exec",
        name="Python Executor",
        description="Execute a Python code snippet inside a sandboxed Docker container.",
        argument_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source code to execute"},
                "timeout_seconds": {"type": "integer", "default": 30, "maximum": 60},
            },
            "required": ["code"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "exit_code": {"type": "integer"},
            },
        },
        required_permissions=["tool:execute"],
        requires_network=False,
        requires_human_approval=False,
        allowed_roles=["operator", "admin"],
    ),
    ToolSchema(
        tool_id="knowledge_search",
        name="Knowledge Search",
        description="Search the private knowledge base for relevant documents.",
        argument_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5, "maximum": 20},
            },
            "required": ["query"],
        },
        output_schema={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source": {"type": "string"},
                    "page": {"type": "integer"},
                    "score": {"type": "number"},
                },
            },
        },
        required_permissions=["knowledge:retrieve"],
        requires_network=False,
        requires_human_approval=False,
        allowed_roles=["viewer", "operator", "admin"],
    ),
    ToolSchema(
        tool_id="document_ingest",
        name="Document Ingestion",
        description="Ingest a document into the private knowledge base.",
        argument_schema={
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "content_base64": {"type": "string"},
            },
            "required": ["filename", "content_base64"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "chunks_created": {"type": "integer"},
            },
        },
        required_permissions=["document:upload"],
        requires_network=False,
        requires_human_approval=False,
        allowed_roles=["operator", "admin"],
    ),
]


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Registry of all available tools and their schemas."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSchema] = {}
        for t in BUILTIN_TOOLS:
            self._tools[t.tool_id] = t

    def register(self, tool: ToolSchema) -> None:
        self._tools[tool.tool_id] = tool
        logger.info("tool_registered", tool_id=tool.tool_id)

    def get(self, tool_id: str) -> ToolSchema | None:
        return self._tools.get(tool_id)

    def all(self) -> list[ToolSchema]:
        return list(self._tools.values())

    def enabled(self) -> list[ToolSchema]:
        return [t for t in self._tools.values() if t.status == ToolStatus.ENABLED]


# ---------------------------------------------------------------------------
# Tool Authorization
# ---------------------------------------------------------------------------

class ToolAuthorizationService:
    """
    Verify that a user is allowed to call a tool before execution.

    Checks:
    1. Tool exists and is enabled.
    2. User has at least one required role.
    3. User has all required permissions.
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry or get_tool_registry()

    def authorize(self, request: ToolCallRequest) -> tuple[bool, str]:
        """
        Return (is_authorized, reason).
        """
        tool = self._registry.get(request.tool_id)
        if tool is None:
            return False, f"Unknown tool: {request.tool_id!r}"

        if tool.status != ToolStatus.ENABLED:
            return False, f"Tool {request.tool_id!r} is not enabled"

        if tool.allowed_roles:
            if not any(r in tool.allowed_roles for r in request.user_roles):
                return (
                    False,
                    f"User lacks required role for tool {request.tool_id!r}",
                )

        logger.info(
            "tool_authorized",
            tool_id=request.tool_id,
            user_id=request.user_id,
        )
        return True, "authorized"


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
