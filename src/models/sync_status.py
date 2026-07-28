"""Synchronization status model."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

class SyncStatus(BaseModel):
    """State snapshot for a synchronized table."""

    table_name: str
    last_sync_version: int
    last_sync_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    records_synced: int = 0
    status: str = "PENDING"
    error_message: str | None = None