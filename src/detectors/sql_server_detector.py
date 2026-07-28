"""SQL Server Change Tracking detector implementation."""

from __future__ import annotations

from typing import Any

from src.connectors.base import SQLServerConnector
from src.core.exceptions import ChangeDetectionError, ErrorCategory
from src.detectors.base import AbstractChangeDetector
from src.models.sync_operation import OperationType, SyncOperation
from src.models.table_config import TableConfig
from src.utils.helpers import utc_now
from src.utils.validators import validate_identifier

class SQLServerChangeDetector(AbstractChangeDetector):
    """Detect table changes using SQL Server Change Tracking."""

    def __init__(self, connector: SQLServerConnector, tables: list[TableConfig]) -> None:
        self.connector = connector
        self.table_map = {table.name: table for table in tables}

    def detect_changes(self, table_name: str, last_sync_version: int) -> list[SyncOperation]:
        if table_name not in self.table_map:
            return []
        table = self.table_map[table_name]
        safe_table = validate_identifier(table_name)
        safe_pk = validate_identifier(table.primary_key)
        query = (
            f"SELECT CT.SYS_CHANGE_OPERATION, CT.SYS_CHANGE_VERSION, "
            f"CT.{safe_pk} AS RecordId, T.* "
            f"FROM CHANGETABLE(CHANGES {safe_table}, ?) AS CT "
            f"LEFT JOIN {safe_table} AS T ON T.{safe_pk} = CT.{safe_pk}"
        )
        try:
            rows = self.connector.execute_query(query, {"last_sync_version": last_sync_version})
        except Exception as exc:
            raise ChangeDetectionError(str(exc), ErrorCategory.CHANGE_TRACKING_ERROR) from exc
        operations: list[SyncOperation] = []
        for row in rows:
            operation = OperationType(row["SYS_CHANGE_OPERATION"])
            payload = self._normalize_payload(row, safe_pk)
            operations.append(
                SyncOperation(
                    table_name=table_name,
                    record_id=str(row["RecordId"]),
                    operation_type=operation,
                    change_version=int(row["SYS_CHANGE_VERSION"]),
                    data=payload if operation != OperationType.DELETE else None,
                    timestamp=utc_now(),
                )
            )
        return operations

    def get_current_version(self, table_name: str) -> int:
        _ = validate_identifier(table_name)
        rows = self.connector.execute_query("SELECT CHANGE_TRACKING_CURRENT_VERSION() AS version")
        if not rows:
            return 0
        return int(rows[0]["version"])

    def _normalize_payload(self, row: dict[str, Any], primary_key: str) -> dict[str, Any]:
        return {
            key: value
            for key, value in row.items()
            if key not in {"SYS_CHANGE_OPERATION", "SYS_CHANGE_VERSION", "RecordId"}
            and key is not None
        }