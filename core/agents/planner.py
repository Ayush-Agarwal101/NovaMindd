"""
NovaMindd — Agent Planner

Multi-step reasoning agent that dynamically switches models per sub-task:
  1. Classify the overall task into typed sub-steps (coding / vision / text …)
  2. For each sub-step, route to the best available model for that capability
  3. Load the required model (unloading the previous one if VRAM is tight)
  4. Execute inference for the sub-step
  5. Execute any TOOL_CALLs via ToolGateway
  6. Synthesise all sub-step answers into a final response
  7. Fail-closed if evidence is truly insufficient
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.control_plane.tools import ToolCallRequest
from core.inference.providers.base import BaseInferenceProvider, InferenceRequest
from core.inference.router import ModelRouter, RoutingRequest, TaskCapability
from core.inference.residency import ResidencyManager
from core.retrieval.engine import EvidenceItem, RetrievalEngine
from core.retrieval.ingestion import DocumentChunk
from core.agents.tool_gateway import ToolGateway
from core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

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
    # Caller-supplied chunks (e.g. freshly ingested user files).
    supplied_chunks: list[DocumentChunk] = field(default_factory=list)
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubStepResult:
    """Result of a single model-switched sub-step."""
    step_index: int
    capability: str
    model_id: str
    model_name: str
    content: str
    tool_calls: list[dict] = field(default_factory=list)


@dataclass
class AgentResponse:
    request_id: str | None
    status: AgentStatus
    answer: str | None
    evidence: list[EvidenceItem] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    sub_steps: list[SubStepResult] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

TASK_DECOMPOSE_PROMPT = """\
You are a task planner for NovaMindd. Given a task description and evidence, \
identify the distinct sub-steps required to complete it.

For each sub-step output a JSON object on its own line:
{{"step": <int>, "capability": "<capability>", "description": "<what to do>"}}

Available capabilities: reasoning, text, coding, vision, document_understanding, \
summarisation, analysis

Rules:
- Only emit sub-steps that are genuinely needed.
- If the whole task fits one capability, emit a single sub-step.
- Order sub-steps logically (e.g. analyse data before writing report).
- Do not emit any text outside the JSON lines.

Evidence summary:
{evidence_summary}

Task: {task}
"""

SUB_STEP_PROMPT = """\
You are an AI assistant inside NovaMindd. Complete the following sub-step.

Rules:
1. Use only the evidence provided below.
2. If you need to execute code, emit exactly:
   TOOL_CALL: {{"tool_id": "python_exec", "arguments": {{"code": "<code>"}}}}
3. If you need to search the knowledge base, emit:
   TOOL_CALL: {{"tool_id": "knowledge_search", "arguments": {{"query": "<query>"}}}}
4. Do not hallucinate. Do not invent sources.
5. Be concise and precise.

Evidence:
{evidence}

Sub-step {step_index}: {description}

Previous results (for context):
{previous_results}
"""

SYNTHESIS_PROMPT = """\
You are a senior analyst inside NovaMindd. \
Combine the sub-step results below into a single, well-structured final answer.

Rules:
1. Preserve all findings from the sub-steps.
2. Structure the output clearly (use sections if appropriate).
3. Do NOT add new information not present in the sub-step results.
4. Write in professional prose unless the task requires code or tables.

Sub-step results:
{sub_step_results}

Original task: {task}
"""


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class AgentPlanner:
    """
    Multi-step agent with dynamic per-step model switching.

    For each sub-step the planner:
      • Routes to the best model for that capability via ModelRouter
      • Calls ResidencyManager.ensure_loaded() — which auto-evicts LRU models
        if VRAM is tight, loading the new one in their place
      • Runs inference with that model
      • Runs any tool calls via ToolGateway
    After all sub-steps a synthesis step (using the routing capability model)
    merges everything into a final answer.

    Accepts an optional IndexManager so it queries the fully-populated shared
    retrieval index rather than an empty standalone RetrievalEngine.
    """

    def __init__(
        self,
        provider: BaseInferenceProvider,
        router: ModelRouter,
        residency: ResidencyManager,
        retrieval: RetrievalEngine,
        tool_gateway: ToolGateway,
        index_manager: Any | None = None,   # core.retrieval.index_manager.IndexManager
    ) -> None:
        self._provider = provider
        self._router = router
        self._residency = residency
        self._retrieval = retrieval
        self._gateway = tool_gateway
        self._index_manager = index_manager

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, request: AgentRequest) -> AgentResponse:
        req_id = request.request_id or str(uuid.uuid4())
        logger.info("agent_start", request_id=req_id, task=request.task[:80])

        # 1. Gather evidence
        evidence = self._gather_evidence(request)
        if not evidence:
            logger.warning("agent_fail_closed_no_evidence", request_id=req_id)
            return AgentResponse(
                request_id=req_id,
                status=AgentStatus.FAIL_CLOSED,
                answer=None,
                error=(
                    "No evidence available. Upload documents via the Knowledge base or "
                    "attach files directly to the agent task, then try again."
                ),
            )

        evidence_text = self._format_evidence(evidence)
        evidence_summary = evidence_text[:2000]   # keep decompose prompt compact

        # 2. Decompose task into sub-steps using a fast text/reasoning model
        sub_steps = await self._decompose_task(
            request=request,
            evidence_summary=evidence_summary,
        )
        logger.info(
            "agent_decomposed",
            request_id=req_id,
            sub_steps=[s["capability"] for s in sub_steps],
        )

        # 3. Execute each sub-step with its best model
        step_results: list[SubStepResult] = []
        all_tool_calls: list[dict] = []
        tool_calls_remaining = request.max_tool_calls

        for step in sub_steps:
            step_idx = step["step"]
            cap_str = step["capability"]
            description = step["description"]

            try:
                cap = TaskCapability(cap_str)
            except ValueError:
                cap = request.capability

            routing = self._router.route(
                RoutingRequest(
                    capability=cap,
                    requires_vision=(cap == TaskCapability.VISION),
                )
            )

            # Dynamic model load/unload
            await self._residency.ensure_loaded(routing.model_id)
            if not routing.already_loaded:
                logger.info(
                    "agent_model_switched",
                    request_id=req_id,
                    step=step_idx,
                    capability=cap_str,
                    model_id=routing.model_id,
                    model_name=routing.model_name,
                )

            previous_results_text = self._format_step_results(step_results)
            prompt = SUB_STEP_PROMPT.format(
                evidence=evidence_text,
                step_index=step_idx,
                description=description,
                previous_results=previous_results_text or "(none yet)",
            )

            inf_resp = await self._provider.generate(
                InferenceRequest(
                    model_name=routing.model_name,
                    prompt=prompt,
                    max_tokens=2048,
                    temperature=0.1,
                )
            )

            content, tc_results, tool_calls_remaining = await self._process_tool_calls(
                content=inf_resp.content,
                request=request,
                req_id=req_id,
                max_calls=tool_calls_remaining,
            )
            all_tool_calls.extend(tc_results)

            step_results.append(SubStepResult(
                step_index=step_idx,
                capability=cap_str,
                model_id=routing.model_id,
                model_name=routing.model_name,
                content=content.strip(),
                tool_calls=tc_results,
            ))

        # 4. Synthesise final answer (use the primary requested capability)
        if len(step_results) == 1:
            # No synthesis needed for a single step
            final_answer = step_results[0].content
        else:
            final_answer = await self._synthesise(
                request=request,
                step_results=step_results,
            )

        # 5. Fail-closed check
        if "FAIL_CLOSED" in final_answer:
            return AgentResponse(
                request_id=req_id,
                status=AgentStatus.FAIL_CLOSED,
                answer=None,
                evidence=evidence,
                tool_calls=all_tool_calls,
                sub_steps=step_results,
                error="Model determined evidence is insufficient for a grounded response.",
            )

        provenance = {
            "request_id": req_id,
            "sub_steps": [
                {
                    "step": s.step_index,
                    "capability": s.capability,
                    "model_id": s.model_id,
                    "model_name": s.model_name,
                }
                for s in step_results
            ],
            "evidence_sources": [
                {"document_id": e.document_id, "page": e.page, "score": e.score}
                for e in evidence
            ],
            "tool_calls": all_tool_calls,
        }

        logger.info(
            "agent_complete",
            request_id=req_id,
            steps=len(step_results),
            tool_calls=len(all_tool_calls),
        )
        return AgentResponse(
            request_id=req_id,
            status=AgentStatus.COMPLETED,
            answer=final_answer.strip(),
            evidence=evidence,
            tool_calls=all_tool_calls,
            provenance=provenance,
            sub_steps=step_results,
        )

    # ------------------------------------------------------------------
    # Evidence gathering
    # ------------------------------------------------------------------

    def _gather_evidence(self, request: AgentRequest) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        if self._index_manager is not None:
            evidence = self._index_manager.retrieve_combined(
                session_id=request.session_id,
                query=request.task,
                top_k=10,
            )
        else:
            evidence = self._retrieval.retrieve(request.task)

        if request.supplied_chunks:
            for i, chunk in enumerate(request.supplied_chunks):
                evidence.append(
                    EvidenceItem(chunk=chunk, score=1.0 + i, source="uploaded")
                )
            evidence.sort(key=lambda e: e.score, reverse=True)

        return evidence

    # ------------------------------------------------------------------
    # Task decomposition
    # ------------------------------------------------------------------

    async def _decompose_task(
        self, request: AgentRequest, evidence_summary: str
    ) -> list[dict]:
        """Ask a fast model to break the task into typed sub-steps."""
        routing = self._router.route(
            RoutingRequest(capability=request.capability)
        )
        await self._residency.ensure_loaded(routing.model_id)

        prompt = TASK_DECOMPOSE_PROMPT.format(
            evidence_summary=evidence_summary,
            task=request.task,
        )
        resp = await self._provider.generate(
            InferenceRequest(
                model_name=routing.model_name,
                prompt=prompt,
                max_tokens=512,
                temperature=0.0,
            )
        )

        steps = []
        for line in resp.content.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if "step" in obj and "capability" in obj and "description" in obj:
                    steps.append(obj)
            except (json.JSONDecodeError, ValueError):
                pass

        if not steps:
            # Fallback: single step using the requested capability
            steps = [{"step": 1, "capability": request.capability.value, "description": request.task}]

        return steps

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    async def _synthesise(
        self, request: AgentRequest, step_results: list[SubStepResult]
    ) -> str:
        routing = self._router.route(
            RoutingRequest(capability=request.capability)
        )
        await self._residency.ensure_loaded(routing.model_id)

        combined = "\n\n".join(
            f"[Step {s.step_index} — {s.capability} — {s.model_name}]\n{s.content}"
            for s in step_results
        )
        prompt = SYNTHESIS_PROMPT.format(
            sub_step_results=combined,
            task=request.task,
        )
        resp = await self._provider.generate(
            InferenceRequest(
                model_name=routing.model_name,
                prompt=prompt,
                max_tokens=3000,
                temperature=0.1,
            )
        )
        return resp.content

    # ------------------------------------------------------------------
    # Tool call processing
    # ------------------------------------------------------------------

    async def _process_tool_calls(
        self,
        content: str,
        request: AgentRequest,
        req_id: str,
        max_calls: int,
    ) -> tuple[str, list[dict], int]:
        tool_call_results: list[dict] = []
        calls_left = max_calls

        while "TOOL_CALL:" in content and calls_left > 0:
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
                content = content[match.end():]
                calls_left -= 1
            except Exception as exc:
                logger.error("agent_tool_call_parse_error", error=str(exc))
                break

        return content, tool_call_results, calls_left

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_evidence(items: list[EvidenceItem]) -> str:
        parts = []
        for i, item in enumerate(items, start=1):
            parts.append(
                f"[{i}] Source: {item.source_path} | Page {item.page} | Score {item.score:.3f}\n"
                f"{item.text}"
            )
        return "\n\n".join(parts)

    @staticmethod
    def _format_step_results(results: list[SubStepResult]) -> str:
        if not results:
            return ""
        return "\n\n".join(
            f"[Step {r.step_index} — {r.capability}]\n{r.content}"
            for r in results
        )
