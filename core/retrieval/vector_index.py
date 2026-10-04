"""
NovaMindd — Vector Index

Semantic retrieval using sentence-transformers embeddings stored in-process.
Production deployments should swap this for pgvector via the same interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.logging import get_logger
from core.retrieval.ingestion import DocumentChunk

logger = get_logger(__name__)

# Project root is three levels up from this file (core/retrieval/vector_index.py)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class VectorResult:
    chunk: DocumentChunk
    score: float      # cosine similarity 0–1


class VectorIndex:
    """
    In-process dense vector index.

    Embeds chunks with a local sentence-transformer model and retrieves by
    cosine similarity.  The model is stored under ``models_dir`` (default
    ``models/embeddings/<model-slug>``).  On first use it is downloaded from
    HuggingFace and saved there; afterwards it is always loaded from disk so
    the application works fully offline.

    Replace with pgvector + asyncpg for production scale.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        models_dir: str = "models/embeddings",
    ) -> None:
        self._model_name = model_name
        # Derive a filesystem-safe subdirectory name from the model id,
        # e.g. "sentence-transformers/all-MiniLM-L6-v2" → "sentence-transformers--all-MiniLM-L6-v2"
        self._local_path: Path = (
            _PROJECT_ROOT / models_dir / model_name.replace("/", "--")
        )
        self._model = None   # lazy-loaded
        self._chunks: list[DocumentChunk] = []
        self._matrix: np.ndarray | None = None   # shape (N, D)

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers is required for vector search"
                )

            if self._local_path.exists():
                # Model already saved locally — load without any network access.
                logger.info(
                    "embedding_model_loaded_local",
                    path=str(self._local_path),
                )
                self._model = SentenceTransformer(
                    str(self._local_path), local_files_only=True
                )
            else:
                # First run: download from HuggingFace and persist to disk.
                logger.info(
                    "embedding_model_downloading",
                    model=self._model_name,
                    destination=str(self._local_path),
                )
                self._model = SentenceTransformer(self._model_name)
                self._local_path.mkdir(parents=True, exist_ok=True)
                self._model.save(str(self._local_path))
                logger.info(
                    "embedding_model_saved",
                    path=str(self._local_path),
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
