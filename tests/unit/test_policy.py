"""
Tests — Policy Engine

Verifies allow/deny decisions and rule evaluation order.
"""
from __future__ import annotations

import pytest

from core.control_plane.policy import (
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
    PolicyRule,
)


def _ctx(action: str, resource: str = "", roles: list[str] | None = None) -> PolicyContext:
    return PolicyContext(
        user_id="user-1",
        user_roles=roles or [],
        action=action,
        resource=resource,
    )


def test_operator_can_execute_tool():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx("tool:execute", "python_exec", roles=["operator"]))
    assert result.decision == PolicyDecision.ALLOW


def test_viewer_cannot_execute_tool():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx("tool:execute", "python_exec", roles=["viewer"]))
    assert result.decision == PolicyDecision.DENY


def test_any_user_can_retrieve_knowledge():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx("knowledge:retrieve", roles=["viewer"]))
    assert result.decision == PolicyDecision.ALLOW


def test_admin_can_manage_models():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx("model:load", roles=["admin"]))
    assert result.decision == PolicyDecision.ALLOW


def test_operator_cannot_manage_models():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx("model:load", roles=["operator"]))
    assert result.decision == PolicyDecision.DENY


def test_default_deny_no_roles():
    engine = PolicyEngine()
    result = engine.evaluate(_ctx("unknown:action", roles=[]))
    assert result.decision == PolicyDecision.DENY


def test_custom_rule_inserted_before_deny():
    engine = PolicyEngine()
    engine.add_rule(PolicyRule(
        rule_id="custom-allow",
        action_pattern="custom:action",
        resource_pattern="",
        required_roles=["special"],
        decision=PolicyDecision.ALLOW,
        reason="Custom allow for special role",
    ))
    result = engine.evaluate(_ctx("custom:action", roles=["special"]))
    assert result.decision == PolicyDecision.ALLOW
    assert result.rule_id == "custom-allow"


def test_escalate_decision():
    engine = PolicyEngine()
    # Insert at position 0 so it takes precedence over the default operator-allow rule
    engine.add_rule(PolicyRule(
        rule_id="escalate-dangerous",
        action_pattern="tool:execute",
        resource_pattern="dangerous_tool",
        required_roles=["operator"],
        decision=PolicyDecision.ESCALATE,
        requires_human_approval=True,
        reason="Dangerous tool requires human approval",
    ), index=0)
    result = engine.evaluate(_ctx("tool:execute", "dangerous_tool", roles=["operator"]))
    assert result.decision == PolicyDecision.ESCALATE
    assert result.requires_human_approval is True
