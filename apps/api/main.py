"""
NovaMindd — FastAPI Application

Entry point for the NovaMindd API service.
Initialises all platform components and mounts routes.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_config
from core.logging import configure_logging, init_audit_logger, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Platform startup and shutdown lifecycle."""
    cfg = get_config()
    configure_logging(cfg.app.log_level)
    init_audit_logger(cfg.audit.log_path, enabled=cfg.audit.enabled)

    logger.info(
        "novamindd_starting",
        version=cfg.app.version,
        api_prefix=cfg.api.prefix,
    )

    # Sync residency manager with backend at startup
    try:
        from apps.api.dependencies import get_residency_manager
        manager = get_residency_manager()
        await manager.sync_from_backend()
        logger.info("residency_sync_complete")
    except Exception as exc:
        logger.warning("residency_sync_skipped", error=str(exc))

    yield

    logger.info("novamindd_shutdown")


def create_app() -> FastAPI:
    cfg = get_config()

    app = FastAPI(
        title="NovaMindd",
        description="Sovereign local-first AI execution platform",
        version=cfg.app.version,
        docs_url=f"{cfg.api.prefix}/docs",
        openapi_url=f"{cfg.api.prefix}/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers
    from apps.api.routes import models, knowledge, agents, artifacts, admin, chat, documents
    api_prefix = cfg.api.prefix
    app.include_router(models.router,    prefix=api_prefix)
    app.include_router(knowledge.router, prefix=api_prefix)
    app.include_router(documents.router, prefix=api_prefix)
    app.include_router(agents.router,    prefix=api_prefix)
    app.include_router(artifacts.router, prefix=api_prefix)
    app.include_router(admin.router,     prefix=api_prefix)
    app.include_router(chat.router,      prefix=api_prefix)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "novamindd"}

    return app


app = create_app()
