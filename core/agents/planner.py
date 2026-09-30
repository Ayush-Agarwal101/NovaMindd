"""
NovaMindd — Agent Planner

Implements a LangGraph-based reasoning agent with fail-closed behaviour.
The agent plans → retrieves evidence → reasons → requests tools → validates.
At no point does the model receive direct system access.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.control_plane.tools import ToolCallRequest
from core.inference.providers.base import BaseInferenceProvider, InferenceRequest
from core.inference.router import ModelRouter, RoutingRequest, TaskCapability
from core.inference.residency import ResidencyManager
from core.retrieval.engine import EvidenceItem, RetrievalEngine
from core.agents.tool_gateway import ToolGateway
from core.logging import get_logger

logger = get_logger(__name__)


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    FAIL_CLOSED = "fail_closed"   # insufficient evidence — no output produced


@dataclass
class AgentRequest:
    task: str
    user_id: str
    user_roles: list[str]
    capability: TaskCapability = TaskCapability.REASONING
    requires_vision: bool = False
    max_tool_calls: int = 5
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    request_id: str | None
    status: AgentStatus
    answer: str | None
    evidence: list[EvidenceItem] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


PLANNER_SYSTEM_PROMPT = """\
You are an AI assistant inside NovaMindd, a sovereign AI execution platform.

Rules you MUST follow:
1. Only use information from the provided evidence snippets.
2. If the evidence is insufficient, respond with FAIL_CLOSED and explain what is missing.
3. If you need to execute code or search for more information, emit a tool call in this exact format:
   TOOL_CALL: {{"tool_id": "<id>", "arguments": {{...}}}}
4. Do not invent facts. Do not hallucinate source references.
5. When you have enough evidence, provide a concise, grounded answer.

Evidence:
{evidence}

Task: {task}
"""


class AgentPlanner:
    """
    Orchestrates a single-turn reasoning cycle:
      1. Retrieve evidence
      2. Route to appropriate model
      3. Ensure model is loaded
      4. Generate reasoning response
      5. Parse any tool calls and execute via ToolGateway
      6. If evidence is insufficient → fail-closed

    This is a simplified single-turn planner.
    A full multi-turn LangGraph implementation would extend this.
    """

    def __init__(
        self,
        provider: BaseInferenceProvider,
        router: ModelRouter,
        residency: ResidencyManager,
        retrieval: RetrievalEngine,
        tool_gateway: ToolGateway,
    ) -> None:
        self._provider = provider
        self._router = router
        self._residency = residency
        self._retrieval = retrieval
        self._gateway = tool_gateway

    async def run(self, request: AgentRequest) -> AgentResponse:
        import uuid
        req_id = request.request_id or str(uuid.uuid4())
        logger.info("agent_start", request_id=req_id, task=request.task[:80])

        # 1. Retrieve evidence
        evidence = self._retrieval.retrieve(request.task)
        if not evidence:
            logger.warning("agent_fail_closed_no_evidence", request_id=req_id)
            return AgentResponse(
                request_id=req_id,
                status=AgentStatus.FAIL_CLOSED,
                answer=None,
                error="No relevant evidence found. Cannot produce a grounded response.",
            )

        # 2. Route to model
        routing = self._router.route(
            RoutingRequest(
                capability=request.capability,
                requires_vision=request.requires_vision,
            )
        )

        # 3. Ensure model is loaded
        await self._residency.ensure_loaded(routing.model_id)

        # 4. Build prompt
        evidence_text = self._format_evidence(evidence)
        prompt = PLANNER_SYSTEM_PROMPT.format(
            evidence=evidence_text, task=request.task
        )

        # 5. Inference
        inf_response = await self._provider.generate(
            InferenceRequest(
                model_name=routing.model_name,
                prompt=prompt,
                max_tokens=2048,
                temperature=0.1,
            )
        )

        # 6. Parse tool calls
        tool_call_results: list[dict] = []
        content = inf_response.content
        tool_calls_made = 0

        while "TOOL_CALL:" in content and tool_calls_made < request.max_tool_calls:
            import json, re
            match = re.search(r"TOOL_CALL:\s*(\{.+?\})", content, re.DOTALL)
            if not match:
                break
            try:
                tc_spec = json.loads(match.group(1))
                tc_result = self._gateway.call(
                    ToolCallRequest(
                        tool_id=tc_spec["tool_id"],
                        arguments=tc_spec.get("arguments", {}),
                        user_id=request.user_id,
                        user_roles=request.user_roles,
                        request_id=req_id,
                    )
                )
                tool_call_results.append({
                    "tool_id": tc_spec["tool_id"],
                    "success": tc_result.success,
                    "output": tc_result.output,
                    "error": tc_result.error,
                })
                # Remove processed tool call and continue
                content = content[match.end():]
                tool_calls_made += 1
            except Exception as exc:
                logger.error("agent_tool_call_parse_error", error=str(exc))
                break

        # 7. Fail-closed check
        if "FAIL_CLOSED" in content:
            return AgentResponse(
                request_id=req_id,
                status=AgentStatus.FAIL_CLOSED,
                answer=None,
                evidence=evidence,
                tool_calls=tool_call_results,
                error="Model determined evidence is insufficient for a grounded response.",
            )

        provenance = {
            "request_id": req_id,
            "model_id": routing.model_id,
            "model_name": routing.model_name,
            "evidence_sources": [
                {"document_id": e.document_id, "page": e.page, "score": e.score}
                for e in evidence
            ],
            "tool_calls": tool_call_results,
        }

        logger.info("agent_complete", request_id=req_id)
        return AgentResponse(
            request_id=req_id,
            status=AgentStatus.COMPLETED,
            answer=content.strip(),
            evidence=evidence,
            tool_calls=tool_call_results,
            provenance=provenance,
        )

    @staticmethod
    def _format_evidence(items: list[EvidenceItem]) -> str:
        parts = []
        for i, item in enumerate(items, start=1):
            parts.append(
                f"[{i}] Source: {item.source_path} | Page {item.page} | Score {item.score:.3f}\n"
                f"{item.text}"
            )
        return "\n\n".join(parts)
