"""Structured logging configuration."""

from __future__ import annotations

import logging
import logging.config
import sys
from pathlib import Path
from typing import Any

import structlog

from src.core.exceptions import ErrorCategory
from src.logging.log_handlers import CompressedTimedRotatingFileHandler
from src.logging.log_schema import CanonicalLogSchema
from src.utils.helpers import utc_now

def _inject_defaults(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.setdefault("timestamp", utc_now().isoformat())
    event_dict.setdefault("sync_id", "system")
    event_dict.setdefault("operation", "unknown")
    event_dict.setdefault("error_category", ErrorCategory.UNKNOWN_ERROR.value)
    event_dict.setdefault("metadata", {})
    return event_dict

def _render_schema(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    level = event_dict.pop("level", event_dict.get("log_level", "INFO"))
    event = event_dict.pop("event", "")
    payload = {
        "timestamp": event_dict.get("timestamp", utc_now().isoformat()),
        "level": str(level).upper(),
        "logger": event_dict.get("logger", event_dict.get("module", "synchronizer")),
        "module": event_dict.get("module", "unknown"),
        "function": event_dict.get("function", "unknown"),
        "line": int(event_dict.get("line", 0)),
        "sync_id": event_dict.get("sync_id", "system"),
        "operation": event_dict.get("operation", "unknown"),
        "table_name": event_dict.get("table_name"),
        "operation_type": event_dict.get("operation_type"),
        "record_count": event_dict.get("record_count"),
        "records_processed": event_dict.get("records_processed"),
        "records_failed": event_dict.get("records_failed"),
        "error_category": event_dict.get("error_category", ErrorCategory.UNKNOWN_ERROR.value),
        "error_code": event_dict.get("error_code"),
        "error_detail": event or event_dict.get("error_detail"),
        "retry_count": event_dict.get("retry_count"),
        "max_retries": event_dict.get("max_retries"),
        "connection_timeout_ms": event_dict.get("connection_timeout_ms"),
        "duration_ms": event_dict.get("duration_ms"),
        "affected_record_ids": event_dict.get("affected_record_ids", []),
        "metadata": event_dict.get("metadata", {}),
        "stack_trace": event_dict.get("stack_trace"),
    }
    return CanonicalLogSchema.model_validate(payload).model_dump()

def configure_logging(settings: Any) -> None:
    """Configure application-wide JSON logging."""
    log_dir = Path(settings.log_directory)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = CompressedTimedRotatingFileHandler(
        filename=str(log_dir / "synchronizer.log"),
        when="midnight",
        backupCount=settings.log_rotation_days,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, settings.level.upper(), logging.INFO))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.MODULE,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                }
            ),
            _inject_defaults,
            _render_schema,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structured logger."""
    return structlog.get_logger(name)