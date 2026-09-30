"""
NovaMindd — Provenance Service

Records the full lineage of every output:
  user request → evidence → model → tool actions → validation → artifact.

Every output can be traced back to its contributing evidence and execution steps.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from core.logging import get_audit_logger, get_logger

logger = get_logger(__name__)


class ProvenanceStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    FAIL_CLOSED = "fail_closed"


@dataclass
class EvidenceRef:
    document_id: str
    source_path: str
    page: int
    chunk_id: str
    score: float


@dataclass
class ToolExecution:
    tool_id: str
    request_id: str
    success: bool
    error: str | None = None


@dataclass
class ValidationRecord:
    step: str
    passed: bool
    detail: str | None = None


@dataclass
class ArtifactRecord:
    artifact_type: str   # docx | xlsx | pptx | json
    artifact_id: str
    byte_size: int
    checksum: str        # SHA-256 hex


@dataclass
class ProvenanceRecord:
    """
    Complete provenance for a single NovaMindd execution.
    Attach this to every output artifact.
    """
    request_id: str
    user: str
    task: str
    model_id: str
    model_name: str
    timestamp: str
    status: ProvenanceStatus
    evidence: list[EvidenceRef] = field(default_factory=list)
    tools_requested: list[str] = field(default_factory=list)
    tools_authorized: list[str] = field(default_factory=list)
    tool_executions: list[ToolExecution] = field(default_factory=list)
    validation: list[ValidationRecord] = field(default_factory=list)
    artifact: ArtifactRecord | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ProvenanceService:
    """Build and persist ProvenanceRecord objects."""

    def __init__(self) -> None:
        self._records: dict[str, ProvenanceRecord] = {}

    def create(
        self,
        *,
        user: str,
        task: str,
        model_id: str,
        model_name: str,
        request_id: str | None = None,
    ) -> ProvenanceRecord:
        rid = request_id or str(uuid.uuid4())
        record = ProvenanceRecord(
            request_id=rid,
            user=user,
            task=task[:200],
            model_id=model_id,
            model_name=model_name,
            timestamp=datetime.now(UTC).isoformat(),
            status=ProvenanceStatus.PENDING,
        )
        self._records[rid] = record
        return record

    def finalise(
        self,
        record: ProvenanceRecord,
        *,
        status: ProvenanceStatus,
        artifact: ArtifactRecord | None = None,
    ) -> None:
        record.status = status
        record.artifact = artifact
        self._persist(record)

    def get(self, request_id: str) -> ProvenanceRecord | None:
        return self._records.get(request_id)

    def _persist(self, record: ProvenanceRecord) -> None:
        try:
            get_audit_logger().log("provenance_finalised", **record.to_dict())
        except RuntimeError:
            pass
        logger.info(
            "provenance_record",
            request_id=record.request_id,
            status=record.status.value,
        )


def compute_checksum(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()
