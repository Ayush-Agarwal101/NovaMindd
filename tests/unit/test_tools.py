"""
Tests — Tool Authorization

Verifies that the tool authorization layer correctly allows/rejects calls.
"""
from __future__ import annotations

import pytest

from core.control_plane.tools import (
    ToolAuthorizationService,
    ToolCallRequest,
    ToolRegistry,
    ToolSchema,
    ToolStatus,
)


def _registry_with_python_exec() -> ToolRegistry:
    registry = ToolRegistry()
    return registry  # python_exec is a builtin


def _req(tool_id: str, roles: list[str]) -> ToolCallRequest:
    return ToolCallRequest(
        tool_id=tool_id,
        arguments={},
        user_id="user-1",
        user_roles=roles,
    )


def test_operator_can_call_python_exec():
    svc = ToolAuthorizationService(_registry_with_python_exec())
    ok, reason = svc.authorize(_req("python_exec", ["operator"]))
    assert ok is True


def test_viewer_cannot_call_python_exec():
    svc = ToolAuthorizationService(_registry_with_python_exec())
    ok, reason = svc.authorize(_req("python_exec", ["viewer"]))
    assert ok is False
    assert "role" in reason.lower()


def test_unknown_tool_denied():
    svc = ToolAuthorizationService(_registry_with_python_exec())
    ok, reason = svc.authorize(_req("nonexistent_tool", ["admin"]))
    assert ok is False
    assert "Unknown tool" in reason


def test_disabled_tool_denied():
    registry = ToolRegistry()
    registry.register(ToolSchema(
        tool_id="disabled_tool",
        name="Disabled",
        description="Should not run",
        argument_schema={},
        output_schema={},
        required_permissions=[],
        status=ToolStatus.DISABLED,
    ))
    svc = ToolAuthorizationService(registry)
    ok, reason = svc.authorize(_req("disabled_tool", ["admin"]))
    assert ok is False
    assert "not enabled" in reason


def test_all_roles_can_search_knowledge():
    svc = ToolAuthorizationService(_registry_with_python_exec())
    for role in ["viewer", "operator", "admin"]:
        ok, _ = svc.authorize(_req("knowledge_search", [role]))
        assert ok is True, f"Expected {role} to be authorized for knowledge_search"
