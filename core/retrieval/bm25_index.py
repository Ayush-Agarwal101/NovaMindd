"""
NovaMindd — BM25 Index

Exact and keyword-based retrieval over document chunks.
Useful for SOP IDs, equipment tags, reference numbers, and exact terminology.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from core.logging import get_logger
from core.retrieval.ingestion import DocumentChunk

logger = get_logger(__name__)


@dataclass
class BM25Result:
    chunk: DocumentChunk
    score: float


class BM25Index:
    """In-process BM25 index over DocumentChunk objects."""

    def __init__(self) -> None:
        self._chunks: list[DocumentChunk] = []
        self._index: BM25Okapi | None = None

    def add(self, chunks: list[DocumentChunk]) -> None:
        self._chunks.extend(chunks)
        self._rebuild()
        logger.debug("bm25_indexed", total_chunks=len(self._chunks))

    def search(self, query: str, top_k: int = 20) -> list[BM25Result]:
        if self._index is None or not self._chunks:
            return []
        tokens = query.lower().split()
        scores = self._index.get_scores(tokens)
        indexed = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )[:top_k]
        return [
            BM25Result(chunk=self._chunks[i], score=float(s))
            for i, s in indexed
            if s > 0
        ]

    def _rebuild(self) -> None:
        corpus = [c.text.lower().split() for c in self._chunks]
        self._index = BM25Okapi(corpus)

    @property
    def size(self) -> int:
        return len(self._chunks)
