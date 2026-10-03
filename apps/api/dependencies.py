"""
NovaMindd — FastAPI Dependency Injection

Singleton accessors for all platform services, injected via FastAPI's Depends().
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from core.config import NovaMinddConfig, get_config
from core.inference.providers.ollama import OllamaProvider
from core.inference.registry import ModelRegistry, get_registry
from core.inference.residency import ResidencyManager
from core.inference.router import ModelRouter
from core.retrieval.document_store import DocumentStore
from core.retrieval.engine import RetrievalEngine
from core.retrieval.index_manager import IndexManager
from core.retrieval.ingestion import DocumentIngestionPipeline
from core.control_plane.policy import PolicyEngine
from core.control_plane.rbac import RBACService, get_rbac
from core.control_plane.tools import ToolRegistry, get_tool_registry
from core.agents.tool_gateway import ToolGateway
from core.provenance.service import ProvenanceService


@lru_cache(maxsize=1)
def get_ollama_provider() -> OllamaProvider:
    cfg = get_config()
    import os
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    return OllamaProvider(base_url=base_url)


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    return get_registry()


@lru_cache(maxsize=1)
def get_residency_manager() -> ResidencyManager:
    return ResidencyManager(
        provider=get_ollama_provider(),
        registry=get_model_registry(),
    )


@lru_cache(maxsize=1)
def get_model_router() -> ModelRouter:
    return ModelRouter(registry=get_model_registry())


@lru_cache(maxsize=1)
def get_retrieval_engine() -> RetrievalEngine:
    return RetrievalEngine()


@lru_cache(maxsize=1)
def get_document_store() -> DocumentStore:
    return DocumentStore()


@lru_cache(maxsize=1)
def get_index_manager() -> IndexManager:
    """Singleton IndexManager — rehydrates from SQLite on first call."""
    return IndexManager(store=get_document_store())


@lru_cache(maxsize=1)
def get_ingestion_pipeline() -> DocumentIngestionPipeline:
    return DocumentIngestionPipeline()


@lru_cache(maxsize=1)
def get_policy_engine() -> PolicyEngine:
    return PolicyEngine()


@lru_cache(maxsize=1)
def get_rbac_service() -> RBACService:
    return get_rbac()


@lru_cache(maxsize=1)
def get_tool_registry_dep() -> ToolRegistry:
    return get_tool_registry()


@lru_cache(maxsize=1)
def get_tool_gateway() -> ToolGateway:
    return ToolGateway(
        registry=get_tool_registry_dep(),
        policy_engine=get_policy_engine(),
        index_manager=get_index_manager(),
        ingestion_pipeline=get_ingestion_pipeline(),
    )


@lru_cache(maxsize=1)
def get_provenance_service() -> ProvenanceService:
    return ProvenanceService()


# Type aliases for FastAPI Depends
ConfigDep        = Annotated[NovaMinddConfig,             Depends(get_config)]
ProviderDep      = Annotated[OllamaProvider,              Depends(get_ollama_provider)]
ResidencyDep     = Annotated[ResidencyManager,            Depends(get_residency_manager)]
RouterDep        = Annotated[ModelRouter,                 Depends(get_model_router)]
RetrievalDep     = Annotated[RetrievalEngine,             Depends(get_retrieval_engine)]
DocumentStoreDep = Annotated[DocumentStore,               Depends(get_document_store)]
IndexManagerDep  = Annotated[IndexManager,                Depends(get_index_manager)]
IngestionDep     = Annotated[DocumentIngestionPipeline,   Depends(get_ingestion_pipeline)]
PolicyDep        = Annotated[PolicyEngine,                Depends(get_policy_engine)]
GatewayDep       = Annotated[ToolGateway,                 Depends(get_tool_gateway)]
ProvenanceDep    = Annotated[ProvenanceService,           Depends(get_provenance_service)]
