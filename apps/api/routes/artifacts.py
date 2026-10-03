"""Artifact generation endpoints (DOCX, XLSX, PPTX, TXT, PDF)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Any

from core.artifacts.ir import DocumentIR, DocumentBlock, BlockType, TableCell

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


class GenerateRequest(BaseModel):
    format: str           # docx | xlsx | pptx | txt | pdf
    document_ir: dict[str, Any]


CONTENT_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt":  "text/plain; charset=utf-8",
    "pdf":  "application/pdf",
}

EXTENSIONS = {"docx": "docx", "xlsx": "xlsx", "pptx": "pptx", "txt": "txt", "pdf": "pdf"}


@router.post("/generate")
async def generate_artifact(body: GenerateRequest) -> Response:
    fmt = body.format.lower()
    if fmt not in CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format {fmt!r}. Choose from: {list(CONTENT_TYPES)}",
        )

    try:
        doc_ir = DocumentIR.from_dict(body.document_ir)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid document IR: {exc}")

    try:
        data = _render(fmt, doc_ir)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    ext = EXTENSIONS[fmt]
    filename = f"{doc_ir.title.replace(' ', '_')}.{ext}"
    return Response(
        content=data,
        media_type=CONTENT_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download/{request_id}/{fmt}")
async def download_agent_output(request_id: str, fmt: str) -> FileResponse:
    """Download a previously saved agent output file from output/."""
    fmt = fmt.lower()
    if fmt not in ("txt", "pdf", "docx"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt!r}")
    path = Path("output") / f"{request_id}.{fmt}"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file not found")
    return FileResponse(
        path=str(path),
        media_type=CONTENT_TYPES.get(fmt, "application/octet-stream"),
        filename=path.name,
    )


def _render(fmt: str, doc_ir: DocumentIR) -> bytes:
    if fmt == "docx":
        from core.artifacts.docx_renderer import DOCXRenderer
        return DOCXRenderer().render(doc_ir)
    if fmt == "xlsx":
        from core.artifacts.xlsx_renderer import XLSXRenderer
        return XLSXRenderer().render(doc_ir)
    if fmt == "pptx":
        from core.artifacts.pptx_renderer import PPTXRenderer
        return PPTXRenderer().render(doc_ir)
    if fmt == "txt":
        from core.artifacts.txt_renderer import TXTRenderer
        return TXTRenderer().render(doc_ir)
    if fmt == "pdf":
        from core.artifacts.pdf_renderer import PDFRenderer
        return PDFRenderer().render(doc_ir)
    raise RuntimeError(f"No renderer for format: {fmt!r}")
