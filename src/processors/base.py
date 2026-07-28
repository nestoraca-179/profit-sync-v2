"""Abstract synchronization processor contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.sync_operation import SyncOperation

class AbstractProcessor(ABC):
    """Abstract base class for synchronization processors."""

    @abstractmethod
    def process_changes(self, changes: dict[str, list[SyncOperation]]) -> dict[str, int]:
        """Process grouped changes and return table statistics."""

    @abstractmethod
    def rollback_failed_batch(self, batch_id: str) -> None:
        """Rollback a failed batch if supported."""