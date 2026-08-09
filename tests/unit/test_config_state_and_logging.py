import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from src.config.config_loader import ConfigLoader
from src.core.state_manager import StateManager
from src.logging.logger_setup import (_inject_defaults, _render_schema,
                                      configure_logging)

class FakeConnector:
    def __init__(self):
        self.rows = {}
        self.executed = []

    def execute_query(self, query, params=None):
        self.executed.append((query, params))
        key = params["table_name"] if params else None
        row = self.rows.get(key)
        return [row] if row else []

    def execute_non_query(self, query, params=None):
        self.executed.append((query, params))
        if query.startswith("INSERT"):
            self.rows[params["table_name"]] = {
                "TableName": params["table_name"],
                "LastSyncVersion": params["version"],
                "LastSyncDate": params["sync_date"],
                "RecordsSynced": params["records_synced"],
                "SyncStatus": params["status"],
                "LastError": params["last_error"],
            }
        elif query.startswith("UPDATE") and params["table_name"] in self.rows:
            self.rows[params["table_name"]].update(
                {
                    "LastSyncVersion": params.get("version", self.rows[params["table_name"]]["LastSyncVersion"]),
                    "LastSyncDate": params["sync_date"],
                    "RecordsSynced": params.get("records_synced", self.rows[params["table_name"]]["RecordsSynced"]),
                    "SyncStatus": params["status"],
                    "LastError": params["last_error"],
                }
            )
        return 1

def test_config_loader_loads_project_configuration():
    project_root = Path(__file__).resolve().parents[2]
    loader = ConfigLoader(base_path=project_root)
    config = loader.load()

    assert config.synchronizer.name == "SQLSyncService"
    assert config.tables[0].name == "saDocumentoVenta"

def test_state_manager_creates_and_updates_directional_state():
    connector = FakeConnector()
    manager = StateManager(connector)

    created = manager.ensure_initialized("saDocumentoVenta", "LOCAL_TO_REMOTE")
    manager.update_status("saDocumentoVenta", "LOCAL_TO_REMOTE", 10, 3)
    status = manager.get_status("saDocumentoVenta", "LOCAL_TO_REMOTE")
    manager.mark_failure("saDocumentoVenta", "LOCAL_TO_REMOTE", "error")
    failed = manager.get_status("saDocumentoVenta", "LOCAL_TO_REMOTE")

    assert created.status == "INITIALIZED"
    assert status.last_sync_version == 10
    assert status.records_synced == 3
    assert failed.error_message == "error"

def test_logging_helpers_build_canonical_payload(tmp_path):
    settings = SimpleNamespace(level="INFO", log_directory=str(tmp_path), log_rotation_days=1)
    configure_logging(settings)
    payload = _inject_defaults(None, "info", {"event": "Mensaje de prueba"})
    rendered = _render_schema(
        None,
        "info",
        {
            **payload,
            "event": "Mensaje de prueba",
            "logger": "test",
            "module": "module",
            "function": "func",
            "line": 10,
        },
    )

    assert rendered["error_category"] == "UNKNOWN_ERROR"
    assert logging.getLogger().handlers