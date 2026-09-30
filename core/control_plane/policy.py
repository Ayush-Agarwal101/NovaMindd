"""
NovaMindd — Policy Engine

Central authority for permission decisions.
Decisions are logged as audit events regardless of outcome.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"   # requires human approval before proceeding


@dataclass
class PolicyContext:
    """All inputs relevant to a policy decision."""
    user_id: str
    user_roles: list[str]
    action: str             # e.g. "tool:execute", "model:load", "document:read"
    resource: str           # e.g. tool name, model id, document id
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyResult:
    decision: PolicyDecision
    reason: str
    rule_id: str | None = None
    requires_human_approval: bool = False


# ---------------------------------------------------------------------------
# Policy rules
# ---------------------------------------------------------------------------

@dataclass
class PolicyRule:
    rule_id: str
    action_pattern: str         # prefix-match against action
    resource_pattern: str       # prefix-match against resource
    required_roles: list[str]   # at least one must match; empty = any role
    decision: PolicyDecision = PolicyDecision.ALLOW
    requires_human_approval: bool = False
    reason: str = ""


_DEFAULT_RULES: list[PolicyRule] = [
    # Operators and admins can execute tools
    PolicyRule(
        rule_id="tool-exec-operator",
        action_pattern="tool:execute",
        resource_pattern="",
        required_roles=["operator", "admin"],
        decision=PolicyDecision.ALLOW,
        reason="Operators may execute approved tools",
    ),
    # Any authenticated user can query knowledge
    PolicyRule(
        rule_id="knowledge-read-any",
        action_pattern="knowledge:retrieve",
        resource_pattern="",
        required_roles=[],
        decision=PolicyDecision.ALLOW,
        reason="All authenticated users may query knowledge",
    ),
    # Only admins may load/unload models
    PolicyRule(
        rule_id="model-manage-admin",
        action_pattern="model:",
        resource_pattern="",
        required_roles=["admin"],
        decision=PolicyDecision.ALLOW,
        reason="Only admins may manage model residency",
    ),
    # Catch-all: deny
    PolicyRule(
        rule_id="default-deny",
        action_pattern="",
        resource_pattern="",
        required_roles=[],
        decision=PolicyDecision.DENY,
        reason="No matching allow rule — default deny",
    ),
]


class PolicyEngine:
    """
    Evaluate policy for a given context against a list of rules.

    Rules are evaluated in order; first match wins.
    """

    def __init__(self, rules: list[PolicyRule] | None = None) -> None:
        self._rules = rules if rules is not None else list(_DEFAULT_RULES)

    def evaluate(self, context: PolicyContext) -> PolicyResult:
        for rule in self._rules:
            if not self._matches(rule, context):
                continue
            result = PolicyResult(
                decision=rule.decision,
                reason=rule.reason,
                rule_id=rule.rule_id,
                requires_human_approval=rule.requires_human_approval,
            )
            logger.info(
                "policy_decision",
                user=context.user_id,
                action=context.action,
                resource=context.resource,
                decision=rule.decision.value,
                rule=rule.rule_id,
            )
            return result

        # Should never reach here if default-deny rule is present
        return PolicyResult(
            decision=PolicyDecision.DENY,
            reason="No matching rule",
        )

    def add_rule(self, rule: PolicyRule, *, index: int | None = None) -> None:
        """Add a rule. Insert before the default-deny if index not specified."""
        if index is not None:
            self._rules.insert(index, rule)
        else:
            # Insert before last rule (assumed to be the catch-all deny)
            self._rules.insert(max(0, len(self._rules) - 1), rule)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    @staticmethod
    def _matches(rule: PolicyRule, ctx: PolicyContext) -> bool:
        if rule.action_pattern and not ctx.action.startswith(rule.action_pattern):
            return False
        if rule.resource_pattern and not ctx.resource.startswith(rule.resource_pattern):
            return False
        if rule.required_roles:
            if not any(r in ctx.user_roles for r in rule.required_roles):
                return False
        return True
