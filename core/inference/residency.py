"""
NovaMindd — Model Residency Manager

Manages which model(s) are currently loaded in VRAM.
Handles load, unload, and swap decisions within the configured VRAM budget.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from core.config import get_config
from core.inference.providers.base import BaseInferenceProvider
from core.inference.registry import ModelRegistry, ModelStatus, get_registry
from core.logging import get_logger

logger = get_logger(__name__)


class ResidencyManager:
    """
    Controls which models occupy GPU VRAM at any given time.

    When a model is requested that is not loaded, the manager:
      1. Checks whether there is sufficient headroom.
      2. If not, evicts the least-recently-used loaded model.
      3. Loads the requested model.

    Concurrency is serialised via an asyncio.Lock so that
    simultaneous requests do not race to load/unload.
    """

    def __init__(
        self,
        provider: BaseInferenceProvider,
        registry: ModelRegistry | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry or get_registry()
        self._cfg = get_config().residency
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ensure_loaded(self, model_id: str) -> None:
        """Ensure model_id is in VRAM, loading (and possibly swapping) as needed."""
        print("model_id : ", model_id)
        async with self._lock:
            entry = self._registry.get(model_id)
            if entry is None:
                raise ValueError(f"Unknown model: {model_id!r}")

            if entry.is_loaded:
                entry.last_used = time.monotonic()
                return

            await self._make_room(entry.vram_limit_mb)
            await self._load(model_id)

    async def ensure_unloaded(self, model_id: str) -> None:
        """Explicitly evict a model from VRAM."""
        async with self._lock:
            entry = self._registry.get(model_id)
            if entry is None or not entry.is_loaded:
                return
            await self._unload(model_id)

    async def sync_from_backend(self) -> None:
        """Reconcile registry status with what the backend actually has loaded."""
        try:
            loaded = set(await self._provider.list_loaded_models())
        except Exception as exc:
            logger.warning("residency_sync_failed", error=str(exc))
            return

        for entry in self._registry.all():
            backend_name = entry.config.name
            if backend_name in loaded and not entry.is_loaded:
                self._registry.set_status(
                    entry.id, ModelStatus.LOADED, loaded_at=time.monotonic()
                )
            elif backend_name not in loaded and entry.is_loaded:
                self._registry.set_status(entry.id, ModelStatus.AVAILABLE)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _make_room(self, required_mb: int) -> None:
        """Evict LRU loaded models until there is enough VRAM headroom."""
        loaded = self._registry.loaded()
        used_mb = sum(e.vram_limit_mb for e in loaded)
        headroom = self._cfg.max_vram_mb - used_mb

        if headroom >= required_mb:
            return

        # Sort by last_used ascending (oldest first)
        loaded.sort(key=lambda e: e.last_used or 0)
        for victim in loaded:
            if headroom >= required_mb:
                break
            logger.info(
                "residency_evicting_model",
                model_id=victim.id,
                freed_mb=victim.vram_limit_mb,
            )
            await self._unload(victim.id)
            headroom += victim.vram_limit_mb

        if headroom < required_mb:
            raise RuntimeError(
                f"Cannot free {required_mb} MB VRAM; "
                f"max budget is {self._cfg.max_vram_mb} MB"
            )

    async def _load(self, model_id: str) -> None:
        entry = self._registry.get(model_id)
        if entry is None:
            return
        self._registry.set_status(model_id, ModelStatus.LOADING)
        try:
            await self._provider.load_model(entry.config.name)
            self._registry.set_status(
                model_id,
                ModelStatus.LOADED,
                loaded_at=time.monotonic(),
                last_used=time.monotonic(),
                vram_used_mb=entry.vram_limit_mb,
            )
            logger.info("model_loaded", model_id=model_id)
        except Exception as exc:
            self._registry.set_status(
                model_id, ModelStatus.ERROR, error_message=str(exc)
            )
            raise

    async def _unload(self, model_id: str) -> None:
        entry = self._registry.get(model_id)
        if entry is None:
            return
        self._registry.set_status(model_id, ModelStatus.UNLOADING)
        try:
            await self._provider.unload_model(entry.config.name)
            self._registry.set_status(
                model_id, ModelStatus.AVAILABLE, vram_used_mb=0
            )
            logger.info("model_unloaded", model_id=model_id)
        except Exception as exc:
            self._registry.set_status(
                model_id, ModelStatus.ERROR, error_message=str(exc)
            )
            raise
