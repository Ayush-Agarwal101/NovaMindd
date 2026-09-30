"""
Tests — Evaluation: Retrieval Quality

Measures retrieval recall and exact-match performance on a synthetic corpus.
"""
from __future__ import annotations

import pytest

from core.retrieval.bm25_index import BM25Index
from core.retrieval.engine import RetrievalEngine
from core.retrieval.ingestion import DocumentChunk


def _chunk(cid: str, text: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=cid,
        document_id="eval-corpus",
        source_path="corpus.pdf",
        page_number=int(cid.split("-")[1]),
        chunk_index=int(cid.split("-")[1]),
        text=text,
    )


# Synthetic corpus covering industrial SOP terminology
CORPUS = [
    _chunk("c-0",  "SOP-47: Valve Inspection Procedure. Check for wear on gate valve VLV-001."),
    _chunk("c-1",  "SOP-12: Pressure Relief Protocol. Maximum operating pressure 12 bar."),
    _chunk("c-2",  "SOP-99: Emergency Shutdown. Activate ESD panel in building 3."),
    _chunk("c-3",  "Scheduled maintenance for compressor unit CMP-003 due Q2."),
    _chunk("c-4",  "Torque specifications for flange assembly: 45 Nm grade 8.8 bolts."),
    _chunk("c-5",  "Inspection of heat exchanger HX-007: fouling factor 0.0002."),
    _chunk("c-6",  "Safety data sheet for chemical CHEM-14: avoid skin contact."),
    _chunk("c-7",  "Calibration record for pressure transmitter PT-201: 4-20 mA output."),
]

EVAL_CASES = [
    # (query, expected_top_chunk_id)
    ("SOP-47 valve inspection VLV-001", "c-0"),
    ("pressure relief maximum operating pressure", "c-1"),
    ("emergency shutdown ESD", "c-2"),
    ("compressor maintenance CMP-003", "c-3"),
    ("flange torque bolt specification", "c-4"),
    ("heat exchanger HX-007 fouling", "c-5"),
    ("safety data sheet CHEM-14", "c-6"),
    ("pressure transmitter PT-201 calibration", "c-7"),
]


class TestBM25ExactRetrieval:
    """BM25 should be very strong on exact SOP identifiers and equipment IDs."""

    def setup_method(self):
        self.index = BM25Index()
        self.index.add(CORPUS)

    def test_recall_at_1(self):
        hits = 0
        for query, expected_id in EVAL_CASES:
            results = self.index.search(query, top_k=1)
            if results and results[0].chunk.chunk_id == expected_id:
                hits += 1
        recall = hits / len(EVAL_CASES)
        print(f"\nBM25 Recall@1: {recall:.2f} ({hits}/{len(EVAL_CASES)})")
        assert recall >= 0.75, f"BM25 Recall@1 {recall:.2f} below threshold 0.75"

    def test_recall_at_3(self):
        hits = 0
        for query, expected_id in EVAL_CASES:
            results = self.index.search(query, top_k=3)
            found_ids = [r.chunk.chunk_id for r in results]
            if expected_id in found_ids:
                hits += 1
        recall = hits / len(EVAL_CASES)
        print(f"\nBM25 Recall@3: {recall:.2f} ({hits}/{len(EVAL_CASES)})")
        assert recall >= 0.875, f"BM25 Recall@3 {recall:.2f} below threshold 0.875"


class TestHybridRRFMerge:
    """RRF merge should keep all unique results and maintain relative order."""

    def test_rrf_scores_are_positive(self):
        from core.retrieval.bm25_index import BM25Result
        from core.retrieval.vector_index import VectorResult

        bm25 = [BM25Result(chunk=CORPUS[0], score=10.0)]
        vec = [VectorResult(chunk=CORPUS[1], score=0.9)]
        merged = RetrievalEngine._rrf_merge(bm25, vec)
        assert all(m.score > 0 for m in merged)

    def test_rrf_deduplicates(self):
        from core.retrieval.bm25_index import BM25Result
        from core.retrieval.vector_index import VectorResult

        c = CORPUS[0]
        bm25 = [BM25Result(chunk=c, score=5.0)]
        vec = [VectorResult(chunk=c, score=0.9)]
        merged = RetrievalEngine._rrf_merge(bm25, vec)
        ids = [m.chunk.chunk_id for m in merged]
        assert len(ids) == len(set(ids)), "RRF should deduplicate chunks"
