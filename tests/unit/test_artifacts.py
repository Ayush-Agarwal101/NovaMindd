"""
Tests — Artifact Renderers

Verifies DOCX, XLSX, and PPTX rendering from a DocumentIR.
"""
from __future__ import annotations

import io
import pytest

from core.artifacts.ir import DocumentIR
from core.artifacts.docx_renderer import DOCXRenderer
from core.artifacts.xlsx_renderer import XLSXRenderer
from core.artifacts.pptx_renderer import PPTXRenderer


def _sample_ir() -> DocumentIR:
    doc = DocumentIR(
        title="Inspection Report Q1",
        author="Test Operator",
        evidence_refs=[
            {"document_id": "doc-001", "page": 3, "score": 0.92}
        ],
    )
    doc.add_heading("Executive Summary", level=1)
    doc.add_paragraph("This report summarises Q1 inspection findings.")
    doc.add_heading("Findings", level=2)
    doc.add_list(["Finding 1: Valve wear detected", "Finding 2: Pressure within limits"])
    doc.add_table(
        [
            ["Equipment ID", "Status", "Action Required"],
            ["VLV-001", "Wear detected", "Schedule replacement"],
            ["PMP-007", "Normal", "No action"],
        ],
        header_row=True,
    )
    doc.add_heading("Recommendations", level=2)
    doc.add_paragraph("Replace VLV-001 within 30 days.")
    return doc


def test_docx_renders_to_bytes():
    pytest.importorskip("docx")
    data = DOCXRenderer().render(_sample_ir())
    assert isinstance(data, bytes)
    assert len(data) > 0
    # DOCX is a ZIP archive; check magic bytes
    assert data[:2] == b"PK"


def test_xlsx_renders_to_bytes():
    pytest.importorskip("openpyxl")
    data = XLSXRenderer().render(_sample_ir())
    assert isinstance(data, bytes)
    assert len(data) > 0
    assert data[:2] == b"PK"


def test_pptx_renders_to_bytes():
    pytest.importorskip("pptx")
    data = PPTXRenderer().render(_sample_ir())
    assert isinstance(data, bytes)
    assert len(data) > 0
    assert data[:2] == b"PK"


def test_document_ir_roundtrip():
    """DocumentIR serialises to dict and deserialises correctly."""
    doc = _sample_ir()
    d = doc.to_dict()
    restored = DocumentIR.from_dict(d)
    assert restored.title == doc.title
    assert len(restored.blocks) == len(doc.blocks)
    assert len(restored.evidence_refs) == len(doc.evidence_refs)


def test_document_ir_add_helpers():
    doc = DocumentIR(title="Test")
    doc.add_heading("H1", level=1)
    doc.add_paragraph("Para 1")
    doc.add_list(["a", "b"])
    doc.add_table([["Col A", "Col B"], ["1", "2"]])
    assert len(doc.blocks) == 4
