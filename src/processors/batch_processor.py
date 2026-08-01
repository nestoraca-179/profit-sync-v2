"""Batch processor that applies synchronization operations."""

from __future__ import annotations

from typing import Any

from src.connectors.base import SQLServerConnector
from src.models.sync_operation import OperationType, SyncOperation
from src.models.table_config import TableConfig
from src.processors.base import AbstractProcessor
from src.utils.helpers import parse_record_id
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

    def _apply_operation(self, cursor, change: SyncOperation):
        """Apply individual operation with support for compound PK."""

        table = self.table_map.get(change.table_name)
        if not table:
            raise ValueError(f"Table {change.table_name} not found")

        # Get primary key columns for the table
        pk_columns = table.primary_key if isinstance(table.primary_key, list) else [table.primary_key]
        pk_values = change.pk_values if change.pk_values else parse_record_id(change.record_id)

        if change.operation_type == OperationType.INSERT:
            columns = ', '.join([f"[{k}]" for k in change.data.keys()])
            placeholders = ', '.join(['?' for _ in change.data])
            query = f"INSERT INTO {change.table_name} ({columns}) VALUES ({placeholders})"
            cursor.execute(query, list(change.data.values()))

        elif change.operation_type == OperationType.UPDATE:
            set_clause = ', '.join([f"[{k}] = ?" for k in change.data.keys()])
            where_clause = ' AND '.join([f"[{pk}] = ?" for pk in pk_columns])
            query = f"UPDATE {change.table_name} SET {set_clause} WHERE {where_clause}"
            values = list(change.data.values()) + pk_values
            cursor.execute(query, values)

        elif change.operation_type == OperationType.DELETE:
            where_clause = ' AND '.join([f"[{pk}] = ?" for pk in pk_columns])
            query = f"DELETE FROM {change.table_name} WHERE {where_clause}"
            cursor.execute(query, pk_values)

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