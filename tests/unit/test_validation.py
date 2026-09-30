"""
Tests — Validation Engine

Unit tests for all validation stages.
"""
from __future__ import annotations

import pytest

from core.control_plane.validation import ValidationEngine, ValidationLevel


def _engine() -> ValidationEngine:
    return ValidationEngine()


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_valid_pdf_upload(self):
        e = _engine()
        r = e.validate_file_upload("report.pdf", b"fake content", allowed_extensions={"pdf"})
        assert r.passed

    def test_empty_content_fails(self):
        e = _engine()
        r = e.validate_file_upload("report.pdf", b"")
        assert not r.passed
        assert any("empty" in err.message.lower() for err in r.errors)

    def test_disallowed_extension_fails(self):
        e = _engine()
        r = e.validate_file_upload("report.exe", b"data", allowed_extensions={"pdf", "txt"})
        assert not r.passed

    def test_oversized_file_fails(self):
        e = _engine()
        r = e.validate_file_upload("big.pdf", b"x" * 1000, max_bytes=500)
        assert not r.passed


# ---------------------------------------------------------------------------
# Retrieval validation
# ---------------------------------------------------------------------------

class TestRetrievalValidation:
    def test_sufficient_evidence_passes(self):
        from types import SimpleNamespace
        items = [SimpleNamespace(score=0.8), SimpleNamespace(score=0.9)]
        e = _engine()
        r = e.validate_evidence(items, min_items=1)
        assert r.passed

    def test_empty_evidence_fails(self):
        e = _engine()
        r = e.validate_evidence([], min_items=1)
        assert not r.passed


# ---------------------------------------------------------------------------
# Tool argument validation
# ---------------------------------------------------------------------------

class TestToolArgumentValidation:
    def test_valid_args_pass(self):
        e = _engine()
        schema = {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "timeout_seconds": {"type": "integer", "maximum": 60},
            },
            "required": ["code"],
        }
        r = e.validate_tool_arguments({"code": "print(1)", "timeout_seconds": 30}, schema)
        assert r.passed

    def test_missing_required_fails(self):
        e = _engine()
        schema = {"properties": {"code": {"type": "string"}}, "required": ["code"]}
        r = e.validate_tool_arguments({}, schema)
        assert not r.passed
        assert any("code" in err.field for err in r.errors)

    def test_wrong_type_fails(self):
        e = _engine()
        schema = {"properties": {"timeout_seconds": {"type": "integer"}}, "required": []}
        r = e.validate_tool_arguments({"timeout_seconds": "not-an-int"}, schema)
        assert not r.passed

    def test_exceeds_maximum_fails(self):
        e = _engine()
        schema = {
            "properties": {"timeout_seconds": {"type": "integer", "maximum": 60}},
            "required": [],
        }
        r = e.validate_tool_arguments({"timeout_seconds": 999}, schema)
        assert not r.passed


# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------

class TestOutputValidation:
    def test_valid_output_passes(self):
        from types import SimpleNamespace
        e = _engine()
        evidence = [SimpleNamespace(score=0.9)]
        r = e.validate_agent_output("Here is the answer.", evidence)
        assert r.passed

    def test_empty_answer_fails(self):
        e = _engine()
        r = e.validate_agent_output("", [])
        assert not r.passed

    def test_no_evidence_fails_closed(self):
        e = _engine()
        r = e.validate_agent_output("Some answer", [], require_evidence=True)
        assert not r.passed
        assert r.level == ValidationLevel.OUTPUT

    def test_valid_artifact_ir(self):
        e = _engine()
        r = e.validate_artifact_ir({"title": "Report", "blocks": []})
        assert r.passed

    def test_missing_title_fails(self):
        e = _engine()
        r = e.validate_artifact_ir({"blocks": []})
        assert not r.passed
