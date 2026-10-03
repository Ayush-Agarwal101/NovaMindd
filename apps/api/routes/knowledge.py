"""Knowledge base ingestion and retrieval endpoints (scope-aware)."""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from apps.api.dependencies import DocumentStoreDep, IndexManagerDep, IngestionDep

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    scope: str = "global"          # "global" | "session" | "combined"
    session_id: str | None = None


class SearchResultItem(BaseModel):
    text: str
    document_id: str
    source_path: str
    page: int
    score: float
    scope: str


class IngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    ocr_needed_pages: list[int]
    scope: str
    session_id: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile = File(...),
    scope: str = Query(default="global"),
    session_id: str | None = Query(default=None),
    ingestion: IngestionDep = ...,
    store: DocumentStoreDep = ...,
    index_mgr: IndexManagerDep = ...,
) -> IngestResponse:
    """
    Ingest a document into either the global library or a specific chat session.

    scope=global    → available everywhere, persists across restarts
    scope=session   → scoped to session_id, still persisted in SQLite
    """
    if scope == "session" and not session_id:
        raise HTTPException(
            status_code=400,
            detail="session_id is required when scope=session",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    doc = ingestion.ingest(data, filename=file.filename or "upload")

    # Persist chunks to SQLite so they survive restarts + navigation
    store.save_document(doc, scope=scope, session_id=session_id)

    # Add to the appropriate in-memory engine
    if scope == "global":
        index_mgr.index_global(doc.chunks)
    else:
        index_mgr.index_session(session_id, doc.chunks)  # type: ignore[arg-type]

    return IngestResponse(
        document_id=doc.document_id,
        chunks_created=doc.total_chunks,
        ocr_needed_pages=doc.metadata.get("ocr_needed_pages", []),
        scope=scope,
        session_id=session_id,
    )


@router.post("/search", response_model=list[SearchResultItem])
async def search(
    body: SearchRequest,
    index_mgr: IndexManagerDep,
    store: DocumentStoreDep,
) -> list[SearchResultItem]:
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if body.scope == "global":
        evidence = index_mgr.retrieve_global(body.query, top_k=body.top_k)
    elif body.scope == "session":
        if not body.session_id:
            raise HTTPException(
                status_code=400,
                detail="session_id is required for scope=session",
            )
        evidence = index_mgr.retrieve_session(
            body.session_id, body.query, top_k=body.top_k
        )
    else:  # "combined"
        evidence = index_mgr.retrieve_combined(
            body.session_id, body.query, top_k=body.top_k
        )

    # Tag each result with the scope of its source document
    doc_scopes: dict[str, str] = {}
    for row in store.list_documents():
        doc_scopes[row["document_id"]] = row["scope"]

    return [
        SearchResultItem(
            text=e.text,
            document_id=e.document_id,
            source_path=e.source_path,
            page=e.page,
            score=e.score,
            scope=doc_scopes.get(e.document_id, "unknown"),
        )
        for e in evidence
    ]
