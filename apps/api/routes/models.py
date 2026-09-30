"""Models / residency management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.api.dependencies import ResidencyDep, RouterDep
from core.inference.registry import ModelStatus
from core.inference.router import RoutingRequest, TaskCapability

router = APIRouter(prefix="/models", tags=["models"])


class ModelStatusOut(BaseModel):
    model_id: str
    model_name: str
    status: str
    capabilities: list[str]
    vram_limit_mb: int
    is_loaded: bool


class RouteRequest(BaseModel):
    capability: str
    requires_vision: bool = False


@router.get("/", response_model=list[ModelStatusOut])
async def list_models(residency: ResidencyDep) -> list[ModelStatusOut]:
    from core.inference.registry import get_registry
    registry = get_registry()
    await residency.sync_from_backend()
    return [
        ModelStatusOut(
            model_id=e.id,
            model_name=e.config.name,
            status=e.status.value,
            capabilities=e.capabilities,
            vram_limit_mb=e.vram_limit_mb,
            is_loaded=e.is_loaded,
        )
        for e in registry.all()
    ]


@router.post("/{model_id}/load", status_code=202)
async def load_model(model_id: str, residency: ResidencyDep) -> dict:
    try:
        await residency.ensure_loaded(model_id)
        return {"status": "loaded", "model_id": model_id}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/{model_id}/unload", status_code=202)
async def unload_model(model_id: str, residency: ResidencyDep) -> dict:
    await residency.ensure_unloaded(model_id)
    return {"status": "unloaded", "model_id": model_id}


@router.post("/route")
async def route_model(body: RouteRequest, model_router: RouterDep) -> dict:
    try:
        cap = TaskCapability(body.capability)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown capability: {body.capability!r}")
    try:
        decision = model_router.route(
            RoutingRequest(capability=cap, requires_vision=body.requires_vision)
        )
        return {
            "model_id": decision.model_id,
            "model_name": decision.model_name,
            "already_loaded": decision.already_loaded,
            "reason": decision.reason,
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
