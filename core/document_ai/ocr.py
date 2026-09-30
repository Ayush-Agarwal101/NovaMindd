"""
NovaMindd — Document AI: OCR Pipeline

Wraps PaddleOCR (or any compatible local OCR engine) to extract text
from scanned pages and images. Returns confidence scores so the platform
can decide whether to escalate to a VLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class OCRResult:
    text: str
    confidence: float       # 0.0 – 1.0
    bounding_boxes: list[dict[str, Any]] | None = None


class OCREngine:
    """
    OCR engine wrapper.

    Primary backend: PaddleOCR (local, no external API).
    Falls back to a stub that returns empty text if PaddleOCR is unavailable
    so the rest of the pipeline can still run in environments without it.
    """

    def __init__(self, lang: str = "en") -> None:
        self._lang = lang
        self._engine = None   # lazy-initialised

    def _get_engine(self):
        if self._engine is None:
            try:
                from paddleocr import PaddleOCR
                self._engine = PaddleOCR(
                    use_angle_cls=True,
                    lang=self._lang,
                    show_log=False,
                )
                logger.info("ocr_engine_loaded", backend="paddleocr", lang=self._lang)
            except ImportError:
                logger.warning(
                    "ocr_engine_unavailable",
                    detail="PaddleOCR not installed. OCR will return empty results.",
                )
                self._engine = None
        return self._engine

    def process_image(self, image_bytes: bytes) -> OCRResult:
        """Run OCR on raw image bytes. Returns text + mean confidence."""
        import tempfile, os
        engine = self._get_engine()
        if engine is None:
            return OCRResult(text="", confidence=0.0)

        # Write to temp file — PaddleOCR expects a file path or numpy array
        suffix = ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            result = engine.ocr(tmp_path, cls=True)
            return self._parse_result(result)
        except Exception as exc:
            logger.error("ocr_failed", error=str(exc))
            return OCRResult(text="", confidence=0.0)
        finally:
            os.unlink(tmp_path)

    @staticmethod
    def _parse_result(raw: list | None) -> OCRResult:
        if not raw or not raw[0]:
            return OCRResult(text="", confidence=0.0)

        lines: list[str] = []
        confidences: list[float] = []
        boxes: list[dict] = []

        for page in raw:
            if page is None:
                continue
            for item in page:
                box, (text, conf) = item
                lines.append(text)
                confidences.append(float(conf))
                boxes.append({"box": box, "text": text, "confidence": float(conf)})

        mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return OCRResult(
            text="\n".join(lines),
            confidence=mean_conf,
            bounding_boxes=boxes,
        )
