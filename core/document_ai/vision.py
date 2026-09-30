"""
NovaMindd — Document AI: VLM Vision Pipeline

Sends images to a local Vision-Language Model (via Ollama) when OCR confidence
is below threshold, or when the document contains diagrams/engineering drawings
that OCR cannot meaningfully interpret.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.config import get_config
from core.inference.providers.base import BaseInferenceProvider, InferenceRequest
from core.logging import get_logger

logger = get_logger(__name__)

DOCUMENT_UNDERSTAND_PROMPT = """\
You are analysing a document image.
Extract all readable text, describe any diagrams, tables, or figures.
Output structured text only. Do not add commentary outside the document content.
"""


@dataclass
class VLMPageResult:
    text: str
    description: str   # description of non-text visual elements
    model_used: str


class VLMDocumentProcessor:
    """
    Processes document images using a local VLM (e.g. llava).
    Used when OCR confidence is low or the document is primarily visual.
    """

    def __init__(
        self,
        provider: BaseInferenceProvider,
        model_name: str | None = None,
    ) -> None:
        self._provider = provider
        self._model_name = model_name or self._detect_vlm_model()

    def _detect_vlm_model(self) -> str:
        cfg = get_config()
        for model in cfg.models:
            if "vision" in model.capabilities:
                return model.name
        return "llava:7b"

    async def process_image(self, image_bytes: bytes) -> VLMPageResult:
        """Send an image to the VLM and return extracted text + description."""
        try:
            response = await self._provider.generate(
                InferenceRequest(
                    model_name=self._model_name,
                    prompt=DOCUMENT_UNDERSTAND_PROMPT,
                    images=[image_bytes],
                    max_tokens=1024,
                    temperature=0.0,
                )
            )
            content = response.content.strip()
            # Simple split: text before "---" is extracted text, after is description
            parts = content.split("---", 1)
            text = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else ""
            return VLMPageResult(
                text=text,
                description=description,
                model_used=self._model_name,
            )
        except Exception as exc:
            logger.error("vlm_document_processing_failed", error=str(exc))
            return VLMPageResult(text="", description="", model_used=self._model_name)
