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


# ---------------------------------------------------------------------------
# exclude_coding_only guard
# ---------------------------------------------------------------------------

def _make_registry_coding_only() -> ModelRegistry:
    """Registry where the only reasoning-capable model is a coding-only model."""
    cfg = NovaMinddConfig(
        models=[
            ModelConfig(
                id="coding",
                name="deepseek-coder:6.7b",
                # deliberately includes "reasoning" so it would normally be selected
                capabilities=["coding", "tool_generation", "reasoning"],
                vram_limit_mb=5000,
                priority=5,
            ),
            ModelConfig(
                id="general",
                name="llama3:3b",
                capabilities=["reasoning", "text"],
                vram_limit_mb=3000,
                priority=10,
            ),
        ],
        residency=ResidencyConfig(max_vram_mb=8192),
    )
    return ModelRegistry(config=cfg)


def test_is_coding_only_true_for_pure_coding_model():
    """A model with only coding/tool_generation caps is flagged as coding-only."""
    cfg = NovaMinddConfig(
        models=[
            ModelConfig(
                id="coder",
                name="deepseek-coder",
                capabilities=["coding", "tool_generation"],
                vram_limit_mb=5000,
                priority=10,
            ),
        ],
        residency=ResidencyConfig(max_vram_mb=8192),
    )
    registry = ModelRegistry(config=cfg)
    router = ModelRouter(registry=registry)
    entry = registry.get("coder")
    assert router._is_coding_only(entry) is True


def test_is_coding_only_false_for_general_model():
    """A model that includes reasoning/text is NOT coding-only."""
    cfg = NovaMinddConfig(
        models=[
            ModelConfig(
                id="general",
                name="llama3",
                capabilities=["reasoning", "text", "coding"],
                vram_limit_mb=3000,
                priority=10,
            ),
        ],
        residency=ResidencyConfig(max_vram_mb=8192),
    )
    registry = ModelRegistry(config=cfg)
    router = ModelRouter(registry=registry)
    entry = registry.get("general")
    assert router._is_coding_only(entry) is False


def test_exclude_coding_only_skips_pure_coding_model():
    """With exclude_coding_only=True a model whose caps are all coding-type is skipped."""
    cfg = NovaMinddConfig(
        models=[
            ModelConfig(
                id="coding",
                name="deepseek-coder:6.7b",
                capabilities=["coding", "tool_generation"],
                vram_limit_mb=5000,
                priority=5,   # higher priority — would normally win
            ),
            ModelConfig(
                id="general",
                name="llama3:3b",
                capabilities=["reasoning", "text"],
                vram_limit_mb=3000,
                priority=10,
            ),
        ],
        residency=ResidencyConfig(max_vram_mb=8192),
    )
    registry = ModelRegistry(config=cfg)
    router = ModelRouter(registry=registry)

    # Without the guard, general wins for REASONING (coding has no reasoning cap)
    decision_normal = router.route(RoutingRequest(capability=TaskCapability.REASONING))
    assert decision_normal.model_id == "general"

    # With the guard, general still wins and coding is never even in the pool
    decision_excl = router.route(
        RoutingRequest(capability=TaskCapability.REASONING, exclude_coding_only=True)
    )
    assert decision_excl.model_id == "general"


def test_exclude_coding_only_raises_when_no_non_coding_model_available():
    """If only coding-only models exist for a capability, exclude_coding_only raises."""
    cfg = NovaMinddConfig(
        models=[
            ModelConfig(
                id="coding",
                name="deepseek-coder:6.7b",
                capabilities=["coding", "tool_generation"],
                vram_limit_mb=5000,
                priority=5,
            ),
        ],
        residency=ResidencyConfig(max_vram_mb=8192),
    )
    registry = ModelRegistry(config=cfg)
    router = ModelRouter(registry=registry)

    # coding cap works normally
    decision = router.route(RoutingRequest(capability=TaskCapability.CODING))
    assert decision.model_id == "coding"

    # But excluding coding-only models when only coding models exist → no candidates
    with pytest.raises(RuntimeError, match="No eligible model"):
        router.route(
            RoutingRequest(capability=TaskCapability.CODING, exclude_coding_only=True)
        )


# ---------------------------------------------------------------------------
# Evidence formatting
# ---------------------------------------------------------------------------

def test_format_evidence_labels_document_not_source():
    """Evidence passages must be labelled with 'Document:' not 'Source:' and
    must not expose the retrieval score (which could mislead a model)."""
    from core.agents.planner import AgentPlanner
    from core.retrieval.engine import EvidenceItem
    from core.retrieval.ingestion import DocumentChunk

    chunk = DocumentChunk(
        chunk_id="c1",
        document_id="d1",
        source_path="policy.pdf",
        page_number=3,
        chunk_index=0,
        text="All valves must be inspected quarterly.",
    )
    item = EvidenceItem(chunk=chunk, score=0.95, source="bm25")
    formatted = AgentPlanner._format_evidence([item])

    assert 'Document: "policy.pdf"' in formatted
    assert "Page 3" in formatted
    assert "All valves must be inspected quarterly." in formatted
    # Score must NOT appear — it is an internal retrieval signal, not evidence content
    assert "0.95" not in formatted
    assert "Score" not in formatted
