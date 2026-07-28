"""Abstract change detector contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.sync_operation import SyncOperation

class AbstractChangeDetector(ABC):
    """Abstract base class for change detectors."""

    @abstractmethod
    def detect_changes(self, table_name: str, last_sync_version: int) -> list[SyncOperation]:
        """Detect changes in one table since the provided version."""

    @abstractmethod
    def get_current_version(self, table_name: str) -> int:
        """Return the current change tracking version for a table."""