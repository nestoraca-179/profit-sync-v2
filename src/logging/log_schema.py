"""Canonical structured log schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

class CanonicalLogSchema(BaseModel):
    """Canonical log payload used by the service."""

    timestamp: str
    level: str
    logger: str
    module: str
    function: str
    line: int
    sync_id: str = "system"
    operation: str = "unknown"
    table_name: str | None = None
    operation_type: str | None = None
    record_count: int | None = None
    records_processed: int | None = None
    records_failed: int | None = None
    error_category: str = "UNKNOWN_ERROR"
    error_code: str | None = None
    error_detail: str | None = None
    retry_count: int | None = None
    max_retries: int | None = None
    connection_timeout_ms: int | None = None
    duration_ms: int | None = None
    affected_record_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    stack_trace: str | None = None