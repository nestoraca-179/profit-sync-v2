"""Domain model for captured synchronization operations."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class OperationType(str, Enum):
    """Supported database operation types."""

    INSERT = "I"
    UPDATE = "U"
    DELETE = "D"

class SyncOperation(BaseModel):
    """Represents a single change tracked operation."""

    table_name: str
    record_id: str
    operation_type: OperationType
    change_version: int
    data: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0