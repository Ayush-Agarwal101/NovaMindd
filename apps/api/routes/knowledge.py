"""Knowledge base ingestion and retrieval endpoints."""
from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from apps.api.dependencies import IngestionDep, RetrievalDep

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class SearchResultItem(BaseModel):
    text: str
    document_id: str
    source_path: str
    page: int
    score: float


class IngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    ocr_needed_pages: list[int]


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    file: UploadFile = File(...),
    ingestion: IngestionDep = ...,
    retrieval: RetrievalDep = ...,
) -> IngestResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    doc = ingestion.ingest(data, filename=file.filename or "upload")
    retrieval.index(doc.chunks)

    return IngestResponse(
        document_id=doc.document_id,
        chunks_created=doc.total_chunks,
        ocr_needed_pages=doc.metadata.get("ocr_needed_pages", []),
    )


@router.post("/search", response_model=list[SearchResultItem])
async def search(body: SearchRequest, retrieval: RetrievalDep) -> list[SearchResultItem]:
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    evidence = retrieval.retrieve(body.query, top_k=body.top_k)
    return [
        SearchResultItem(
            text=e.text,
            document_id=e.document_id,
            source_path=e.source_path,
            page=e.page,
            score=e.score,
        )
        for e in evidence
    ]
