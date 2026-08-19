"""Domain model for captured synchronization operations."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

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
    pk_values: List[Any] = Field(default_factory=list)
    operation_type: OperationType
    change_version: int
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0