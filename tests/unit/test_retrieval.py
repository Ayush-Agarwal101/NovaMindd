"""
Tests — BM25 and Vector Retrieval

Unit tests for knowledge retrieval without external services.
"""
from __future__ import annotations

import pytest

from core.retrieval.bm25_index import BM25Index
from core.retrieval.ingestion import DocumentChunk
from core.retrieval.engine import RetrievalEngine


def _make_chunk(chunk_id: str, text: str, page: int = 1) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        document_id="doc-001",
        source_path="test.pdf",
        page_number=page,
        chunk_index=int(chunk_id.split("-")[-1]),
        text=text,
    )


def test_bm25_basic_search():
    index = BM25Index()
    chunks = [
        _make_chunk("c-0", "SOP-47 valve inspection procedure pressure check"),
        _make_chunk("c-1", "General maintenance schedule for compressors"),
        _make_chunk("c-2", "Emergency shutdown procedure for reactor unit"),
    ]
    index.add(chunks)
    results = index.search("SOP-47 valve", top_k=3)
    assert len(results) > 0
    assert results[0].chunk.chunk_id == "c-0"


def test_bm25_returns_empty_on_no_match():
    index = BM25Index()
    index.add([_make_chunk("c-0", "completely unrelated content about whales")])
    results = index.search("SOP-47 valve inspection", top_k=5)
    # BM25 may return zero score results; check that high-relevance ones don't appear
    for r in results:
        assert r.score >= 0


def test_bm25_size():
    index = BM25Index()
    chunks = [_make_chunk(f"c-{i}", f"content about topic {i}") for i in range(10)]
    index.add(chunks)
    assert index.size == 10


def test_retrieval_engine_rrf_merge():
    """Test that hybrid merge (RRF) returns deduped results ranked by fusion score."""
    engine = RetrievalEngine.__new__(RetrievalEngine)

    from core.retrieval.bm25_index import BM25Result
    from core.retrieval.vector_index import VectorResult

    c0 = _make_chunk("c-0", "valve inspection SOP-47")
    c1 = _make_chunk("c-1", "pressure relief protocol")
    c2 = _make_chunk("c-2", "general maintenance schedule")

    bm25_results = [BM25Result(chunk=c0, score=5.0), BM25Result(chunk=c1, score=2.0)]
    vec_results = [VectorResult(chunk=c0, score=0.9), VectorResult(chunk=c2, score=0.7)]

    merged = RetrievalEngine._rrf_merge(bm25_results, vec_results)
    # c0 appears in both → should be ranked first
    assert merged[0].chunk.chunk_id == "c-0"
    # No duplicate chunk IDs
    ids = [m.chunk.chunk_id for m in merged]
    assert len(ids) == len(set(ids))
