"""
NovaMindd — Configuration System

Loads and validates platform configuration from YAML + environment.
All settings are immutable after startup.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class AppConfig(BaseModel):
    name: str = "NovaMindd"
    version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"


class APIConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]


class AuthConfig(BaseModel):
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


class DatabaseConfig(BaseModel):
    url: str = "postgresql+asyncpg://novamindd:novamindd@localhost:5432/novamindd"
    pool_size: int = 10
    max_overflow: int = 20
    echo: bool = False


class ModelConfig(BaseModel):
    id: str
    name: str
    provider: str = "ollama"
    capabilities: list[str] = []
    vram_limit_mb: int = 4096
    context_length: int = 8192
    priority: int = 10


class ResidencyConfig(BaseModel):
    max_vram_mb: int = 6144
    unload_timeout_seconds: int = 300
    preload_on_startup: list[str] = []


class RetrievalConfig(BaseModel):
    chunk_size: int = 512
    chunk_overlap: int = 64
    top_k_bm25: int = 20
    top_k_vector: int = 20
    top_k_rerank: int = 5
    embedding_model: str = "all-MiniLM-L6-v2"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class DocumentAIConfig(BaseModel):
    ocr_confidence_threshold: float = 0.85
    max_pages: int = 500
    extract_tables: bool = True
    extract_images: bool = True


class NetworkPolicy(BaseModel):
    default: str = "deny"
    allowed_destinations: list[str] = []


class FilesystemPolicy(BaseModel):
    host_mounts: bool = False
    writable_paths: list[str] = ["/workspace"]
    read_only_paths: list[str] = ["/knowledge"]


class ExecutionPolicy(BaseModel):
    non_root: bool = True
    cpu_limit: str = "1.0"
    memory_limit_mb: int = 512
    timeout_seconds: int = 60
    max_output_size_bytes: int = 10 * 1024 * 1024


class ToolsPolicy(BaseModel):
    require_explicit_authorization: bool = True
    human_approval_required: list[str] = []


class PoliciesConfig(BaseModel):
    network: NetworkPolicy = NetworkPolicy()
    filesystem: FilesystemPolicy = FilesystemPolicy()
    execution: ExecutionPolicy = ExecutionPolicy()
    tools: ToolsPolicy = ToolsPolicy()


class SandboxConfig(BaseModel):
    image: str = "novamindd-sandbox:latest"
    network_mode: str = "none"
    remove_on_exit: bool = True


class AuditConfig(BaseModel):
    enabled: bool = True
    log_to_file: bool = True
    log_path: str = "logs/audit.jsonl"
    include_request_body: bool = False


class NovaMinddConfig(BaseModel):
    app: AppConfig = AppConfig()
    api: APIConfig = APIConfig()
    auth: AuthConfig = AuthConfig()
    database: DatabaseConfig = DatabaseConfig()
    models: list[ModelConfig] = []
    residency: ResidencyConfig = ResidencyConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    document_ai: DocumentAIConfig = DocumentAIConfig()
    policies: PoliciesConfig = PoliciesConfig()
    sandbox: SandboxConfig = SandboxConfig()
    audit: AuditConfig = AuditConfig()

    def model_by_id(self, model_id: str) -> ModelConfig | None:
        return next((m for m in self.models if m.id == model_id), None)

    def models_for_capability(self, capability: str) -> list[ModelConfig]:
        return [m for m in self.models if capability in m.capabilities]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _expand_env(value: Any) -> Any:
    """Recursively expand ${VAR} placeholders using environment variables."""
    if isinstance(value, str):
        import re
        def _replace(match: re.Match) -> str:
            return os.environ.get(match.group(1), match.group(0))
        return re.sub(r"\$\{([^}]+)\}", _replace, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_config(path: str | Path | None = None) -> NovaMinddConfig:
    """Load configuration from YAML file with environment-variable expansion."""
    if path is None:
        path = Path(__file__).parent.parent / "configs" / "config.yaml"
    path = Path(path)

    if not path.exists():
        return NovaMinddConfig()

    with path.open() as fh:
        raw = yaml.safe_load(fh) or {}

    expanded = _expand_env(raw)
    return NovaMinddConfig(**expanded)


@lru_cache(maxsize=1)
def get_config() -> NovaMinddConfig:
    """Return the singleton application configuration."""
    return load_config()
