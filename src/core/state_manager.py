"""Persistence for synchronization state stored in SyncControl."""

from __future__ import annotations

from src.constants import DEFAULT_STATUS, SYNC_CONTROL_TABLE
from src.connectors.base import SQLServerConnector
from src.models.sync_status import SyncStatus
from src.utils.helpers import utc_now
from src.utils.validators import validate_identifier

class StateManager:
    """Read and update directional synchronization state."""

    def __init__(self, connector: SQLServerConnector) -> None:
        self.connector = connector

    def ensure_initialized(self, table_name: str, direction: str) -> SyncStatus:
        """Ensure a SyncControl row exists for the given direction."""
        status = self.get_status(table_name, direction)
        if status is not None:
            return status
        key = self._build_key(table_name, direction)
        self.connector.execute_non_query(
            f"INSERT INTO {validate_identifier(SYNC_CONTROL_TABLE)} "
            "(TableName, LastSyncVersion, LastSyncDate, SyncStatus, RecordsSynced, LastError) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            {
                "table_name": key,
                "version": 0,
                "sync_date": utc_now(),
                "status": "INITIALIZED",
                "records_synced": 0,
                "last_error": None,
            },
        )
        return SyncStatus(table_name=table_name, last_sync_version=0, status="INITIALIZED")

    def get_status(self, table_name: str, direction: str) -> SyncStatus | None:
        """Read directional state for a table."""
        key = self._build_key(table_name, direction)
        rows = self.connector.execute_query(
            f"SELECT TableName, LastSyncVersion, LastSyncDate, RecordsSynced, SyncStatus, LastError "
            f"FROM {validate_identifier(SYNC_CONTROL_TABLE)} WHERE TableName = ?",
            {"table_name": key},
        )
        if not rows:
            return None
        row = rows[0]
        return SyncStatus(
            table_name=table_name,
            last_sync_version=int(row["LastSyncVersion"]),
            last_sync_date=row["LastSyncDate"],
            records_synced=int(row.get("RecordsSynced") or 0),
            status=row.get("SyncStatus") or DEFAULT_STATUS,
            error_message=row.get("LastError"),
        )

    def update_status(self, table_name: str, direction: str, version: int, records_synced: int, status: str = "COMPLETED") -> None:
        """Persist a successful synchronization state."""
        key = self._build_key(table_name, direction)
        self.connector.execute_non_query(
            f"UPDATE {validate_identifier(SYNC_CONTROL_TABLE)} "
            "SET LastSyncVersion = ?, LastSyncDate = ?, RecordsSynced = ?, SyncStatus = ?, LastError = ? "
            "WHERE TableName = ?",
            {
                "version": version,
                "sync_date": utc_now(),
                "records_synced": records_synced,
                "status": status,
                "last_error": None,
                "table_name": key,
            },
        )

    def mark_failure(self, table_name: str, direction: str, error_message: str) -> None:
        """Persist a failed synchronization state."""
        key = self._build_key(table_name, direction)
        self.connector.execute_non_query(
            f"UPDATE {validate_identifier(SYNC_CONTROL_TABLE)} "
            "SET LastSyncDate = ?, SyncStatus = ?, LastError = ? WHERE TableName = ?",
            {
                "sync_date": utc_now(),
                "status": "FAILED",
                "last_error": error_message,
                "table_name": key,
            },
        )

    def _build_key(self, table_name: str, direction: str) -> str:
        return f"{table_name}|{direction}"