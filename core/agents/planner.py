"""
NovaMindd — Agent Planner

Multi-step reasoning agent that dynamically switches models per sub-task:
  1. Classify the overall task into typed sub-steps (coding / vision / text …)
  2. For each sub-step, route to the best available model for that capability
  3. Load the required model (unloading the previous one if VRAM is tight)
  4. Execute inference for the sub-step
  5. Execute any TOOL_CALLs via ToolGateway
  6. Synthesise all sub-step answers into a final response
  7. Verify consistency — re-check that the synthesis is actually supported by
     the cited evidence; downgrade to NOT_EVIDENCED / human-review if not.
  8. Fail-closed if evidence is truly insufficient
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
- Use "coding" capability ONLY when the sub-step genuinely requires writing or \
running code or performing data computation. Document reading, classification, \
summarisation, and requirement-checking are NOT coding tasks.
- Do not emit any text outside the JSON lines.

Evidence summary:
{evidence_summary}

Task: {task}
"""

SUB_STEP_PROMPT = """\
You are an analytical assistant inside NovaMindd. Complete the following sub-step \
strictly using the evidence provided.

GROUNDING RULES — these are mandatory and override everything else:
1. Base every statement solely on the evidence passages numbered below.
   Cite the evidence number [N] whenever you make a factual claim.
2. Never infer, assume, or add domain knowledge not present in the evidence.
3. If a classification or assessment is requested use ONLY these three verdicts:
   - PASS   — the evidence explicitly and unambiguously satisfies the requirement.
   - FAIL   — the evidence explicitly and unambiguously contradicts the requirement.
   - NOT_EVIDENCED — the evidence does not mention or resolve the requirement.
   Do not use any other verdict. When in doubt, choose NOT_EVIDENCED.
4. Never invent requirements, criteria, or checklist items. Only evaluate what
   the task description explicitly asks you to evaluate.
5. If you need to execute code or query the knowledge base, emit exactly:
   TOOL_CALL: {{"tool_id": "python_exec", "arguments": {{"code": "<code>"}}}}
   TOOL_CALL: {{"tool_id": "knowledge_search", "arguments": {{"query": "<query>"}}}}
6. Be concise and precise.

Evidence (passages from the uploaded source documents):
{evidence}

Sub-step {step_index}: {description}

Previous sub-step results (for context only — do not re-classify based on these):
{previous_results}
"""

SYNTHESIS_PROMPT = """\
You are a senior analyst inside NovaMindd. \
Combine the sub-step results below into a single, well-structured final answer.

GROUNDING RULES — these are mandatory:
1. Preserve all findings from the sub-steps exactly as stated.
2. Structure the output clearly (use sections if appropriate).
3. Do NOT add new information, requirements, or criteria not present in the sub-step results.
4. Do NOT upgrade a NOT_EVIDENCED finding to PASS or FAIL.
5. Do NOT downgrade a cited PASS or FAIL without explicit counter-evidence in the sub-steps.
6. Write in professional prose unless the task requires code or tables.

Sub-step results:
{sub_step_results}

Original task: {task}
"""

CONSISTENCY_VERIFY_PROMPT = """\
You are a consistency auditor inside NovaMindd. \
Your job is to verify that the draft answer below is actually supported by the \
evidence passages provided.

INSTRUCTIONS:
1. For each classification verdict (PASS / FAIL / NOT_EVIDENCED) in the draft answer,
   check whether it is directly supported by at least one of the evidence passages.
2. If a verdict is supported, keep it unchanged.
3. If a PASS or FAIL verdict has no supporting passage in the evidence, change it to
   NOT_EVIDENCED and append "(flagged: no supporting evidence — human review required)".
4. If the draft answer contains a requirement or criterion that does not appear in the
   evidence at all, mark it NOT_EVIDENCED.
5. Do not add new information. Do not change verdicts that ARE supported.
6. Return the full corrected answer and nothing else.

Evidence passages:
{evidence}

Draft answer:
{draft_answer}
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
        # Per-model KV-cache context arrays.  Key = model_name; value = the
        # token array returned by the last call to that model.  When the model
        # stays the same across consecutive sub-steps the cache is reused so
        # Ollama does not re-encode the prompt from scratch.  When the model
        # changes the cache is intentionally left alone (it is model-specific).
        model_contexts: dict[str, list[int]] = {}

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
                    context=model_contexts.get(routing.model_name),
                )
            )
            # Store the returned KV-cache for the next call to this model
            if inf_resp.context:
                model_contexts[routing.model_name] = inf_resp.context

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

        # 5. Consistency verification — re-check that every claim in the
        #    synthesised answer is actually supported by the retrieved evidence.
        final_answer = await self._verify_consistency(
            evidence_text=evidence_text,
            draft_answer=final_answer,
            request=request,
        )

        # 6. Fail-closed check
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
        """
        Retrieve evidence from the index.

        Uploaded files are ingested into the session index in the API layer
        before this method is called, so they are already searchable through
        the normal retrieval path.  We do NOT re-inject the raw chunks here
        as floating EvidenceItems — that would bypass scoring, cause duplicate
        passages, and inflate their apparent relevance.  The session-scoped
        engine already contains them and will return them if they are relevant.
        """
        if self._index_manager is not None:
            return self._index_manager.retrieve_combined(
                session_id=request.session_id,
                query=request.task,
                top_k=10,
            )
        return self._retrieval.retrieve(request.task)

    # ------------------------------------------------------------------
    # Task decomposition
    # ------------------------------------------------------------------

    async def _decompose_task(
        self, request: AgentRequest, evidence_summary: str
    ) -> list[dict]:
        """Ask a fast model to break the task into typed sub-steps."""
        routing = self._router.route(
            RoutingRequest(
                capability=request.capability,
                exclude_coding_only=True,
            )
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
            RoutingRequest(
                capability=request.capability,
                exclude_coding_only=True,
            )
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
    # Consistency verification
    # ------------------------------------------------------------------

    async def _verify_consistency(
        self,
        evidence_text: str,
        draft_answer: str,
        request: AgentRequest,
    ) -> str:
        """
        Lightweight post-synthesis check: ask the reasoning model to confirm
        that every verdict in the draft is actually backed by the evidence.
        Unsupported PASS/FAIL verdicts are downgraded to NOT_EVIDENCED.
        """
        # Only bother if the answer looks like it contains classifications.
        # This avoids a wasted LLM call on purely narrative answers.
        classification_markers = ("PASS", "FAIL", "NOT_EVIDENCED")
        if not any(m in draft_answer for m in classification_markers):
            return draft_answer

        routing = self._router.route(
            RoutingRequest(
                capability=TaskCapability.REASONING,
                exclude_coding_only=True,
            )
        )
        await self._residency.ensure_loaded(routing.model_id)

        prompt = CONSISTENCY_VERIFY_PROMPT.format(
            evidence=evidence_text,
            draft_answer=draft_answer,
        )
        resp = await self._provider.generate(
            InferenceRequest(
                model_name=routing.model_name,
                prompt=prompt,
                max_tokens=3000,
                temperature=0.0,   # deterministic — auditing, not creative
            )
        )
        verified = resp.content.strip()
        if verified:
            logger.info("consistency_verified", request_id=None)
            return verified
        # If the model returns empty (shouldn't happen), pass the draft through
        return draft_answer

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
                # Replace the TOOL_CALL marker with the tool's actual output so
                # the content that preceded the call is preserved and the result
                # is inline where the model requested it.
                tool_output_text = (
                    f"\n[Tool: {tc_spec['tool_id']}]\n{tc_result.output or tc_result.error or ''}\n"
                )
                content = content[: match.start()] + tool_output_text + content[match.end():]
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
        """
        Format evidence items for inclusion in a prompt.

        Each passage is labelled with its source document and page so the model
        can cite it by number.  The label clearly identifies these as passages
        extracted from uploaded source documents, not as independent facts.
        """
        parts = []
        for i, item in enumerate(items, start=1):
            parts.append(
                f"[{i}] Document: \"{item.source_path}\" | Page {item.page}\n"
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
