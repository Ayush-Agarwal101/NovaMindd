"""
Tests — Model Router

Verifies routing decisions without requiring any running models.
"""
from __future__ import annotations

import pytest

from core.config import ModelConfig, NovaMinddConfig, ResidencyConfig
from core.inference.registry import ModelRegistry, ModelStatus
from core.inference.router import ModelRouter, RoutingRequest, TaskCapability


def _make_registry() -> ModelRegistry:
    cfg = NovaMinddConfig(
        models=[
            ModelConfig(
                id="general",
                name="llama3:3b",
                capabilities=["reasoning", "text"],
                vram_limit_mb=3000,
                priority=10,
            ),
            ModelConfig(
                id="coding",
                name="deepseek-coder:6.7b",
                capabilities=["coding", "tool_generation"],
                vram_limit_mb=5000,
                priority=20,
            ),
            ModelConfig(
                id="vision",
                name="llava:7b",
                capabilities=["vision", "document_understanding"],
                vram_limit_mb=4096,
                priority=15,
            ),
        ],
        residency=ResidencyConfig(max_vram_mb=6144),
    )
    return ModelRegistry(config=cfg)


def test_router_selects_by_capability():
    registry = _make_registry()
    router = ModelRouter(registry=registry)
    decision = router.route(RoutingRequest(capability=TaskCapability.CODING))
    assert decision.model_id == "coding"


def test_router_prefers_loaded_model():
    registry = _make_registry()
    # Mark general as loaded
    registry.set_status("general", ModelStatus.LOADED)
    router = ModelRouter(registry=registry)
    decision = router.route(RoutingRequest(capability=TaskCapability.REASONING))
    assert decision.model_id == "general"
    assert decision.already_loaded is True


def test_router_explicit_override():
    registry = _make_registry()
    router = ModelRouter(registry=registry)
    decision = router.route(
        RoutingRequest(
            capability=TaskCapability.REASONING,
            preferred_model_id="general",
        )
    )
    assert decision.model_id == "general"
    assert decision.reason == "explicit_override"


def test_router_raises_when_no_candidate():
    registry = _make_registry()
    router = ModelRouter(registry=registry)
    with pytest.raises(RuntimeError, match="No eligible model"):
        router.route(RoutingRequest(capability=TaskCapability.OCR_ASSIST))


def test_router_excludes_errored_models():
    registry = _make_registry()
    registry.set_status("coding", ModelStatus.ERROR)
    router = ModelRouter(registry=registry)
    # coding is the only model with tool_generation capability
    with pytest.raises(RuntimeError):
        router.route(RoutingRequest(capability=TaskCapability.TOOL_GENERATION))


def test_router_respects_vram_limit():
    registry = _make_registry()
    router = ModelRouter(registry=registry)
    # Request with a very tight VRAM budget — only general fits
    decision = router.route(
        RoutingRequest(capability=TaskCapability.REASONING, max_vram_mb=3500)
    )
    assert decision.model_id == "general"
    assert decision.vram_required_mb <= 3500
