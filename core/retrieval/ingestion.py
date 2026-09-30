"""
NovaMindd — Document Ingestion Pipeline

Processes uploaded documents into chunks suitable for indexing.
Supports PDF (digital + scanned), with OCR escalation on low confidence.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from core.config import get_config
from core.logging import get_logger

logger = get_logger(__name__)


class DocumentType(str, Enum):
    PDF = "pdf"
    TEXT = "text"
    IMAGE = "image"
    UNKNOWN = "unknown"


@dataclass
class PageContent:
    page_number: int
    text: str
    confidence: float = 1.0         # 0–1; <threshold triggers VLM escalation
    images: list[bytes] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    source: str = ""


@dataclass
class DocumentChunk:
    chunk_id: str
    document_id: str
    source_path: str
    page_number: int
    chunk_index: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.chunk_id:
            content = f"{self.document_id}:{self.page_number}:{self.chunk_index}"
            self.chunk_id = hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class IngestedDocument:
    document_id: str
    source_path: str
    doc_type: DocumentType
    page_count: int
    chunks: list[DocumentChunk]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)


# ---------------------------------------------------------------------------
# PDF Parser
# ---------------------------------------------------------------------------

class PDFParser:
    """Extract text and images from PDF files using PyMuPDF."""

    def __init__(self) -> None:
        self._cfg = get_config().document_ai

    def parse(self, data: bytes, source_path: str = "") -> list[PageContent]:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError("PyMuPDF is required for PDF parsing (pip install pymupdf)")

        pages: list[PageContent] = []
        doc = fitz.open(stream=data, filetype="pdf")
        limit = min(len(doc), self._cfg.max_pages)

        for page_num in range(limit):
            page = doc[page_num]
            text = page.get_text().strip()
            confidence = 1.0

            images: list[bytes] = []
            if self._cfg.extract_images:
                for img_ref in page.get_images(full=True):
                    xref = img_ref[0]
                    try:
                        pix = fitz.Pixmap(doc, xref)
                        images.append(pix.tobytes("png"))
                    except Exception:
                        pass

            # Heuristic: low text density on a page with images → probably scanned
            if len(text) < 50 and images:
                confidence = 0.3

            tables: list[dict] = []
            if self._cfg.extract_tables:
                try:
                    tables = [t.to_dict() for t in page.find_tables().tables]
                except Exception:
                    pass

            pages.append(PageContent(
                page_number=page_num + 1,
                text=text,
                confidence=confidence,
                images=images,
                tables=tables,
                source=source_path,
            ))

        doc.close()
        return pages


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------

class TextChunker:
    """Split text into overlapping chunks."""

    def __init__(self, chunk_size: int = 512, overlap: int = 64) -> None:
        self._size = chunk_size
        self._overlap = overlap

    def chunk(
        self,
        text: str,
        document_id: str,
        source_path: str,
        page_number: int,
    ) -> list[DocumentChunk]:
        words = text.split()
        if not words:
            return []

        chunks: list[DocumentChunk] = []
        start = 0
        idx = 0
        while start < len(words):
            end = start + self._size
            chunk_words = words[start:end]
            chunks.append(DocumentChunk(
                chunk_id="",
                document_id=document_id,
                source_path=source_path,
                page_number=page_number,
                chunk_index=idx,
                text=" ".join(chunk_words),
                metadata={"word_count": len(chunk_words)},
            ))
            idx += 1
            if end >= len(words):
                break
            start = end - self._overlap
        return chunks


# ---------------------------------------------------------------------------
# Ingestion Orchestrator
# ---------------------------------------------------------------------------

class DocumentIngestionPipeline:
    """
    Full document ingestion pipeline:
      1. Detect document type
      2. Parse pages
      3. Flag low-confidence pages for OCR / VLM escalation
      4. Chunk text
      5. Return IngestedDocument
    """

    def __init__(self) -> None:
        self._cfg = get_config()
        self._pdf_parser = PDFParser()
        self._chunker = TextChunker(
            chunk_size=self._cfg.retrieval.chunk_size,
            overlap=self._cfg.retrieval.chunk_overlap,
        )

    def ingest(
        self,
        data: bytes,
        filename: str,
        document_id: str | None = None,
    ) -> IngestedDocument:
        doc_type = self._detect_type(filename)
        if document_id is None:
            document_id = hashlib.sha256(data).hexdigest()[:24]

        logger.info(
            "ingestion_start",
            document_id=document_id,
            filename=filename,
            doc_type=doc_type.value,
        )

        if doc_type == DocumentType.PDF:
            pages = self._pdf_parser.parse(data, source_path=filename)
        elif doc_type == DocumentType.TEXT:
            pages = [PageContent(
                page_number=1,
                text=data.decode("utf-8", errors="replace"),
                source=filename,
            )]
        else:
            # Image or unknown: wrap as single page, flag for VLM
            pages = [PageContent(
                page_number=1,
                text="",
                confidence=0.0,
                images=[data],
                source=filename,
            )]

        all_chunks: list[DocumentChunk] = []
        ocr_needed: list[int] = []
        threshold = self._cfg.document_ai.ocr_confidence_threshold

        for page in pages:
            if page.confidence < threshold:
                ocr_needed.append(page.page_number)
            chunks = self._chunker.chunk(
                text=page.text,
                document_id=document_id,
                source_path=filename,
                page_number=page.page_number,
            )
            all_chunks.extend(chunks)

        if ocr_needed:
            logger.info(
                "ingestion_ocr_needed",
                document_id=document_id,
                pages=ocr_needed,
            )

        doc = IngestedDocument(
            document_id=document_id,
            source_path=filename,
            doc_type=doc_type,
            page_count=len(pages),
            chunks=all_chunks,
            metadata={"ocr_needed_pages": ocr_needed},
        )
        logger.info(
            "ingestion_complete",
            document_id=document_id,
            pages=doc.page_count,
            chunks=doc.total_chunks,
        )
        return doc

    @staticmethod
    def _detect_type(filename: str) -> DocumentType:
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            return DocumentType.PDF
        if ext in {".txt", ".md", ".rst", ".csv"}:
            return DocumentType.TEXT
        if ext in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}:
            return DocumentType.IMAGE
        return DocumentType.UNKNOWN
