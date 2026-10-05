"""
NovaMindd — Inference Provider Interface

All local model backends implement this ABC.
The rest of the platform talks only to this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class InferenceRequest:
    model_name: str
    prompt: str
    system_prompt: str | None = None
    images: list[bytes] | None = None   # raw image bytes for VLM
    max_tokens: int = 2048
    temperature: float = 0.2
    stop: list[str] | None = None
    stream: bool = False
    # Ollama /api/generate KV-cache token array from a previous response.
    # Pass back the value returned in InferenceResponse.context to continue
    # from the same KV cache instead of re-encoding the whole prompt.
    context: list[int] | None = None


@dataclass
class InferenceResponse:
    model_name: str
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    done: bool = True
    raw: dict | None = None
    # Ollama KV-cache context token array — pass back on the next call to the
    # same model to avoid re-encoding and to preserve implicit conversation state.
    context: list[int] | None = None


class BaseInferenceProvider(ABC):
    """Abstract inference provider.  Implement one per backend (Ollama, llama.cpp, …)."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Return True if the backend is reachable."""
        ...

    @abstractmethod
    async def list_loaded_models(self) -> list[str]:
        """Return model names currently in the backend's memory."""
        ...

    @abstractmethod
    async def load_model(self, model_name: str) -> None:
        """Pre-load a model into the backend."""
        ...

    @abstractmethod
    async def unload_model(self, model_name: str) -> None:
        """Evict a model from the backend's memory."""
        ...

    @abstractmethod
    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        """Run a single, non-streaming inference call."""
        ...

    @abstractmethod
    async def generate_stream(
        self, request: InferenceRequest
    ) -> AsyncIterator[InferenceResponse]:
        """Stream tokens as they are generated."""
        ...
