"""
NovaMindd — Index Manager

Manages two in-memory retrieval engines:
  • global_engine  – loaded from all 'global' scope documents at startup
  • session engines – keyed by session_id, loaded on first access

This is the offline-capable layer: on startup it rehydrates from SQLite so
previously ingested documents are immediately searchable without re-uploading.
"""
from __future__ import annotations

import threading

from core.logging import get_logger
from core.retrieval.bm25_index import BM25Index
from core.retrieval.document_store import DocumentStore
from core.retrieval.engine import EvidenceItem, RetrievalEngine
from core.retrieval.ingestion import DocumentChunk
from core.retrieval.vector_index import VectorIndex

logger = get_logger(__name__)


def _make_engine() -> RetrievalEngine:
    from core.config import get_config
    cfg = get_config().retrieval
    return RetrievalEngine(
        bm25=BM25Index(),
        vector=VectorIndex(cfg.embedding_model),
    )


class IndexManager:
    """
    Manages separate RetrievalEngines per scope.

    Thread-safe. Rehydrates from the DocumentStore on startup.
    """

    def __init__(self, store: DocumentStore) -> None:
        self._store = store
        self._lock = threading.Lock()

        # Global engine – one shared across all requests
        self._global: RetrievalEngine = _make_engine()

        # Session engines – created on demand
        self._sessions: dict[str, RetrievalEngine] = {}

        # Rehydrate both scopes from SQLite
        self._rehydrate()

    # ------------------------------------------------------------------
    # Startup rehydration
    # ------------------------------------------------------------------

    def _rehydrate(self) -> None:
        """Load all persisted chunks back into memory after a restart."""
        global_chunks = self._store.load_chunks(scope="global")
        if global_chunks:
            self._global.index(global_chunks)
            logger.info("index_manager_rehydrated_global", chunks=len(global_chunks))

        # Rehydrate every known session
        docs = self._store.list_documents()
        session_ids = {
            d["session_id"]
            for d in docs
            if d["scope"] == "session" and d["session_id"]
        }
        for sid in session_ids:
            chunks = self._store.load_chunks(scope="session", session_id=sid)
            if chunks:
                engine = _make_engine()
                engine.index(chunks)
                with self._lock:
                    self._sessions[sid] = engine
                logger.info(
                    "index_manager_rehydrated_session",
                    session_id=sid,
                    chunks=len(chunks),
                )

    # ------------------------------------------------------------------
    # Index (called after a new document is ingested)
    # ------------------------------------------------------------------

    def index_global(self, chunks: list[DocumentChunk]) -> None:
        self._global.index(chunks)

    def index_session(self, session_id: str, chunks: list[DocumentChunk]) -> None:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = _make_engine()
        self._sessions[session_id].index(chunks)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def retrieve_global(self, query: str, top_k: int = 5) -> list[EvidenceItem]:
        return self._global.retrieve(query, top_k=top_k)

    def retrieve_session(
        self, session_id: str, query: str, top_k: int = 5
    ) -> list[EvidenceItem]:
        engine = self._sessions.get(session_id)
        if engine is None:
            return []
        return engine.retrieve(query, top_k=top_k)

    def retrieve_combined(
        self, session_id: str | None, query: str, top_k: int = 5
    ) -> list[EvidenceItem]:
        """Merge global + session results, deduplicated by chunk_id."""
        results = self.retrieve_global(query, top_k=top_k * 2)
        if session_id:
            results += self.retrieve_session(session_id, query, top_k=top_k * 2)

        seen: set[str] = set()
        deduped: list[EvidenceItem] = []
        for item in sorted(results, key=lambda x: x.score, reverse=True):
            cid = item.chunk.chunk_id
            if cid not in seen:
                seen.add(cid)
                deduped.append(item)
        return deduped[:top_k]

    # ------------------------------------------------------------------
    # Cleanup (when a session is deleted)
    # ------------------------------------------------------------------

    def drop_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
