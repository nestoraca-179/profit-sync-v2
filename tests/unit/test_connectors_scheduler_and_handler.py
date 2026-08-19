from __future__ import annotations

from pathlib import Path

import src.connectors.base as connector_module
from src.config.config_loader import DatabaseSettings
from src.connectors.local_connector import LocalSQLConnector
from src.connectors.remote_connector import RemoteSQLConnector
from src.connectors.base import SQLServerConnector
from src.core.scheduler import SyncScheduler
from src.logging.log_handlers import CompressedTimedRotatingFileHandler
from src.main import Application

class FakeCursor:
    def __init__(self):
        self.description = [("value",)]
        self.rowcount = 1
        self.executed = []

    def execute(self, query, params):
        self.executed.append((query, params))
        if query.startswith("DELETE"):
            self.description = None
        else:
            self.description = [("value",)]
        return self

    def fetchall(self):
        return [(1,)]

class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.closed = False
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

def build_settings() -> DatabaseSettings:
    return DatabaseSettings(
        server="localhost",
        database="db",
        username="user",
        password="pwd",
    )

def test_sql_server_connector_executes_queries_and_transactions(monkeypatch):
    fake_connection = FakeConnection()
    monkeypatch.setattr(connector_module, "pyodbc", type("FakePyodbc", (), {"connect": staticmethod(lambda *a, **k: fake_connection)}))
    connector = SQLServerConnector(build_settings(), source_name="local")

    connector.connect()
    rows = connector.execute_query("SELECT 1 AS value")
    count = connector.execute_non_query("DELETE FROM Demo", {"id": 1})
    with connector.transaction():
        connector.execute_non_query("DELETE FROM Demo", {"id": 1})
    row = connector.get_row_by_primary_key("Demo", "Id", "1")
    connector.disconnect()

    assert rows == [{"value": 1}]
    assert count == 1
    assert row == {"value": 1}
    assert fake_connection.committed is True
    assert fake_connection.closed is True

def test_sql_server_connector_commits_standalone_writes(monkeypatch):
    fake_connection = FakeConnection()
    monkeypatch.setattr(connector_module, "pyodbc", type("FakePyodbc", (), {"connect": staticmethod(lambda *a, **k: fake_connection)}))
    connector = SQLServerConnector(build_settings(), source_name="local")

    connector.execute_non_query("UPDATE SyncControl SET SyncStatus = ?", {"status": "COMPLETED"})

    assert fake_connection.committed is True

def test_connector_test_connection_returns_false_on_failure(monkeypatch):
    monkeypatch.setattr(connector_module, "pyodbc", type("FakePyodbc", (), {"connect": staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))}))
    connector = SQLServerConnector(build_settings(), source_name="remote")

    assert connector.test_connection() is False

def test_local_and_remote_connectors_set_source_name():
    assert LocalSQLConnector(build_settings()).source_name == "local"
    assert RemoteSQLConnector(build_settings()).source_name == "remote"

def test_scheduler_starts_runs_cycle_and_stops(monkeypatch):
    calls = []

    class FakeBackgroundScheduler:
        def __init__(self, timezone):
            self.timezone = timezone
            self.running = False

        def add_job(self, func, trigger, minutes, id, replace_existing, max_instances):
            calls.append((trigger, minutes, id, replace_existing, max_instances))
            self.func = func

        def start(self):
            self.running = True
            calls.append("started")

        def shutdown(self, wait=False):
            self.running = False
            calls.append(("stopped", wait))

    monkeypatch.setattr("src.core.scheduler.BackgroundScheduler", FakeBackgroundScheduler)
    engine = type("Engine", (), {"run_cycle": lambda self: calls.append("cycle")})()
    config = type("Config", (), {"synchronizer": type("S", (), {"timezone": "UTC", "run_interval_minutes": 5})()})()

    scheduler = SyncScheduler(config=config, engine=engine)
    scheduler.start()
    scheduler.stop()

    assert calls[0][0] == "interval"
    assert "cycle" in calls
    assert ("stopped", False) in calls

def test_log_handler_compresses_rotated_files(tmp_path, monkeypatch):
    log_file = tmp_path / "service.log"
    rotated = tmp_path / "service.log.2026-07-20"
    rotated.write_text("hello", encoding="utf-8")
    log_file.write_text("current", encoding="utf-8")
    monkeypatch.setattr("logging.handlers.TimedRotatingFileHandler.doRollover", lambda self: None)
    handler = CompressedTimedRotatingFileHandler(str(log_file), when="midnight")

    handler.doRollover()

    assert (tmp_path / "service.log.2026-07-20.gz").exists()

def test_application_wait_forever_returns_when_stopped():
    app = Application()
    app.stop()
    app.wait_forever()