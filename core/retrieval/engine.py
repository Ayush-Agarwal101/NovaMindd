"""
NovaMindd — Retrieval Engine

Combines BM25 + vector search with optional reranking into a single
hybrid retrieval call. Returns ranked evidence with source metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.config import get_config
from core.logging import get_logger
from core.retrieval.bm25_index import BM25Index, BM25Result
from core.retrieval.ingestion import DocumentChunk
from core.retrieval.vector_index import VectorIndex, VectorResult

logger = get_logger(__name__)


@dataclass
class EvidenceItem:
    chunk: DocumentChunk
    score: float
    source: str            # "bm25" | "vector" | "rerank"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.chunk.text

    @property
    def page(self) -> int:
        return self.chunk.page_number

    @property
    def document_id(self) -> str:
        return self.chunk.document_id

    @property
    def source_path(self) -> str:
        return self.chunk.source_path


class RetrievalEngine:
    """
    Hybrid BM25 + dense retrieval with optional cross-encoder reranking.

    Usage:
        engine = RetrievalEngine()
        engine.index(chunks)
        evidence = engine.retrieve("SOP-47 valve inspection procedure")
    """

    def __init__(
        self,
        bm25: BM25Index | None = None,
        vector: VectorIndex | None = None,
    ) -> None:
        self._cfg = get_config().retrieval
        self._bm25 = bm25 or BM25Index()
        self._vector = vector or VectorIndex(self._cfg.embedding_model)
        self._reranker = None   # lazy-loaded

    def index(self, chunks: list[DocumentChunk]) -> None:
        """Add chunks to both indexes."""
        self._bm25.add(chunks)
        self._vector.add(chunks)
        logger.info("retrieval_indexed", chunks=len(chunks))

    def retrieve(self, query: str, top_k: int | None = None) -> list[EvidenceItem]:
        """
        Retrieve evidence for a query using hybrid search.

        Returns up to `top_k` items after reranking (defaults to config value).
        """
        k_final = top_k or self._cfg.top_k_rerank
        k_bm25 = self._cfg.top_k_bm25
        k_vec = self._cfg.top_k_vector

        bm25_results = self._bm25.search(query, top_k=k_bm25)
        vec_results = self._vector.search(query, top_k=k_vec)

        # Merge and deduplicate by chunk_id (reciprocal rank fusion)
        merged = self._rrf_merge(bm25_results, vec_results)

        if self._should_rerank():
            merged = self._rerank(query, merged, k_final)
        else:
            merged = merged[:k_final]

        logger.debug(
            "retrieval_complete",
            query_preview=query[:80],
            returned=len(merged),
        )
        return merged

    # ------------------------------------------------------------------
    # Merge strategy: Reciprocal Rank Fusion
    # ------------------------------------------------------------------

    @staticmethod
    def _rrf_merge(
        bm25: list[BM25Result],
        vec: list[VectorResult],
        k: int = 60,
    ) -> list[EvidenceItem]:
        scores: dict[str, float] = {}
        chunks: dict[str, DocumentChunk] = {}

        for rank, r in enumerate(bm25, start=1):
            cid = r.chunk.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            chunks[cid] = r.chunk

        for rank, r in enumerate(vec, start=1):
            cid = r.chunk.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            chunks[cid] = r.chunk

        ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            EvidenceItem(chunk=chunks[cid], score=score, source="hybrid")
            for cid, score in ordered
        ]

    # ------------------------------------------------------------------
    # Reranking
    # ------------------------------------------------------------------

    def _should_rerank(self) -> bool:
        try:
            from sentence_transformers import CrossEncoder  # noqa: F401
            return True
        except ImportError:
            return False

    def _rerank(
        self,
        query: str,
        items: list[EvidenceItem],
        top_k: int,
    ) -> list[EvidenceItem]:
        try:
            from sentence_transformers import CrossEncoder
            if self._reranker is None:
                self._reranker = CrossEncoder(self._cfg.reranker_model)
            pairs = [(query, item.text) for item in items]
            scores = self._reranker.predict(pairs)
            for item, score in zip(items, scores):
                item.score = float(score)
                item.source = "rerank"
            items.sort(key=lambda x: x.score, reverse=True)
            return items[:top_k]
        except Exception as exc:
            logger.warning("rerank_failed", error=str(exc))
            return items[:top_k]
