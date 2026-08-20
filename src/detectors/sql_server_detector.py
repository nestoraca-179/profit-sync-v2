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

        pk_aliases = [f"__sync_pk_{index}" for index, _ in enumerate(safe_pk_list)]
        select_parts = [
            "CT.SYS_CHANGE_OPERATION",
            "CT.SYS_CHANGE_VERSION",
        ]
        select_parts.extend(
            f"CT.[{column}] AS [{alias}]"
            for column, alias in zip(safe_pk_list, pk_aliases, strict=True)
        )
        writable_columns = self._get_writable_columns(table_name, safe_pk_list)
        if writable_columns is None:
            select_parts.append("T.*")
        else:
            select_parts.extend(
                f"T.[{column}] AS [{column}]"
                for column in writable_columns
            )
        pk_join = ' AND '.join([f"T.{pk} = CT.{pk}" for pk in safe_pk_list])

        query = (
            f"SELECT {', '.join(select_parts)} "
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

            pk_values = [row[alias] for alias in pk_aliases]
            record_id = build_record_id([str(value) for value in pk_values])

            payload = self._normalize_payload(table, row, pk_aliases, writable_columns)
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

    def _get_writable_columns(self, table_name: str, primary_keys: List[str]) -> List[str] | None:
        """Return table columns excluding SQL Server-generated version columns."""
        query = """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
          AND DATA_TYPE NOT IN ('timestamp', 'rowversion')
        ORDER BY ORDINAL_POSITION
        """
        rows = self.connector.execute_query(query, {"table_name": validate_identifier(table_name)})
        if not rows or not all("COLUMN_NAME" in row for row in rows):
            return None
        primary_key_names = {column.lower() for column in primary_keys}
        return [
            row["COLUMN_NAME"]
            for row in rows
            if row["COLUMN_NAME"].lower() not in primary_key_names
        ]

    def _normalize_payload(
        self,
        table: TableConfig,
        row: dict[str, Any],
        pk_aliases: List[str],
        writable_columns: List[str] | None,
    ) -> dict[str, Any]:
        """Build a writable payload without system, PK, or version columns."""
        primary_keys = self._get_primary_key_columns(table.name)
        excluded_columns = {
            "sys_change_operation",
            "sys_change_version",
            *(column.lower() for column in primary_keys),
            *(alias.lower() for alias in pk_aliases),
        }
        if table.version_column:
            excluded_columns.add(table.version_column.lower())
        writable_names = {column.lower() for column in writable_columns} if writable_columns is not None else None
        return {
            key: value
            for key, value in row.items()
            if key is not None
            and key.lower() not in excluded_columns
            and (writable_names is None or key.lower() in writable_names)
            and value is not None
        }