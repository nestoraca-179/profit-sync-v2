"""Configuration model for synchronized tables."""

from __future__ import annotations

from pydantic import BaseModel, Field

class TableConfig(BaseModel):
    """Describes synchronization behavior for one SQL table."""

    name: str
    enabled: bool = True
    primary_key: str
    version_column: str | None = "rowversion"
    dependencies: list[str] = Field(default_factory=list)
    batch_size: int = 500
    order: int = 99