"""
NovaMindd — Model Router

Maps an incoming task to the most appropriate available local model based on:
  - required capability
  - VRAM budget
  - current residency (prefer already-loaded models)
  - organisational policy
  - explicit model override

The router is independently testable and does not perform inference itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.config import get_config
from core.inference.registry import ModelRegistry, ModelRegistryEntry, get_registry
from core.logging import get_logger

logger = get_logger(__name__)


class TaskCapability(str, Enum):
    REASONING = "reasoning"
    CODING = "coding"
    VISION = "vision"
    DOCUMENT_UNDERSTANDING = "document_understanding"
    SUMMARISATION = "summarisation"
    TEXT = "text"
    TOOL_GENERATION = "tool_generation"
    OCR_ASSIST = "ocr_assist"
    ANALYSIS = "analysis"


@dataclass
class RoutingRequest:
    """Inputs to the routing decision."""
    capability: TaskCapability
    requires_vision: bool = False
    max_vram_mb: int | None = None          # override VRAM limit
    preferred_model_id: str | None = None   # explicit override
    # When True, models whose *only* capabilities are coding/tool_generation are
    # excluded from selection.  Set this for decomposition, synthesis, and
    # verification calls so a coding-specialist model is never invoked for
    # document analysis or reasoning tasks.
    exclude_coding_only: bool = False
    metadata: dict[str, Any] | None = None


@dataclass
class RoutingDecision:
    model_id: str
    model_name: str
    capability: str
    already_loaded: bool
    vram_required_mb: int
    reason: str


class ModelRouter:
    """
    Deterministic model router.

    Selection order:
      1. If preferred_model_id is specified and the model supports the capability → use it.
      2. Among eligible models, prefer already-loaded ones.
      3. Among equally-loaded candidates, sort by model priority (ascending).
      4. Among equally-prioritised candidates, prefer lower VRAM cost.
    """

    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self._registry = registry or get_registry()
        self._cfg = get_config()

    def route(self, request: RoutingRequest) -> RoutingDecision:
        """Return the best model for the request, or raise if no model qualifies."""

        # 1. Explicit override
        if request.preferred_model_id:
            entry = self._registry.get(request.preferred_model_id)
            if entry is not None and request.capability.value in entry.capabilities:
                return self._decision(entry, request.capability.value, "explicit_override")
            logger.warning(
                "router_override_ineligible",
                preferred=request.preferred_model_id,
                capability=request.capability.value,
            )

        # 2. Gather eligible candidates
        candidates = self._eligible(request)
        if not candidates:
            raise RuntimeError(
                f"No eligible model for capability={request.capability.value}"
            )

        # 3. Sort: (not_loaded, priority, vram)
        candidates.sort(
            key=lambda e: (
                0 if e.is_loaded else 1,
                e.config.priority,
                e.config.vram_limit_mb,
            )
        )

        chosen = candidates[0]
        reason = "loaded" if chosen.is_loaded else "best_available"
        logger.info(
            "router_selected_model",
            model_id=chosen.id,
            capability=request.capability.value,
            reason=reason,
        )
        return self._decision(chosen, request.capability.value, reason)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # Capabilities that mark a model as coding-specialist.
    # A model is considered "coding-only" when ALL of its declared capabilities
    # are in this set — meaning it provides no general reasoning or text ability.
    _CODING_ONLY_CAPS: frozenset[str] = frozenset({"coding", "tool_generation"})

    def _eligible(self, request: RoutingRequest) -> list[ModelRegistryEntry]:
        from core.inference.registry import ModelStatus

        max_vram = request.max_vram_mb or self._cfg.residency.max_vram_mb
        candidates = []
        for entry in self._registry.with_capability(request.capability.value):
            if entry.status == ModelStatus.ERROR:
                continue
            if entry.config.vram_limit_mb > max_vram:
                continue
            if request.requires_vision and "vision" not in entry.capabilities:
                continue
            if request.exclude_coding_only and self._is_coding_only(entry):
                continue
            candidates.append(entry)
        return candidates

    def _is_coding_only(self, entry: ModelRegistryEntry) -> bool:
        """Return True when the model's capabilities are exclusively coding-related."""
        return bool(entry.capabilities) and set(entry.capabilities).issubset(
            self._CODING_ONLY_CAPS
        )

    @staticmethod
    def _decision(
        entry: ModelRegistryEntry, capability: str, reason: str
    ) -> RoutingDecision:
        return RoutingDecision(
            model_id=entry.id,
            model_name=entry.config.name,
            capability=capability,
            already_loaded=entry.is_loaded,
            vram_required_mb=entry.config.vram_limit_mb,
            reason=reason,
        )
