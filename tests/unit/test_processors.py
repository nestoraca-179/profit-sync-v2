from src.models.sync_operation import OperationType, SyncOperation
from src.models.table_config import TableConfig
from src.processors.batch_processor import BatchProcessor

class FakeConnector:
    def __init__(self):
        self.commands = []

    def transaction(self):
        connector = self

        class _Context:
            def __enter__(self_nonlocal):
                return connector

            def __exit__(self_nonlocal, exc_type, exc, tb):
                return False

        return _Context()

    def execute(self, query, params):
        self.commands.append((query, params))

def test_process_changes_inserts_configured_primary_key():
    connector = FakeConnector()
    processor = BatchProcessor(connector, [TableConfig(name="saDocumentoVenta", primary_key="IdDocumento")])

    stats = processor.process_changes(
        {
            "saDocumentoVenta": [
                SyncOperation(
                    table_name="saDocumentoVenta",
                    record_id="1",
                    operation_type=OperationType.INSERT,
                    change_version=1,
                    data={"Descripcion": "Demo"},
                )
            ]
        }
    )

    assert stats["saDocumentoVenta"] == 1
    assert "INSERT INTO saDocumentoVenta ([IdDocumento], [Descripcion])" in connector.commands[0][0]
    assert connector.commands[0][1] == ["1", "Demo"]

def test_process_changes_uses_delete_for_delete_operations():
    connector = FakeConnector()
    processor = BatchProcessor(connector, [TableConfig(name="saDocumentoVenta", primary_key="IdDocumento")])

    processor.process_changes(
        {
            "saDocumentoVenta": [
                SyncOperation(
                    table_name="saDocumentoVenta",
                    record_id="1",
                    operation_type=OperationType.DELETE,
                    change_version=1,
                )
            ]
        }
    )

    assert "DELETE FROM saDocumentoVenta" in connector.commands[0][0]
    assert connector.commands[0][1] == ["1"]