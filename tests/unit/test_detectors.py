from src.detectors.sql_server_detector import SQLServerChangeDetector
from src.models.table_config import TableConfig

class FakeConnector:
    def __init__(self, rows, metadata=None):
        self.rows = rows
        self.metadata = metadata

    def execute_query(self, query, params=None):
        if "CHANGE_TRACKING_CURRENT_VERSION" in query:
            return [{"version": 42}]
        if "INFORMATION_SCHEMA.COLUMNS" in query:
            return self.metadata if self.metadata is not None else self.rows
        return self.rows

def test_detect_changes_maps_change_tracking_rows():
    detector = SQLServerChangeDetector(
        connector=FakeConnector(
            [
                {
                    "SYS_CHANGE_OPERATION": "I",
                    "SYS_CHANGE_VERSION": 10,
                    "__sync_pk_0": 7,
                    "IdDocumento": 7,
                    "Descripcion": "Factura A",
                    "timestamp": b"\x00\x00\x00\x01",
                }
            ],
            metadata=[
                {"COLUMN_NAME": "IdDocumento"},
                {"COLUMN_NAME": "Descripcion"},
            ],
        ),
        tables=[TableConfig(name="saDocumentoVenta", primary_key="IdDocumento")],
    )

    changes = detector.detect_changes("saDocumentoVenta", 0)

    assert len(changes) == 1
    assert changes[0].record_id == "7"
    assert changes[0].pk_values == [7]
    assert changes[0].data["Descripcion"] == "Factura A"
    assert "timestamp" not in changes[0].data

def test_detector_uses_change_tracking_key_for_delete():
    detector = SQLServerChangeDetector(
        connector=FakeConnector(
            [
                {
                    "SYS_CHANGE_OPERATION": "D",
                    "SYS_CHANGE_VERSION": 11,
                    "__sync_pk_0": 42,
                    "doc_num": None,
                }
            ]
        ),
        tables=[TableConfig(name="saFacturaVenta", primary_key="doc_num")],
    )

    changes = detector.detect_changes("saFacturaVenta", 0)

    assert changes[0].record_id == "42"
    assert changes[0].pk_values == [42]
    assert changes[0].data is None

def test_detector_uses_configured_single_primary_key():
    detector = SQLServerChangeDetector(
        connector=FakeConnector([]),
        tables=[TableConfig(name="saFacturaVenta", primary_key="doc_num")],
    )

    assert detector._get_primary_key_columns("saFacturaVenta") == ["doc_num"]

def test_get_current_version_reads_change_tracking_version():
    detector = SQLServerChangeDetector(
        connector=FakeConnector([]),
        tables=[TableConfig(name="saDocumentoVenta", primary_key="IdDocumento")],
    )

    assert detector.get_current_version("saDocumentoVenta") == 42