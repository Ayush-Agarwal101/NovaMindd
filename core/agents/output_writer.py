"""
NovaMindd — Agent Output Writer

Converts a completed AgentResponse into DocumentIR and saves .txt and .pdf
files to the output/ directory.

The output directory is created automatically if it does not exist.
Files are named:  output/<request_id>.<ext>
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from core.artifacts.ir import DocumentIR, BlockType
from core.logging import get_logger

if TYPE_CHECKING:
    from core.agents.planner import AgentResponse

logger = get_logger(__name__)

OUTPUT_DIR = Path("output")


def _build_ir(response: "AgentResponse", task: str) -> DocumentIR:
    """Build a DocumentIR from an AgentResponse."""
    ir = DocumentIR(
        title=_truncate(task, 80),
        author="NovaMindd Agent",
        metadata={
            "request_id": response.request_id,
            "status": response.status.value,
            "generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        },
    )

    # ── Header metadata block ──────────────────────────────────────────
    ir.add_heading("Task", level=2)
    ir.add_paragraph(task)

    meta_lines = [
        f"Request ID: {response.request_id or '—'}",
        f"Status: {response.status.value}",
        f"Generated: {ir.metadata['generated_at']}",
        f"Evidence sources: {len(response.evidence)}",
        f"Tool calls: {len(response.tool_calls)}",
    ]
    if response.sub_steps:
        models_used = list(dict.fromkeys(s.model_name for s in response.sub_steps))
        meta_lines.append(f"Models used: {', '.join(models_used)}")
    ir.add_list(meta_lines)

    # ── Answer ─────────────────────────────────────────────────────────
    if response.answer:
        ir.add_heading("Answer", level=1)
        # Split on double-newlines to preserve paragraph structure
        paragraphs = [p.strip() for p in response.answer.split("\n\n") if p.strip()]
        for para in paragraphs:
            ir.add_paragraph(para)

    # ── Sub-step breakdown ─────────────────────────────────────────────
    if response.sub_steps and len(response.sub_steps) > 1:
        ir.add_heading("Reasoning Steps", level=1)
        for step in response.sub_steps:
            ir.add_heading(
                f"Step {step.step_index} — {step.capability.title()} ({step.model_name})",
                level=2,
            )
            for para in (step.content or "").split("\n\n"):
                if para.strip():
                    ir.add_paragraph(para.strip())

    # ── Tool call results ──────────────────────────────────────────────
    if response.tool_calls:
        ir.add_heading("Tool Call Results", level=1)
        for tc in response.tool_calls:
            ir.add_heading(
                f"{tc['tool_id']} — {'✓' if tc['success'] else '✗'}",
                level=2,
            )
            if tc.get("output"):
                import json
                ir.add_paragraph(json.dumps(tc["output"], indent=2))
            if tc.get("error"):
                ir.add_paragraph(f"Error: {tc['error']}")

    # ── Evidence appendix ──────────────────────────────────────────────
    if response.evidence:
        ir.evidence_refs = [
            {
                "document_id": e.document_id,
                "page": e.page,
                "score": round(e.score, 4),
            }
            for e in response.evidence
        ]

    return ir


def save_agent_output(
    response: "AgentResponse",
    task: str,
    formats: list[str] | None = None,
) -> dict[str, str]:
    """
    Save the agent response to output/<request_id>.txt and/or .pdf.

    Parameters
    ----------
    response : AgentResponse
        Completed (or fail-closed) agent response.
    task : str
        The original task string (used as the document title).
    formats : list[str] | None
        Which formats to write.  Defaults to ["txt", "pdf"].

    Returns
    -------
    dict mapping format → absolute file path  (only successfully written files)
    """
    if formats is None:
        formats = ["txt", "pdf"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    req_id = response.request_id or f"run_{int(time.time())}"
    ir = _build_ir(response, task)
    saved: dict[str, str] = {}

    for fmt in formats:
        try:
            data = _render(fmt, ir)
            out_path = OUTPUT_DIR / f"{req_id}.{fmt}"
            out_path.write_bytes(data)
            saved[fmt] = str(out_path.resolve())
            logger.info(
                "agent_output_saved",
                format=fmt,
                path=str(out_path),
                request_id=req_id,
            )
        except Exception as exc:
            logger.warning(
                "agent_output_save_failed",
                format=fmt,
                request_id=req_id,
                error=str(exc),
            )

    return saved


def _render(fmt: str, ir: DocumentIR) -> bytes:
    if fmt == "txt":
        from core.artifacts.txt_renderer import TXTRenderer
        return TXTRenderer().render(ir)
    if fmt == "pdf":
        from core.artifacts.pdf_renderer import PDFRenderer
        return PDFRenderer().render(ir)
    if fmt == "docx":
        from core.artifacts.docx_renderer import DOCXRenderer
        return DOCXRenderer().render(ir)
    raise ValueError(f"Unknown output format: {fmt!r}")


def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"
