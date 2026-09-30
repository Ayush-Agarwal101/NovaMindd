"""
Tests — End-to-End Provenance

Verifies that a completed agent run produces a traceable provenance record
linking: request → evidence → model → tool actions → artifact.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.provenance.service import (
    ArtifactRecord,
    EvidenceRef,
    ProvenanceRecord,
    ProvenanceService,
    ProvenanceStatus,
    ToolExecution,
    ValidationRecord,
    compute_checksum,
)


def _service() -> ProvenanceService:
    return ProvenanceService()


def test_create_provenance_record():
    svc = _service()
    record = svc.create(
        user="operator-1",
        task="Inspect VLV-001",
        model_id="general",
        model_name="llama3:3b",
    )
    assert record.request_id is not None
    assert record.status == ProvenanceStatus.PENDING
    assert record.user == "operator-1"


def test_finalise_provenance_completed():
    svc = _service()
    record = svc.create(
        user="operator-1",
        task="Generate Q1 report",
        model_id="general",
        model_name="llama3:3b",
    )
    record.evidence.append(
        EvidenceRef(
            document_id="doc-001",
            source_path="inspection_report.pdf",
            page=3,
            chunk_id="abc123",
            score=0.91,
        )
    )
    record.tool_executions.append(
        ToolExecution(tool_id="python_exec", request_id=record.request_id, success=True)
    )
    record.validation.append(
        ValidationRecord(step="output", passed=True, detail="Schema valid")
    )
    artifact_data = b"PK fake docx content"
    artifact = ArtifactRecord(
        artifact_type="docx",
        artifact_id="art-001",
        byte_size=len(artifact_data),
        checksum=compute_checksum(artifact_data),
    )
    svc.finalise(record, status=ProvenanceStatus.COMPLETED, artifact=artifact)

    assert record.status == ProvenanceStatus.COMPLETED
    assert record.artifact is not None
    assert len(record.evidence) == 1
    assert len(record.tool_executions) == 1
    assert len(record.validation) == 1


def test_provenance_to_dict_is_serialisable():
    svc = _service()
    record = svc.create(
        user="u1",
        task="task",
        model_id="m1",
        model_name="llama",
    )
    d = record.to_dict()
    import json
    # Must be JSON-serialisable
    serialised = json.dumps(d)
    assert "request_id" in serialised
    assert "status" in serialised


def test_compute_checksum_deterministic():
    data = b"fixed content"
    assert compute_checksum(data) == compute_checksum(data)
    assert compute_checksum(b"a") != compute_checksum(b"b")


def test_provenance_retrieval():
    svc = _service()
    record = svc.create(
        user="u1", task="t", model_id="m", model_name="m"
    )
    fetched = svc.get(record.request_id)
    assert fetched is not None
    assert fetched.request_id == record.request_id


def test_provenance_fail_closed_status():
    svc = _service()
    record = svc.create(
        user="u1", task="insufficient evidence query", model_id="m", model_name="m"
    )
    svc.finalise(record, status=ProvenanceStatus.FAIL_CLOSED)
    assert record.status == ProvenanceStatus.FAIL_CLOSED
    assert record.artifact is None
