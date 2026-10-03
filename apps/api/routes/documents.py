"""
NovaMindd — Global Document Library API

CRUD endpoints for the shared, persistent document library.
Documents uploaded here are available to every chat session.
Accepts PDF, plain-text, Markdown, and common image formats.
"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from apps.api.dependencies import DocumentStoreDep, IndexManagerDep, IngestionDep

router = APIRouter(prefix="/documents", tags=["documents"])


# ── Response schemas ──────────────────────────────────────────────────────────

class DocumentMeta(BaseModel):
    document_id: str
    filename: str
    doc_type: str
    scope: str
    session_id: str | None
    page_count: int
    chunk_count: int
    created_at: float


class IngestDocumentResponse(BaseModel):
    document_id: str
    filename: str
    chunks_created: int
    ocr_needed_pages: list[int]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestDocumentResponse)
async def ingest_global_document(
    file: UploadFile = File(...),
    ingestion: IngestionDep = ...,
    store: DocumentStoreDep = ...,
    index_mgr: IndexManagerDep = ...,
) -> IngestDocumentResponse:
    """
    Upload a document into the global library.
    Persists to SQLite and indexes into the global retrieval engine.
    Survives server restarts and navigation changes.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    doc = ingestion.ingest(data, filename=file.filename or "upload")

    # Persist to SQLite
    store.save_document(doc, scope="global")

    # Index into global in-memory engine
    index_mgr.index_global(doc.chunks)

    return IngestDocumentResponse(
        document_id=doc.document_id,
        filename=doc.source_path,
        chunks_created=doc.total_chunks,
        ocr_needed_pages=doc.metadata.get("ocr_needed_pages", []),
    )


@router.get("/", response_model=list[DocumentMeta])
async def list_global_documents(store: DocumentStoreDep) -> list[DocumentMeta]:
    """List all documents in the global library."""
    rows = store.list_documents(scope="global")
    return [
        DocumentMeta(
            document_id=r["document_id"],
            filename=r["filename"],
            doc_type=r["doc_type"],
            scope=r["scope"],
            session_id=r.get("session_id"),
            page_count=r["page_count"],
            chunk_count=r["chunk_count"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.delete("/{document_id}", status_code=204)
async def delete_global_document(
    document_id: str,
    store: DocumentStoreDep,
) -> None:
    """
    Remove a document from the global library.
    The in-memory index is NOT updated (requires restart to fully purge);
    this is acceptable for the offline-first use case.
    """
    if not store.delete_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found")
