from src.detectors.sql_server_detector import SQLServerChangeDetector
from src.models.table_config import TableConfig

class FakeConnector:
    def __init__(self, rows):
        self.rows = rows

    def execute_query(self, query, params=None):
        if "CHANGE_TRACKING_CURRENT_VERSION" in query:
            return [{"version": 42}]
        return self.rows

def test_detect_changes_maps_change_tracking_rows():
    detector = SQLServerChangeDetector(
        connector=FakeConnector(
            [
                {
                    "SYS_CHANGE_OPERATION": "I",
                    "SYS_CHANGE_VERSION": 10,
                    "RecordId": 7,
                    "IdDocumento": 7,
                    "Descripcion": "Factura A",
                }
            ]
        ),
        tables=[TableConfig(name="saDocumentoVenta", primary_key="IdDocumento")],
    )

    changes = detector.detect_changes("saDocumentoVenta", 0)

    assert len(changes) == 1
    assert changes[0].record_id == "7"
    assert changes[0].data["Descripcion"] == "Factura A"

def test_get_current_version_reads_change_tracking_version():
    detector = SQLServerChangeDetector(
        connector=FakeConnector([]),
        tables=[TableConfig(name="saDocumentoVenta", primary_key="IdDocumento")],
    )

    assert detector.get_current_version("saDocumentoVenta") == 42