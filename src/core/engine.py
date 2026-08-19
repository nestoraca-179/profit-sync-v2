"""Main synchronization engine orchestration."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from src.config.config_loader import AppConfig
from src.constants import PENDING_OPERATIONS_TABLE
from src.connectors.local_connector import LocalSQLConnector
from src.connectors.remote_connector import RemoteSQLConnector
from src.core.conflict_resolver import ConflictResolver
from src.core.exceptions import CircuitBreakerOpenError, ErrorCategory, ProcessingError, SynchronizerError
from src.core.state_manager import StateManager
from src.detectors.sql_server_detector import SQLServerChangeDetector
from src.logging.logger_setup import get_logger
from src.models.sync_operation import OperationType, SyncOperation
from src.models.table_config import TableConfig
from src.processors.batch_processor import BatchProcessor
from src.utils.circuit_breaker import CircuitBreaker
from src.utils.helpers import chunked, generate_sync_id, parse_record_id
from src.utils.retry_decorator import build_retry_decorator
from src.utils.validators import validate_identifier

logger = get_logger(__name__)

DIRECTION_LOCAL_TO_REMOTE = "LOCAL_TO_REMOTE"
DIRECTION_REMOTE_TO_LOCAL = "REMOTE_TO_LOCAL"

class _HealthRequestHandler(BaseHTTPRequestHandler):
    """Internal HTTP handler for health and metrics."""

    engine: "SynchronizationEngine"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            payload = json.dumps(self.engine.health_snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/metrics":
            metrics = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(metrics)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return None

class SynchronizationEngine:
    """Coordinate detection, conflict resolution, and replication."""

    def __init__(
        self,
        config: AppConfig,
        local_connector: LocalSQLConnector,
        remote_connector: RemoteSQLConnector,
    ) -> None:
        self.config = config
        self.local_connector = local_connector
        self.remote_connector = remote_connector
        self.tables = sorted(
            [table for table in config.tables if table.enabled],
            key=lambda item: (item.order, item.name),
        )
        self.local_detector = SQLServerChangeDetector(local_connector, self.tables)
        self.remote_detector = SQLServerChangeDetector(remote_connector, self.tables)
        self.remote_processor = BatchProcessor(remote_connector, self.tables)
        self.local_processor = BatchProcessor(local_connector, self.tables)
        self.local_state = StateManager(local_connector)
        self.remote_state = StateManager(remote_connector)
        breaker = config.synchronizer.synchronization.circuit_breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=breaker.failure_threshold,
            timeout_seconds=breaker.timeout_seconds,
            half_open_timeout_seconds=breaker.half_open_timeout_seconds,
        )
        self.conflict_resolver = ConflictResolver(config.synchronizer.synchronization.conflict_resolution)
        self.sync_counter = Counter(
            "synchronizer_operations_total",
            "Number of synchronized records",
            labelnames=("table_name", "direction"),
        )
        self.failure_counter = Counter(
            "synchronizer_failures_total",
            "Number of synchronization failures",
            labelnames=("category",),
        )
        self.duration_histogram = Histogram(
            "synchronizer_cycle_duration_seconds",
            "Synchronization cycle duration",
        )
        self.breaker_gauge = Gauge(
            "synchronizer_circuit_breaker_state",
            "Circuit breaker state: 0 closed, 1 open, 2 half-open",
        )
        self._health_server: ThreadingHTTPServer | None = None
        self._health_thread: threading.Thread | None = None
        self._last_sync_id = "system"
        self._last_cycle_status = "PENDING"
        self._last_cycle_error: str | None = None
        self._configure_dependencies()

    @classmethod
    def from_config(cls, config: AppConfig) -> "SynchronizationEngine":
        """Build and initialize the engine from application config."""
        local_connector = LocalSQLConnector(config.synchronizer.local_database)
        remote_connector = RemoteSQLConnector(config.synchronizer.remote_database)
        engine = cls(config=config, local_connector=local_connector, remote_connector=remote_connector)
        engine.startup()
        return engine

    def startup(self) -> None:
        """Connect to dependencies and start health services."""
        self.local_connector.connect()
        self.remote_connector.connect()
        if self.config.synchronizer.synchronization.enable_health_check:
            self._start_health_server()

    def shutdown(self) -> None:
        """Stop health services and close connectors."""
        if self._health_server is not None:
            self._health_server.shutdown()
            self._health_server.server_close()
            self._health_server = None
        self.local_connector.disconnect()
        self.remote_connector.disconnect()

    def run_cycle(self) -> None:
        """Execute one full synchronization cycle."""
        sync_id = generate_sync_id()
        self._last_sync_id = sync_id
        cycle_start = time.perf_counter()
        bound_logger = logger.bind(sync_id=sync_id, logger="synchronizer.engine")
        try:
            self._validate_preconditions()
            self._process_pending_operations()
            for table in self.tables:
                self._sync_table(table, bound_logger)
            self.circuit_breaker.record_success()
            self._last_cycle_status = "COMPLETED"
            self._last_cycle_error = None
            bound_logger.info(
                "Operación completada exitosamente",
                operation="sync_cycle",
                error_category=ErrorCategory.UNKNOWN_ERROR.value,
            )
        except SynchronizerError as exc:
            self.circuit_breaker.record_failure(str(exc))
            self.failure_counter.labels(category=exc.category.value).inc()
            self._last_cycle_status = "FAILED"
            self._last_cycle_error = str(exc)
            bound_logger.exception(
                "Error durante el ciclo de sincronizacion",
                operation="sync_cycle",
                error_category=exc.category.value,
            )
            raise
        except Exception as exc:
            self.circuit_breaker.record_failure(str(exc))
            self.failure_counter.labels(category=ErrorCategory.UNKNOWN_ERROR.value).inc()
            self._last_cycle_status = "FAILED"
            self._last_cycle_error = str(exc)
            bound_logger.exception(
                "Error inesperado durante el ciclo de sincronizacion",
                operation="sync_cycle",
                error_category=ErrorCategory.UNKNOWN_ERROR.value,
            )
            raise ProcessingError(str(exc), ErrorCategory.UNKNOWN_ERROR) from exc
        finally:
            duration = time.perf_counter() - cycle_start
            self.duration_histogram.observe(duration)
            self.breaker_gauge.set(self._breaker_value())

    def health_snapshot(self) -> dict[str, Any]:
        """Return a serializable health snapshot."""
        return {
            "service": self.config.synchronizer.name,
            "version": self.config.synchronizer.version,
            "last_sync_id": self._last_sync_id,
            "last_cycle_status": self._last_cycle_status,
            "last_cycle_error": self._last_cycle_error,
            "local_connection": self.local_connector.test_connection(),
            "remote_connection": self.remote_connector.test_connection(),
            "circuit_breaker": self.circuit_breaker.snapshot,
        }

    def _configure_dependencies(self) -> None:
        retry_config = self.config.synchronizer.synchronization
        self._execute_with_retry = build_retry_decorator(
            retry_config.max_retries,
            retry_config.retry_delay_seconds,
            retry_config.retry_backoff_multiplier,
        )(self._execute_sync)

    def _validate_preconditions(self) -> None:
        if not self.circuit_breaker.allow_request():
            raise CircuitBreakerOpenError(
                "Circuit breaker abierto",
                ErrorCategory.OPERATION_TIMEOUT,
            )
        if not self._has_internet_access():
            raise ProcessingError(
                "No hay conectividad de red",
                ErrorCategory.NETWORK_CONNECTION_FAILED,
            )
        if not self.local_connector.test_connection():
            raise ProcessingError(
                "Error al conectar con servidor local",
                ErrorCategory.LOCAL_SERVER_DOWN,
            )
        if not self.remote_connector.test_connection():
            raise ProcessingError(
                "Error al conectar con servidor remoto",
                ErrorCategory.REMOTE_SERVER_DOWN,
            )

    def _sync_table(self, table: TableConfig, bound_logger: Any) -> None:
        self.local_state.ensure_initialized(table.name, DIRECTION_LOCAL_TO_REMOTE)
        self.remote_state.ensure_initialized(table.name, DIRECTION_REMOTE_TO_LOCAL)
        local_status = self.local_state.get_status(table.name, DIRECTION_LOCAL_TO_REMOTE)
        remote_status = self.remote_state.get_status(table.name, DIRECTION_REMOTE_TO_LOCAL)
        local_changes = self.local_detector.detect_changes(table.name, local_status.last_sync_version if local_status else 0)
        remote_changes = self.remote_detector.detect_changes(table.name, remote_status.last_sync_version if remote_status else 0)
        if not local_changes and not remote_changes:
            bound_logger.info(
                "No hay operaciones pendientes por sincronizar",
                operation="sync_table",
                table_name=table.name,
                error_category=ErrorCategory.UNKNOWN_ERROR.value,
            )
            return
        resolution = self.conflict_resolver.resolve(local_changes, remote_changes)
        if resolution.conflicts:
            bound_logger.warning(
                "Conflicto de datos detectado",
                operation="sync_table",
                table_name=table.name,
                record_count=len(resolution.conflicts),
                error_category=ErrorCategory.DATA_CONFLICT.value,
                metadata={"conflicts": resolution.conflicts},
            )
        self._execute_with_retry(table, resolution.local_to_remote, resolution.remote_to_local)
        self.local_state.update_status(
            table.name,
            DIRECTION_LOCAL_TO_REMOTE,
            self.local_detector.get_current_version(table.name),
            len(resolution.local_to_remote),
        )
        self.remote_state.update_status(
            table.name,
            DIRECTION_REMOTE_TO_LOCAL,
            self.remote_detector.get_current_version(table.name),
            len(resolution.remote_to_local),
        )
        bound_logger.info(
            "Operación completada exitosamente",
            operation="sync_table",
            table_name=table.name,
            records_processed=len(resolution.local_to_remote) + len(resolution.remote_to_local),
            records_failed=0,
            error_category=ErrorCategory.UNKNOWN_ERROR.value,
        )

    def _execute_sync(
        self,
        table: TableConfig,
        local_to_remote: list[SyncOperation],
        remote_to_local: list[SyncOperation],
    ) -> None:
        if local_to_remote:
            self._process_direction(table, DIRECTION_LOCAL_TO_REMOTE, local_to_remote, self.remote_processor)
        if remote_to_local:
            self._process_direction(table, DIRECTION_REMOTE_TO_LOCAL, remote_to_local, self.local_processor)

    def _process_direction(
        self,
        table: TableConfig,
        direction: str,
        operations: list[SyncOperation],
        processor: BatchProcessor,
    ) -> None:
        grouped_stats: dict[str, int] = defaultdict(int)
        try:
            for batch in chunked(operations, table.batch_size):
                stats = processor.process_changes({table.name: batch})
                grouped_stats[table.name] += stats.get(table.name, 0)
            self.sync_counter.labels(table_name=table.name, direction=direction).inc(grouped_stats[table.name])
        except Exception as exc:
            state_manager = self.local_state if direction == DIRECTION_LOCAL_TO_REMOTE else self.remote_state
            source_connector = self.local_connector if direction == DIRECTION_LOCAL_TO_REMOTE else self.remote_connector
            state_manager.mark_failure(table.name, direction, str(exc))
            self._queue_pending_operations(source_connector, operations, str(exc))
            raise ProcessingError(str(exc), ErrorCategory.WRITE_OPERATION_FAILED) from exc

    def _process_pending_operations(self) -> None:
        pending_local = self._load_pending_operations(self.local_connector)
        pending_remote = self._load_pending_operations(self.remote_connector)
        if pending_local:
            self._replay_pending(self.local_connector, self.remote_processor, pending_local)
        if pending_remote:
            self._replay_pending(self.remote_connector, self.local_processor, pending_remote)

    def _start_health_server(self) -> None:
        if self._health_server is not None:
            return
        handler = type("HealthHandler", (_HealthRequestHandler,), {})
        handler.engine = self
        port = int(os.getenv("PROMETHEUS_PORT", "8000"))
        self._health_server = ThreadingHTTPServer(("0.0.0.0", port), handler)
        self._health_thread = threading.Thread(
            target=self._health_server.serve_forever,
            name="health-server",
            daemon=True,
        )
        self._health_thread.start()

    def _has_internet_access(self) -> bool:
        try:
            with socket.create_connection(("8.8.8.8", 53), timeout=3):
                return True
        except OSError:
            return False

    def _breaker_value(self) -> int:
        state = self.circuit_breaker.state.value
        if state == "OPEN":
            return 1
        if state == "HALF_OPEN":
            return 2
        return 0

    def _load_pending_operations(self, connector: Any) -> dict[str, list[SyncOperation]]:
        query = (
            f"SELECT Id, TableName, RecordId, OperationType, RecordData, ChangeVersion, RetryCount "
            f"FROM {validate_identifier(PENDING_OPERATIONS_TABLE)} WHERE Status = ? ORDER BY CreatedDate"
        )
        rows = connector.execute_query(query, {"status": "PENDING"})
        grouped: dict[str, list[SyncOperation]] = defaultdict(list)
        for row in rows:
            stored_data = json.loads(row["RecordData"]) if row.get("RecordData") else {}
            if "data" in stored_data and "pk_values" in stored_data:
                payload = stored_data["data"]
                pk_values = stored_data["pk_values"]
            else:
                payload = stored_data or None
                pk_values = parse_record_id(str(row["RecordId"]))

            grouped[row["TableName"]].append(
                SyncOperation(
                    table_name=row["TableName"],
                    record_id=str(row["RecordId"]),
                    pk_values=pk_values,
                    operation_type=OperationType(row["OperationType"]),
                    change_version=int(row["ChangeVersion"]),
                    data=payload,
                    retry_count=int(row.get("RetryCount") or 0),
                )
            )

        return grouped

    def _replay_pending(
        self,
        source_connector: Any,
        processor: BatchProcessor,
        grouped_operations: dict[str, list[SyncOperation]],
    ) -> None:
        for table_name, operations in grouped_operations.items():
            for batch in chunked(operations, self._table_config(table_name).batch_size):
                processor.process_changes({table_name: batch})
                self._mark_pending_completed(source_connector, table_name, batch)

    def _queue_pending_operations(
        self,
        connector: Any,
        operations: list[SyncOperation],
        error_message: str,
    ) -> None:
        safe_table = validate_identifier(PENDING_OPERATIONS_TABLE)
        for operation in operations:
            connector.execute_non_query(
                f"INSERT INTO {safe_table} "
                "(TableName, RecordId, OperationType, RecordData, ChangeVersion, RetryCount, LastError, Status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                {
                    "table_name": operation.table_name,
                    "record_id": operation.record_id,
                    "operation_type": operation.operation_type.value,
                    "record_data": json.dumps(
                        {"data": operation.data, "pk_values": operation.pk_values},
                        default=self._json_default,
                    ),
                    "change_version": operation.change_version,
                    "retry_count": operation.retry_count + 1,
                    "last_error": error_message,
                    "status": "PENDING",
                },
            )

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    def _mark_pending_completed(
        self,
        connector: Any,
        table_name: str,
        operations: list[SyncOperation],
    ) -> None:
        safe_table = validate_identifier(PENDING_OPERATIONS_TABLE)
        for operation in operations:
            connector.execute_non_query(
                f"UPDATE {safe_table} SET Status = ?, LastError = ? WHERE TableName = ? AND RecordId = ? AND ChangeVersion = ?",
                {
                    "status": "COMPLETED",
                    "last_error": None,
                    "table_name": table_name,
                    "record_id": operation.record_id,
                    "change_version": operation.change_version,
                },
            )

    def _table_config(self, table_name: str) -> TableConfig:
        for table in self.tables:
            if table.name == table_name:
                return table

        raise ProcessingError(
            f"Tabla no configurada: {table_name}",
            ErrorCategory.UNKNOWN_ERROR,
        )