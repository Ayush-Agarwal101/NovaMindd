"""Agent task execution endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.api.dependencies import (
    GatewayDep,
    ProvenanceDep,
    ResidencyDep,
    RetrievalDep,
    RouterDep,
    ProviderDep,
)
from core.agents.planner import AgentPlanner, AgentRequest, AgentStatus
from core.inference.router import TaskCapability

router = APIRouter(prefix="/agents", tags=["agents"])


class RunTaskRequest(BaseModel):
    task: str
    capability: str = "reasoning"
    requires_vision: bool = False
    user_id: str = "anonymous"
    user_roles: list[str] = ["viewer"]
    max_tool_calls: int = 5


class RunTaskResponse(BaseModel):
    request_id: str | None
    status: str
    answer: str | None
    tool_calls: list[dict]
    evidence_count: int
    error: str | None


@router.post("/run", response_model=RunTaskResponse)
async def run_task(
    body: RunTaskRequest,
    provider: ProviderDep,
    model_router: RouterDep,
    residency: ResidencyDep,
    retrieval: RetrievalDep,
    gateway: GatewayDep,
    provenance: ProvenanceDep,
) -> RunTaskResponse:
    try:
        cap = TaskCapability(body.capability)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown capability: {body.capability!r}")

    planner = AgentPlanner(
        provider=provider,
        router=model_router,
        residency=residency,
        retrieval=retrieval,
        tool_gateway=gateway,
    )

    result = await planner.run(
        AgentRequest(
            task=body.task,
            user_id=body.user_id,
            user_roles=body.user_roles,
            capability=cap,
            requires_vision=body.requires_vision,
            max_tool_calls=body.max_tool_calls,
        )
    )

    return RunTaskResponse(
        request_id=result.request_id,
        status=result.status.value,
        answer=result.answer,
        tool_calls=result.tool_calls,
        evidence_count=len(result.evidence),
        error=result.error,
    )
