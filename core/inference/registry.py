"""
NovaMindd — Model Registry

Central registry of known models, their capabilities, and current status.
The registry is the source of truth for what the platform can use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.config import ModelConfig, NovaMinddConfig, get_config
from core.logging import get_logger

logger = get_logger(__name__)


class ModelStatus(str, Enum):
    AVAILABLE = "available"   # weight file present, not loaded
    LOADED = "loaded"         # in VRAM, ready for inference
    LOADING = "loading"       # being loaded right now
    UNLOADING = "unloading"   # being evicted from VRAM
    ERROR = "error"           # failed to load / health-check failed
    UNKNOWN = "unknown"       # registry entry only, not yet probed


@dataclass
class ModelRegistryEntry:
    config: ModelConfig
    status: ModelStatus = ModelStatus.UNKNOWN
    loaded_at: float | None = None     # epoch seconds
    last_used: float | None = None     # epoch seconds
    vram_used_mb: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def capabilities(self) -> list[str]:
        return self.config.capabilities

    @property
    def is_loaded(self) -> bool:
        return self.status == ModelStatus.LOADED

    @property
    def vram_limit_mb(self) -> int:
        return self.config.vram_limit_mb


class ModelRegistry:
    """In-memory registry for all configured models."""

    def __init__(self, config: NovaMinddConfig | None = None) -> None:
        self._cfg = config or get_config()
        self._entries: dict[str, ModelRegistryEntry] = {}
        self._load_from_config()

    def _load_from_config(self) -> None:
        for model_cfg in self._cfg.models:
            self._entries[model_cfg.id] = ModelRegistryEntry(config=model_cfg)
        logger.info("model_registry_loaded", count=len(self._entries))

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get(self, model_id: str) -> ModelRegistryEntry | None:
        return self._entries.get(model_id)

    def all(self) -> list[ModelRegistryEntry]:
        return list(self._entries.values())

    def loaded(self) -> list[ModelRegistryEntry]:
        return [e for e in self._entries.values() if e.is_loaded]

    def with_capability(self, capability: str) -> list[ModelRegistryEntry]:
        return [
            e for e in self._entries.values()
            if capability in e.capabilities
        ]

    def best_for_capability(self, capability: str) -> ModelRegistryEntry | None:
        """Return the highest-priority available model for the given capability."""
        candidates = [
            e for e in self.with_capability(capability)
            if e.status != ModelStatus.ERROR
        ]
        if not candidates:
            return None
        # Prefer already-loaded; then sort by priority (lower = higher priority)
        candidates.sort(key=lambda e: (0 if e.is_loaded else 1, e.config.priority))
        return candidates[0]

    # ------------------------------------------------------------------
    # Status updates (called by Residency Manager)
    # ------------------------------------------------------------------

    def set_status(self, model_id: str, status: ModelStatus, **kwargs: Any) -> None:
        entry = self._entries.get(model_id)
        if entry is None:
            logger.warning("registry_set_status_unknown_model", model_id=model_id)
            return
        entry.status = status
        for k, v in kwargs.items():
            if hasattr(entry, k):
                setattr(entry, k, v)
        logger.debug("model_status_updated", model_id=model_id, status=status.value)

    def register(self, config: ModelConfig) -> ModelRegistryEntry:
        """Dynamically register a model (e.g. discovered at runtime)."""
        entry = ModelRegistryEntry(config=config)
        self._entries[config.id] = entry
        logger.info("model_registered", model_id=config.id)
        return entry


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
