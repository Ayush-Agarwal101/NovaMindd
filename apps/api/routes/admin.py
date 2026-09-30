"""Admin endpoints — model management, policy, audit."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/tools")
async def list_tools() -> list[dict]:
    from core.control_plane.tools import get_tool_registry
    registry = get_tool_registry()
    return [
        {
            "tool_id": t.tool_id,
            "name": t.name,
            "description": t.description,
            "status": t.status.value,
            "required_permissions": t.required_permissions,
            "requires_network": t.requires_network,
            "requires_human_approval": t.requires_human_approval,
        }
        for t in registry.all()
    ]


@router.get("/config")
async def get_platform_config() -> dict:
    from core.config import get_config
    cfg = get_config()
    return {
        "app": cfg.app.model_dump(),
        "api": cfg.api.model_dump(),
        "retrieval": cfg.retrieval.model_dump(),
        "document_ai": cfg.document_ai.model_dump(),
        "residency": cfg.residency.model_dump(),
        "sandbox": cfg.sandbox.model_dump(),
    }
