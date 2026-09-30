"""
NovaMindd — Structured Logging

All application logging is JSON-structured via structlog.
Audit events are written to a separate append-only JSONL file.
"""
from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
import structlog


def configure_logging(log_level: str = "INFO", *, json_logs: bool = True) -> None:
    """Configure structlog for the entire application."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer(serializer=orjson.dumps)
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)  # type: ignore[assignment]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Quieten noisy third-party loggers
    for name in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# Audit logger
# ---------------------------------------------------------------------------

class AuditLogger:
    """Append-only structured audit log for security-sensitive events."""

    def __init__(self, log_path: str | Path, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self._path = Path(log_path)
        if enabled:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **kwargs: Any) -> None:
        if not self._enabled:
            return
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            **kwargs,
        }
        with self._path.open("ab") as fh:
            fh.write(orjson.dumps(record) + b"\n")


_audit_logger: AuditLogger | None = None


def init_audit_logger(log_path: str | Path, *, enabled: bool = True) -> AuditLogger:
    global _audit_logger
    _audit_logger = AuditLogger(log_path, enabled=enabled)
    return _audit_logger


def get_audit_logger() -> AuditLogger:
    if _audit_logger is None:
        raise RuntimeError("Audit logger not initialised. Call init_audit_logger() first.")
    return _audit_logger
