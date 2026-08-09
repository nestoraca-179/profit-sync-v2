"""SQL Server Change Tracking detector implementation."""

from __future__ import annotations
from typing import Any, List
from src.connectors.base import SQLServerConnector
from src.core.exceptions import ChangeDetectionError, ErrorCategory
from src.detectors.base import AbstractChangeDetector
from src.models.sync_operation import OperationType, SyncOperation
from src.models.table_config import TableConfig
from src.utils.helpers import utc_now, build_record_id
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

        pk_columns = self._get_primary_key_columns(table_name)
        safe_pk_list = [validate_identifier(pk) for pk in pk_columns]

        # Build SELECT with multiple PKs
        pk_select = ', '.join([f"CT.{pk}" for pk in safe_pk_list])
        pk_join = ' AND '.join([f"T.{pk} = CT.{pk}" for pk in safe_pk_list])

        query = (
            f"SELECT CT.SYS_CHANGE_OPERATION, CT.SYS_CHANGE_VERSION, "
            f"{pk_select}, T.* "
            f"FROM CHANGETABLE(CHANGES {safe_table}, ?) AS CT "
            f"LEFT JOIN {safe_table} AS T ON {pk_join}"
        )

        try:
            rows = self.connector.execute_query(query, {"last_sync_version": last_sync_version})
        except Exception as exc:
            raise ChangeDetectionError(str(exc), ErrorCategory.CHANGE_TRACKING_ERROR) from exc

        operations: list[SyncOperation] = []
        for row in rows:
            operation = OperationType(row["SYS_CHANGE_OPERATION"])

            # Build compound record_id
            pk_values = [str(row[pk]) for pk in safe_pk_list]
            record_id = build_record_id(pk_values)

            payload = self._normalize_payload(row, safe_pk_list)
            operations.append(
                SyncOperation(
                    table_name=table_name,
                    record_id=record_id,
                    pk_values=pk_values,
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

    def _get_primary_key_columns(self, table_name: str) -> List[str]:
        """Return the primary key configured for the synchronized table."""
        table_config = self.table_map.get(table_name)
        if table_config is None:
            raise ValueError(f"Table {table_name} is not configured")
        primary_key = table_config.primary_key
        return primary_key if isinstance(primary_key, list) else [primary_key]

    def _normalize_payload(self, row: dict[str, Any], primary_keys: List[str]) -> dict[str, Any]:
        """Normaliza el payload excluyendo columnas de sistema y PKs."""
        exclude_keys = {"SYS_CHANGE_OPERATION", "SYS_CHANGE_VERSION"} | set(primary_keys)
        return {
            key: value
            for key, value in row.items()
            if key not in exclude_keys
            and key is not None
            and value is not None
        }