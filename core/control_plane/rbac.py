"""
NovaMindd — RBAC (Role-Based Access Control)

Simple role/permission model. Users carry roles; roles carry permissions.
Integrates with the Policy Engine for runtime authorization checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class User:
    user_id: str
    username: str
    hashed_password: str
    roles: list[str] = field(default_factory=list)
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles)


# ---------------------------------------------------------------------------
# Built-in roles and permissions
# ---------------------------------------------------------------------------

ROLE_VIEWER = "viewer"
ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"

BUILT_IN_ROLES: dict[str, list[str]] = {
    ROLE_VIEWER: [
        "knowledge:retrieve",
        "document:read",
    ],
    ROLE_OPERATOR: [
        "knowledge:retrieve",
        "document:read",
        "document:upload",
        "tool:execute",
        "agent:run",
        "artifact:generate",
    ],
    ROLE_ADMIN: [
        "knowledge:retrieve",
        "knowledge:manage",
        "document:read",
        "document:upload",
        "document:delete",
        "tool:execute",
        "tool:manage",
        "agent:run",
        "artifact:generate",
        "model:load",
        "model:unload",
        "model:manage",
        "policy:manage",
        "user:manage",
        "audit:read",
    ],
}


class RBACService:
    """In-memory user store with role-based permission checks."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def add_user(self, user: User) -> None:
        self._users[user.user_id] = user

    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> User | None:
        return next(
            (u for u in self._users.values() if u.username == username), None
        )

    def has_permission(self, user_id: str, permission: str) -> bool:
        user = self._users.get(user_id)
        if user is None or not user.is_active:
            return False
        for role in user.roles:
            perms = BUILT_IN_ROLES.get(role, [])
            if permission in perms:
                return True
        return False

    def user_roles(self, user_id: str) -> list[str]:
        user = self._users.get(user_id)
        return user.roles if user else []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_rbac: RBACService | None = None


def get_rbac() -> RBACService:
    global _rbac
    if _rbac is None:
        _rbac = RBACService()
    return _rbac
