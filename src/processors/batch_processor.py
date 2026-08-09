"""Batch processor that applies synchronization operations."""

from __future__ import annotations

from src.connectors.base import SQLServerConnector
from src.models.sync_operation import OperationType, SyncOperation
from src.models.table_config import TableConfig
from src.processors.base import AbstractProcessor
from src.utils.helpers import parse_record_id

class BatchProcessor(AbstractProcessor):
    """Apply batches of changes to a target database."""

    def __init__(self, connector: SQLServerConnector, table_configs: list[TableConfig]) -> None:
        self.connector = connector
        self.table_map = {config.name: config for config in table_configs}

    def process_changes(self, changes: dict[str, list[SyncOperation]]) -> dict[str, int]:
        stats: dict[str, int] = {}
        for table_name, operations in changes.items():
            if not operations:
                stats[table_name] = 0
                continue
            with self.connector.transaction() as cursor:
                for operation in operations:
                    self._apply_operation(cursor, operation)
            stats[table_name] = len(operations)
        return stats

    def rollback_failed_batch(self, batch_id: str) -> None:
        return None

    def _apply_operation(self, cursor, change: SyncOperation) -> None:
        """Apply individual operation with support for compound PK."""

        table = self.table_map.get(change.table_name)
        if not table:
            raise ValueError(f"Table {change.table_name} not found")

        # Get primary key columns for the table
        pk_columns = table.primary_key if isinstance(table.primary_key, list) else [table.primary_key]
        pk_values = change.pk_values if change.pk_values else parse_record_id(change.record_id)

        if change.operation_type == OperationType.INSERT:
            payload = change.data or {}
            if len(pk_columns) != len(pk_values):
                raise ValueError(f"Primary key values do not match {change.table_name}")
            values_by_column = dict(zip(pk_columns, pk_values, strict=True))
            values_by_column.update(payload)
            columns = ", ".join(f"[{column}]" for column in values_by_column)
            placeholders = ", ".join("?" for _ in values_by_column)
            query = f"INSERT INTO {change.table_name} ({columns}) VALUES ({placeholders})"
            cursor.execute(query, list(values_by_column.values()))

        elif change.operation_type == OperationType.UPDATE:
            payload = change.data or {}
            if not payload:
                return
            set_clause = ", ".join(f"[{column}] = ?" for column in payload)
            where_clause = " AND ".join(f"[{column}] = ?" for column in pk_columns)
            query = f"UPDATE {change.table_name} SET {set_clause} WHERE {where_clause}"
            values = list(payload.values()) + pk_values
            cursor.execute(query, values)

        elif change.operation_type == OperationType.DELETE:
            where_clause = " AND ".join(f"[{column}] = ?" for column in pk_columns)
            query = f"DELETE FROM {change.table_name} WHERE {where_clause}"
            cursor.execute(query, pk_values)
