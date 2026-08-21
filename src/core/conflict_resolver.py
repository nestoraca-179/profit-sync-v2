"""Conflict resolution strategies for bidirectional synchronization."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models.sync_operation import OperationType
from src.models.sync_operation import SyncOperation

@dataclass(slots=True)
class ConflictResolutionResult:
    """Resolved synchronization operations and conflict details."""

    local_to_remote: list[SyncOperation] = field(default_factory=list)
    remote_to_local: list[SyncOperation] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

class ConflictResolver:
    """Resolve conflicts using timestamp priority with version fallback."""

    def __init__(self, strategy: str = "timestamp_priority") -> None:
        self.strategy = strategy

    def resolve(
        self,
        local_operations: list[SyncOperation],
        remote_operations: list[SyncOperation],
    ) -> ConflictResolutionResult:
        local_map = {(item.table_name, item.record_id): item for item in local_operations}
        remote_map = {(item.table_name, item.record_id): item for item in remote_operations}
        result = ConflictResolutionResult()
        shared_keys = set(local_map) & set(remote_map)
        for key in shared_keys:
            local_operation = local_map[key]
            remote_operation = remote_map[key]
            if (
                local_operation.operation_type == OperationType.DELETE
                and remote_operation.operation_type == OperationType.DELETE
            ):
                continue
            winner = self._choose_winner(local_operation, remote_operation)
            loser = remote_operation if winner is local_operation else local_operation
            result.conflicts.append(
                f"{key[0]}:{key[1]} -> {winner.change_version}>{loser.change_version}"
            )
            if winner is local_map[key]:
                result.local_to_remote.append(winner)
            else:
                result.remote_to_local.append(winner)
        for key, operation in local_map.items():
            if key not in shared_keys:
                result.local_to_remote.append(operation)
        for key, operation in remote_map.items():
            if key not in shared_keys:
                result.remote_to_local.append(operation)
        return result

    def _choose_winner(self, local_operation: SyncOperation, remote_operation: SyncOperation) -> SyncOperation:
        if self.strategy == "timestamp_priority":
            if local_operation.timestamp != remote_operation.timestamp:
                return (
                    local_operation
                    if local_operation.timestamp >= remote_operation.timestamp
                    else remote_operation
                )
        return (
            local_operation
            if local_operation.change_version >= remote_operation.change_version
            else remote_operation
        )