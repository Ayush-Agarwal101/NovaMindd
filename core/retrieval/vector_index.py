"""
NovaMindd — Vector Index

Semantic retrieval using sentence-transformers embeddings stored in-process.
Production deployments should swap this for pgvector via the same interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from core.logging import get_logger
from core.retrieval.ingestion import DocumentChunk

logger = get_logger(__name__)


@dataclass
class VectorResult:
    chunk: DocumentChunk
    score: float      # cosine similarity 0–1


class VectorIndex:
    """
    In-process dense vector index.

    Embeds chunks with a local sentence-transformer model and retrieves by
    cosine similarity. Suitable for development and small deployments.
    Replace with pgvector + asyncpg for production scale.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None   # lazy-loaded
        self._chunks: list[DocumentChunk] = []
        self._matrix: np.ndarray | None = None   # shape (N, D)

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
                logger.info("embedding_model_loaded", model=self._model_name)
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers is required for vector search"
                )
        return self._model

    def add(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return
        model = self._get_model()
        texts = [c.text for c in chunks]
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        self._chunks.extend(chunks)
        if self._matrix is None:
            self._matrix = embeddings
        else:
            self._matrix = np.vstack([self._matrix, embeddings])
        logger.debug("vector_indexed", added=len(chunks), total=len(self._chunks))

    def search(self, query: str, top_k: int = 20) -> list[VectorResult]:
        if self._matrix is None or not self._chunks:
            return []
        model = self._get_model()
        q_emb = model.encode([query], normalize_embeddings=True)[0]
        scores = self._matrix.dot(q_emb)          # cosine (already normalised)
        top_idx = np.argsort(scores)[::-1][:top_k]
        return [
            VectorResult(chunk=self._chunks[i], score=float(scores[i]))
            for i in top_idx
            if scores[i] > 0
        ]

    @property
    def size(self) -> int:
        return len(self._chunks)
