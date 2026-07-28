from __future__ import annotations

from types import SimpleNamespace

import pytest
from src.config.config_loader import AppConfig
from src.core.engine import (DIRECTION_LOCAL_TO_REMOTE, DIRECTION_REMOTE_TO_LOCAL, SynchronizationEngine)
from src.core.exceptions import (CircuitBreakerOpenError, ErrorCategory, ProcessingError)
from src.main import Application
from src.models.sync_operation import OperationType, SyncOperation

class FakeMetric:
    def __init__(self, *args, **kwargs):
        self.value = 0

    def labels(self, **kwargs):
        return self

    def inc(self, amount=1):
        self.value += amount

    def observe(self, amount):
        self.value = amount

    def set(self, amount):
        self.value = amount

class FakeConnector:
    def __init__(self, pending_rows=None):
        self.pending_rows = pending_rows or []
        self.executed = []
        self.connected = False
        self.test_ok = True

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def test_connection(self):
        return self.test_ok

    def execute_query(self, query, params=None):
        self.executed.append((query, params))
        if "PendingOperations" in query:
            return self.pending_rows
        if "CHANGE_TRACKING_CURRENT_VERSION" in query:
            return [{"version": 12}]
        return []

    def execute_non_query(self, query, params=None):
        self.executed.append((query, params))
        return 1

class FakeStateManager:
    def __init__(self):
        self.failures = []
        self.updates = []

    def ensure_initialized(self, table_name, direction):
        return SimpleNamespace(status="INITIALIZED")

    def get_status(self, table_name, direction):
        return SimpleNamespace(last_sync_version=0)

    def update_status(self, table_name, direction, version, records_synced, status="COMPLETED"):
        self.updates.append((table_name, direction, version, records_synced, status))

    def mark_failure(self, table_name, direction, error_message):
        self.failures.append((table_name, direction, error_message))

class FakeProcessor:
    def __init__(self):
        self.calls = []
        self.raise_error = False

    def process_changes(self, changes):
        self.calls.append(changes)
        if self.raise_error:
            raise RuntimeError("write failed")
        table_name = next(iter(changes))
        return {table_name: len(changes[table_name])}

class FakeDetector:
    def __init__(self, changes=None):
        self.changes = changes or []

    def detect_changes(self, table_name, last_sync_version):
        return self.changes

    def get_current_version(self, table_name):
        return 99

def build_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "synchronizer": {
                "name": "SQLSyncService",
                "version": "1.0.0",
                "run_interval_minutes": 5,
                "timezone": "UTC",
                "local_database": {
                    "server": "local",
                    "database": "db",
                    "username": "user",
                    "password": "pwd",
                },
                "remote_database": {
                    "server": "remote",
                    "database": "db",
                    "username": "user",
                    "password": "pwd",
                },
                "synchronization": {
                    "enable_health_check": False,
                    "enable_metrics": True,
                    "logging": {
                        "log_directory": "logs"
                    },
                },
            },
            "tables": [
                {
                    "name": "saDocumentoVenta",
                    "primary_key": "IdDocumento",
                }
            ],
        }
    )

def build_engine(monkeypatch, pending_rows=None):
    monkeypatch.setattr("src.core.engine.Counter", FakeMetric)
    monkeypatch.setattr("src.core.engine.Gauge", FakeMetric)
    monkeypatch.setattr("src.core.engine.Histogram", FakeMetric)
    config = build_config()
    local = FakeConnector(pending_rows=pending_rows)
    remote = FakeConnector(pending_rows=pending_rows)
    engine = SynchronizationEngine(config, local, remote)
    engine.local_state = FakeStateManager()
    engine.remote_state = FakeStateManager()
    engine.local_detector = FakeDetector()
    engine.remote_detector = FakeDetector()
    engine.local_processor = FakeProcessor()
    engine.remote_processor = FakeProcessor()
    return engine, local, remote

def test_engine_loads_and_marks_pending_operations(monkeypatch):
    engine, local, _ = build_engine(
        monkeypatch,
        pending_rows=[
            {
                "TableName": "saDocumentoVenta",
                "RecordId": "1",
                "OperationType": "I",
                "RecordData": '{"Descripcion": "Demo"}',
                "ChangeVersion": 5,
                "RetryCount": 0,
            }
        ],
    )

    pending = engine._load_pending_operations(local)
    engine._replay_pending(local, engine.remote_processor, pending)

    assert pending["saDocumentoVenta"][0].operation_type == OperationType.INSERT
    assert any("UPDATE PendingOperations SET Status = ?" in command for command, _ in local.executed)

def test_engine_queues_pending_operations_on_failure(monkeypatch):
    engine, local, _ = build_engine(monkeypatch)
    engine.remote_processor.raise_error = True
    operation = SyncOperation(
        table_name="saDocumentoVenta",
        record_id="1",
        operation_type=OperationType.INSERT,
        change_version=2,
        data={"Descripcion": "Demo"},
    )

    with pytest.raises(ProcessingError):
        engine._process_direction(
            engine.tables[0],
            DIRECTION_LOCAL_TO_REMOTE,
            [operation],
            engine.remote_processor,
        )

    assert engine.local_state.failures
    assert any("INSERT INTO PendingOperations" in command for command, _ in local.executed)

def test_engine_validates_preconditions(monkeypatch):
    engine, _, remote = build_engine(monkeypatch)
    engine.circuit_breaker.state = engine.circuit_breaker.state.OPEN

    with pytest.raises(CircuitBreakerOpenError):
        engine._validate_preconditions()

    engine.circuit_breaker.record_success()
    monkeypatch.setattr(engine, "_has_internet_access", lambda: False)
    with pytest.raises(ProcessingError) as error:
        engine._validate_preconditions()
    assert error.value.category == ErrorCategory.NETWORK_CONNECTION_FAILED

    monkeypatch.setattr(engine, "_has_internet_access", lambda: True)
    remote.test_ok = False
    with pytest.raises(ProcessingError) as remote_error:
        engine._validate_preconditions()
    assert remote_error.value.category == ErrorCategory.REMOTE_SERVER_DOWN

def test_engine_syncs_changes_and_updates_state(monkeypatch):
    engine, _, _ = build_engine(monkeypatch)
    operation = SyncOperation(
        table_name="saDocumentoVenta",
        record_id="1",
        operation_type=OperationType.INSERT,
        change_version=1,
        data={"Descripcion": "Demo"},
    )
    engine.local_detector = FakeDetector([operation])
    engine.remote_detector = FakeDetector([])

    engine._sync_table(engine.tables[0], SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None))

    assert engine.remote_processor.calls
    assert engine.local_state.updates

def test_engine_run_cycle_success(monkeypatch):
    engine, _, _ = build_engine(monkeypatch)
    monkeypatch.setattr(engine, "_validate_preconditions", lambda: None)
    monkeypatch.setattr(engine, "_process_pending_operations", lambda: None)
    monkeypatch.setattr(engine, "_sync_table", lambda table, bound_logger: None)

    engine.run_cycle()

    snapshot = engine.health_snapshot()
    assert snapshot["last_cycle_status"] == "COMPLETED"

def test_application_start_and_stop(monkeypatch):
    scheduler_calls = []

    class FakeScheduler:
        def __init__(self, config, engine):
            self.config = config
            self.engine = engine

        def start(self):
            scheduler_calls.append("start")

        def stop(self):
            scheduler_calls.append("stop")

    class FakeEngine:
        def shutdown(self):
            scheduler_calls.append("shutdown")

        @classmethod
        def from_config(cls, config):
            scheduler_calls.append("engine")
            return cls()

    monkeypatch.setattr("src.main.ConfigLoader", lambda: SimpleNamespace(load=build_config))
    monkeypatch.setattr("src.main.configure_logging", lambda settings: scheduler_calls.append("logging"))
    monkeypatch.setattr("src.main.SyncScheduler", FakeScheduler)
    monkeypatch.setattr("src.main.SynchronizationEngine", FakeEngine)

    app = Application()
    app.start()
    app.stop()

    assert scheduler_calls == ["logging", "engine", "start", "stop", "shutdown"]