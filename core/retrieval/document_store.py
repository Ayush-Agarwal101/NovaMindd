"""
NovaMindd — Persistent Document Store

SQLite-backed store for ingested document metadata and raw chunks.
Works fully offline with zero external services.

Two scopes:
  • global   – documents available to every session and the Knowledge page
  • session  – documents attached to one specific chat session (ephemeral from
               the user's perspective, but still persisted so they survive
               page navigation)
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from core.logging import get_logger
from core.retrieval.ingestion import DocumentChunk, DocumentType, IngestedDocument

logger = get_logger(__name__)

# Default DB path – override via env var NOVAMINDD_DB_PATH
_DEFAULT_DB = Path(__file__).parent.parent.parent / "data" / "documents.db"


def _db_path() -> Path:
    import os
    p = Path(os.environ.get("NOVAMINDD_DB_PATH", str(_DEFAULT_DB)))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


_DDL = """
CREATE TABLE IF NOT EXISTS documents (
    document_id  TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    doc_type     TEXT NOT NULL,
    scope        TEXT NOT NULL DEFAULT 'global',   -- 'global' | 'session'
    session_id   TEXT,                              -- NULL for global
    page_count   INTEGER NOT NULL DEFAULT 0,
    chunk_count  INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id     TEXT PRIMARY KEY,
    document_id  TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    source_path  TEXT NOT NULL,
    page_number  INTEGER NOT NULL,
    chunk_index  INTEGER NOT NULL,
    text         TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_docs_scope      ON documents(scope);
CREATE INDEX IF NOT EXISTS idx_docs_session    ON documents(session_id);
"""


class DocumentStore:
    """
    Thread-safe SQLite document store.

    The same instance is shared across requests via lru_cache in dependencies.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or _db_path()
        self._lock = threading.Lock()
        self._ensure_schema()
        logger.info("document_store_ready", path=str(self._path))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_DDL)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_document(
        self,
        doc: IngestedDocument,
        scope: str = "global",
        session_id: str | None = None,
    ) -> None:
        """Persist an IngestedDocument and all its chunks."""
        import time

        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents
                    (document_id, filename, doc_type, scope, session_id,
                     page_count, chunk_count, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc.document_id,
                    doc.source_path,
                    doc.doc_type.value,
                    scope,
                    session_id,
                    doc.page_count,
                    doc.total_chunks,
                    json.dumps(doc.metadata),
                    time.time(),
                ),
            )
            conn.executemany(
                """
                INSERT OR IGNORE INTO chunks
                    (chunk_id, document_id, source_path, page_number,
                     chunk_index, text, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.chunk_id,
                        c.document_id,
                        c.source_path,
                        c.page_number,
                        c.chunk_index,
                        c.text,
                        json.dumps(c.metadata),
                    )
                    for c in doc.chunks
                ],
            )
        logger.info(
            "document_store_saved",
            document_id=doc.document_id,
            scope=scope,
            chunks=doc.total_chunks,
        )

    def delete_document(self, document_id: str) -> bool:
        """Delete a document and its chunks. Returns True if it existed."""
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM documents WHERE document_id = ?", (document_id,)
            )
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_chunks(
        self,
        scope: str | None = None,
        session_id: str | None = None,
        document_id: str | None = None,
    ) -> list[DocumentChunk]:
        """
        Load chunks filtered by scope / session / document.

        Passing scope='global' returns all global chunks.
        Passing scope='session' + session_id returns chunks for that session.
        Passing neither returns everything.
        """
        sql = "SELECT * FROM chunks c JOIN documents d ON c.document_id = d.document_id WHERE 1=1"
        params: list = []

        if document_id:
            sql += " AND c.document_id = ?"
            params.append(document_id)
        elif scope == "global":
            sql += " AND d.scope = 'global'"
        elif scope == "session" and session_id:
            sql += " AND d.scope = 'session' AND d.session_id = ?"
            params.append(session_id)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            DocumentChunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                source_path=r["source_path"],
                page_number=r["page_number"],
                chunk_index=r["chunk_index"],
                text=r["text"],
                metadata=json.loads(r["metadata_json"]),
            )
            for r in rows
        ]

    def list_documents(
        self,
        scope: str | None = None,
        session_id: str | None = None,
    ) -> list[dict]:
        """Return document metadata rows as plain dicts."""
        sql = "SELECT * FROM documents WHERE 1=1"
        params: list = []

        if scope == "global":
            sql += " AND scope = 'global'"
        elif scope == "session" and session_id:
            sql += " AND scope = 'session' AND session_id = ?"
            params.append(session_id)

        sql += " ORDER BY created_at DESC"

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [dict(r) for r in rows]

    def get_document(self, document_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        return dict(row) if row else None
