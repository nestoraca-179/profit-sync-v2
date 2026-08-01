"""Configuration model for synchronized tables."""

from __future__ import annotations
from typing import List, Optional, Union
from pydantic import BaseModel, Field

class TableConfig(BaseModel):
    """Describes synchronization behavior for one SQL table."""

    name: str
    enabled: bool = True
    primary_key: Union[str, List[str]]  # ← Cambiar a Union
    version_column: Optional[str] = "rowversion"
    dependencies: List[str] = []
    order: int = 99
    batch_size: int = 500