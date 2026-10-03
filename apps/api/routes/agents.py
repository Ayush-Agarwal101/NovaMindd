"""Agent task execution endpoint.

Accepts a multipart/form-data request so users can attach files (PDFs, images,
text, CSV …) alongside their task description.  Uploaded files are ingested into
a temporary session-scoped index that is merged with the global knowledge base
before the planner runs, enabling the agent to reason over user-supplied data
without requiring prior document indexing.

After a successful run the response is saved to output/<request_id>.txt and
output/<request_id>.pdf automatically.  Download links are included in the
response.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from apps.api.dependencies import (
    GatewayDep,
    IndexManagerDep,
    IngestionDep,
    ProvenanceDep,
    ResidencyDep,
    RouterDep,
    ProviderDep,
    RetrievalDep,
)
from core.agents.planner import AgentPlanner, AgentRequest, AgentStatus
from core.agents.output_writer import save_agent_output
from core.inference.router import TaskCapability
from core.retrieval.ingestion import DocumentChunk

router = APIRouter(prefix="/agents", tags=["agents"])


class SubStepInfo(BaseModel):
    step_index: int
    capability: str
    model_id: str
    model_name: str


class RunTaskResponse(BaseModel):
    request_id: str | None
    status: str
    answer: str | None
    tool_calls: list[dict]
    evidence_count: int
    files_ingested: int
    sub_steps: list[SubStepInfo]
    output_files: dict[str, str]   # format → server-side path (informational)
    download_urls: dict[str, str]  # format → API download URL
    error: str | None


@router.post("/run", response_model=RunTaskResponse)
async def run_task(
    # ── Form fields ──────────────────────────────────────────────────────
    task: str = Form(..., description="Task description / question for the agent"),
    capability: str = Form("reasoning"),
    requires_vision: bool = Form(False),
    user_id: str = Form("web-user"),
    user_roles: str = Form("operator"),          # comma-separated list
    max_tool_calls: int = Form(5),
    session_id: Optional[str] = Form(None),
    # ── Optional file uploads ─────────────────────────────────────────────
    files: List[UploadFile] = File(default=[]),
    # ── Injected dependencies ─────────────────────────────────────────────
    provider: ProviderDep = ...,
    model_router: RouterDep = ...,
    residency: ResidencyDep = ...,
    retrieval: RetrievalDep = ...,
    gateway: GatewayDep = ...,
    index_manager: IndexManagerDep = ...,
    ingestion: IngestionDep = ...,
    provenance: ProvenanceDep = ...,
) -> RunTaskResponse:
    # Validate capability
    try:
        cap = TaskCapability(capability)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown capability: {capability!r}")

    roles = [r.strip() for r in user_roles.split(",") if r.strip()]

    # ── Ingest any uploaded files into a temporary session index ─────────
    sid = session_id or str(uuid.uuid4())
    supplied_chunks: list[DocumentChunk] = []
    files_ingested = 0

    for upload in files:
        if upload.filename and upload.size == 0:
            continue
        data = await upload.read()
        if not data:
            continue
        doc = ingestion.ingest(data, filename=upload.filename or "upload")
        # Index into the session scope so retrieval can find these chunks
        index_manager.index_session(sid, doc.chunks)
        supplied_chunks.extend(doc.chunks)
        files_ingested += 1

    # ── Build planner with IndexManager wired in ─────────────────────────
    planner = AgentPlanner(
        provider=provider,
        router=model_router,
        residency=residency,
        retrieval=retrieval,
        tool_gateway=gateway,
        index_manager=index_manager,
    )

    result = await planner.run(
        AgentRequest(
            task=task,
            user_id=user_id,
            user_roles=roles,
            capability=cap,
            requires_vision=requires_vision,
            max_tool_calls=max_tool_calls,
            session_id=sid,
            supplied_chunks=supplied_chunks,
        )
    )

    # ── Save output files ─────────────────────────────────────────────────
    output_files: dict[str, str] = {}
    download_urls: dict[str, str] = {}
    if result.status == AgentStatus.COMPLETED and result.answer:
        output_files = save_agent_output(result, task=task, formats=["txt", "pdf"])
        req_id = result.request_id or ""
        for fmt in output_files:
            download_urls[fmt] = f"/api/v1/artifacts/download/{req_id}/{fmt}"

    # ── Build sub-step metadata for the response ──────────────────────────
    sub_steps = [
        SubStepInfo(
            step_index=s.step_index,
            capability=s.capability,
            model_id=s.model_id,
            model_name=s.model_name,
        )
        for s in result.sub_steps
    ]

    return RunTaskResponse(
        request_id=result.request_id,
        status=result.status.value,
        answer=result.answer,
        tool_calls=result.tool_calls,
        evidence_count=len(result.evidence),
        files_ingested=files_ingested,
        sub_steps=sub_steps,
        output_files=output_files,
        download_urls=download_urls,
        error=result.error,
    )
