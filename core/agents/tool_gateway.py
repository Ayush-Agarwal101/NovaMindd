"""
NovaMindd — Tool Gateway

The Tool Gateway is the single entry point for all tool calls from agent code.
It enforces: authorization → validation → sandbox execution → result validation.

The LLM proposes a tool call.
The Gateway decides whether it is permitted and executes it safely.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from core.control_plane.policy import PolicyContext, PolicyDecision, PolicyEngine
from core.control_plane.rbac import get_rbac
from core.control_plane.tools import (
    ToolCallRequest,
    ToolCallResult,
    ToolRegistry,
    ToolAuthorizationService,
    get_tool_registry,
)
from core.logging import get_audit_logger, get_logger
from core.sandbox.docker_sandbox import DockerSandbox, SandboxRequest

if TYPE_CHECKING:
    from core.retrieval.index_manager import IndexManager
    from core.retrieval.ingestion import DocumentIngestionPipeline

logger = get_logger(__name__)


class ToolGateway:
    """
    Authorise and execute a tool call end-to-end.

    Pipeline:
      1. Look up tool schema
      2. Policy check (PolicyEngine)
      3. Role/permission check (ToolAuthorizationService)
      4. Human approval gate (if required)
      5. Execute (sandbox or direct handler)
      6. Audit result
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        policy_engine: PolicyEngine | None = None,
        index_manager: "IndexManager | None" = None,
        ingestion_pipeline: "DocumentIngestionPipeline | None" = None,
    ) -> None:
        self._registry = registry or get_tool_registry()
        self._auth = ToolAuthorizationService(self._registry)
        self._policy = policy_engine or PolicyEngine()
        self._sandbox = DockerSandbox()
        self._rbac = get_rbac()
        self._index_manager = index_manager
        self._ingestion = ingestion_pipeline

    def call(self, request: ToolCallRequest) -> ToolCallResult:
        req_id = request.request_id or str(uuid.uuid4())
        start = time.monotonic()

        # --- 1. Policy check ---
        ctx = PolicyContext(
            user_id=request.user_id,
            user_roles=request.user_roles,
            action="tool:execute",
            resource=request.tool_id,
        )
        policy_result = self._policy.evaluate(ctx)

        if policy_result.decision == PolicyDecision.DENY:
            self._audit("tool_denied", req_id, request, reason=policy_result.reason)
            return ToolCallResult(
                tool_id=request.tool_id,
                request_id=req_id,
                success=False,
                output=None,
                error=f"Policy denied: {policy_result.reason}",
            )

        if policy_result.decision == PolicyDecision.ESCALATE:
            self._audit("tool_escalated", req_id, request, reason=policy_result.reason)
            return ToolCallResult(
                tool_id=request.tool_id,
                request_id=req_id,
                success=False,
                output=None,
                error="Tool call requires human approval before execution.",
            )

        # --- 2. Authorization check ---
        authorized, reason = self._auth.authorize(request)
        if not authorized:
            self._audit("tool_unauthorized", req_id, request, reason=reason)
            return ToolCallResult(
                tool_id=request.tool_id,
                request_id=req_id,
                success=False,
                output=None,
                error=f"Unauthorized: {reason}",
            )

        # --- 3. Human approval gate ---
        tool = self._registry.get(request.tool_id)
        if tool and tool.requires_human_approval:
            self._audit("tool_pending_approval", req_id, request)
            return ToolCallResult(
                tool_id=request.tool_id,
                request_id=req_id,
                success=False,
                output=None,
                error="Tool requires human approval. Workflow paused.",
            )

        # --- 4. Execute ---
        result = self._dispatch(request, req_id)
        elapsed = int((time.monotonic() - start) * 1000)
        result.execution_time_ms = elapsed

        self._audit(
            "tool_executed",
            req_id,
            request,
            success=result.success,
            exit_code=getattr(result.output, "exit_code", None),
        )
        return result

    # ------------------------------------------------------------------
    # Dispatch to handler
    # ------------------------------------------------------------------

    def _dispatch(self, request: ToolCallRequest, req_id: str) -> ToolCallResult:
        if request.tool_id == "python_exec":
            return self._handle_python_exec(request, req_id)
        if request.tool_id == "knowledge_search":
            return self._handle_knowledge_search(request, req_id)
        if request.tool_id == "document_ingest":
            return self._handle_document_ingest(request, req_id)
        return ToolCallResult(
            tool_id=request.tool_id,
            request_id=req_id,
            success=False,
            output=None,
            error=f"No handler registered for tool: {request.tool_id!r}",
        )

    def _handle_python_exec(
        self, request: ToolCallRequest, req_id: str
    ) -> ToolCallResult:
        code = request.arguments.get("code", "")
        timeout = request.arguments.get("timeout_seconds", 30)
        sandbox_result = self._sandbox.execute(
            SandboxRequest(code=code, language="python", timeout_seconds=timeout, request_id=req_id)
        )
        return ToolCallResult(
            tool_id=request.tool_id,
            request_id=req_id,
            success=sandbox_result.success,
            output={
                "stdout": sandbox_result.stdout,
                "stderr": sandbox_result.stderr,
                "exit_code": sandbox_result.exit_code,
            },
            error=None if sandbox_result.success else sandbox_result.stderr,
        )

    def _handle_knowledge_search(
        self, request: ToolCallRequest, req_id: str
    ) -> ToolCallResult:
        if self._index_manager is None:
            return ToolCallResult(
                tool_id=request.tool_id,
                request_id=req_id,
                success=False,
                output=None,
                error="Retrieval engine not available.",
            )
        query = request.arguments.get("query", "")
        top_k = int(request.arguments.get("top_k", 5))
        session_id = request.arguments.get("session_id")
        results = self._index_manager.retrieve_combined(
            session_id=session_id, query=query, top_k=top_k
        )
        return ToolCallResult(
            tool_id=request.tool_id,
            request_id=req_id,
            success=True,
            output={
                "results": [
                    {
                        "text": r.text,
                        "source": r.source_path,
                        "page": r.page,
                        "score": round(r.score, 4),
                    }
                    for r in results
                ]
            },
            error=None,
        )

    def _handle_document_ingest(
        self, request: ToolCallRequest, req_id: str
    ) -> ToolCallResult:
        if self._ingestion is None:
            return ToolCallResult(
                tool_id=request.tool_id,
                request_id=req_id,
                success=False,
                output=None,
                error="Ingestion pipeline not available.",
            )
        # Accepts raw text content as a quick ingest path for the agent
        content = request.arguments.get("content", "")
        filename = request.arguments.get("filename", "agent_upload.txt")
        if not content:
            return ToolCallResult(
                tool_id=request.tool_id,
                request_id=req_id,
                success=False,
                output=None,
                error="No content provided for ingestion.",
            )
        doc = self._ingestion.ingest(content.encode("utf-8"), filename=filename)
        if self._index_manager is not None:
            self._index_manager.index_global(doc.chunks)
        return ToolCallResult(
            tool_id=request.tool_id,
            request_id=req_id,
            success=True,
            output={
                "document_id": doc.document_id,
                "chunks_created": doc.total_chunks,
            },
            error=None,
        )

    # ------------------------------------------------------------------
    # Audit helper
    # ------------------------------------------------------------------

    def _audit(self, event: str, req_id: str, request: ToolCallRequest, **kwargs: Any) -> None:
        try:
            get_audit_logger().log(
                event,
                request_id=req_id,
                tool_id=request.tool_id,
                user_id=request.user_id,
                **kwargs,
            )
        except RuntimeError:
            pass
