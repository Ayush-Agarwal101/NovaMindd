"""
NovaMindd — Ollama Inference Provider

Wraps the Ollama REST API as a BaseInferenceProvider.
Supports text models and vision-language models.
"""
from __future__ import annotations

import base64
from typing import AsyncIterator

import httpx
import orjson

from core.inference.providers.base import (
    BaseInferenceProvider,
    InferenceRequest,
    InferenceResponse,
)
from core.logging import get_logger

logger = get_logger(__name__)


class OllamaProvider(BaseInferenceProvider):
    """Inference provider backed by a locally running Ollama instance."""

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=300)

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def is_available(self) -> bool:
        try:
            r = await self._client.get("/api/tags")
            return r.status_code == 200
        except httpx.TransportError:
            return False

    async def list_loaded_models(self) -> list[str]:
        try:
            r = await self._client.get("/api/ps")
            r.raise_for_status()
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            logger.warning("ollama_list_loaded_failed", error=str(exc))
            return []

    async def load_model(self, model_name: str) -> None:
        """Warm up the model by sending a zero-length generation request."""
        payload = {"model": model_name, "prompt": "", "keep_alive": "10m"}
        try:
            r = await self._client.post("/api/generate", json=payload)
            r.raise_for_status()
            logger.info("ollama_model_loaded", model=model_name)
        except Exception as exc:
            logger.error("ollama_load_failed", model=model_name, error=str(exc))
            raise

    async def unload_model(self, model_name: str) -> None:
        """Evict a model from Ollama's VRAM by setting keep_alive=0."""
        payload = {"model": model_name, "prompt": "", "keep_alive": 0}
        try:
            r = await self._client.post("/api/generate", json=payload)
            r.raise_for_status()
            logger.info("ollama_model_unloaded", model=model_name)
        except Exception as exc:
            logger.warning("ollama_unload_failed", model=model_name, error=str(exc))

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        payload = self._build_payload(request, stream=False)
        try:
            r = await self._client.post("/api/generate", json=payload)
            r.raise_for_status()
            data = r.json()
            return InferenceResponse(
                model_name=request.model_name,
                content=data.get("response", ""),
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                done=data.get("done", True),
                raw=data,
                context=data.get("context"),   # KV-cache token array
            )
        except Exception as exc:
            logger.error("ollama_generate_failed", model=request.model_name, error=str(exc))
            raise

    async def generate_stream(
        self, request: InferenceRequest
    ) -> AsyncIterator[InferenceResponse]:
        payload = self._build_payload(request, stream=True)
        async with self._client.stream("POST", "/api/generate", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = orjson.loads(line)
                except Exception:
                    continue
                yield InferenceResponse(
                    model_name=request.model_name,
                    content=data.get("response", ""),
                    done=data.get("done", False),
                    raw=data,
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_payload(self, req: InferenceRequest, *, stream: bool) -> dict:
        payload: dict = {
            "model": req.model_name,
            "prompt": req.prompt,
            "stream": stream,
            "options": {
                "num_predict": req.max_tokens,
                "temperature": req.temperature,
            },
        }
        if req.system_prompt:
            payload["system"] = req.system_prompt
        if req.stop:
            payload["options"]["stop"] = req.stop
        if req.images:
            payload["images"] = [
                base64.b64encode(img).decode() for img in req.images
            ]
        # Reuse the KV-cache from a previous call to the same model so Ollama
        # does not re-encode the prompt from scratch.
        if req.context:
            payload["context"] = req.context
        return payload

    async def aclose(self) -> None:
        await self._client.aclose()
