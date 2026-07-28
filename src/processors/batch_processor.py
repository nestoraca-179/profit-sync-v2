"""Batch processor that applies synchronization operations."""

from __future__ import annotations

from typing import Any

from src.connectors.base import SQLServerConnector
from src.models.sync_operation import OperationType, SyncOperation
from src.models.table_config import TableConfig
from src.processors.base import AbstractProcessor
from src.utils.validators import validate_identifier

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
            with self.connector.transaction():
                for operation in operations:
                    self._apply_operation(operation)
            stats[table_name] = len(operations)
        return stats

    def rollback_failed_batch(self, batch_id: str) -> None:
        return None

    def _apply_operation(self, operation: SyncOperation) -> None:
        table_config = self.table_map[operation.table_name]
        safe_table = validate_identifier(operation.table_name)
        safe_pk = validate_identifier(table_config.primary_key)
        if operation.operation_type == OperationType.DELETE:
            self.connector.execute_non_query(
                f"DELETE FROM {safe_table} WHERE {safe_pk} = ?",
                {"record_id": operation.record_id},
            )
            return
        data = dict(operation.data or {})
        data[safe_pk] = operation.record_id
        self._upsert(safe_table, safe_pk, data)

    def _upsert(self, table_name: str, primary_key: str, data: dict[str, Any]) -> None:
        columns = [validate_identifier(column) for column in data]
        update_columns = [column for column in columns if column != primary_key]
        source_columns = ", ".join(f"? AS {column}" for column in columns)
        insert_columns = ", ".join(columns)
        insert_values = ", ".join("source." + column for column in columns)
        update_clause = ", ".join(f"target.{column} = source.{column}" for column in update_columns) or f"target.{primary_key} = source.{primary_key}"
        sql = (
            f"MERGE {table_name} AS target "
            f"USING (SELECT {source_columns}) AS source "
            f"ON target.{primary_key} = source.{primary_key} "
            f"WHEN MATCHED THEN UPDATE SET {update_clause} "
            f"WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values});"
        )
        self.connector.execute_non_query(sql, {column: data[column] for column in columns})